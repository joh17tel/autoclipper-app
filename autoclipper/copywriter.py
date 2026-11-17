"""Writes hooks, titles and captions for each clip — free, no AI service needed.

Uses what the streamer actually said around the hype moment, plus varied
templates so no two posts look the same (repetitive posts get flagged).
"""
import random
import re

# Shouted reactions that make good hooks
HYPE_WORDS = {
    "no", "way", "what", "bro", "oh", "my", "god", "insane", "crazy", "clutch", "clutched",
    "let's", "lets", "go", "dude", "wtf", "yes", "omg", "how", "why", "stop", "wait",
    "noo", "nooo", "holy", "dead", "ace", "won", "win", "lost", "help", "run",
}

HOOK_TEMPLATES = [
    "{s} couldn't believe this",
    "wait for it...",
    "this is why {s} is cracked",
    "{s} was NOT ready",
    "chat went crazy after this",
    "nobody expected this",
    "{s} lost it here",
    "the ending got me",
    "how did {s} do that?",
    "this moment broke the stream",
]

TITLE_TEMPLATES = [
    "{hook} 😳",
    "{hook} 💀",
    "{s}: \"{quote}\"",
    "{hook} | {s}",
    "{s} reacts: {quote}",
]

EMOJI = ["😳", "💀", "🔥", "😂", "🤯", "😭"]


def _clean(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip(" .,!?-\"'")
    return text


def quote_near_peak(words: list[dict], peak_t: float, span: float = 4.0, max_words: int = 5) -> str | None:
    """The streamer's own words around the loudest moment."""
    if not words:
        return None
    near = [w for w in words if peak_t - span <= w["start"] <= peak_t + span]
    if not near:
        return None
    # start from the most "hype" word if there is one
    idx = 0
    for i, w in enumerate(near):
        if re.sub(r"[^a-z']", "", w["word"].lower()) in HYPE_WORDS:
            idx = i
            break
    q = _clean(" ".join(w["word"].strip() for w in near[idx:idx + max_words]))
    return q if len(q) >= 3 else None


def write_copy(streamer: str, words: list[dict], peak_t: float, hashtags: str,
               seed: str, used: set | None = None, disclosure_tag: str = "",
               hook_hint: str | None = None) -> dict:
    """used: hooks already given to other clips of this stream (avoids repeats)."""
    rnd = random.Random(seed)  # same clip -> same text if re-run
    used = used if used is not None else set()
    quote = quote_near_peak(words, peak_t)
    options = [t.format(s=streamer) for t in HOOK_TEMPLATES]
    rnd.shuffle(options)
    template_hook = next((o for o in options if o not in used), options[0])
    # On-screen hook: a viewer's clip title (written by a fan = best hook), else their words, else a template
    hint = _clean(re.sub(r"[^\w\s'!?.,-]", "", hook_hint or ""))
    good_hint = hint and 2 <= len(hint.split()) <= 9 and hint.lower() not in (streamer.lower(), "clip") \
        and not re.fullmatch(r"(clip|stream|highlight)s?\s*\d*", hint.lower())
    if good_hint:
        hook = hint
    elif quote and len(quote.split()) <= 6:
        hook = quote
    else:
        hook = template_hook
    used.add(hook)

    pool = TITLE_TEMPLATES if quote else TITLE_TEMPLATES[:2] + TITLE_TEMPLATES[3:4]
    if streamer.lower() in hook.lower():  # don't repeat the name twice
        pool = [t for t in pool if "{s}" not in t] or ["{hook} 🔥"]
    title_t = rnd.choice(pool)
    title = title_t.format(hook=hook[:1].upper() + hook[1:], s=streamer, quote=quote or hook)
    tags = hashtags.strip()

    youtube_title = f"{title} #shorts"[:100]
    lead = f"{disclosure_tag.strip()} " if disclosure_tag.strip() else ""
    youtube_desc = (f"{lead}{streamer} stream highlight {rnd.choice(EMOJI)}\n"
                    f"Full stream on {streamer}'s channel.\n\n{tags} #shorts #gaming #streamer")
    tiktok_caption = f"{lead}{title} {tags} #gaming #fyp #streamer"[:2000]
    return {
        "hook": hook,
        "quote": quote,
        "youtube_title": youtube_title,
        "youtube_description": youtube_desc,
        "tiktok_caption": tiktok_caption,
        "disclosure": bool(lead),
    }


def caption_txt(meta: dict) -> str:
    plats = meta.get("platforms") or ["tiktok", "youtube"]
    rules = meta.get("manual_rules") or []
    checks = meta.get("checks") or []
    extra = ""
    if checks:
        extra += "\n===== AUTO CHECKS =====\n" + "\n".join(
            ("OK   " if c["ok"] else "FIX  ") + c["text"] for c in checks) + "\n"
    if rules:
        extra += "\n===== BRIEF RULES TO CHECK YOURSELF =====\n" + "\n".join(f"- {r}" for r in rules) + "\n"
    extra += "\nAllowed platforms for this campaign: " + ", ".join(plats) + "\n"
    yt = "youtube" in plats
    tt = "tiktok" in plats or "instagram" in plats
    out = ""
    if yt:
        out += ("===== YOUTUBE SHORTS =====\n"
                f"TITLE:\n{meta['youtube_title']}\n\n"
                f"DESCRIPTION:\n{meta['youtube_description']}\n\n")
    if tt:
        label = " / ".join(p.upper() for p in plats if p in ("tiktok", "instagram"))
        out += f"===== {label} =====\nCAPTION:\n{meta['tiktok_caption']}\n"
    if meta.get("disclosure"):
        out += "\n===== BEFORE YOU POST =====\n"
        if "tiktok" in plats:
            out += "TikTok: turn ON 'Content disclosure' > 'Paid partnership'.\n"
        if "instagram" in plats:
            out += "Instagram: turn ON 'Add paid partnership label'.\n"
        if yt:
            out += "YouTube: tick 'Paid promotion' in the video's settings.\n"
    return out + extra
