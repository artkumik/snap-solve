"""Find related YouTube videos for a search phrase, using the YouTube Data API.

Needs YOUTUBE_API_KEY (in .env or the environment). Each search uses 1 of the default
100 searches per day; results are saved in the user's browser, so a problem is only
searched once. Without a key, or if the search fails, this returns no videos.
"""
import html
import json
import logging
import os
import re
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
log = logging.getLogger(__name__)


def find_videos(query: str, count: int = 3) -> list[dict]:
    """Return up to `count` videos as {"id", "title", "channel"}; [] if unavailable."""
    if not query.strip():
        return []
    key = os.getenv("YOUTUBE_API_KEY")
    if not key:
        log.warning("YOUTUBE_API_KEY is not set, so no related videos. Add it to .env "
                    "(see .env.example) and restart the server.")
        return []
    params = urlencode({
        "part": "snippet",
        "q": query,
        "type": "video",
        "videoEmbeddable": "true",  # only videos that are allowed to play on our page
        "safeSearch": "strict",
        "relevanceLanguage": "en",
        "maxResults": count,
        "key": key,
    })
    try:
        with urlopen(f"{SEARCH_URL}?{params}", timeout=10) as response:
            data = json.load(response)
    except (URLError, OSError, ValueError) as exc:
        # Bad key, quota used up, network error, ... The rest of the result still works.
        log.warning("YouTube search failed: %r", exc)
        return []

    videos = []
    for item in data.get("items", []):
        video_id = item.get("id", {}).get("videoId", "")
        if not VIDEO_ID.match(video_id):
            continue
        snippet = item.get("snippet", {})
        videos.append({
            "id": video_id,
            # The API returns titles with HTML escapes like &#39; for apostrophes.
            "title": html.unescape(snippet.get("title", "")),
            "channel": html.unescape(snippet.get("channelTitle", "")),
        })
    return videos[:count]
