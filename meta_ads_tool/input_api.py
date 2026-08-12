"""Read Meta Ads account credentials from the NSS DATAMETA API source.

The source API returns account credentials in ``Detail``. Access tokens are kept
in memory only and are never included in logs, exceptions, output reports, or
checkpoint metadata.
"""

import time
from typing import Any, Callable, Dict, List, Optional

import requests

from .input_excel import normalize_account_id, normalize_text, normalize_token
from .logging_utils import info, warning


DEFAULT_SOURCE_API_URL = "https://api2nss.nusantara-sakti.co.id/ksapisvr"


def build_datameta_body(
    no_hp: str,
    since: str,
    until: str,
    lat_mulai: str = "0.00",
    lon_mulai: str = "0.00",
    jam_mulai: str = "-10:00:00",
) -> Dict[str, Any]:
    """Build the POST JSON body required by the DATAMETA source API."""
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


def _response_detail(payload: Any) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        raise RuntimeError("Response API DATAMETA harus berupa object JSON.")

    status = _first_present(payload, ["status", "Status", "STATUS"])
    if status not in (None, ""):
        normalized_status = str(status).strip().lower()
        if normalized_status not in {"ok", "success", "sukses"}:
            raise RuntimeError(
                "API DATAMETA mengembalikan status '{}' dan data akun tidak dipakai.".format(
                    normalized_status
                )
            )

    detail = _first_present(payload, ["Detail", "detail", "DETAIL"])
    if detail is None:
        raise RuntimeError("Response API DATAMETA tidak memiliki array Detail.")
    if not isinstance(detail, list):
        raise RuntimeError("Field Detail pada response API DATAMETA harus berupa array.")
    return detail


def parse_accounts_from_datameta_payload(payload: Any) -> List[Dict[str, str]]:
    """Normalize all account rows from a DATAMETA response payload."""
    detail = _response_detail(payload)
    accounts_by_id: Dict[str, Dict[str, str]] = {}

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
        if not cabang:
            missing.append("cabang")
        if not bisnis:
            missing.append("bisnis")
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
    return accounts


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
    session: Optional[requests.Session] = None,
    sleep_func: Callable[[float], None] = time.sleep,
) -> List[Dict[str, str]]:
    """POST to the source API and return all normalized accounts in Detail.

    Response bodies are intentionally never copied into exceptions because they
    may contain live Meta access tokens.
    """
    resolved_url = str(api_url or "").strip()
    resolved_no_hp = str(no_hp or "").strip()
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
            "Accept": "application/json",
            "User-Agent": "MetaAdsExporter/5.4.0",
        }
    )

    response = None
    for attempt in range(max_retries + 1):
        try:
            response = http.post(
                resolved_url,
                json=body,
                timeout=(10, float(timeout_seconds)),
            )
        except requests.RequestException as exc:
            if attempt >= max_retries:
                raise RuntimeError(
                    "Gagal menghubungi API DATAMETA setelah {} percobaan: {}".format(
                        attempt + 1,
                        exc.__class__.__name__,
                    )
                )
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
            break

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

        raise RuntimeError("API DATAMETA mengembalikan HTTP {}.".format(status_code))

    if response is None:
        raise RuntimeError("API DATAMETA tidak menghasilkan response.")

    try:
        payload = response.json()
    except (ValueError, TypeError):
        raise RuntimeError(
            "Response API DATAMETA bukan JSON valid. Isi response tidak ditampilkan "
            "karena dapat mengandung access token."
        )

    accounts = parse_accounts_from_datameta_payload(payload)
    info(
        "Ditemukan {} akun dari API DATAMETA. Token dipakai di memori dan tidak ditampilkan di log.".format(
            len(accounts)
        )
    )
    return accounts
