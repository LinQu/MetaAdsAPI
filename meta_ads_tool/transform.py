"""Flatten Meta API data into report rows."""

import re
from typing import Any, Dict, List, Optional, Tuple

from .metrics import (
    choose_primary_result,
    cost_per_link_click,
    link_ctr_percent,
    safe_float,
)


def format_attribution_spec(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    parts: List[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        event_type = str(item.get("event_type", "")).strip()
        window_days = item.get("window_days")
        if event_type and window_days not in (None, ""):
            parts.append("{}d_{}".format(window_days, event_type.lower()))
        elif event_type:
            parts.append(event_type.lower())
    return ", ".join(parts)


def extract_creative(ad: Dict[str, Any]) -> Dict[str, Any]:
    creative = ad.get("creative")
    if isinstance(creative, dict):
        return creative
    return {}


def choose_image_url(creative: Dict[str, Any]) -> str:
    image_url = creative.get("image_url")
    thumbnail_url = creative.get("thumbnail_url")
    if isinstance(image_url, str) and image_url.startswith(("http://", "https://")):
        return image_url
    if isinstance(thumbnail_url, str) and thumbnail_url.startswith(("http://", "https://")):
        return thumbnail_url
    return ""


def normalize_ad_name(value: Any) -> str:
    """Extract quoted text from Meta-generated names such as Postingan: "...".

    Values that do not match the expected Postingan prefix are returned unchanged.
    Straight and typographic double quotation marks are supported.
    """
    if value is None:
        return ""

    text = str(value).strip()
    if not text:
        return ""

    patterns = (
        r'^\s*Postingan\s*:\s*"(?P<content>.*)"\s*$',
        r'^\s*Postingan\s*:\s*“(?P<content>.*)”\s*$',
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return match.group("content").strip()

    return text


def parse_hour_bucket(value: Any) -> Tuple[str, Optional[int]]:
    """Return normalized text bucket and numeric start hour."""
    if value is None:
        return "", None
    text = str(value).strip()
    if not text:
        return "", None

    match = re.fullmatch(
        r"\s*(\d{1,2}):(\d{2})(?::\d{2})?\s*-\s*"
        r"(\d{1,2}):(\d{2})(?::\d{2})?\s*",
        text,
    )
    if not match:
        return text, None

    start_hour, start_minute, end_hour, end_minute = (
        int(part) for part in match.groups()
    )
    if (
        not 0 <= start_hour <= 23
        or not 0 <= end_hour <= 23
        or not 0 <= start_minute <= 59
        or not 0 <= end_minute <= 59
    ):
        return text, None

    normalized = "{:02d}:{:02d} - {:02d}:{:02d}".format(
        start_hour,
        start_minute,
        end_hour,
        end_minute,
    )
    return normalized, start_hour


def time_category(start_hour: Optional[int]) -> str:
    if start_hour is None:
        return ""
    if 0 <= start_hour <= 4:
        return "Dini hari"
    if 5 <= start_hour <= 10:
        return "Pagi"
    if 11 <= start_hour <= 14:
        return "Siang"
    if 15 <= start_hour <= 17:
        return "Sore"
    if 18 <= start_hour <= 23:
        return "Malam"
    return ""


def flatten_rekap_row(
    account_info: Dict[str, Any],
    source_account_id: str,
    cabang: str,
    bisnis: str,
    ad: Dict[str, Any],
    insight: Dict[str, Any],
    campaign: Dict[str, Any],
    adset: Dict[str, Any],
    image_url: str,
    since: str,
    until: str,
) -> Dict[str, Any]:
    result_value, cost_value = choose_primary_result(insight)
    if insight.get("_summed_result") not in (None, ""):
        result_value = str(insight.get("_summed_result"))
        spend = safe_float(insight.get("spend"))
        result_number = safe_float(result_value)
        cost_value = str(spend / result_number) if result_number > 0 else ""

    attribution = insight.get("attribution_setting") or format_attribution_spec(
        adset.get("attribution_spec")
    )
    return {
        "ID ACCOUNT": source_account_id,
        "Nama akun": account_info.get("name", ""),
        "ID kampanye": ad.get("campaign_id", ""),
        "Nama kampanye": insight.get("campaign_name") or campaign.get("name", ""),
        "Tujuan kampanye": insight.get("objective") or campaign.get("objective", ""),
        "ID set iklan": ad.get("adset_id", ""),
        "Nama set iklan": insight.get("adset_name") or adset.get("name", ""),
        "Optimasi": insight.get("optimization_goal") or adset.get("optimization_goal", ""),
        "ID iklan": ad.get("id", ""),
        "Nama iklan": normalize_ad_name(ad.get("name", "")),
        "Status efektif": ad.get("effective_status", ""),
        "Status konfigurasi": ad.get("configured_status", ""),
        "Gambar iklan": "",
        "URL gambar": image_url,
        "Pengaturan atribusi": attribution,
        "Mulai": insight.get("adset_start") or adset.get("start_time", ""),
        "Berakhir": insight.get("adset_end") or adset.get("end_time", ""),
        "Impresi": insight.get("impressions", "0"),
        "Jangkauan": insight.get("reach", "0"),
        "Frekuensi": insight.get("frequency", "0"),
        "Klik tautan": insight.get("inline_link_clicks", "0"),
        "CTR klik tautan": link_ctr_percent(insight),
        "Biaya per klik tautan": cost_per_link_click(insight),
        "Hasil": result_value,
        "Biaya per hasil": cost_value,
        "Jumlah yang dibelanjakan": insight.get("spend", "0"),
        "Mata uang": account_info.get("currency", ""),
        "Awal pelaporan": since,
        "Akhir pelaporan": until,
        "CABANG": cabang,
        "BISNIS": bisnis,
    }


def flatten_rinci_row(
    account_info: Dict[str, Any],
    source_account_id: str,
    cabang: str,
    bisnis: str,
    row: Dict[str, Any],
    adset_map: Dict[str, Dict[str, Any]],
    since: str,
    until: str,
    daily_result: Optional[Dict[str, str]] = None,
    include_daily_result: bool = False,
) -> Dict[str, Any]:
    # Mode rinci tidak lagi mengambil Hasil dari row hourly. Hasil resmi diambil
    # dari query harian tanpa breakdown dan hanya ditulis sekali per ad+tanggal.
    daily_result = daily_result or {}
    result_value = (
        str(daily_result.get("result_value", ""))
        if include_daily_result
        else ""
    )
    cost_value = (
        str(daily_result.get("cost_value", ""))
        if include_daily_result
        else ""
    )
    adset_id = str(row.get("adset_id", "")).strip()
    adset = adset_map.get(adset_id, {})
    attribution = row.get("attribution_setting") or format_attribution_spec(
        adset.get("attribution_spec")
    )
    hour_text, start_hour = parse_hour_bucket(
        row.get("hourly_stats_aggregated_by_advertiser_time_zone", "")
    )
    return {
        "ID ACCOUNT": source_account_id,
        "Nama akun": account_info.get("name", ""),
        "ID kampanye": str(row.get("campaign_id", "")),
        "Nama kampanye": row.get("campaign_name", ""),
        "ID set iklan": str(row.get("adset_id", "")),
        "Nama set iklan": row.get("adset_name", ""),
        "ID iklan": str(row.get("ad_id", "")),
        "Nama iklan": normalize_ad_name(row.get("ad_name", "")),
        "Tanggal": row.get("date_start", ""),
        "Waktu (zona waktu akun iklan)": hour_text,
        "Jam mulai": start_hour,
        "Kategori waktu": time_category(start_hour),
        "Pengaturan atribusi": attribution,
        "Mulai": row.get("adset_start") or adset.get("start_time", ""),
        "Berakhir": row.get("adset_end") or adset.get("end_time", ""),
        "Impresi": row.get("impressions", "0"),
        "Klik tautan": row.get("inline_link_clicks", "0"),
        "CTR klik tautan": link_ctr_percent(row),
        "Biaya per klik tautan": cost_per_link_click(row),
        "Hasil": result_value,
        "Biaya per hasil": cost_value,
        "Jumlah yang dibelanjakan": row.get("spend", "0"),
        "Mata uang": account_info.get("currency", ""),
        "Awal pelaporan": since,
        "Akhir pelaporan": until,
        "CABANG": cabang,
        "BISNIS": bisnis,
    }
