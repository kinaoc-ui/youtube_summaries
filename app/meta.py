from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def fetch_video_meta(video_id: str) -> dict[str, Any]:
    """Fetch public title/author via YouTube oEmbed (no API key)."""
    watch = f"https://www.youtube.com/watch?v={video_id}"
    oembed = "https://www.youtube.com/oembed?" + urllib.parse.urlencode(
        {"url": watch, "format": "json"}
    )
    try:
        with urllib.request.urlopen(oembed, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return {
            "video_id": video_id,
            "title": data.get("title") or video_id,
            "author": data.get("author_name") or "",
            "url": watch,
        }
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return {"video_id": video_id, "title": video_id, "author": "", "url": watch}
