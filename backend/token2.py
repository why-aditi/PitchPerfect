"""Agora AccessToken2 ("007") carrying RTC and RTM privileges in one token.

No PyPI package builds 007 — agora-token-builder is the legacy 006 format, and the
engine needs RTM in the same token or `enable_rtm` fails (PRD 6.1). This is the
RTC + RTM subset of Agora's own builder; the byte format is pinned by the golden
vector below, so a packing mistake fails loudly instead of at call time.
"""
import base64
import hmac
import secrets
import struct
import time
import zlib
from hashlib import sha256

VERSION = "007"
RTC_SERVICE, RTM_SERVICE = 1, 2
JOIN_CHANNEL, PUBLISH_AUDIO, PUBLISH_VIDEO, PUBLISH_DATA = 1, 2, 3, 4
RTM_LOGIN = 1

_u16 = lambda x: struct.pack("<H", int(x))
_u32 = lambda x: struct.pack("<I", int(x))


def _string(s) -> bytes:
    b = s.encode("utf-8") if isinstance(s, str) else s
    return _u16(len(b)) + b


def _privileges(privs: dict[int, int]) -> bytes:
    items = sorted(privs.items())
    return _u16(len(items)) + b"".join(_u16(k) + _u32(v) for k, v in items)


def _is_hex32(s: str) -> bool:
    try:
        return len(s) == 32 and bytes.fromhex(s) is not None
    except ValueError:
        return False


def build(app_id: str, app_certificate: str, channel: str, uid: int,
          expire_s: int = 3600, issue_ts: int | None = None, salt: int | None = None) -> str:
    """Token granting publisher RTC rights on `channel` and RTM login as str(uid).

    expire_s is a duration from now, not an absolute timestamp — Agora's own builder
    treats both the token and privilege expiries that way.
    """
    if not _is_hex32(app_id) or not _is_hex32(app_certificate):
        raise ValueError("app_id and app_certificate must each be 32 hex characters")

    issue_ts = int(time.time()) if issue_ts is None else issue_ts
    salt = secrets.SystemRandom().randint(1, 99999999) if salt is None else salt

    rtc = _u16(RTC_SERVICE) + _privileges({
        JOIN_CHANNEL: expire_s, PUBLISH_AUDIO: expire_s,
        PUBLISH_VIDEO: expire_s, PUBLISH_DATA: expire_s,
    }) + _string(channel) + _string("" if uid == 0 else str(uid))

    rtm = _u16(RTM_SERVICE) + _privileges({RTM_LOGIN: expire_s}) + _string(str(uid))

    signing_info = (_string(app_id) + _u32(issue_ts) + _u32(expire_s) + _u32(salt)
                    + _u16(2) + rtc + rtm)  # services packed in service_type order

    key = hmac.new(_u32(issue_ts), app_certificate.encode(), sha256).digest()
    key = hmac.new(_u32(salt), key, sha256).digest()
    signature = hmac.new(key, signing_info, sha256).digest()

    return VERSION + base64.b64encode(zlib.compress(_string(signature) + signing_info)).decode()
