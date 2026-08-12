"""Meta Marketing API client with pagination, retry, and status filtering."""

import json
import random
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

from .logging_utils import info, warning


RETRY_HTTP_STATUSES = {408, 425, 429, 500, 502, 503, 504}
RETRY_META_CODES = {1, 2, 4, 17, 32, 341, 613}


class MetaApiError(RuntimeError):
    def __init__(
        self,
        message: str,
        http_status: Optional[int] = None,
        code: Optional[int] = None,
        subcode: Optional[int] = None,
        error_type: str = "",
        trace_id: str = "",
        retryable: bool = False,
        data_too_large: bool = False,
    ) -> None:
        RuntimeError.__init__(self, message)
        self.http_status = http_status
        self.code = code
        self.subcode = subcode
        self.error_type = error_type
        self.trace_id = trace_id
        self.retryable = retryable
        self.data_too_large = data_too_large


class MetaAdsClient:
    def __init__(
        self,
        api_version: str,
        access_token: str,
        max_retries: int = 5,
        retry_base_delay: float = 1.5,
        retry_max_delay: float = 60.0,
        sleep_func: Callable[[float], None] = time.sleep,
        jitter_func: Callable[[float, float], float] = random.uniform,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.api_version = api_version
        self.base_url = "https://graph.facebook.com/{}".format(api_version)
        self.max_retries = max(0, int(max_retries))
        self.retry_base_delay = max(0.0, float(retry_base_delay))
        self.retry_max_delay = max(0.0, float(retry_max_delay))
        self.sleep_func = sleep_func
        self.jitter_func = jitter_func
        self.session = session or requests.Session()
        self.session.headers.update({
            "Authorization": "Bearer {}".format(access_token),
            "Accept": "application/json",
            "User-Agent": "MetaAdsReportXlsx/5.3",
        })

    @staticmethod
    def account_node(account_id: str) -> str:
        return "act_{}".format(account_id)

    def _retry_delay(self, retry_index: int, retry_after: str = "") -> float:
        if retry_after:
            try:
                return min(self.retry_max_delay, max(0.0, float(retry_after)))
            except (TypeError, ValueError):
                pass
        exponential = self.retry_base_delay * (2 ** retry_index)
        jitter_upper = max(0.25, min(1.0, self.retry_base_delay))
        jitter = self.jitter_func(0.0, jitter_upper)
        return min(self.retry_max_delay, exponential + jitter)

    def _wait_before_retry(
        self,
        retry_index: int,
        reason: str,
        retry_after: str = "",
    ) -> None:
        delay = self._retry_delay(retry_index, retry_after=retry_after)
        warning(
            "Request Meta gagal sementara: {}. Retry {}/{} dalam {:.2f} detik.".format(
                reason,
                retry_index + 1,
                self.max_retries,
                delay,
            )
        )
        self.sleep_func(delay)

    @staticmethod
    def _parse_error(
        response: Any,
        payload: Optional[Dict[str, Any]],
    ) -> MetaApiError:
        http_status = getattr(response, "status_code", None)
        error_data: Dict[str, Any] = {}
        if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
            error_data = payload["error"]

        message = str(error_data.get("message", "Unknown Meta API error"))
        error_type = str(error_data.get("type", ""))
        code_value = error_data.get("code")
        subcode_value = error_data.get("error_subcode")
        trace_id = str(error_data.get("fbtrace_id", ""))
        is_transient = bool(error_data.get("is_transient", False))
        code = code_value if isinstance(code_value, int) else None
        subcode = subcode_value if isinstance(subcode_value, int) else None
        message_lower = message.lower()
        data_too_large = (
            "reduce the amount of data" in message_lower
            or "requesting too much data" in message_lower
            or "too much data" in message_lower
        )
        # Error ukuran query tidak akan membaik dengan mengulang request yang sama.
        # Biarkan pemanggil memecah rentang tanggal atau mengurangi field.
        retryable = (
            not data_too_large
            and (
                http_status in RETRY_HTTP_STATUSES
                or code in RETRY_META_CODES
                or is_transient
            )
        )
        full_message = (
            "Meta API error HTTP {http}; code={code}; subcode={subcode}; "
            "type={etype}; message={message}; fbtrace_id={trace}"
        ).format(
            http=http_status if http_status is not None else "",
            code=code if code is not None else "",
            subcode=subcode if subcode is not None else "",
            etype=error_type,
            message=message,
            trace=trace_id,
        )
        return MetaApiError(
            full_message,
            http_status=http_status if isinstance(http_status, int) else None,
            code=code,
            subcode=subcode,
            error_type=error_type,
            trace_id=trace_id,
            retryable=retryable,
            data_too_large=data_too_large,
        )

    def get_json(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.get(
                    url,
                    params=params,
                    timeout=(15, 180),
                )
            except (
                requests.exceptions.Timeout,
                requests.exceptions.ConnectionError,
            ) as exc:
                if attempt < self.max_retries:
                    self._wait_before_retry(attempt, str(exc) or exc.__class__.__name__)
                    continue
                raise MetaApiError(
                    "Request ke Meta API gagal setelah retry: {}".format(exc),
                    retryable=True,
                ) from exc
            except requests.exceptions.RequestException as exc:
                if attempt < self.max_retries:
                    self._wait_before_retry(attempt, str(exc) or exc.__class__.__name__)
                    continue
                raise MetaApiError(
                    "Request ke Meta API gagal: {}".format(exc),
                    retryable=True,
                ) from exc

            payload: Optional[Dict[str, Any]] = None
            parse_error: Optional[Exception] = None
            try:
                parsed = response.json()
                if isinstance(parsed, dict):
                    payload = parsed
                else:
                    parse_error = ValueError(
                        "Diharapkan object JSON, diterima {}".format(
                            type(parsed).__name__
                        )
                    )
            except ValueError as exc:
                parse_error = exc

            response_ok = bool(getattr(response, "ok", False))
            has_api_error = isinstance(payload, dict) and "error" in payload

            if response_ok and payload is not None and not has_api_error:
                return payload

            if parse_error is not None and getattr(response, "status_code", None) in RETRY_HTTP_STATUSES:
                if attempt < self.max_retries:
                    self._wait_before_retry(
                        attempt,
                        "HTTP {} dengan response bukan JSON".format(response.status_code),
                        retry_after=str(getattr(response, "headers", {}).get("Retry-After", "")),
                    )
                    continue

            if payload is not None:
                api_error = self._parse_error(response, payload)
                if api_error.retryable and attempt < self.max_retries:
                    self._wait_before_retry(
                        attempt,
                        str(api_error),
                        retry_after=str(getattr(response, "headers", {}).get("Retry-After", "")),
                    )
                    continue
                raise api_error

            body_preview = str(getattr(response, "text", ""))[:500].replace("\n", " ")
            status_code = getattr(response, "status_code", None)
            retryable = status_code in RETRY_HTTP_STATUSES
            if retryable and attempt < self.max_retries:
                self._wait_before_retry(
                    attempt,
                    "HTTP {} response bukan JSON".format(status_code),
                    retry_after=str(getattr(response, "headers", {}).get("Retry-After", "")),
                )
                continue
            raise MetaApiError(
                "Response Meta bukan JSON. HTTP {}. Isi response: {}".format(
                    status_code,
                    body_preview or "<kosong>",
                ),
                http_status=status_code if isinstance(status_code, int) else None,
                retryable=retryable,
            )

        raise MetaApiError("Request Meta API gagal tanpa detail.")

    def fetch_paginated_data(
        self,
        url: str,
        params: Dict[str, Any],
        progress_prefix: str,
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        page_number = 1
        current_url: Optional[str] = url
        current_params: Optional[Dict[str, Any]] = params

        while current_url:
            payload = self.get_json(current_url, params=current_params)
            page_rows = payload.get("data", [])
            if not isinstance(page_rows, list):
                raise MetaApiError("Field 'data' pada response Meta bukan list.")

            rows.extend(item for item in page_rows if isinstance(item, dict))
            info(
                "{} halaman {}: {} baris".format(
                    progress_prefix,
                    page_number,
                    len(page_rows),
                )
            )

            paging = payload.get("paging", {})
            if not isinstance(paging, dict):
                paging = {}
            next_url = paging.get("next")
            current_url = next_url if isinstance(next_url, str) and next_url else None
            current_params = None
            page_number += 1

        return rows

    def get_account_information(self, account_id: str) -> Dict[str, Any]:
        return self.get_json(
            "{}/{}".format(self.base_url, self.account_node(account_id)),
            params={
                "fields": (
                    "id,account_id,name,currency,timezone_name,"
                    "timezone_offset_hours_utc"
                )
            },
        )

    def fetch_campaigns(self, account_id: str) -> Dict[str, Dict[str, Any]]:
        rows = self.fetch_paginated_data(
            "{}/{}/campaigns".format(self.base_url, self.account_node(account_id)),
            {
                "fields": "id,name,objective,status,effective_status",
                "limit": "500",
            },
            "Kampanye",
        )
        return {
            str(row.get("id")): row
            for row in rows
            if row.get("id") not in (None, "")
        }

    def fetch_adsets(self, account_id: str) -> Dict[str, Dict[str, Any]]:
        rows = self.fetch_paginated_data(
            "{}/{}/adsets".format(self.base_url, self.account_node(account_id)),
            {
                "fields": (
                    "id,name,campaign_id,optimization_goal,status,effective_status,"
                    "start_time,end_time,attribution_spec"
                ),
                "limit": "500",
            },
            "Set iklan",
        )
        return {
            str(row.get("id")): row
            for row in rows
            if row.get("id") not in (None, "")
        }

    def fetch_ads(
        self,
        account_id: str,
        status_filter: str,
    ) -> List[Dict[str, Any]]:
        url = "{}/{}/ads".format(self.base_url, self.account_node(account_id))
        field_attempts = [
            (
                "id,name,campaign_id,adset_id,configured_status,effective_status,"
                "created_time,updated_time,"
                "creative{id,name,image_url,thumbnail_url,object_type}"
            ),
            (
                "id,name,campaign_id,adset_id,configured_status,effective_status,"
                "created_time,updated_time,creative{id,name,thumbnail_url}"
            ),
            (
                "id,name,campaign_id,adset_id,configured_status,effective_status,"
                "created_time,updated_time,creative{id}"
            ),
            (
                "id,name,campaign_id,adset_id,configured_status,effective_status,"
                "created_time,updated_time,creative"
            ),
        ]

        last_error: Optional[MetaApiError] = None
        for attempt_number, fields in enumerate(field_attempts, start=1):
            params: Dict[str, Any] = {
                "fields": fields,
                "limit": "500",
            }
            if status_filter == "aktif":
                params["effective_status"] = json.dumps(["ACTIVE"])

            try:
                rows = self.fetch_paginated_data(url, params, "Metadata iklan")
                if status_filter == "aktif":
                    rows = [
                        row for row in rows
                        if str(row.get("effective_status", "")).upper() == "ACTIVE"
                    ]
                elif status_filter == "tidak-aktif":
                    rows = [
                        row for row in rows
                        if str(row.get("effective_status", "")).upper() != "ACTIVE"
                    ]

                if attempt_number > 1:
                    info(
                        "Metadata iklan berhasil dengan fallback field tingkat {}.".format(
                            attempt_number
                        )
                    )
                return rows
            except MetaApiError as exc:
                last_error = exc
                if exc.code != 100 or attempt_number == len(field_attempts):
                    raise
                warning(
                    "Field metadata iklan tingkat {} ditolak; mencoba fallback. "
                    "Detail: {}".format(attempt_number, exc)
                )

        if last_error is not None:
            raise last_error
        return []

    def fetch_creative_metadata(self, creative_id: str) -> Dict[str, Any]:
        if not creative_id:
            return {}
        try:
            return self.get_json(
                "{}/{}".format(self.base_url, creative_id),
                params={
                    "fields": "id,name,image_url,thumbnail_url,object_type",
                    "thumbnail_width": "400",
                    "thumbnail_height": "400",
                },
            )
        except MetaApiError as exc:
            warning("Creative {} tidak dapat dibaca: {}".format(creative_id, exc))
            return {}

    @staticmethod
    def insight_field_attempts(mode: str) -> List[List[str]]:
        """Field Insights untuk rekap dan statistik hourly.

        Mode rinci sengaja TIDAK meminta results/actions. Results harian diambil
        melalui request terpisah tanpa breakdown agar tidak tercampur dengan
        metric hourly.
        """
        common_fields = [
            "account_currency",
            "campaign_id",
            "campaign_name",
            "adset_id",
            "adset_name",
            "ad_id",
            "ad_name",
            "date_start",
            "date_stop",
            "impressions",
            "frequency",
            "inline_link_clicks",
            "inline_link_click_ctr",
            "cost_per_inline_link_click",
            "spend",
            "objective",
            "optimization_goal",
        ]

        if mode == "rekap":
            common_fields.extend([
                "reach",
                "actions",
                "cost_per_action_type",
            ])
            optional_groups = [
                [
                    "attribution_setting",
                    "adset_start",
                    "adset_end",
                    "results",
                    "cost_per_result",
                    "objective_results",
                    "cost_per_objective_result",
                ],
                [
                    "attribution_setting",
                    "adset_start",
                    "adset_end",
                    "results",
                    "cost_per_result",
                ],
                ["attribution_setting", "adset_start", "adset_end"],
                ["attribution_setting"],
                [],
            ]
        else:
            # Hourly hanya untuk delivery/spend. Jangan gunakan result hourly
            # sebagai sumber kolom Hasil.
            optional_groups = [
                ["attribution_setting", "adset_start", "adset_end"],
                ["attribution_setting"],
                [],
            ]

        return [common_fields + group for group in optional_groups]

    @staticmethod
    def daily_result_field_attempts() -> List[List[str]]:
        """Field untuk Results harian tanpa breakdown jam.

        ``results`` wajib tetap ada pada setiap fallback. Jika Meta tidak dapat
        mengembalikan field itu, program tidak diam-diam menggantinya dengan
        ``actions``.
        """
        common_fields = [
            "campaign_id",
            "campaign_name",
            "adset_id",
            "adset_name",
            "ad_id",
            "ad_name",
            "date_start",
            "date_stop",
            "spend",
            "objective",
            "optimization_goal",
        ]
        optional_groups = [
            ["attribution_setting", "results", "cost_per_result"],
            ["results", "cost_per_result"],
            ["results"],
        ]
        return [common_fields + group for group in optional_groups]

    @staticmethod
    def _split_date_range(
        since: str,
        until: str,
        chunk_days: int,
    ) -> List[Tuple[str, str]]:
        """Pecah rentang inklusif menjadi beberapa rentang kecil."""
        start_date = datetime.strptime(since, "%Y-%m-%d").date()
        end_date = datetime.strptime(until, "%Y-%m-%d").date()
        if start_date > end_date:
            raise ValueError("Tanggal since tidak boleh melebihi until.")

        size = max(1, int(chunk_days))
        chunks: List[Tuple[str, str]] = []
        cursor = start_date
        while cursor <= end_date:
            chunk_end = min(end_date, cursor + timedelta(days=size - 1))
            chunks.append((cursor.isoformat(), chunk_end.isoformat()))
            cursor = chunk_end + timedelta(days=1)
        return chunks

    @staticmethod
    def _insight_params(
        mode: str,
        since: str,
        until: str,
        fields: List[str],
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "level": "ad",
            "time_range": json.dumps({"since": since, "until": until}),
            "use_unified_attribution_setting": "true",
            "fields": ",".join(fields),
            "limit": "500",
        }
        if mode == "rinci":
            params["time_increment"] = "1"
            params["breakdowns"] = (
                "hourly_stats_aggregated_by_advertiser_time_zone"
            )
        return params

    @staticmethod
    def _daily_result_params(
        since: str,
        until: str,
        fields: List[str],
    ) -> Dict[str, Any]:
        """Params Results harian: time_increment=1, TANPA hourly breakdown."""
        return {
            "level": "ad",
            "time_range": json.dumps({"since": since, "until": until}),
            "time_increment": "1",
            "use_unified_attribution_setting": "true",
            "fields": ",".join(fields),
            "limit": "500",
        }

    def fetch_daily_result_insights(
        self,
        account_id: str,
        since: str,
        until: str,
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Ambil ``results`` harian tanpa breakdown jam.

        Rentang tetap dipecah per hari agar request ringan dan agar setiap row
        dapat dipetakan tepat dengan key (ad_id, date_start).
        """
        url = "{}/{}/insights".format(self.base_url, self.account_node(account_id))
        attempts = self.daily_result_field_attempts()
        date_ranges = self._split_date_range(since, until, chunk_days=1)
        last_error: Optional[MetaApiError] = None

        if len(date_ranges) > 1:
            info(
                "Results harian dipecah menjadi {} request tanpa breakdown jam.".format(
                    len(date_ranges)
                )
            )

        for attempt_number, fields in enumerate(attempts, start=1):
            rows: List[Dict[str, Any]] = []
            try:
                for chunk_number, (chunk_since, chunk_until) in enumerate(
                    date_ranges,
                    start=1,
                ):
                    prefix = "Results harian"
                    if len(date_ranges) > 1:
                        prefix = "Results harian {}/{} [{}]".format(
                            chunk_number,
                            len(date_ranges),
                            chunk_since,
                        )
                    rows.extend(
                        self.fetch_paginated_data(
                            url,
                            self._daily_result_params(
                                since=chunk_since,
                                until=chunk_until,
                                fields=fields,
                            ),
                            prefix,
                        )
                    )

                if attempt_number > 1:
                    info(
                        "Results harian berhasil dengan fallback field tingkat {}.".format(
                            attempt_number
                        )
                    )
                return rows, fields
            except MetaApiError as exc:
                last_error = exc
                if (
                    (exc.code == 100 or exc.data_too_large)
                    and attempt_number < len(attempts)
                ):
                    warning(
                        "Field Results harian tingkat {} ditolak; mencoba field "
                        "yang lebih ringan. Detail: {}".format(attempt_number, exc)
                    )
                    continue
                raise

        if last_error is not None:
            raise last_error
        raise MetaApiError("Gagal mengambil Results harian tanpa detail error.")

    def fetch_all_insights(
        self,
        account_id: str,
        mode: str,
        since: str,
        until: str,
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Ambil Insights dengan pemecahan harian untuk mode rinci.

        Breakdown jam pada level iklan dapat menghasilkan jumlah baris sangat besar.
        Karena itu mode rinci selalu dipecah per hari. Jika Meta masih menolak
        ukuran data, percobaan berikutnya otomatis memakai field yang lebih ringan.
        """
        url = "{}/{}/insights".format(self.base_url, self.account_node(account_id))
        attempts = self.insight_field_attempts(mode)
        last_error: Optional[MetaApiError] = None

        date_ranges = [(since, until)]
        if mode == "rinci":
            date_ranges = self._split_date_range(since, until, chunk_days=1)
            if len(date_ranges) > 1:
                info(
                    "Insights rinci dipecah menjadi {} request harian agar data "
                    "tidak terlalu besar.".format(len(date_ranges))
                )

        for attempt_number, fields in enumerate(attempts, start=1):
            rows: List[Dict[str, Any]] = []
            try:
                for chunk_number, (chunk_since, chunk_until) in enumerate(
                    date_ranges,
                    start=1,
                ):
                    prefix = "Insights"
                    if len(date_ranges) > 1:
                        prefix = "Insights {}/{} [{}]".format(
                            chunk_number,
                            len(date_ranges),
                            chunk_since,
                        )
                    rows.extend(
                        self.fetch_paginated_data(
                            url,
                            self._insight_params(
                                mode=mode,
                                since=chunk_since,
                                until=chunk_until,
                                fields=fields,
                            ),
                            prefix,
                        )
                    )

                if attempt_number > 1:
                    info(
                        "Insights berhasil dengan fallback field tingkat {}.".format(
                            attempt_number
                        )
                    )
                return rows, fields
            except MetaApiError as exc:
                last_error = exc
                if exc.code == 100 and attempt_number < len(attempts):
                    warning(
                        "Field Insights tingkat {} ditolak; mencoba fallback. "
                        "Detail: {}".format(attempt_number, exc)
                    )
                    continue

                if exc.data_too_large and attempt_number < len(attempts):
                    warning(
                        "Meta masih menilai data terlalu besar pada field tingkat {}. "
                        "Mencoba kumpulan field yang lebih ringan.".format(
                            attempt_number
                        )
                    )
                    continue

                if exc.data_too_large:
                    raise MetaApiError(
                        "Meta menolak query karena data masih terlalu besar, bahkan "
                        "setelah mode rinci dipecah per hari dan field dikurangi. "
                        "Coba rentang tanggal yang lebih pendek atau proses akun "
                        "tersebut secara terpisah. Detail asli: {}".format(exc),
                        http_status=exc.http_status,
                        code=exc.code,
                        subcode=exc.subcode,
                        error_type=exc.error_type,
                        trace_id=exc.trace_id,
                        retryable=False,
                        data_too_large=True,
                    ) from exc
                raise

        if last_error is not None:
            raise last_error
        raise MetaApiError("Gagal mengambil Insights tanpa detail error.")
