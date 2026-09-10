import hashlib
import secrets


def hash_api_key(raw_key: str) -> str:
    """SHA-256 hex digest. Store this, never the raw key."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def generate_api_key() -> str:
    """Opaque secret shown once at creation time. Prefix helps humans identify keys."""
    return f"sk_{secrets.token_urlsafe(32)}"


def key_prefix(raw_key: str, length: int = 12) -> str:
    return raw_key[:length]
