"""Sends email through Azure Communication Services' REST API (HMAC-signed, so no Azure SDK)."""
import base64
import hashlib
import hmac
import json
import logging
from email.utils import formatdate
from urllib.parse import urlparse

import httpx

from .. import config

log = logging.getLogger(__name__)
API_VERSION = "2023-03-31"


def _parse(conn: str) -> tuple[str, bytes]:
    parts = dict(p.split("=", 1) for p in conn.split(";") if "=" in p)
    return parts["endpoint"].rstrip("/"), base64.b64decode(parts["accesskey"])


def send(to: str, subject: str, text: str, html: str) -> None:
    if not config.EMAIL_CONNECTION_STRING:
        log.error("EMAIL_CONNECTION_STRING not set: email to %s not sent (%s)", to, subject)
        return
    endpoint, key = _parse(config.EMAIL_CONNECTION_STRING)
    path = f"/emails:send?api-version={API_VERSION}"
    body = json.dumps({
        "senderAddress": config.EMAIL_SENDER,
        "recipients": {"to": [{"address": to}]},
        "content": {"subject": subject, "plainText": text, "html": html},
    }).encode("utf-8")
    date = formatdate(usegmt=True)
    host = urlparse(endpoint).netloc
    content_hash = base64.b64encode(hashlib.sha256(body).digest()).decode()
    signed = f"POST\n{path}\n{date};{host};{content_hash}"
    sig = base64.b64encode(hmac.new(key, signed.encode("utf-8"), hashlib.sha256).digest()).decode()
    r = httpx.post(endpoint + path, content=body, timeout=20, headers={
        "Content-Type": "application/json",
        "x-ms-date": date,
        "x-ms-content-sha256": content_hash,
        "Authorization": f"HMAC-SHA256 SignedHeaders=x-ms-date;host;x-ms-content-sha256&Signature={sig}",
    })
    if r.status_code != 202:
        log.error("Email to %s failed: %s %s", to, r.status_code, r.text[:300])
