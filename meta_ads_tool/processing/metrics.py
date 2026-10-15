"""Meta Insights metric selection and numeric helpers.

Tujuan modul ini:
- mengubah metric array dari Meta Insights menjadi dictionary;
- menentukan metric utama untuk kolom Hasil;
- menentukan Biaya per hasil yang sesuai dengan metric Hasil;
- menghitung CTR klik tautan dan biaya per klik tautan;
- menggabungkan Insight rekap per ad_id.

Aturan kolom Hasil (sejak 5.5.1):
Kolom Hasil diambil dari field ``results`` dengan urutan prioritas tetap --
indicator conversation lebih dulu, lalu indicator lead. Meta hanya mengembalikan
indikator yang sesuai dengan performance goal iklan, sehingga satu baris lazimnya
hanya memuat satu jenis. Kedua keluarga angka TIDAK dijumlahkan: bila tidak ada
satu pun indikator yang dikenali, Hasil dan Biaya per hasil dikosongkan.
"""

from typing import Any, Dict, Iterable, Tuple

# Indicator utama conversation; dipertahankan sebagai nama konstanta karena
# dipakai harness golden dan jadi acuan rekam.
TARGET_RESULT_INDICATOR = (
    "actions:onsite_conversion.messaging_conversation_started_7d"
)

# Urutan pembacaan: conversation dulu, baru lead.
CONVERSATION_INDICATORS = (
    "onsite_conversion.messaging_conversation_started_7d",
    "messaging_conversation_started_7d",
    "onsite_conversion.messaging_first_reply",
)

LEAD_INDICATORS = (
    "onsite_conversion.lead_grouped",
    "lead",
    "offsite_conversion.fb_pixel_lead",
    "onsite_conversion.lead",
)

# Meta dapat mengembalikan indikator dengan atau tanpa awalan "actions:".
# Perbandingan dinormalisasi lewat canonical_indicator() sehingga urutan
# prioritas benar-benar conversation-dulu, terlepas dari prefix maupun urutan
# kemunculan di payload.
RESULT_INDICATOR_PRIORITY = CONVERSATION_INDICATORS + LEAD_INDICATORS

INDICATOR_PREFIX = "actions:"


def canonical_indicator(name: Any) -> str:
    """Bentuk kanonik indikator: lowercase tanpa awalan ``actions:``."""
    text = str(name or "").strip().lower()

    if text.startswith(INDICATOR_PREFIX):
        text = text[len(INDICATOR_PREFIX):]

    return text


def safe_float(value: Any, default: float = 0.0) -> float:
    """Konversi nilai Meta menjadi float dengan fallback aman."""
    if value in (None, ""):
        return default

    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def extract_metric_map(items: Any) -> Dict[str, str]:
    """Ubah array metric Meta menjadi mapping {metric_type: value}.

    Mendukung bentuk seperti::

        [
            {"action_type": "link_click", "value": "10"},
            {"action_type": "lead", "value": "2"},
        ]

    dan struktur nested ``values`` apabila Meta mengembalikannya.
    """
    output: Dict[str, str] = {}

    if not isinstance(items, list):
        return output

    for item in items:
        if not isinstance(item, dict):
            continue

        metric_type = (
            item.get("indicator")
            or item.get("action_type")
            or item.get("type")
            or item.get("name")
        )

        direct_value = item.get("value")

        if metric_type is not None and direct_value is not None:
            output[str(metric_type)] = str(direct_value)
            continue

        nested_values = item.get("values")

        if not isinstance(nested_values, list):
            continue

        for nested in nested_values:
            if not isinstance(nested, dict):
                continue

            nested_type = (
                nested.get("indicator")
                or nested.get("action_type")
                or nested.get("type")
                or nested.get("name")
                or metric_type
            )

            nested_value = nested.get("value")

            if nested_type is not None and nested_value is not None:
                output[str(nested_type)] = str(nested_value)

    return output


def select_result_by_priority(
    row: Dict[str, Any],
) -> Tuple[str, str, str]:
    """Pilih Hasil dan Biaya per hasil dari indikator conversation lalu lead.

    Urutan prioritas tidak bergantung pada optimization_goal. Yang dibaca hanya
    isi ``results`` yang dikembalikan Meta:

    1. indikator conversation (dulu satu-satunya sumber);
    2. bila tidak ada, indikator lead;
    3. bila keduanya tidak ada, Hasil dan Biaya per hasil dikosongkan.

    Goal lain (purchase, traffic, engagement, app install) sengaja tidak
    dihitung pada versi ini dan tetap menghasilkan kolom kosong.

    ``cost_per_result`` dibaca untuk indikator yang terpilih. Bila Meta tidak
    menyediakannya, nilai dihitung dari spend/hasil pada baris yang sama. Nilai
    dari indikator lain tidak pernah dipakai.

    Returns:
        tuple(metric_type, result_value, cost_value)
    """
    result_map = extract_metric_map(row.get("results"))
    cost_map = extract_metric_map(row.get("cost_per_result"))

    # Kunci dinormalisasi tanpa awalan "actions:" supaya conversation selalu
    # menang atas lead, apa pun prefix dan urutan payload.
    results_by_indicator = {}
    for metric_type, metric_value in result_map.items():
        results_by_indicator.setdefault(canonical_indicator(metric_type), (metric_type, metric_value))

    costs_by_indicator = {}
    for metric_type, metric_value in cost_map.items():
        costs_by_indicator.setdefault(canonical_indicator(metric_type), metric_value)

    for indicator in RESULT_INDICATOR_PRIORITY:
        found = results_by_indicator.get(indicator)

        if found is None:
            continue

        metric_type, result_value = found

        if result_value in (None, ""):
            continue

        cost_value = costs_by_indicator.get(indicator, "")

        if not cost_value:
            result_number = safe_float(result_value)
            spend = safe_float(row.get("spend"))
            if result_number > 0 and spend > 0:
                cost_value = str(spend / result_number)

        return (
            str(metric_type),
            str(result_value),
            str(cost_value),
        )

    return "", "", ""


def choose_primary_result_detail(
    row: Dict[str, Any],
) -> Tuple[str, str, str]:
    """Hasil mode rekap: conversation dulu, lalu lead.

    Returns:
        tuple(metric_type, result_value, cost_value)
    """
    return select_result_by_priority(row)


def choose_primary_result(row: Dict[str, Any]) -> Tuple[str, str]:
    """``choose_primary_result_detail`` tanpa ``metric_type``.

    Returns:
        tuple(result_value, cost_value)
    """
    _, result_value, cost_value = choose_primary_result_detail(row)

    return result_value, cost_value


def link_ctr_percent(row: Dict[str, Any]) -> float:
    """CTR klik tautan dalam skala persen, misalnya 3.25 berarti 3.25%."""
    raw = row.get("inline_link_click_ctr")

    if raw not in (None, ""):
        return safe_float(raw)

    impressions = safe_float(row.get("impressions"))
    clicks = safe_float(row.get("inline_link_clicks"))

    if impressions <= 0:
        return 0.0

    return clicks / impressions * 100.0


def cost_per_link_click(row: Dict[str, Any]) -> float:
    """Biaya per klik tautan."""
    raw = row.get("cost_per_inline_link_click")

    if raw not in (None, ""):
        return safe_float(raw)

    clicks = safe_float(row.get("inline_link_clicks"))
    spend = safe_float(row.get("spend"))

    if clicks <= 0:
        return 0.0

    return spend / clicks


def build_insight_map(
    rows: Iterable[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Gabungkan Insight rekap berdasarkan ad_id.

    Biasanya Meta menghasilkan satu row per iklan untuk mode rekap. Jika ada
    lebih dari satu row, metric aditif dijumlahkan sebagai fallback.
    """
    output: Dict[str, Dict[str, Any]] = {}

    for row in rows:
        ad_id = str(row.get("ad_id", "")).strip()

        if not ad_id:
            continue

        if ad_id not in output:
            output[ad_id] = dict(row)
            continue

        existing = output[ad_id]

        # Metric yang aman untuk dijumlahkan.
        for field in (
            "impressions",
            "inline_link_clicks",
            "spend",
        ):
            existing[field] = str(
                safe_float(existing.get(field))
                + safe_float(row.get(field))
            )

        _, result_a, _ = choose_primary_result_detail(existing)
        _, result_b, _ = choose_primary_result_detail(row)

        if result_a or result_b:
            existing["_summed_result"] = str(
                safe_float(result_a)
                + safe_float(result_b)
            )

        existing["inline_link_click_ctr"] = str(
            link_ctr_percent(existing)
        )

        existing["cost_per_inline_link_click"] = str(
            cost_per_link_click(existing)
        )

    return output


def choose_daily_result_detail(
    row: Dict[str, Any],
) -> Tuple[str, str, str]:
    """Hasil harian: conversation dulu, lalu lead.

    Aturan prioritas identik dengan mode rekap dan dihitung dari row harian
    tanpa breakdown jam. Baris harian ditulis satu kali per ad+tanggal.

    Returns:
        tuple(metric_type, result_value, cost_value)
    """
    return select_result_by_priority(row)

def daily_frequency_value(row: Dict[str, Any]) -> str:
    """Ambil frequency harian tanpa breakdown.

    Meta dapat tidak mengembalikan ``frequency`` pada query dengan breakdown
    hourly. Karena itu mode rinci mengambil frequency dari query harian tanpa
    breakdown. Jika field ``frequency`` tidak tersedia tetapi ``impressions``
    dan ``reach`` tersedia, hitung fallback ``impressions / reach``.
    """
    raw = row.get("frequency")
    if raw not in (None, ""):
        return str(raw)

    impressions = safe_float(row.get("impressions"))
    reach = safe_float(row.get("reach"))
    if impressions > 0 and reach > 0:
        return str(impressions / reach)

    return ""


def build_daily_result_map(
    rows: Iterable[Dict[str, Any]],
) -> Dict[Tuple[str, str], Dict[str, str]]:
    """Buat map metric harian dengan key ``(ad_id, date_start)``.

    Selain Results harian, map ini menyimpan ``frequency`` harian agar mode
    rinci tidak bergantung pada field frequency dari breakdown per jam.
    """
    output: Dict[Tuple[str, str], Dict[str, str]] = {}

    for row in rows:
        ad_id = str(row.get("ad_id", "")).strip()
        date_start = str(row.get("date_start", "")).strip()
        if not ad_id or not date_start:
            continue

        metric_type, result_value, cost_value = choose_daily_result_detail(row)
        output[(ad_id, date_start)] = {
            "metric_type": metric_type,
            "result_value": result_value,
            "cost_value": cost_value,
            "frequency": daily_frequency_value(row),
        }

    return output
