import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote


def generate_totp_secret() -> str:
    """Generate a 32-character Base32 secret (160 bits of entropy) suitable
    for Google Authenticator / standard RFC 6238 TOTP apps."""
    return base64.b32encode(secrets.token_bytes(20)).decode("utf-8")


def get_totp_uri(secret: str, username: str, issuer: str = "SentinelDesk") -> str:
    """Construct an otpauth:// URI recognized by authenticator apps."""
    encoded_issuer = quote(issuer)
    encoded_user = quote(f"{issuer}:{username}")
    return f"otpauth://totp/{encoded_user}?secret={secret}&issuer={encoded_issuer}&algorithm=SHA1&digits=6&period=30"


def generate_current_totp_code(secret: str, offset: int = 0) -> str:
    """Generate the current 6-digit TOTP code for a given secret.
    Used for testing and verification."""
    clean_secret = secret.strip().replace(" ", "").upper()
    padding = (8 - len(clean_secret) % 8) % 8
    key = base64.b32decode(clean_secret + "=" * padding)
    interval = int(time.time() // 30) + offset
    counter_bytes = struct.pack(">Q", interval)
    h = hmac.new(key, counter_bytes, hashlib.sha1).digest()
    offset_byte = h[-1] & 0x0F
    code_int = struct.unpack(">I", h[offset_byte : offset_byte + 4])[0] & 0x7FFFFFFF
    return f"{code_int % 1000000:06d}"


def verify_totp(secret: str, code: str, window: int = 1) -> bool:
    """Verify a 6-digit TOTP code against the current time ± `window` intervals (30s each).
    Default window of 1 allows for ±30s of clock drift."""
    if not secret or not code:
        return False
    code_str = str(code).strip()
    if len(code_str) != 6 or not code_str.isdigit():
        return False

    try:
        clean_secret = secret.strip().replace(" ", "").upper()
        padding = (8 - len(clean_secret) % 8) % 8
        key = base64.b32decode(clean_secret + "=" * padding)

        current_interval = int(time.time() // 30)
        for offset in range(-window, window + 1):
            interval = current_interval + offset
            counter_bytes = struct.pack(">Q", interval)
            h = hmac.new(key, counter_bytes, hashlib.sha1).digest()
            offset_byte = h[-1] & 0x0F
            code_int = struct.unpack(">I", h[offset_byte : offset_byte + 4])[0] & 0x7FFFFFFF
            totp_code = f"{code_int % 1000000:06d}"
            if hmac.compare_digest(totp_code, code_str):
                return True
        return False
    except Exception:
        return False

