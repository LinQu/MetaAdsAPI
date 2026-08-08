"""Meta Insights metric selection and numeric helpers.

Tujuan modul ini:
- mengubah metric array dari Meta Insights menjadi dictionary;
- menentukan metric utama untuk kolom Hasil;
- menentukan Biaya per hasil yang sesuai dengan metric Hasil;
- menghitung CTR klik tautan dan biaya per klik tautan;
- menggabungkan Insight rekap per ad_id.

Catatan penting:
Kolom "Hasil" di Meta Ads Manager bersifat kontekstual. Metric yang ditampilkan
bergantung pada performance goal / optimization goal dan objective iklan.
Karena itu pemilihan action_type di sini memprioritaskan optimization_goal,
kemudian objective, kemudian fallback umum.
"""

from typing import Any, Dict, Iterable, List, Tuple


TARGET_RESULT_INDICATOR = (
    "actions:onsite_conversion.messaging_conversation_started_7d"
)


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


def _first_metric_pair(metric_map: Dict[str, str]) -> Tuple[str, str]:
    """Ambil pasangan metric pertama yang memiliki value."""
    for metric_type, metric_value in metric_map.items():
        if metric_value not in (None, ""):
            return str(metric_type), str(metric_value)

    return "", ""


def _find_metric(
    metric_map: Dict[str, str],
    candidate_types: List[str],
) -> Tuple[str, str]:
    """Cari metric berdasarkan daftar prioritas.

    Tahap pencarian:
    1. exact match case-insensitive;
    2. suffix match untuk variasi prefix dari Meta.
    """
    lowered = {
        str(metric_type).lower(): (
            str(metric_type),
            str(metric_value),
        )
        for metric_type, metric_value in metric_map.items()
    }

    # Exact match lebih aman dan diprioritaskan.
    for candidate in candidate_types:
        exact = lowered.get(candidate.lower())

        if exact is not None:
            return exact

    # Fallback suffix match.
    for candidate in candidate_types:
        candidate_lower = candidate.lower()

        for metric_type, metric_value in metric_map.items():
            metric_lower = str(metric_type).lower()

            if metric_lower.endswith(candidate_lower):
                return str(metric_type), str(metric_value)

    return "", ""


def _find_cost_for_metric(
    cost_map: Dict[str, str],
    metric_type: str,
) -> str:
    """Cari cost metric yang sesuai dengan action/result metric."""
    if not metric_type:
        return ""

    direct = cost_map.get(metric_type)

    if direct not in (None, ""):
        return str(direct)

    target = metric_type.lower()

    # Case-insensitive exact match.
    for cost_type, value in cost_map.items():
        if str(cost_type).lower() == target:
            return str(value)

    # Beberapa respons dapat memakai prefix yang sedikit berbeda.
    for cost_type, value in cost_map.items():
        cost_lower = str(cost_type).lower()

        if cost_lower.endswith(target) or target.endswith(cost_lower):
            return str(value)

    # Jika hanya ada satu cost, masih cukup aman sebagai fallback terakhir.
    if len(cost_map) == 1:
        return str(next(iter(cost_map.values())))

    return ""


def _append_unique(
    output: List[str],
    values: Iterable[str],
) -> None:
    """Tambahkan kandidat tanpa duplikasi, mempertahankan urutan."""
    existing = {item.lower() for item in output}

    for value in values:
        key = value.lower()

        if key in existing:
            continue

        output.append(value)
        existing.add(key)


def preferred_action_types(row: Dict[str, Any]) -> List[str]:
    """Susun kandidat action_type untuk menentukan kolom Hasil.

    Prioritas utama adalah ``optimization_goal`` karena ini lebih dekat dengan
    performance goal yang menentukan arti kolom Results/Hasil di Ads Manager.
    Setelah itu digunakan ``objective`` sebagai fallback konteks.
    """
    objective = str(row.get("objective", "")).strip().upper()
    optimization = str(row.get("optimization_goal", "")).strip().upper()

    candidates: List[str] = []

    # ------------------------------------------------------------------
    # 1. PRIORITAS BERDASARKAN OPTIMIZATION GOAL
    # ------------------------------------------------------------------

    if "CONVERSATION" in optimization or "MESSAG" in optimization:
        _append_unique(
            candidates,
            [
                "onsite_conversion.messaging_conversation_started_7d",
                "messaging_conversation_started_7d",
                "onsite_conversion.messaging_first_reply",
                "onsite_conversion.total_messaging_connection",
            ],
        )

    if "LEAD" in optimization:
        _append_unique(
            candidates,
            [
                "lead",
                "onsite_conversion.lead_grouped",
                "offsite_conversion.fb_pixel_lead",
                "onsite_conversion.lead",
            ],
        )

    if (
        "PURCHASE" in optimization
        or "VALUE" in optimization
        or "CONVERSION" in optimization
    ):
        _append_unique(
            candidates,
            [
                "omni_purchase",
                "purchase",
                "offsite_conversion.fb_pixel_purchase",
            ],
        )

    if "LANDING_PAGE" in optimization:
        _append_unique(
            candidates,
            [
                "landing_page_view",
                "link_click",
            ],
        )

    if "LINK_CLICK" in optimization:
        _append_unique(
            candidates,
            [
                "link_click",
                "landing_page_view",
            ],
        )

    if "APP_INSTALL" in optimization:
        _append_unique(
            candidates,
            [
                "mobile_app_install",
                "app_install",
            ],
        )

    if "THRUPLAY" in optimization:
        _append_unique(
            candidates,
            [
                "video_thruplay_watched_actions",
                "video_view",
            ],
        )

    if "ENGAGEMENT" in optimization or "POST_ENGAGEMENT" in optimization:
        _append_unique(
            candidates,
            [
                "post_engagement",
                "page_engagement",
            ],
        )

    if "REACH" in optimization:
        _append_unique(
            candidates,
            [
                "reach",
            ],
        )

    # ------------------------------------------------------------------
    # 2. FALLBACK BERDASARKAN OBJECTIVE
    # ------------------------------------------------------------------

    if "LEAD" in objective:
        _append_unique(
            candidates,
            [
                "lead",
                "onsite_conversion.lead_grouped",
                "offsite_conversion.fb_pixel_lead",
                "onsite_conversion.lead",
            ],
        )

    if (
        "MESSAG" in objective
        or "CONVERSATION" in objective
        or "ENGAGEMENT" in objective
    ):
        _append_unique(
            candidates,
            [
                "onsite_conversion.messaging_conversation_started_7d",
                "messaging_conversation_started_7d",
                "onsite_conversion.messaging_first_reply",
                "post_engagement",
                "page_engagement",
            ],
        )

    if (
        "PURCHASE" in objective
        or "SALES" in objective
        or "CONVERSION" in objective
    ):
        _append_unique(
            candidates,
            [
                "omni_purchase",
                "purchase",
                "offsite_conversion.fb_pixel_purchase",
            ],
        )

    if "APP" in objective:
        _append_unique(
            candidates,
            [
                "mobile_app_install",
                "app_install",
            ],
        )

    if "TRAFFIC" in objective:
        _append_unique(
            candidates,
            [
                "landing_page_view",
                "link_click",
            ],
        )

    if "VIDEO" in objective:
        _append_unique(
            candidates,
            [
                "video_thruplay_watched_actions",
                "video_view",
            ],
        )

    # ------------------------------------------------------------------
    # 3. FALLBACK UMUM
    # ------------------------------------------------------------------

    _append_unique(
        candidates,
        [
            "onsite_conversion.messaging_conversation_started_7d",
            "messaging_conversation_started_7d",
            "lead",
            "onsite_conversion.lead_grouped",
            "offsite_conversion.fb_pixel_lead",
            "omni_purchase",
            "purchase",
            "offsite_conversion.fb_pixel_purchase",
            "mobile_app_install",
            "app_install",
            "landing_page_view",
            "link_click",
            "post_engagement",
            "page_engagement",
            "video_thruplay_watched_actions",
            "video_view",
        ],
    )

    return candidates


def choose_primary_result_detail(
    row: Dict[str, Any],
) -> Tuple[str, str, str]:
    """Ambil Hasil hanya dari indicator messaging conversation yang ditetapkan.

    Tidak ada fallback ke objective_results, actions, lead, purchase, link_click,
    atau metric lain. Jika indicator target tidak ada pada ``results``, Hasil dan
    Biaya per hasil dikosongkan.

    Returns:
        tuple(metric_type, result_value, cost_value)
    """
    result_map = extract_metric_map(row.get("results"))
    result_value = result_map.get(TARGET_RESULT_INDICATOR, "")

    if result_value in (None, ""):
        return "", "", ""

    cost_map = extract_metric_map(row.get("cost_per_result"))
    cost_value = cost_map.get(TARGET_RESULT_INDICATOR, "")

    # Jika Meta tidak menyediakan cost_per_result untuk indicator yang sama,
    # hitung hanya dari spend/result pada row yang sama. Tidak memakai metric lain.
    if not cost_value:
        result_number = safe_float(result_value)
        spend = safe_float(row.get("spend"))
        if result_number > 0 and spend > 0:
            cost_value = str(spend / result_number)

    return (
        TARGET_RESULT_INDICATOR,
        str(result_value),
        str(cost_value),
    )

def choose_primary_result(row: Dict[str, Any]) -> Tuple[str, str]:
    """Kompatibilitas dengan transform.py yang sudah ada.

    Returns:
        tuple(result_value, cost_value)

    ``metric_type`` sengaja tidak dikembalikan di fungsi ini agar file
    ``transform.py`` versi lama tidak perlu diubah.
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
    """Ambil Results harian hanya dari indicator messaging conversation target.

    Indicator yang diterima harus persis::

        actions:onsite_conversion.messaging_conversation_started_7d

    Jika indicator tersebut tidak ada pada ``results``, fungsi mengembalikan
    nilai kosong. Tidak ada fallback ke indicator atau action lain.

    Returns:
        tuple(metric_type, result_value, cost_value)
    """
    result_map = extract_metric_map(row.get("results"))
    result_value = result_map.get(TARGET_RESULT_INDICATOR, "")

    if result_value in (None, ""):
        return "", "", ""

    cost_map = extract_metric_map(row.get("cost_per_result"))
    cost_value = cost_map.get(TARGET_RESULT_INDICATOR, "")

    # Jika Meta tidak mengembalikan cost_per_result untuk indicator yang sama,
    # hitung dari angka harian yang sama. Tidak memakai hasil dari action lain.
    if not cost_value:
        result_number = safe_float(result_value)
        spend = safe_float(row.get("spend"))
        if result_number > 0 and spend > 0:
            cost_value = str(spend / result_number)

    return (
        TARGET_RESULT_INDICATOR,
        str(result_value),
        str(cost_value),
    )

def build_daily_result_map(
    rows: Iterable[Dict[str, Any]],
) -> Dict[Tuple[str, str], Dict[str, str]]:
    """Buat map Results harian dengan key ``(ad_id, date_start)``."""
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
        }

    return output