"""Web research: finds what's trending about your streamers RIGHT NOW (free, no account).

Source: Reddit's public listings (r/LivestreamFail - where viral streamer moments surface first -
plus a site-wide search). For each streamer it collects the most upvoted recent posts, then:
  * TRENDING MOMENTS - posts that link a Twitch/Kick/YouTube clip of that streamer are clipped
    first (they're already proven to go viral), with the post title as the hook
  * HOT WORDS        - words in the most upvoted titles count as "hooky" when picking quotes
  * INSIGHTS         - the trending list shows on the Insights page with links
"""
import json
import re
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime

UA = {"User-Agent": "AutoClipper/6 (personal clip helper)"}
STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "is", "it", "this", "that", "at",
        "his", "her", "he", "she", "i", "you", "my", "me", "be", "was", "are", "after", "gets", "from", "while",
        "clip", "clips", "stream", "streamer", "twitch", "kick", "live", "lsf", "about", "when", "what", "who"}
CLIP_LINK = re.compile(r"(clips\.twitch\.tv/|twitch\.tv/\w+/clip/|kick\.com/[\w-]+/clips/|kick\.com/[\w-]+\?clip=|"
                       r"youtube\.com/(watch|shorts|clip)|youtu\.be/)", re.I)


def _get_json(url: str, timeout: int = 20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def _posts(listing) -> list[dict]:
    out = []
    for ch in (listing or {}).get("data", {}).get("children", []):
        d = ch.get("data") or {}
        if d.get("over_18") or d.get("removed_by_category"):
            continue
        out.append({"title": (d.get("title") or "").strip(), "score": int(d.get("score") or 0),
                    "comments": int(d.get("num_comments") or 0), "url": d.get("url_overridden_by_dest") or d.get("url") or "",
                    "permalink": "https://www.reddit.com" + (d.get("permalink") or ""),
                    "created": datetime.fromtimestamp(d.get("created_utc") or 0).isoformat(timespec="minutes"),
                    "sub": d.get("subreddit") or ""})
    return out


def scan_streamer(name: str, period: str = "week", limit: int = 25) -> dict | None:
    """Most upvoted recent Reddit posts about this streamer."""
    q = urllib.parse.quote(name)
    urls = [f"https://www.reddit.com/r/LivestreamFail/search.json?q={q}&restrict_sr=1&sort=top&t={period}&limit={limit}",
            f"https://www.reddit.com/search.json?q={q}&sort=top&t={period}&limit={limit}"]
    items, seen = [], set()
    for u in urls:
        try:
            for p in _posts(_get_json(u)):
                if p["permalink"] in seen or name.lower().split()[0][:5] not in p["title"].lower() + p["url"].lower():
                    continue
                seen.add(p["permalink"])
                items.append(p)
        except Exception:
            pass
        time.sleep(2)   # be polite (Reddit rate-limits fast requests)
    if not items:
        return None
    items.sort(key=lambda p: p["score"] + 2 * p["comments"], reverse=True)
    words = Counter()
    for p in items[:15]:
        for w in re.findall(r"[a-z']+", p["title"].lower()):
            if len(w) > 2 and w not in STOP and w not in name.lower():
                words[w] += 1
    for p in items:
        p["clip_url"] = p["url"] if CLIP_LINK.search(p["url"]) else None
    return {"scanned": datetime.now().isoformat(timespec="minutes"), "posts": len(items),
            "hot_words": [w for w, c in words.most_common(12) if c >= 2],
            "trending": items[:15]}


def trending_clips(web: dict, streamer: str) -> list[dict]:
    """Proven-viral clip links for a streamer (best first)."""
    r = (web or {}).get(streamer.lower()) or {}
    return [p for p in r.get("trending", []) if p.get("clip_url")]


def hot_words(web: dict, streamer: str) -> set:
    return set(((web or {}).get(streamer.lower()) or {}).get("hot_words") or [])
