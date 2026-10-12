import hashlib
import hmac
import json
import time

import httpx

from app.config import settings


def push_digest(digest: dict, student_ids: list[str]) -> bool:
    """POST the digest to Zigex, signed with HMAC-SHA256. Returns True on success."""
    if not settings.zigex_webhook_url:
        return False
    body = json.dumps({"event": "weekly_digest", "digest": digest, "student_ids": student_ids},
                      ensure_ascii=False, separators=(",", ":")).encode()
    headers = {"Content-Type": "application/json"}
    if settings.zigex_webhook_secret:
        sig = hmac.new(settings.zigex_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
        headers["X-Zigex-Signature"] = f"sha256={sig}"
    for attempt in range(3):
        try:
            res = httpx.post(settings.zigex_webhook_url, content=body, headers=headers, timeout=30)
            res.raise_for_status()
            return True
        except httpx.HTTPError:
            time.sleep(2 ** attempt * 2)
    return False
