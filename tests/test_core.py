import csv
import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from datetime import date
from unittest.mock import patch

from openpyxl import Workbook, load_workbook

from meta_ads_tool.accounts.datameta import (
    build_datameta_body,
    parse_accounts_from_datameta_payload,
    parse_datameta_response,
    read_accounts_from_api,
)
from meta_ads_tool.accounts.excel import read_accounts_from_excel
from meta_ads_tool.cli import (
    home_report_directory,
    project_root,
    resolve_output,
)
from meta_ads_tool.cli import (
    main as cli_main,
)
from meta_ads_tool.constants import CSV_DELIMITER, CSV_REPORT_COLUMNS, ERROR_COLUMNS, INPUT_HEADERS
from meta_ads_tool.dates import preset_date_range, resolve_date_range
from meta_ads_tool.graph.client import MetaAdsClient, MetaApiError
from meta_ads_tool.processing.flatten import normalize_ad_name, parse_hour_bucket, time_category
from meta_ads_tool.processing.metrics import choose_daily_result_detail, daily_frequency_value
from meta_ads_tool.processing.runner import process_rinci_account, run_accounts
from meta_ads_tool.reporting import (
    export_csv,
    export_xlsx,
    resolve_csv_delimiter,
    sanitize_spreadsheet_text,
)
from meta_ads_tool.storage.checkpoint import CheckpointMismatchError, CheckpointStore
from meta_ads_tool.summary import format_elapsed_seconds


class FakeResponse:
    def __init__(self, status_code, payload, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.ok = 200 <= status_code < 300
        self.headers = {}

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0
        self.requests = []
        self.headers = {}

    def get(self, *args, **kwargs):
        self.requests.append((args, kwargs))
        response = self.responses[self.calls]
        self.calls += 1
        return response

    def post(self, *args, **kwargs):
        self.requests.append((args, kwargs))
        response = self.responses[self.calls]
        self.calls += 1
        return response


class DateTests(unittest.TestCase):
    def test_presets(self):
        current = date(2026, 8, 5)
        self.assertEqual(
            preset_date_range("7-hari-terakhir", today=current),
            (date(2026, 7, 30), date(2026, 8, 5)),
        )
        self.assertEqual(
            preset_date_range("bulan-lalu", today=current),
            (date(2026, 7, 1), date(2026, 7, 31)),
        )

    def test_resolve_manual(self):
        since, until, source = resolve_date_range(
            "2026-08-01", "2026-08-05", None
        )
        self.assertEqual(
            (since, until, source),
            ("2026-08-01", "2026-08-05", "manual"),
        )


class TransformTests(unittest.TestCase):
    def test_hour_bucket_and_category(self):
        text, hour = parse_hour_bucket("7:00:00 - 7:59:59")
        self.assertEqual(text, "07:00 - 07:59")
        self.assertEqual(hour, 7)
        self.assertEqual(time_category(hour), "Pagi")
        self.assertEqual(time_category(0), "Dini hari")
        self.assertEqual(time_category(12), "Siang")
        self.assertEqual(time_category(16), "Sore")
        self.assertEqual(time_category(22), "Malam")

    def test_formula_injection(self):
        self.assertEqual(sanitize_spreadsheet_text("=1+1"), "'=1+1")
        self.assertEqual(
            sanitize_spreadsheet_text("  @SUM(A1)"),
            "'  @SUM(A1)",
        )
        self.assertEqual(sanitize_spreadsheet_text("Nama normal"), "Nama normal")

    def test_normalize_ad_name(self):
        self.assertEqual(
            normalize_ad_name('Postingan: "Lagi butuh dana cepat tapi nggak mau"'),
            "Lagi butuh dana cepat tapi nggak mau",
        )
        self.assertEqual(
            normalize_ad_name("postingan: “Teks dengan petik tipografis”"),
            "Teks dengan petik tipografis",
        )
        self.assertEqual(normalize_ad_name("Nama iklan biasa"), "Nama iklan biasa")
        self.assertEqual(normalize_ad_name(None), "")


class InputExcelTests(unittest.TestCase):
    def test_reads_exact_four_columns_and_token(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "accounts.xlsx")
            workbook = Workbook()
            sheet = workbook.active
            sheet.append(list(INPUT_HEADERS))
            sheet.append(["123456789", "EAA-secret-token", "JKT01", "GADAI"])
            workbook.save(path)
            workbook.close()

            accounts = read_accounts_from_excel(path)
            self.assertEqual(accounts, [{
                "account_id": "123456789",
                "access_token": "EAA-secret-token",
                "cabang": "JKT01",
                "bisnis": "GADAI",
            }])

    def test_rejects_wrong_header_order(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "accounts.xlsx")
            workbook = Workbook()
            sheet = workbook.active
            sheet.append(["TOKEN", "ID ACCOUNT", "CABANG", "BISNIS"])
            sheet.append(["token", "123", "CAB", "GADAI"])
            workbook.save(path)
            workbook.close()

            with self.assertRaises(RuntimeError):
                read_accounts_from_excel(path)


class InputApiTests(unittest.TestCase):
    def test_build_datameta_body_uses_report_dates(self):
        body = build_datameta_body(
            no_hp="081234",
            since="2026-02-01",
            until="2026-02-28",
        )
        item = body["api_jsoncmonss"][0]
        self.assertEqual(item["Request"], "DATAMETA")
        self.assertEqual(item["tanggalAwal"], "2026-02-01")
        self.assertEqual(item["tanggalAkhir"], "2026-02-28")
        self.assertEqual(item["latMulai"], "0.00")
        self.assertEqual(item["lonMulai"], "0.00")
        self.assertEqual(item["jamMulai"], "-10:00:00")

    def test_parse_all_accounts_supports_id_acoount_spelling(self):
        accounts = parse_accounts_from_datameta_payload({
            "status": "ok",
            "Detail": [
                {
                    "idAcoount": "1001712982604688",
                    "token": "secret-a",
                    "cabang": "34THJO81",
                    "bisnis": "MGA",
                },
                {
                    "idAcoount": "1004504647673778",
                    "token": "secret-b",
                    "cabang": "33KDGP81",
                    "bisnis": "MGA",
                },
            ],
        })
        self.assertEqual(len(accounts), 2)
        self.assertEqual(accounts[0]["account_id"], "1001712982604688")
        self.assertEqual(accounts[1]["cabang"], "33KDGP81")
        self.assertEqual(accounts[0]["access_token"], "secret-a")

    def test_read_accounts_posts_json_without_logging_response_body(self):
        session = FakeSession([
            FakeResponse(200, {
                "status": "ok",
                "Detail": [{
                    "idAcoount": "123",
                    "token": "secret-token",
                    "cabang": "CAB",
                    "bisnis": "MGA",
                }],
            })
        ])
        accounts = read_accounts_from_api(
            api_url="https://example.invalid/ksapisvr",
            no_hp="081234",
            since="2026-02-01",
            until="2026-02-28",
            max_retries=0,
            session=session,
        )
        self.assertEqual(accounts[0]["access_token"], "secret-token")
        args, kwargs = session.requests[0]
        self.assertEqual(args[0], "https://example.invalid/ksapisvr")
        self.assertEqual(
            kwargs["json"]["api_jsoncmonss"][0]["tanggalAkhir"],
            "2026-02-28",
        )

    def test_parse_bom_and_stringified_json_response(self):
        payload_text = '\ufeff' + json.dumps({
            "status": "ok",
            "Detail": [{
                "idAcoount": "123",
                "token": "secret-token",
                "cabang": "CAB",
                "bisnis": "MGA",
            }],
        })
        response = FakeResponse(200, ValueError("not direct json"), text=payload_text)
        parsed = parse_datameta_response(response)
        self.assertEqual(parsed["status"], "ok")

        stringified = json.dumps(json.dumps({"status": "ok", "Detail": []}))
        response2 = FakeResponse(200, ValueError("nested"), text=stringified)
        parsed2 = parse_datameta_response(response2)
        self.assertEqual(parsed2["status"], "ok")

    def test_parse_form_encoded_response(self):
        detail = json.dumps([{
            "idAcoount": "123",
            "token": "secret-token",
            "cabang": "CAB",
            "bisnis": "MGA",
        }])
        response = FakeResponse(200, ValueError("not json"), text="status=ok&Detail=" + detail)
        parsed = parse_datameta_response(response)
        self.assertEqual(parsed["status"], "ok")
        self.assertEqual(parsed["Detail"][0]["idAcoount"], "123")

    def test_parse_nss_legacy_status_equals_response(self):
        legacy_text = (
            '{ status = ok , "Detail":['
            '{"idAcoount":"1001712982604688","token":"secret-token",'
            '"cabang":"34THJO81","bisnis":"MGA"}'
            ']}'
        )
        response = FakeResponse(200, ValueError("malformed json"), text=legacy_text)
        parsed = parse_datameta_response(response)
        self.assertEqual(parsed["status"], "ok")
        self.assertEqual(parsed["Detail"][0]["idAcoount"], "1001712982604688")

    def test_api_account_allows_blank_cabang(self):
        accounts = parse_accounts_from_datameta_payload({
            "status": "ok",
            "Detail": [{
                "idAcoount": "381557894799853",
                "token": "secret-token",
                "cabang": "",
                "bisnis": "HMC",
            }],
        })
        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0]["cabang"], "")
        self.assertEqual(accounts[0]["bisnis"], "HMC")

    def test_auto_uses_json_mode_for_nss_legacy_response(self):
        legacy_text = (
            '{ status = ok , "Detail":['
            '{"idAcoount":"123","token":"secret-token",'
            '"cabang":"CAB","bisnis":"MGA"}'
            ']}'
        )
        session = FakeSession([
            FakeResponse(200, ValueError("malformed json"), text=legacy_text),
        ])
        accounts = read_accounts_from_api(
            api_url="https://example.invalid/ksapisvr",
            no_hp="081234",
            since="2026-02-01",
            until="2026-02-28",
            max_retries=0,
            body_mode="auto",
            session=session,
        )
        self.assertEqual(accounts[0]["account_id"], "123")
        self.assertEqual(session.calls, 1)
        _, kwargs = session.requests[0]
        self.assertIn("json", kwargs)

    def test_auto_falls_back_to_form_when_json_response_is_invalid(self):
        session = FakeSession([
            FakeResponse(200, ValueError("html"), text="<html>invalid request</html>"),
            FakeResponse(200, {
                "status": "ok",
                "Detail": [{
                    "idAcoount": "123",
                    "token": "secret-token",
                    "cabang": "CAB",
                    "bisnis": "MGA",
                }],
            }),
        ])
        accounts = read_accounts_from_api(
            api_url="https://example.invalid/ksapisvr",
            no_hp="081234",
            since="2026-02-01",
            until="2026-02-28",
            max_retries=0,
            body_mode="auto",
            session=session,
        )
        self.assertEqual(accounts[0]["account_id"], "123")
        self.assertEqual(session.calls, 2)
        _, first_kwargs = session.requests[0]
        _, second_kwargs = session.requests[1]
        self.assertIn("json", first_kwargs)
        self.assertIn("data", second_kwargs)
        self.assertIn("api_jsoncmonss", second_kwargs["data"])


class RetryTests(unittest.TestCase):
    def test_retry_then_success(self):
        session = FakeSession([
            FakeResponse(
                500,
                {
                    "error": {
                        "message": "temporary",
                        "code": 2,
                        "is_transient": True,
                    }
                },
            ),
            FakeResponse(200, {"data": [{"id": "1"}]}),
        ])
        sleeps = []
        client = MetaAdsClient(
            api_version="v25.0",
            access_token="token",
            max_retries=2,
            retry_base_delay=0.1,
            retry_max_delay=1.0,
            sleep_func=sleeps.append,
            jitter_func=lambda low, high: 0.0,
            session=session,
        )
        payload = client.get_json("https://example.invalid")
        self.assertEqual(payload["data"][0]["id"], "1")
        self.assertEqual(session.calls, 2)
        self.assertEqual(len(sleeps), 1)

    def test_data_too_large_is_not_retried_identically(self):
        session = FakeSession([
            FakeResponse(
                500,
                {
                    "error": {
                        "message": (
                            "Please reduce the amount of data you're asking for, "
                            "then retry your request"
                        ),
                        "code": 1,
                    }
                },
            ),
        ])
        sleeps = []
        client = MetaAdsClient(
            api_version="v25.0",
            access_token="token",
            max_retries=5,
            sleep_func=sleeps.append,
            session=session,
        )
        with self.assertRaises(MetaApiError) as context:
            client.get_json("https://example.invalid")
        self.assertTrue(context.exception.data_too_large)
        self.assertEqual(session.calls, 1)
        self.assertEqual(sleeps, [])

    def test_rinci_insights_are_split_per_day(self):
        session = FakeSession([
            FakeResponse(200, {"data": [{"date_start": "2026-08-01"}]}),
            FakeResponse(200, {"data": [{"date_start": "2026-08-02"}]}),
            FakeResponse(200, {"data": [{"date_start": "2026-08-03"}]}),
        ])
        client = MetaAdsClient(
            api_version="v25.0",
            access_token="token",
            max_retries=0,
            session=session,
        )
        rows, _ = client.fetch_all_insights(
            account_id="123",
            mode="rinci",
            since="2026-08-01",
            until="2026-08-03",
        )
        self.assertEqual(len(rows), 3)
        ranges = [
            json.loads(call[1]["params"]["time_range"])
            for call in session.requests
        ]
        self.assertEqual(
            ranges,
            [
                {"since": "2026-08-01", "until": "2026-08-01"},
                {"since": "2026-08-02", "until": "2026-08-02"},
                {"since": "2026-08-03", "until": "2026-08-03"},
            ],
        )


class FrequencyTests(unittest.TestCase):

    def test_frequency_source_is_daily_for_rinci_and_direct_for_rekap(self):
        rinci_fields = MetaAdsClient.insight_field_attempts("rinci")[0]
        rekap_fields = MetaAdsClient.insight_field_attempts("rekap")[0]
        daily_fields = MetaAdsClient.daily_result_field_attempts()[0]
        self.assertNotIn("frequency", rinci_fields)
        self.assertIn("frequency", rekap_fields)
        self.assertIn("frequency", daily_fields)
        self.assertIn("impressions", daily_fields)
        self.assertIn("reach", daily_fields)

    def test_daily_frequency_uses_meta_value(self):
        self.assertEqual(
            daily_frequency_value({"frequency": "1.150628"}),
            "1.150628",
        )

    def test_daily_frequency_falls_back_to_impressions_div_reach(self):
        value = daily_frequency_value({
            "impressions": "1150628",
            "reach": "1000000",
        })
        self.assertAlmostEqual(float(value), 1.150628, places=6)


class DailyResultsTests(unittest.TestCase):
    def test_daily_result_request_has_no_hourly_breakdown(self):
        session = FakeSession([
            FakeResponse(200, {"data": [{
                "ad_id": "52510676405480",
                "date_start": "2026-07-01",
                "results": [{
                    "indicator": (
                        "actions:onsite_conversion."
                        "messaging_conversation_started_7d"
                    ),
                    "values": [{"value": "9"}],
                }],
            }]}),
        ])
        client = MetaAdsClient(
            api_version="v25.0",
            access_token="token",
            max_retries=0,
            session=session,
        )
        rows, fields = client.fetch_daily_result_insights(
            account_id="123",
            since="2026-07-01",
            until="2026-07-01",
        )
        self.assertEqual(rows[0]["ad_id"], "52510676405480")
        self.assertIn("results", fields)
        params = session.requests[0][1]["params"]
        self.assertEqual(params["time_increment"], "1")
        self.assertNotIn("breakdowns", params)

    def test_daily_result_written_once_across_hourly_rows(self):
        class Client:
            def fetch_adsets(self, account_id):
                return {}

            def fetch_all_insights(self, account_id, mode, since, until):
                return ([
                    {
                        "ad_id": "52510676405480",
                        "ad_name": "Iklan",
                        "date_start": "2026-07-01",
                        "hourly_stats_aggregated_by_advertiser_time_zone": (
                            "10:00:00 - 10:59:59"
                        ),
                        "impressions": "344",
                        "inline_link_clicks": "5",
                        "inline_link_click_ctr": "1.45",
                        "spend": "4932",
                    },
                    {
                        "ad_id": "52510676405480",
                        "ad_name": "Iklan",
                        "date_start": "2026-07-01",
                        "hourly_stats_aggregated_by_advertiser_time_zone": (
                            "03:00:00 - 03:59:59"
                        ),
                        "impressions": "13",
                        "inline_link_clicks": "1",
                        "inline_link_click_ctr": "7.69",
                        "spend": "96",
                    },
                ], [])

            def fetch_daily_result_insights(self, account_id, since, until):
                return ([{
                    "ad_id": "52510676405480",
                    "date_start": "2026-07-01",
                    "spend": "9000",
                    "frequency": "1.150628",
                    "optimization_goal": "CONVERSATIONS",
                    "results": [{
                        "indicator": (
                            "actions:onsite_conversion."
                            "messaging_conversation_started_7d"
                        ),
                        "values": [{"value": "9"}],
                    }],
                }], [])

        rows = process_rinci_account(
            client=Client(),
            account_id="123",
            cabang="CAB",
            bisnis="GADAI",
            account_info={"name": "Akun", "currency": "IDR"},
            since="2026-07-01",
            until="2026-07-01",
            status_filter="semua",
        )
        self.assertEqual([row["Jam mulai"] for row in rows], [3, 10])
        self.assertEqual(rows[0]["Hasil"], "9")
        self.assertEqual(rows[0]["Biaya per hasil"], "1000.0")
        self.assertEqual(rows[0]["Frekuensi"], "1.150628")
        self.assertEqual(rows[1]["Frekuensi"], "1.150628")
        self.assertEqual(rows[1]["Hasil"], "")
        self.assertEqual(rows[1]["Biaya per hasil"], "")
        self.assertEqual(sum(float(row["Hasil"] or 0) for row in rows), 9.0)


    def test_daily_result_ignores_unrelated_indicators(self):
        metric_type, result_value, cost_value = choose_daily_result_detail({
            "ad_id": "52510676405480",
            "date_start": "2026-07-01",
            "spend": "9000",
            "results": [
                {
                    "indicator": "actions:link_click",
                    "values": [{"value": "123"}],
                },
                {
                    "indicator": "actions:omni_purchase",
                    "values": [{"value": "7"}],
                },
            ],
        })
        self.assertEqual(metric_type, "")
        self.assertEqual(result_value, "")
        self.assertEqual(cost_value, "")

    def test_daily_result_falls_back_to_lead_indicator(self):
        metric_type, result_value, cost_value = choose_daily_result_detail({
            "ad_id": "52510676405480",
            "date_start": "2026-07-01",
            "spend": "9000",
            "results": [
                {
                    "indicator": "actions:lead",
                    "values": [{"value": "99"}],
                },
                {
                    "indicator": "actions:link_click",
                    "values": [{"value": "123"}],
                },
            ],
        })
        self.assertEqual(metric_type, "actions:lead")
        self.assertEqual(result_value, "99")
        # Tanpa cost_per_result, biaya dihitung dari spend/hasil pada baris yang sama.
        self.assertEqual(cost_value, str(9000.0 / 99))

    def test_daily_result_prefers_conversation_over_lead(self):
        metric_type, result_value, _ = choose_daily_result_detail({
            "spend": "9000",
            "results": [
                {
                    "indicator": "actions:onsite_conversion.lead_grouped",
                    "values": [{"value": "40"}],
                },
                {
                    "indicator": "actions:onsite_conversion."
                    "messaging_conversation_started_7d",
                    "values": [{"value": "9"}],
                },
            ],
        })
        self.assertEqual(
            metric_type,
            "actions:onsite_conversion.messaging_conversation_started_7d",
        )
        self.assertEqual(result_value, "9")

    def test_daily_result_conversation_wins_over_unprefixed_lead(self):
        # Regresi: conversation berawalan "actions:" pernah kalah dari lead tanpa
        # awalan karena perbandingan tidak dinormalisasi.
        metric_type, result_value, _ = choose_daily_result_detail({
            "spend": "9000",
            "results": [
                {"indicator": "lead", "values": [{"value": "40"}]},
                {
                    "indicator": "actions:onsite_conversion."
                    "messaging_conversation_started_7d",
                    "values": [{"value": "9"}],
                },
            ],
        })
        self.assertEqual(
            metric_type,
            "actions:onsite_conversion.messaging_conversation_started_7d",
        )
        self.assertEqual(result_value, "9")

    def test_daily_result_priority_ignores_prefix_and_payload_order(self):
        conversation = "actions:onsite_conversion.messaging_conversation_started_7d"
        lead = "onsite_conversion.lead"

        for indicators in ([conversation, lead], [lead, conversation]):
            metric_type, result_value, _ = choose_daily_result_detail({
                "spend": "9000",
                "results": [
                    {"indicator": name, "values": [{"value": "5"}]}
                    for name in indicators
                ],
            })
            self.assertEqual(metric_type, conversation)
            self.assertEqual(result_value, "5")

    def test_daily_result_matches_cost_across_prefix_difference(self):
        metric_type, result_value, cost_value = choose_daily_result_detail({
            "spend": "9000",
            "results": [{
                "indicator": "onsite_conversion.lead_grouped",
                "values": [{"value": "4"}],
            }],
            "cost_per_result": [{
                "indicator": "actions:onsite_conversion.lead_grouped",
                "values": [{"value": "2250"}],
            }],
        })
        self.assertEqual(metric_type, "onsite_conversion.lead_grouped")
        self.assertEqual(result_value, "4")
        self.assertEqual(cost_value, "2250")

    def test_daily_result_uses_cost_for_selected_lead_indicator(self):
        metric_type, result_value, cost_value = choose_daily_result_detail({
            "spend": "9000",
            "results": [{
                "indicator": "actions:onsite_conversion.lead_grouped",
                "values": [{"value": "10"}],
            }],
            "cost_per_result": [{
                "indicator": "actions:onsite_conversion.lead_grouped",
                "values": [{"value": "900.0"}],
            }],
        })
        self.assertEqual(metric_type, "actions:onsite_conversion.lead_grouped")
        self.assertEqual(result_value, "10")
        self.assertEqual(cost_value, "900.0")

    def test_daily_result_uses_exact_messaging_indicator(self):
        metric_type, result_value, cost_value = choose_daily_result_detail({
            "spend": "9000",
            "results": [{
                "indicator": (
                    "actions:onsite_conversion."
                    "messaging_conversation_started_7d"
                ),
                "values": [{"value": "9"}],
            }],
        })
        self.assertEqual(
            metric_type,
            "actions:onsite_conversion.messaging_conversation_started_7d",
        )
        self.assertEqual(result_value, "9")
        self.assertEqual(cost_value, "1000.0")


class FakeMetaClient:
    created_tokens = []

    def __init__(self, *args, **kwargs):
        self.__class__.created_tokens.append(kwargs.get("access_token"))

    def get_account_information(self, account_id):
        return {
            "name": "Akun Test",
            "currency": "IDR",
            "timezone_name": "Asia/Jakarta",
        }

    def fetch_adsets(self, account_id):
        return {
            "2001": {
                "id": "2001",
                "name": "Set",
                "attribution_spec": [
                    {"event_type": "CLICK_THROUGH", "window_days": 7}
                ],
            }
        }

    def fetch_all_insights(self, account_id, mode, since, until):
        return ([{
            "campaign_id": "1001",
            "campaign_name": "Kampanye",
            "adset_id": "2001",
            "adset_name": "Set",
            "ad_id": "3001",
            "ad_name": 'Postingan: "Lagi butuh dana cepat tapi nggak mau"',
            "date_start": since,
            "hourly_stats_aggregated_by_advertiser_time_zone": (
                "18:00:00 - 18:59:59"
            ),
            "impressions": "100",
            "inline_link_clicks": "5",
            "inline_link_click_ctr": "5",
            "spend": "10000",
        }], [])

    def fetch_daily_result_insights(self, account_id, since, until):
        return ([{
            "ad_id": "3001",
            "date_start": since,
            "spend": "10000",
            "optimization_goal": "CONVERSATIONS",
            "results": [{
                "indicator": (
                    "actions:onsite_conversion."
                    "messaging_conversation_started_7d"
                ),
                "values": [{"value": "9", "attribution_windows": ["default"]}],
            }],
        }], [])


class RunnerTests(unittest.TestCase):
    def test_per_account_token_and_checkpoint(self):
        FakeMetaClient.created_tokens = []
        with tempfile.TemporaryDirectory() as temp_dir:
            checkpoint_path = os.path.join(temp_dir, "state.sqlite3")
            signature = {"schema_version": "2", "test": "runner"}
            store = CheckpointStore(checkpoint_path, signature, resume=False)
            try:
                result = run_accounts(
                    accounts=[
                        {
                            "account_id": "123",
                            "access_token": "secret-token-123",
                            "cabang": "CAB",
                            "bisnis": "GADAI",
                        },
                        {
                            "account_id": "456",
                            "access_token": "secret-token-456",
                            "cabang": "CAB2",
                            "bisnis": "MIKRO",
                        },
                    ],
                    mode="rinci",
                    status_filter="semua",
                    since="2026-08-01",
                    until="2026-08-05",
                    checkpoint=store,
                    api_version="v25.0",
                    max_retries=0,
                    retry_base_delay=0,
                    retry_max_delay=0,
                    client_factory=FakeMetaClient,
                )
                self.assertEqual(
                    FakeMetaClient.created_tokens,
                    ["secret-token-123", "secret-token-456"],
                )
                self.assertEqual(len(result.rows), 2)
                row = result.rows[0]
                self.assertEqual(row["ID ACCOUNT"], "123")
                self.assertEqual(row["CABANG"], "CAB")
                self.assertEqual(row["BISNIS"], "GADAI")
                self.assertEqual(row["ID kampanye"], "1001")
                self.assertEqual(row["ID set iklan"], "2001")
                self.assertEqual(row["ID iklan"], "3001")
                self.assertEqual(row["Jam mulai"], 18)
                self.assertEqual(row["Kategori waktu"], "Malam")
                self.assertEqual(row["Hasil"], "9")
                self.assertEqual(
                    row["Nama iklan"],
                    "Lagi butuh dana cepat tapi nggak mau",
                )
                self.assertNotIn("TOKEN", row)
                self.assertEqual(store.completed_accounts(), {"123", "456"})

                tables = store.connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
                self.assertNotIn("token", " ".join(str(item) for item in tables).lower())
                account_columns = [
                    item[1]
                    for item in store.connection.execute("PRAGMA table_info(accounts)")
                ]
                self.assertNotIn("token", account_columns)
            finally:
                store.close()


class CheckpointTests(unittest.TestCase):
    def test_roundtrip_and_resume(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "checkpoint.sqlite3")
            signature = {"test": "signature", "schema_version": "2"}
            store = CheckpointStore(path, signature, resume=False)
            store.save_account_result(
                account_id="123",
                cabang="CAB",
                bisnis="GADAI",
                rows=[{"ID iklan": "456", "Nama iklan": "Test"}],
                errors=[],
                status="completed",
            )
            store.close()

            resumed = CheckpointStore(path, signature, resume=True)
            self.assertEqual(resumed.completed_accounts(), {"123"})
            self.assertEqual(resumed.load_rows()[0]["ID iklan"], "456")
            self.assertEqual(resumed.account_summary()[0]["bisnis"], "GADAI")
            resumed.close()

            with self.assertRaises(CheckpointMismatchError):
                CheckpointStore(path, {"test": "different"}, resume=True)


class OutputLocationTests(unittest.TestCase):
    def test_project_output_location_uses_project_root(self):
        output, fmt = resolve_output(
            output_value="laporan.csv",
            format_value="csv",
            input_file="",
            input_source="api",
            mode="rinci",
            status="semua",
            since="2026-08-01",
            until="2026-08-05",
            output_location="project",
        )
        self.assertEqual(fmt, "csv")
        self.assertEqual(output, os.path.join(project_root(), "laporan.csv"))

    def test_home_output_location_uses_home_laporan_folder(self):
        with patch("meta_ads_tool.cli.os.path.expanduser", return_value="/fake/home"):
            output, fmt = resolve_output(
                output_value="laporan.csv",
                format_value="csv",
                input_file="",
                input_source="api",
                mode="rinci",
                status="semua",
                since="2026-08-01",
                until="2026-08-05",
                output_location="home",
            )
            self.assertEqual(fmt, "csv")
            self.assertEqual(
                output,
                os.path.abspath(os.path.join("/fake/home", "laporan", "laporan.csv")),
            )

    def test_absolute_output_path_wins_over_output_location(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            absolute = os.path.join(temp_dir, "absolute.csv")
            output, fmt = resolve_output(
                output_value=absolute,
                format_value="csv",
                input_file="",
                input_source="api",
                mode="rinci",
                status="semua",
                since="2026-08-01",
                until="2026-08-05",
                output_location="home",
            )
            self.assertEqual(fmt, "csv")
            self.assertEqual(output, os.path.abspath(absolute))

    def test_default_location_preserves_v544_behavior_for_api(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                output, fmt = resolve_output(
                    output_value="",
                    format_value="csv",
                    input_file="",
                    input_source="api",
                    mode="rinci",
                    status="semua",
                    since="2026-08-01",
                    until="2026-08-05",
                    output_location="default",
                )
            finally:
                os.chdir(old_cwd)
            self.assertEqual(fmt, "csv")
            self.assertEqual(os.path.dirname(output), temp_dir)



class TechnicalOutputIsolationMixin:
    """Cegah test menulis file teknis ke folder project asli.

    ``cli.main`` selalu menaruh file ``_errors.csv``/``_info.csv``/checkpoint di
    ``auxiliary_output_directory()``, yang menunjuk ``project_root()``. Test yang
    hanya mengarahkan output utama ke temp dir tetap akan menimpa folder project
    asli bila folder teknis tidak diisolasi.
    """

    def setUp(self):
        super().setUp()
        isolation_dir = tempfile.mkdtemp(prefix="meta_ads_teknis_")
        for target in (
            "meta_ads_tool.paths.project_root",
            "meta_ads_tool.cli.project_root",
            "meta_ads_tool.summary.auxiliary_output_directory",
        ):
            patcher = patch(target, return_value=isolation_dir)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(shutil.rmtree, isolation_dir, True)


class CliIntegrationTests(TechnicalOutputIsolationMixin, unittest.TestCase):
    def test_cli_end_to_end_without_network(self):
        FakeMetaClient.created_tokens = []
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = os.path.join(temp_dir, "accounts.xlsx")
            output_path = os.path.join(temp_dir, "report.xlsx")
            workbook = Workbook()
            sheet = workbook.active
            sheet.append(list(INPUT_HEADERS))
            sheet.append(["123", "token-dari-excel", "CAB", "GADAI"])
            workbook.save(input_path)
            workbook.close()

            # `--sumber-akun excel` wajib eksplisit: tanpa itu argparse memakai
            # META_ACCOUNT_SOURCE dari .env lokal dan test ini contacting API
            # DATAMETA produksi sungguhan.
            with patch("meta_ads_tool.cli.MetaAdsClient", FakeMetaClient), patch(
                "meta_ads_tool.cli.read_accounts_from_api",
                side_effect=AssertionError(
                    "test hermetik tidak boleh memanggil API DATAMETA"
                ),
            ):
                code = cli_main([
                    "--sumber-akun",
                    "excel",
                    "--mode",
                    "rinci",
                    "--status",
                    "semua",
                    "--since",
                    "2026-08-01",
                    "--until",
                    "2026-08-05",
                    "--output",
                    output_path,
                    input_path,
                ])

            self.assertEqual(code, 0)
            self.assertEqual(FakeMetaClient.created_tokens, ["token-dari-excel"])
            self.assertTrue(os.path.isfile(output_path))
            self.assertFalse(os.path.exists(output_path + ".checkpoint.sqlite3"))
            result_book = load_workbook(output_path, read_only=True)
            try:
                sheet = result_book["Rinci Iklan"]
                self.assertEqual(sheet.max_row, 2)
                headers = [cell.value for cell in sheet[1]]
                self.assertIn("CABANG", headers)
                self.assertIn("BISNIS", headers)
                self.assertNotIn("TOKEN", headers)
            finally:
                result_book.close()


class CliApiSourceIntegrationTests(TechnicalOutputIsolationMixin, unittest.TestCase):
    def test_cli_api_source_without_excel(self):
        FakeMetaClient.created_tokens = []
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "report.csv")
            api_accounts = [{
                "account_id": "123",
                "access_token": "token-dari-api",
                "cabang": "CAB",
                "bisnis": "MGA",
            }]
            with patch(
                "meta_ads_tool.cli.read_accounts_from_api",
                return_value=api_accounts,
            ), patch("meta_ads_tool.cli.MetaAdsClient", FakeMetaClient):
                code = cli_main([
                    "--sumber-akun", "api",
                    "--source-api-nohp", "081234",
                    "--mode", "rinci",
                    "--status", "semua",
                    "--since", "2026-08-01",
                    "--until", "2026-08-05",
                    "--format", "csv",
                    "--output", output_path,
                ])
            self.assertEqual(code, 0)
            self.assertEqual(FakeMetaClient.created_tokens, ["token-dari-api"])
            self.assertTrue(os.path.isfile(output_path))
            with open(output_path, "r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle, delimiter=CSV_DELIMITER)
                row = next(reader)
                self.assertEqual(row["Tanggal"], "01-08-2026")
                self.assertEqual(row["BISNIS"], "MGA")


class ExportTests(TechnicalOutputIsolationMixin, unittest.TestCase):
    @staticmethod
    def sample_row():
        return {
            "ID ACCOUNT": "123",
            "Nama akun": "=nama-berbahaya",
            "ID kampanye": "1001",
            "Nama kampanye": "Kampanye | Juli",
            "ID set iklan": "2001",
            "Nama set iklan": "Set",
            "ID iklan": "3001",
            "Nama iklan": "Iklan",
            "Tanggal": "2026-08-05",
            "Waktu (zona waktu akun iklan)": "07:00 - 07:59",
            "Jam mulai": 7,
            "Kategori waktu": "Pagi",
            "Pengaturan atribusi": "7d_click",
            "Mulai": "2026-08-01T00:00:00+0700",
            "Berakhir": "2026-08-31T23:59:59+0700",
            "Impresi": "100",
            "Frekuensi": "1.150628",
            "Klik tautan": "5",
            "CTR klik tautan": 5.0,
            "Biaya per klik tautan": "1000",
            "Hasil": "2",
            "Biaya per hasil": "2500",
            "Jumlah yang dibelanjakan": "5000",
            "Mata uang": "IDR",
            "Awal pelaporan": "2026-08-01",
            "Akhir pelaporan": "2026-08-05",
            "CABANG": "CAB",
            "BISNIS": "GADAI",
        }

    def test_xlsx_and_csv(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            xlsx = os.path.join(temp_dir, "report.xlsx")
            csv_path = os.path.join(temp_dir, "report.csv")
            row = self.sample_row()

            export_xlsx(
                output_file=xlsx,
                mode="rinci",
                rows=[row],
                errors=[],
                input_file=xlsx + ".input.xlsx",
                api_version="v25.0",
                since="2026-08-01",
                until="2026-08-05",
                status_filter="semua",
                date_source="manual",
                image_width=160,
                image_height=100,
                embed_images=False,
            )
            workbook = load_workbook(xlsx, data_only=False)
            try:
                sheet = workbook["Rinci Iklan"]
                headers = [cell.value for cell in sheet[1]]
                self.assertIn("ID kampanye", headers)
                self.assertIn("Jam mulai", headers)
                self.assertIn("Kategori waktu", headers)
                self.assertIn("Frekuensi", headers)
                self.assertIn("CABANG", headers)
                self.assertIn("BISNIS", headers)
                self.assertNotIn("TOKEN", headers)
                name_col = headers.index("Nama akun") + 1
                self.assertEqual(sheet.cell(2, name_col).value, "'=nama-berbahaya")
            finally:
                workbook.close()

            result = export_csv(
                output_file=csv_path,
                mode="rinci",
                rows=[row],
                errors=[],
                input_file="input.xlsx",
                api_version="v25.0",
                since="2026-08-01",
                until="2026-08-05",
                status_filter="semua",
                date_source="manual",
                process_date="2026-08-05",
            )
            self.assertTrue(os.path.isfile(result.report_file))
            self.assertTrue(os.path.isfile(result.error_file))
            self.assertTrue(os.path.isfile(result.info_file))
            with open(csv_path, "r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle, delimiter=CSV_DELIMITER)
                self.assertEqual(reader.fieldnames, CSV_REPORT_COLUMNS)
                loaded = next(reader)
                self.assertEqual(loaded["Nama akun"], "'=nama-berbahaya")
                self.assertEqual(loaded["ID iklan"], "3001")
                self.assertEqual(loaded["Nama kampanye"], "Kampanye | Juli")
                self.assertEqual(loaded["Frekuensi"], "1.150628")
                self.assertEqual(
                    loaded["Waktu (zona waktu akun iklan)"],
                    "07:00 - 07:59",
                )
                self.assertEqual(loaded["CABANG"], "CAB")
                self.assertEqual(loaded["BISNIS"], "GADAI")
                self.assertEqual(loaded["Tanggal"], "05-08-2026")
                self.assertEqual(loaded["Tanggal proses"], "05-08-2026")
                self.assertNotIn("TOKEN", loaded)
                self.assertNotIn("ID set iklan", loaded)
                self.assertNotIn("Jam mulai", loaded)
                self.assertNotIn("Kategori waktu", loaded)

    def test_csv_flexible_delimiters(self):
        row = self.sample_row()
        cases = {
            "comma": ",",
            "tab": "\t",
            "pipe": "|",
            "semicolon": ";",
            ",": ",",
            "|": "|",
            ";": ";",
            "tsv": "\t",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            for index, (choice, expected) in enumerate(cases.items()):
                with self.subTest(choice=choice):
                    self.assertEqual(resolve_csv_delimiter(choice), expected)
                    csv_path = os.path.join(temp_dir, "report_{}.csv".format(index))
                    result = export_csv(
                        output_file=csv_path,
                        mode="rinci",
                        rows=[row],
                        errors=[],
                        input_file="input.xlsx",
                        api_version="v25.0",
                        since="2026-08-01",
                        until="2026-08-05",
                        status_filter="semua",
                        date_source="manual",
                        process_date="2026-08-05",
                        csv_delimiter=choice,
                    )
                    for path in (result.report_file, result.error_file, result.info_file):
                        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
                            first_line = handle.readline()
                            self.assertIn(expected, first_line)
                    with open(csv_path, "r", encoding="utf-8-sig", newline="") as handle:
                        loaded = next(csv.DictReader(handle, delimiter=expected))
                        self.assertEqual(loaded["Tanggal"], "05-08-2026")
                        self.assertEqual(loaded["Frekuensi"], "1.150628")

    def test_csv_without_header(self):
        row = self.sample_row()
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = os.path.join(temp_dir, "report_no_header.csv")
            result = export_csv(
                output_file=csv_path,
                mode="rinci",
                rows=[row],
                errors=[{column: "" for column in ERROR_COLUMNS}],
                input_file="input.xlsx",
                api_version="v25.0",
                since="2026-08-01",
                until="2026-08-05",
                status_filter="semua",
                date_source="manual",
                process_date="2026-08-05",
                csv_delimiter="pipe",
                csv_include_header=False,
            )
            with open(result.report_file, "r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.reader(handle, delimiter="|"))
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0][0], "123")
                self.assertNotEqual(rows[0], CSV_REPORT_COLUMNS)
                self.assertEqual(rows[0][CSV_REPORT_COLUMNS.index("Tanggal")], "05-08-2026")
            with open(result.error_file, "r", encoding="utf-8-sig", newline="") as handle:
                first = next(csv.reader(handle, delimiter="|"))
                self.assertNotEqual(first, ERROR_COLUMNS)
            with open(result.info_file, "r", encoding="utf-8-sig", newline="") as handle:
                first = next(csv.reader(handle, delimiter="|"))
                self.assertNotEqual(first, ["Parameter", "Nilai"])
                self.assertEqual(first[0], "Mode")

    def test_cli_csv_no_header(self):
        FakeMetaClient.created_tokens = []
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "report.csv")
            api_accounts = [{
                "account_id": "123",
                "access_token": "token-dari-api",
                "cabang": "CAB",
                "bisnis": "MGA",
            }]
            with patch(
                "meta_ads_tool.cli.read_accounts_from_api",
                return_value=api_accounts,
            ), patch("meta_ads_tool.cli.MetaAdsClient", FakeMetaClient):
                code = cli_main([
                    "--sumber-akun", "api",
                    "--source-api-nohp", "081234",
                    "--mode", "rinci",
                    "--status", "semua",
                    "--since", "2026-08-01",
                    "--until", "2026-08-05",
                    "--format", "csv",
                    "--csv-delimiter", "pipe",
                    "--csv-no-header",
                    "--output", output_path,
                ])
            self.assertEqual(code, 0)
            with open(output_path, "r", encoding="utf-8-sig", newline="") as handle:
                first = next(csv.reader(handle, delimiter="|"))
                self.assertEqual(first[0], "123")
                self.assertNotEqual(first, CSV_REPORT_COLUMNS)

    def test_cli_project_output_location(self):
        FakeMetaClient.created_tokens = []
        with tempfile.TemporaryDirectory() as temp_dir:
            api_accounts = [{
                "account_id": "123",
                "access_token": "token-dari-api",
                "cabang": "CAB",
                "bisnis": "MGA",
            }]
            with patch(
                "meta_ads_tool.cli.read_accounts_from_api",
                return_value=api_accounts,
            ), patch("meta_ads_tool.cli.MetaAdsClient", FakeMetaClient), patch(
                "meta_ads_tool.cli.project_root", return_value=temp_dir
            ):
                code = cli_main([
                    "--sumber-akun", "api",
                    "--source-api-nohp", "081234",
                    "--mode", "rinci",
                    "--status", "semua",
                    "--since", "2026-08-01",
                    "--until", "2026-08-05",
                    "--format", "csv",
                    "--output-location", "project",
                    "--output", "project_report.csv",
                ])
            self.assertEqual(code, 0)
            self.assertTrue(os.path.isfile(os.path.join(temp_dir, "project_report.csv")))

    def test_cli_home_output_location(self):
        FakeMetaClient.created_tokens = []
        with tempfile.TemporaryDirectory() as temp_dir:
            report_dir = os.path.join(temp_dir, "laporan")
            api_accounts = [{
                "account_id": "123",
                "access_token": "token-dari-api",
                "cabang": "CAB",
                "bisnis": "MGA",
            }]
            with patch(
                "meta_ads_tool.cli.read_accounts_from_api",
                return_value=api_accounts,
            ), patch("meta_ads_tool.cli.MetaAdsClient", FakeMetaClient), patch(
                "meta_ads_tool.cli.home_report_directory", return_value=report_dir
            ):
                code = cli_main([
                    "--sumber-akun", "api",
                    "--source-api-nohp", "081234",
                    "--mode", "rinci",
                    "--status", "semua",
                    "--since", "2026-08-01",
                    "--until", "2026-08-05",
                    "--format", "csv",
                    "--output-location", "home",
                    "--output", "home_report.csv",
                ])
            self.assertEqual(code, 0)
            self.assertTrue(os.path.isfile(os.path.join(report_dir, "home_report.csv")))

    def test_home_location_moves_only_report_and_keeps_technical_files_in_project(self):
        FakeMetaClient.created_tokens = []
        with tempfile.TemporaryDirectory() as temp_dir:
            report_dir = os.path.join(temp_dir, "home", "laporan")
            project_dir = os.path.join(temp_dir, "project")
            os.makedirs(project_dir, exist_ok=True)
            api_accounts = [{
                "account_id": "123",
                "access_token": "token-dari-api",
                "cabang": "CAB",
                "bisnis": "MGA",
            }]
            messages = []
            with patch(
                "meta_ads_tool.cli.read_accounts_from_api",
                return_value=api_accounts,
            ), patch("meta_ads_tool.cli.MetaAdsClient", FakeMetaClient), patch(
                "meta_ads_tool.cli.home_report_directory", return_value=report_dir
            ), patch(
                "meta_ads_tool.cli.project_root", return_value=project_dir
            ), patch(
                "meta_ads_tool.paths.project_root", return_value=project_dir
            ), patch(
                "meta_ads_tool.cli.info", side_effect=messages.append
            ), patch(
                "meta_ads_tool.summary.info", side_effect=messages.append
            ):
                code = cli_main([
                    "--sumber-akun", "api",
                    "--source-api-nohp", "081234",
                    "--mode", "rinci",
                    "--status", "semua",
                    "--since", "2026-08-01",
                    "--until", "2026-08-05",
                    "--format", "csv",
                    "--output-location", "home",
                    "--keep-checkpoint",
                    "--output", "home_report.csv",
                ])
            self.assertEqual(code, 0)
            self.assertTrue(os.path.isfile(os.path.join(report_dir, "home_report.csv")))
            self.assertFalse(os.path.exists(os.path.join(report_dir, "home_report_errors.csv")))
            self.assertFalse(os.path.exists(os.path.join(report_dir, "home_report_info.csv")))
            self.assertTrue(os.path.isfile(os.path.join(project_dir, "home_report_errors.csv")))
            self.assertTrue(os.path.isfile(os.path.join(project_dir, "home_report_info.csv")))
            self.assertTrue(os.path.isfile(os.path.join(project_dir, "home_report.csv.checkpoint.sqlite3")))
            self.assertTrue(any(message.startswith("Durasi proses") for message in messages))
            self.assertTrue(any(message.startswith("Selesai proses") for message in messages))

    def test_elapsed_duration_format(self):
        self.assertEqual(format_elapsed_seconds(0), "00:00:00")
        self.assertEqual(format_elapsed_seconds(61), "00:01:01")
        self.assertEqual(format_elapsed_seconds(3661.6), "01:01:02")

    def test_cli_semicolon_delimiter(self):
        FakeMetaClient.created_tokens = []
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "report.csv")
            api_accounts = [{
                "account_id": "123",
                "access_token": "token-dari-api",
                "cabang": "CAB",
                "bisnis": "MGA",
            }]
            with patch(
                "meta_ads_tool.cli.read_accounts_from_api",
                return_value=api_accounts,
            ), patch("meta_ads_tool.cli.MetaAdsClient", FakeMetaClient):
                code = cli_main([
                    "--sumber-akun", "api",
                    "--source-api-nohp", "081234",
                    "--mode", "rinci",
                    "--status", "semua",
                    "--since", "2026-08-01",
                    "--until", "2026-08-05",
                    "--format", "csv",
                    "--csv-delimiter", "semicolon",
                    "--output", output_path,
                ])
            self.assertEqual(code, 0)
            with open(output_path, "r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle, delimiter=";")
                row_loaded = next(reader)
                self.assertEqual(row_loaded["BISNIS"], "MGA")


if __name__ == "__main__":
    unittest.main()
