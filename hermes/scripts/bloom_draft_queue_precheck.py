#!/usr/bin/env python3
"""Pre-check for the Hermes cron job that turns panel requests into drafts.

Asks Bloom how many draft requests are waiting, without reserving any. The last
stdout line is the gate read by the Hermes scheduler: {"wakeAgent": false}
skips the LLM run entirely, so an empty queue costs nothing.
"""

import json
import os
import sys
import urllib.request
from typing import Callable, Mapping
from urllib.parse import urlparse

TENANT = "viralbarato"
TIMEOUT_SECONDS = 20
# Bloom's edge rejects the default Python user agent with 403.
USER_AGENT = "Mozilla/5.0 (compatible; bloom-draft-queue-precheck)"


def config(env: Mapping[str, str]) -> tuple[str, str]:
    base_url = env.get("BLOOM_API_URL", "").strip().rstrip("/")
    token = env.get("BLOOM_CONTENT_API_TOKEN", "").strip()
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.path:
        raise ValueError("BLOOM_API_URL must be an HTTPS origin without a path")
    if not token:
        raise ValueError("BLOOM_CONTENT_API_TOKEN is not configured")
    return base_url, token


def fetch_pending(env: Mapping[str, str]) -> int:
    base_url, token = config(env)
    request = urllib.request.Request(
        f"{base_url}/api/v1/{TENANT}/editorial/draft-requests/pending",
        headers={"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return int(json.load(response)["pending"])


def decide(get_pending: Callable[[], int]) -> str:
    """Return the script output; its last line is the scheduler gate."""
    try:
        pending = get_pending()
    except Exception as error:  # network, HTTP or config problem: the agent would fail too
        return f"pre-check failed: {error}\n{json.dumps({'wakeAgent': False})}"
    if pending <= 0:
        return json.dumps({"wakeAgent": False})
    return json.dumps({"wakeAgent": True, "pending": pending})


if __name__ == "__main__":
    print(decide(lambda: fetch_pending(os.environ)))
    sys.exit(0)
