"""Meta Insights metric selection and numeric helpers."""

from typing import Any, Dict, Iterable, List, Tuple


def safe_float(value: Any, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def extract_metric_map(items: Any) -> Dict[str, str]:
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
    for metric_type, metric_value in metric_map.items():
        if metric_value not in (None, ""):
            return metric_type, str(metric_value)
    return "", ""


def _find_metric(
    metric_map: Dict[str, str],
    candidate_types: List[str],
) -> Tuple[str, str]:
    lowered = {
        str(metric_type).lower(): (str(metric_type), str(metric_value))
        for metric_type, metric_value in metric_map.items()
    }
    for candidate in candidate_types:
        exact = lowered.get(candidate.lower())
        if exact is not None:
            return exact
    for candidate in candidate_types:
        candidate_lower = candidate.lower()
        for metric_type, metric_value in metric_map.items():
            metric_lower = str(metric_type).lower()
            if metric_lower.endswith(candidate_lower):
                return str(metric_type), str(metric_value)
    return "", ""


def preferred_action_types(row: Dict[str, Any]) -> List[str]:
    objective = str(row.get("objective", "")).upper()
    optimization = str(row.get("optimization_goal", "")).upper()
    context = "{} {}".format(objective, optimization)
    candidates: List[str] = []

    if "LEAD" in context:
        candidates.extend([
            "lead",
            "onsite_conversion.lead_grouped",
            "offsite_conversion.fb_pixel_lead",
        ])
    if "MESSAG" in context or "CONVERSATION" in context:
        candidates.extend([
            "onsite_conversion.messaging_conversation_started_7d",
            "onsite_conversion.messaging_first_reply",
            "messaging_conversation_started_7d",
        ])
    if "PURCHASE" in context or "SALES" in context or "CONVERSION" in context:
        candidates.extend([
            "omni_purchase",
            "purchase",
            "offsite_conversion.fb_pixel_purchase",
        ])
    if "APP_INSTALL" in context:
        candidates.extend(["mobile_app_install", "app_install"])
    if "LANDING_PAGE" in context:
        candidates.append("landing_page_view")
    if "LINK_CLICK" in context or "TRAFFIC" in context:
        candidates.extend(["link_click", "landing_page_view"])
    if "THRUPLAY" in context or "VIDEO" in context:
        candidates.extend(["video_thruplay_watched_actions", "video_view"])
    if "ENGAGEMENT" in context:
        candidates.extend(["post_engagement", "page_engagement"])

    candidates.extend([
        "lead",
        "onsite_conversion.messaging_conversation_started_7d",
        "omni_purchase",
        "purchase",
        "offsite_conversion.fb_pixel_purchase",
        "mobile_app_install",
        "landing_page_view",
        "link_click",
        "post_engagement",
        "video_thruplay_watched_actions",
    ])

    unique_candidates: List[str] = []
    seen = set()
    for candidate in candidates:
        key = candidate.lower()
        if key not in seen:
            seen.add(key)
            unique_candidates.append(candidate)
    return unique_candidates


def choose_primary_result(row: Dict[str, Any]) -> Tuple[str, str]:
    result_sources = [
        (
            extract_metric_map(row.get("results")),
            extract_metric_map(row.get("cost_per_result")),
        ),
        (
            extract_metric_map(row.get("objective_results")),
            extract_metric_map(row.get("cost_per_objective_result")),
        ),
    ]
    for result_map, cost_map in result_sources:
        if not result_map:
            continue
        metric_type, result_value = _first_metric_pair(result_map)
        cost_value = cost_map.get(metric_type, "")
        if not cost_value and len(cost_map) == 1:
            cost_value = next(iter(cost_map.values()))
        return result_value, str(cost_value)

    action_map = extract_metric_map(row.get("actions"))
    cost_action_map = extract_metric_map(row.get("cost_per_action_type"))
    metric_type, result_value = _find_metric(
        action_map,
        preferred_action_types(row),
    )
    if metric_type:
        cost_value = cost_action_map.get(metric_type, "")
        if not cost_value:
            lower_metric = metric_type.lower()
            for cost_type, value in cost_action_map.items():
                if str(cost_type).lower() == lower_metric:
                    cost_value = value
                    break
        return result_value, str(cost_value)
    return "", ""


def link_ctr_percent(row: Dict[str, Any]) -> float:
    raw = row.get("inline_link_click_ctr")
    if raw not in (None, ""):
        return safe_float(raw)
    impressions = safe_float(row.get("impressions"))
    clicks = safe_float(row.get("inline_link_clicks"))
    if impressions <= 0:
        return 0.0
    return clicks / impressions * 100.0


def cost_per_link_click(row: Dict[str, Any]) -> float:
    raw = row.get("cost_per_inline_link_click")
    if raw not in (None, ""):
        return safe_float(raw)
    clicks = safe_float(row.get("inline_link_clicks"))
    spend = safe_float(row.get("spend"))
    if clicks <= 0:
        return 0.0
    return spend / clicks


def build_insight_map(rows: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    output: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        ad_id = str(row.get("ad_id", "")).strip()
        if not ad_id:
            continue
        if ad_id not in output:
            output[ad_id] = dict(row)
            continue

        existing = output[ad_id]
        for field in ("impressions", "inline_link_clicks", "spend"):
            existing[field] = str(
                safe_float(existing.get(field)) + safe_float(row.get(field))
            )
        result_a, _ = choose_primary_result(existing)
        result_b, _ = choose_primary_result(row)
        if result_a or result_b:
            existing["_summed_result"] = str(
                safe_float(result_a) + safe_float(result_b)
            )
        existing["inline_link_click_ctr"] = str(link_ctr_percent(existing))
        existing["cost_per_inline_link_click"] = str(cost_per_link_click(existing))
    return output
