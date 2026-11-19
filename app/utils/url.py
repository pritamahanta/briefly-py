import hashlib
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PARAMS = {"fbclid", "gclid", "mc_cid", "mc_eid"}


def normalize_url(raw_url: str) -> str:
    parts = urlsplit(raw_url.strip())
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError(f"Not a valid HTTP(S) URL: {raw_url!r}")

    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.startswith("utm_") and key not in TRACKING_PARAMS
    ]

    return urlunsplit(
        (parts.scheme, parts.netloc.lower(), parts.path or "/", urlencode(query), "")
    )


def hash_link(link: str) -> str:
    return hashlib.sha256(link.encode("utf-8")).hexdigest()