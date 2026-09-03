"""Normalize stored Telegram session strings to Telethon StringSession format."""

from __future__ import annotations

import base64
import struct

from telethon.crypto import AuthKey
from telethon.sessions import StringSession

# Production Telegram DCs (IPv4). Used when converting Pyrogram session strings.
_PROD_DC_IPV4 = {
    1: ("149.154.175.53", 443),
    2: ("149.154.167.51", 443),
    3: ("149.154.175.100", 443),
    4: ("149.154.167.91", 443),
    5: ("91.108.56.130", 443),
}
_TEST_DC_IPV4 = {
    1: ("149.154.175.10", 443),
    2: ("149.154.167.40", 443),
    3: ("149.154.175.117", 443),
}

_PYROGRAM_FORMATS = (
    ">BI?256sQ?",
    ">B?256sQ?",
    ">B?256sI?",
)


def _b64decode_session(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded)


def _unpack_pyrogram(session_string: str) -> tuple[int, bool, bytes]:
    packed = _b64decode_session(session_string)
    for fmt in _PYROGRAM_FORMATS:
        if len(packed) != struct.calcsize(fmt):
            continue
        parts = struct.unpack(fmt, packed)
        if fmt.startswith(">BI?"):
            dc_id, _api_id, test_mode, auth_key, _user_id, _is_bot = parts
        else:
            dc_id, test_mode, auth_key, _user_id, _is_bot = parts
        return int(dc_id), bool(test_mode), auth_key
    raise ValueError("Unrecognized Pyrogram session string")


def _pyrogram_to_telethon(session_string: str) -> str:
    dc_id, test_mode, auth_key = _unpack_pyrogram(session_string)
    dc_map = _TEST_DC_IPV4 if test_mode else _PROD_DC_IPV4
    address, port = dc_map.get(dc_id, _PROD_DC_IPV4[2])
    session = StringSession()
    session.set_dc(dc_id, address, port)
    session.auth_key = AuthKey(auth_key)
    converted = session.save()
    if not converted:
        raise ValueError("Failed to convert Pyrogram session to Telethon StringSession")
    return converted


def to_telethon_string_session(session_string: str) -> str:
    """Return a Telethon StringSession, converting from Pyrogram if needed."""
    raw = (session_string or "").strip()
    if not raw:
        raise ValueError("Empty Telegram session string")
    if raw[0] == "1":
        StringSession(raw)
        return raw
    return _pyrogram_to_telethon(raw)
