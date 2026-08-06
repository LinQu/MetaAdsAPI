"""Account processing orchestration."""

from dataclasses import dataclass
from typing import Any, Callable, Dict, List

from .api import MetaAdsClient, MetaApiError
from .checkpoint import CheckpointStore
from .logging_utils import error, info
from .metrics import build_insight_map
from .transform import (
    choose_image_url,
    extract_creative,
    flatten_rekap_row,
    flatten_rinci_row,
)


@dataclass
class RunResult:
    rows: List[Dict[str, Any]]
    errors: List[Dict[str, Any]]
    total_accounts: int
    skipped_accounts: int


def process_rekap_account(
    client: MetaAdsClient,
    account_id: str,
    cabang: str,
    bisnis: str,
    account_info: Dict[str, Any],
    since: str,
    until: str,
    status_filter: str,
) -> List[Dict[str, Any]]:
    campaigns = client.fetch_campaigns(account_id)
    adsets = client.fetch_adsets(account_id)
    selected_ads = client.fetch_ads(account_id, status_filter)
    insight_rows, _ = client.fetch_all_insights(account_id, "rekap", since, until)
    insight_map = build_insight_map(insight_rows)

    creative_cache: Dict[str, Dict[str, Any]] = {}
    output: List[Dict[str, Any]] = []
    for ad in selected_ads:
        ad_id = str(ad.get("id", "")).strip()
        campaign_id = str(ad.get("campaign_id", "")).strip()
        adset_id = str(ad.get("adset_id", "")).strip()
        creative = extract_creative(ad)
        image_url = choose_image_url(creative)
        creative_id = str(creative.get("id", "")).strip()

        if not image_url and creative_id:
            if creative_id not in creative_cache:
                creative_cache[creative_id] = client.fetch_creative_metadata(creative_id)
            creative = creative_cache[creative_id]
            image_url = choose_image_url(creative)

        output.append(
            flatten_rekap_row(
                account_info=account_info,
                source_account_id=account_id,
                cabang=cabang,
                bisnis=bisnis,
                ad=ad,
                insight=insight_map.get(ad_id, {}),
                campaign=campaigns.get(campaign_id, {}),
                adset=adsets.get(adset_id, {}),
                image_url=image_url,
                since=since,
                until=until,
            )
        )
    return output


def process_rinci_account(
    client: MetaAdsClient,
    account_id: str,
    cabang: str,
    bisnis: str,
    account_info: Dict[str, Any],
    since: str,
    until: str,
    status_filter: str,
) -> List[Dict[str, Any]]:
    adsets = client.fetch_adsets(account_id)
    insight_rows, _ = client.fetch_all_insights(account_id, "rinci", since, until)

    if status_filter != "semua":
        selected_ads = client.fetch_ads(account_id, status_filter)
        allowed_ad_ids = {
            str(ad.get("id", "")).strip()
            for ad in selected_ads
            if ad.get("id") not in (None, "")
        }
        insight_rows = [
            row for row in insight_rows
            if str(row.get("ad_id", "")).strip() in allowed_ad_ids
        ]

    return [
        flatten_rinci_row(
            account_info=account_info,
            source_account_id=account_id,
            cabang=cabang,
            bisnis=bisnis,
            row=row,
            adset_map=adsets,
            since=since,
            until=until,
        )
        for row in insight_rows
    ]


def run_accounts(
    accounts: List[Dict[str, str]],
    mode: str,
    status_filter: str,
    since: str,
    until: str,
    checkpoint: CheckpointStore,
    api_version: str,
    max_retries: int,
    retry_base_delay: float,
    retry_max_delay: float,
    client_factory: Callable[..., MetaAdsClient] = MetaAdsClient,
) -> RunResult:
    """Process accounts using the token stored on each Excel row.

    Tokens are passed directly to the API client and are never written to logs,
    report rows, error rows, or the checkpoint database.
    """
    completed = checkpoint.completed_accounts()
    total_accounts = len(accounts)
    skipped_accounts = 0

    if completed:
        info(
            "Checkpoint memuat {} akun yang sudah selesai.".format(
                len(completed)
            )
        )

    for index, account_source in enumerate(accounts, start=1):
        account_id = account_source["account_id"]
        access_token = account_source["access_token"]
        cabang = account_source["cabang"]
        bisnis = account_source["bisnis"]

        if account_id in completed:
            skipped_accounts += 1
            info(
                "[{}/{}] ID {} dilewati karena sudah selesai di checkpoint.".format(
                    index,
                    total_accounts,
                    account_id,
                )
            )
            continue

        info(
            "[{}/{}] Mode {} | Status {} | ID {} | CABANG {} | BISNIS {}".format(
                index,
                total_accounts,
                mode,
                status_filter,
                account_id,
                cabang,
                bisnis,
            )
        )

        account_rows: List[Dict[str, Any]] = []
        account_errors: List[Dict[str, Any]] = []
        try:
            client = client_factory(
                api_version=api_version,
                access_token=access_token,
                max_retries=max_retries,
                retry_base_delay=retry_base_delay,
                retry_max_delay=retry_max_delay,
            )
            account_info = client.get_account_information(account_id)
            info(
                "Akun: {} | Mata uang: {} | Zona waktu: {}".format(
                    account_info.get("name", ""),
                    account_info.get("currency", ""),
                    account_info.get("timezone_name", ""),
                )
            )
            if mode == "rekap":
                account_rows = process_rekap_account(
                    client=client,
                    account_id=account_id,
                    cabang=cabang,
                    bisnis=bisnis,
                    account_info=account_info,
                    since=since,
                    until=until,
                    status_filter=status_filter,
                )
            else:
                account_rows = process_rinci_account(
                    client=client,
                    account_id=account_id,
                    cabang=cabang,
                    bisnis=bisnis,
                    account_info=account_info,
                    since=since,
                    until=until,
                    status_filter=status_filter,
                )

            checkpoint.save_account_result(
                account_id=account_id,
                cabang=cabang,
                bisnis=bisnis,
                rows=account_rows,
                errors=[],
                status="completed",
            )
            completed.add(account_id)
            info(
                "Selesai akun {}: {} baris output; checkpoint disimpan.".format(
                    account_id,
                    len(account_rows),
                )
            )
        except (MetaApiError, ValueError, RuntimeError) as exc:
            account_errors.append({
                "ID ACCOUNT": account_id,
                "CABANG": cabang,
                "BISNIS": bisnis,
                "ID iklan": "",
                "Tahap": "Meta API",
                "Error": str(exc),
            })
            checkpoint.save_account_result(
                account_id=account_id,
                cabang=cabang,
                bisnis=bisnis,
                rows=[],
                errors=account_errors,
                status="failed",
            )
            error("Gagal akun {}: {}".format(account_id, exc))
            continue

    return RunResult(
        rows=checkpoint.load_rows(),
        errors=checkpoint.load_errors(),
        total_accounts=total_accounts,
        skipped_accounts=skipped_accounts,
    )
