"""Read Meta Ads account credentials from the NSS DATAMETA API source.

The source API returns account credentials in ``Detail``. Access tokens are kept
in memory only and are never written to report/checkpoint files. Optional debug
output is sanitized before being printed.
"""

import json
import re
import time
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import parse_qs

import requests

from ..logging_utils import info, warning
from .excel import normalize_account_id, normalize_text, normalize_token

DEFAULT_SOURCE_API_URL = "https://api2nss.nusantara-sakti.co.id/ksapisvr"
SOURCE_API_BODY_MODES = ("auto", "json", "form")


def build_datameta_body(
    no_hp: str,
    since: str,
    until: str,
    lat_mulai: str = "0.00",
    lon_mulai: str = "0.00",
    jam_mulai: str = "-10:00:00",
) -> Dict[str, Any]:
    """Build the POST payload required by the DATAMETA source API."""
    return {
        "api_jsoncmonss": [
            {
                "Request": "DATAMETA",
                "noHP": str(no_hp).strip(),
                "tanggalAwal": str(since).strip(),
                "tanggalAkhir": str(until).strip(),
                "latMulai": str(lat_mulai).strip(),
                "lonMulai": str(lon_mulai).strip(),
                "jamMulai": str(jam_mulai).strip(),
            }
        ]
    }


def _first_present(item: Dict[str, Any], keys: List[str]) -> Any:
    for key in keys:
        if key in item and item.get(key) not in (None, ""):
            return item.get(key)
    return None


def _safe_text(value: Any, limit: int = 300) -> str:
    text = str(value or "").strip().replace("\r", " ").replace("\n", " ")
    # JSON/form token fields.
    text = re.sub(
        r'(?i)(["\']?(?:token|access_token)["\']?\s*[:=]\s*["\']?)([^"\'&,}\s]+)',
        r'\1***REDACTED***',
        text,
    )
    # Meta access token prefixes commonly start with EAA/EAG/etc. Redact any
    # long EA-prefixed opaque value even if the server did not label the field.
    text = re.sub(r'\bEA[A-Za-z0-9_\-]{18,}\b', '***REDACTED_TOKEN***', text)
    # Phone number fields may also be present in server errors/debug echoes.
    text = re.sub(
        r'(?i)(["\']?noHP["\']?\s*[:=]\s*["\']?)([0-9+\- ]{6,})',
        r'\1***REDACTED***',
        text,
    )
    if len(text) > limit:
        return text[:limit] + "..."
    return text


def _response_text(response: Any) -> str:
    content = getattr(response, "content", None)
    if isinstance(content, (bytes, bytearray)):
        raw = bytes(content)
        for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                return raw.decode(encoding).strip("\x00\ufeff \r\n\t")
            except UnicodeDecodeError:
                continue
    return str(getattr(response, "text", "") or "").strip("\x00\ufeff \r\n\t")


def _loads_nested_json(value: Any, max_depth: int = 3) -> Any:
    current = value
    for _ in range(max_depth):
        if not isinstance(current, str):
            return current
        text = current.strip("\x00\ufeff \r\n\t")
        if not text:
            return current
        try:
            current = json.loads(text)
        except (ValueError, TypeError):
            return current
    return current


def _parse_form_encoded_response(text: str) -> Optional[Dict[str, Any]]:
    if "=" not in text or "&" not in text:
        return None
    try:
        parsed = parse_qs(text, keep_blank_values=True)
    except Exception:
        return None
    if not parsed:
        return None
    result: Dict[str, Any] = {}
    for key, values in parsed.items():
        value: Any = values[0] if values else ""
        value = _loads_nested_json(value)
        result[key] = value
    return result


def _parse_nss_legacy_object(text: str) -> Optional[Dict[str, Any]]:
    """Parse the legacy NSS object wrapper used by ksapisvr.

    The endpoint may return a body that looks like JSON but starts with::

        { status = ok , "Detail": [...] }

    Only the leading ``status = value`` fragment is normalized. The remainder
    must still be valid JSON. This deliberately avoids broad replacements of
    ``=`` characters because opaque access tokens may contain arbitrary data.
    """
    candidate = str(text or "").strip("\x00\ufeff \r\n\t")
    if not candidate:
        return None
    if candidate.endswith(";"):
        candidate = candidate[:-1].rstrip()

    patterns = (
        re.compile(r"^\{\s*[\"']?status[\"']?\s*=\s*([A-Za-z0-9_.-]+)\s*,", re.IGNORECASE),
        re.compile(r"^\{\s*[\"']?status[\"']?\s*=\s*[\"']([^\"']+)[\"']\s*,", re.IGNORECASE),
        re.compile(r"^\{\s*[\"']?status[\"']?\s*:\s*([A-Za-z0-9_.-]+)\s*,", re.IGNORECASE),
    )

    for pattern in patterns:
        match = pattern.search(candidate)
        if not match:
            continue
        status_value = match.group(1)
        normalized_prefix = '{\"status\":' + json.dumps(status_value, ensure_ascii=False) + ','
        normalized = normalized_prefix + candidate[match.end():]
        try:
            payload = json.loads(normalized)
        except (ValueError, TypeError):
            continue
        if isinstance(payload, dict):
            return payload
    return None


def parse_datameta_response(response: Any) -> Any:
    """Parse normal JSON plus common legacy response wrappers safely.

    Supported forms:
    - regular JSON object;
    - UTF-8 BOM JSON;
    - JSON encoded as a JSON string;
    - NSS legacy object ``{ status = ok , "Detail": [...] }``;
    - callback/prefix text surrounding a JSON object;
    - form-url-encoded ``status=ok&Detail=[...]`` response.
    """
    try:
        payload = response.json()
        payload = _loads_nested_json(payload)
        if isinstance(payload, (dict, list)):
            return payload
    except (ValueError, TypeError, AttributeError):
        pass

    text = _response_text(response)
    if not text:
        raise ValueError("response body kosong")

    payload = _loads_nested_json(text)
    if isinstance(payload, (dict, list)):
        return payload

    legacy_payload = _parse_nss_legacy_object(text)
    if isinstance(legacy_payload, dict):
        return legacy_payload

    form_payload = _parse_form_encoded_response(text)
    if isinstance(form_payload, dict):
        return form_payload

    # Some legacy services prepend/append non-JSON text around a valid object.
    first = text.find("{")
    last = text.rfind("}")
    if first >= 0 and last > first:
        candidate = text[first:last + 1]
        payload = _loads_nested_json(candidate)
        if isinstance(payload, (dict, list)):
            return payload

    raise ValueError("response body tidak dapat diparse sebagai JSON")


def _response_detail(payload: Any) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        raise RuntimeError("Response API DATAMETA harus berupa object JSON.")

    status = _first_present(payload, ["status", "Status", "STATUS"])
    if status not in (None, ""):
        normalized_status = str(status).strip().lower()
        if normalized_status not in {"ok", "success", "sukses"}:
            message = _first_present(
                payload,
                ["message", "Message", "MESSAGE", "pesan", "Pesan", "error", "Error"],
            )
            suffix = ""
            if message not in (None, ""):
                suffix = " Pesan: {}".format(_safe_text(message, limit=200))
            raise RuntimeError(
                "API DATAMETA mengembalikan status '{}'.{}".format(
                    normalized_status,
                    suffix,
                )
            )

    detail = _first_present(payload, ["Detail", "detail", "DETAIL"])
    if isinstance(detail, str):
        parsed_detail = _loads_nested_json(detail)
        if isinstance(parsed_detail, list):
            detail = parsed_detail
    if detail is None:
        raise RuntimeError("Response API DATAMETA tidak memiliki array Detail.")
    if not isinstance(detail, list):
        raise RuntimeError("Field Detail pada response API DATAMETA harus berupa array.")
    return detail


def parse_accounts_from_datameta_payload(payload: Any) -> List[Dict[str, str]]:
    """Normalize all account rows from a DATAMETA response payload."""
    detail = _response_detail(payload)
    accounts_by_id: Dict[str, Dict[str, str]] = {}
    blank_cabang_count = 0

    for index, item in enumerate(detail, start=1):
        if not isinstance(item, dict):
            warning("Detail[{}] dilewati karena bukan object JSON.".format(index))
            continue

        account_raw = _first_present(
            item,
            [
                "idAcoount",  # spelling used by the source API contract
                "idAccount",
                "id_account",
                "ID ACCOUNT",
                "account_id",
            ],
        )
        token_raw = _first_present(item, ["token", "TOKEN", "access_token"])
        cabang_raw = _first_present(item, ["cabang", "CABANG"])
        bisnis_raw = _first_present(item, ["bisnis", "BISNIS"])

        coordinate = "API Detail[{}]".format(index)
        account_id = normalize_account_id(account_raw, coordinate + ".idAcoount")
        if not account_id:
            warning("Detail[{}] dilewati karena ID ACCOUNT kosong.".format(index))
            continue

        access_token = normalize_token(token_raw, coordinate + ".token")
        cabang = normalize_text(cabang_raw)
        bisnis = normalize_text(bisnis_raw)

        missing = []
        if not access_token:
            missing.append("token")
        if not bisnis:
            missing.append("bisnis")
        if not cabang:
            blank_cabang_count += 1
        if missing:
            raise RuntimeError(
                "API Detail[{}] untuk ID ACCOUNT {} memiliki field wajib kosong: {}.".format(
                    index,
                    account_id,
                    ", ".join(missing),
                )
            )

        current = {
            "account_id": account_id,
            "access_token": access_token,
            "cabang": cabang,
            "bisnis": bisnis,
        }

        if account_id in accounts_by_id:
            previous = accounts_by_id[account_id]
            differences = []
            if previous["access_token"] != access_token:
                differences.append("token")
            if previous["cabang"] != cabang:
                differences.append("cabang")
            if previous["bisnis"] != bisnis:
                differences.append("bisnis")
            if differences:
                raise RuntimeError(
                    "ID ACCOUNT {} muncul lebih dari sekali pada API dengan {} berbeda. "
                    "Data dibatalkan untuk mencegah checkpoint/output tertukar.".format(
                        account_id,
                        ", ".join(differences),
                    )
                )
            continue

        accounts_by_id[account_id] = current

    accounts = list(accounts_by_id.values())
    if not accounts:
        raise RuntimeError("API DATAMETA tidak menghasilkan akun Meta Ads yang valid.")
    if blank_cabang_count:
        warning(
            "API DATAMETA memiliki {} akun dengan CABANG kosong; akun tetap diproses dan CABANG output dibiarkan kosong.".format(
                blank_cabang_count
            )
        )
    return accounts


def _post_kwargs(body_mode: str, body: Dict[str, Any]) -> Dict[str, Any]:
    if body_mode == "json":
        return {"json": body}
    if body_mode == "form":
        # Legacy NSS/PHP-style endpoint: one form parameter whose value is the
        # JSON representation of the api_jsoncmonss array.
        return {
            "data": {
                "api_jsoncmonss": json.dumps(
                    body["api_jsoncmonss"],
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            }
        }
    raise ValueError("body mode API DATAMETA tidak valid: {}".format(body_mode))


def _response_diagnostic(response: Any, body_mode: str, include_preview: bool) -> str:
    status_code = int(getattr(response, "status_code", 0) or 0)
    headers = getattr(response, "headers", {}) or {}
    content_type = ""
    try:
        content_type = str(headers.get("Content-Type") or headers.get("content-type") or "")
    except AttributeError:
        content_type = ""
    text = _response_text(response)
    detail = "mode={} HTTP={} Content-Type={} panjang={} byte".format(
        body_mode,
        status_code,
        content_type or "(tidak ada)",
        len(text.encode("utf-8", errors="ignore")),
    )
    if include_preview:
        detail += " preview='{}'".format(_safe_text(text, limit=700))
    return detail


def _post_with_retries(
    http: requests.Session,
    resolved_url: str,
    body: Dict[str, Any],
    body_mode: str,
    timeout_seconds: float,
    max_retries: int,
    retry_base_delay: float,
    sleep_func: Callable[[float], None],
) -> Any:
    response = None
    for attempt in range(max_retries + 1):
        try:
            response = http.post(
                resolved_url,
                timeout=(10, float(timeout_seconds)),
                **_post_kwargs(body_mode, body)
            )
        except requests.RequestException as exc:
            if attempt >= max_retries:
                raise RuntimeError(
                    "Gagal menghubungi API DATAMETA setelah {} percobaan: {}".format(
                        attempt + 1,
                        exc.__class__.__name__,
                    )
                ) from exc
            delay = min(float(retry_base_delay) * (2 ** attempt), 30.0)
            warning(
                "API DATAMETA gagal terhubung; retry {}/{} setelah {:.1f} detik.".format(
                    attempt + 1,
                    max_retries,
                    delay,
                )
            )
            sleep_func(delay)
            continue

        status_code = int(getattr(response, "status_code", 0) or 0)
        if 200 <= status_code < 300:
            return response

        retryable = status_code in {408, 429} or status_code >= 500
        if retryable and attempt < max_retries:
            delay = min(float(retry_base_delay) * (2 ** attempt), 30.0)
            warning(
                "API DATAMETA HTTP {}; retry {}/{} setelah {:.1f} detik.".format(
                    status_code,
                    attempt + 1,
                    max_retries,
                    delay,
                )
            )
            sleep_func(delay)
            continue
        return response

    return response


def read_accounts_from_api(
    api_url: str,
    no_hp: str,
    since: str,
    until: str,
    lat_mulai: str = "0.00",
    lon_mulai: str = "0.00",
    jam_mulai: str = "-10:00:00",
    timeout_seconds: float = 60.0,
    max_retries: int = 3,
    retry_base_delay: float = 1.0,
    body_mode: str = "auto",
    debug_response: bool = False,
    session: Optional[requests.Session] = None,
    sleep_func: Callable[[float], None] = time.sleep,
) -> List[Dict[str, str]]:
    """POST to the source API and return all normalized accounts in Detail.

    ``body_mode=auto`` tries a normal JSON request first and then a legacy
    form-encoded request if the first response cannot be parsed/used.
    """
    resolved_url = str(api_url or "").strip()
    resolved_no_hp = str(no_hp or "").strip()
    resolved_body_mode = str(body_mode or "auto").strip().lower()
    if not resolved_url.startswith(("http://", "https://")):
        raise RuntimeError("URL API sumber akun tidak valid.")
    if not resolved_no_hp:
        raise RuntimeError(
            "Sumber akun API membutuhkan --source-api-nohp atau META_SOURCE_API_NOHP."
        )
    if timeout_seconds <= 0:
        raise RuntimeError("Timeout API sumber harus lebih besar dari 0.")
    if max_retries < 0:
        raise RuntimeError("Retry API sumber tidak boleh negatif.")
    if resolved_body_mode not in SOURCE_API_BODY_MODES:
        raise RuntimeError(
            "--source-api-body-mode harus salah satu: {}.".format(
                ", ".join(SOURCE_API_BODY_MODES)
            )
        )

    body = build_datameta_body(
        no_hp=resolved_no_hp,
        since=since,
        until=until,
        lat_mulai=lat_mulai,
        lon_mulai=lon_mulai,
        jam_mulai=jam_mulai,
    )

    http = session or requests.Session()
    http.headers.update(
        {
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "MetaAdsExporter/5.4.2",
        }
    )

    modes = ["json", "form"] if resolved_body_mode == "auto" else [resolved_body_mode]
    failures: List[str] = []

    for mode_index, current_mode in enumerate(modes):
        response = _post_with_retries(
            http=http,
            resolved_url=resolved_url,
            body=body,
            body_mode=current_mode,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            retry_base_delay=retry_base_delay,
            sleep_func=sleep_func,
        )
        if response is None:
            failures.append("mode={} tidak menghasilkan response".format(current_mode))
            continue

        diagnostic = _response_diagnostic(
            response,
            body_mode=current_mode,
            include_preview=bool(debug_response),
        )
        if debug_response:
            info("DEBUG DATAMETA: {}".format(diagnostic))

        status_code = int(getattr(response, "status_code", 0) or 0)
        if not 200 <= status_code < 300:
            failures.append(diagnostic)
            if mode_index + 1 < len(modes):
                warning(
                    "API DATAMETA mode {} mengembalikan HTTP {}; mencoba mode {}.".format(
                        current_mode,
                        status_code,
                        modes[mode_index + 1],
                    )
                )
                continue
            raise RuntimeError(
                "API DATAMETA gagal. {}".format("; ".join(failures[-2:]))
            )

        try:
            payload = parse_datameta_response(response)
        except (ValueError, TypeError) as exc:
            failures.append(diagnostic)
            if mode_index + 1 < len(modes):
                warning(
                    "Response DATAMETA mode {} tidak dapat diparse; mencoba mode {}.".format(
                        current_mode,
                        modes[mode_index + 1],
                    )
                )
                continue
            debug_hint = ""
            if not debug_response:
                debug_hint = (
                    " Jalankan ulang dengan --source-api-debug untuk melihat preview "
                    "response yang sudah disensor."
                )
            raise RuntimeError(
                "Response API DATAMETA bukan JSON/format yang dikenali. {}.{}".format(
                    diagnostic,
                    debug_hint,
                )
            ) from exc

        try:
            accounts = parse_accounts_from_datameta_payload(payload)
        except RuntimeError as exc:
            failures.append("{} parse={}".format(diagnostic, _safe_text(exc, 220)))
            if mode_index + 1 < len(modes):
                warning(
                    "Response DATAMETA mode {} terbaca tetapi tidak menghasilkan Detail valid; "
                    "mencoba mode {}.".format(current_mode, modes[mode_index + 1])
                )
                continue
            raise

        info(
            "Ditemukan {} akun dari API DATAMETA (mode request: {}). Token dipakai di memori dan tidak ditampilkan di log.".format(
                len(accounts),
                current_mode,
            )
        )
        if debug_response:
            sample = [
                {
                    "idAcoount": item["account_id"],
                    "token": "***REDACTED***",
                    "cabang": item["cabang"],
                    "bisnis": item["bisnis"],
                }
                for item in accounts[:5]
            ]
            info(
                "DEBUG DATAMETA akun contoh (maks 5): {}".format(
                    json.dumps(sample, ensure_ascii=False)
                )
            )
        return accounts

    raise RuntimeError(
        "API DATAMETA tidak menghasilkan data akun yang dapat digunakan. {}".format(
            "; ".join(failures[-2:])
        )
    )
