"""Hooks, titles and captions for each clip — free, no AI service needed.

How a hook is chosen (best first):
  1. a fan's Twitch clip title (fans write great hooks)
  2. the punchiest thing the streamer actually SAID in the clip
  3. a template from a large, category-specific bank (gaming / IRL / talk)
Every hook is checked against the last 200 hooks you've made (across all
streams and campaigns), so the same line or the same opening never repeats.
The title is written differently from the on-screen hook, so they don't echo.
"""
import json
import random
import re

CATEGORIES = ("gaming", "irl", "talk")
HISTORY_FILE = "hooks_history.json"

HYPE_WORDS = {
    "no", "way", "what", "bro", "oh", "god", "insane", "crazy", "clutch", "clutched", "dude", "wtf",
    "yes", "omg", "how", "why", "stop", "wait", "noo", "nooo", "holy", "dead", "ace", "won", "lost",
    "help", "run", "yo", "chat", "bruh", "nah", "fr", "deadass", "actually", "literally", "never",
    "ever", "cooked", "real", "serious", "swear", "kidding", "believe", "look",
}
FILLER = {"um", "uh", "like", "you", "know", "i", "mean", "so", "and", "but", "the", "a", "okay", "ok"}
BAD_STARTS = {"and", "but", "so", "um", "uh", "like", "because", "or", "the", "a", "to", "of", "my", "your",
              "his", "her", "at", "in", "on", "for", "with", "yeah", "anyway", "then", "is", "was", "it's"}
BAD_ENDS = {"and", "but", "so", "um", "uh", "like", "the", "a", "an", "to", "of", "at", "in", "on", "for",
            "with", "my", "your", "his", "her", "is", "are", "was", "were", "i", "you", "he", "she", "we",
            "they", "it", "this", "just", "because", "or", "if", "when", "gonna", "about"}

HOOKS = {
    "gaming": [
        "{s} couldn't believe this", "this is why {s} is cracked", "{s} was NOT ready",
        "nobody expected this play", "the ending got me", "how did {s} do that?",
        "this moment broke the stream", "1 in a million play", "{s} called it before it happened",
        "the timing on this", "he really pulled this off", "this shouldn't have worked",
        "{s} with the comeback", "chat thought it was over", "{s} turned this around",
        "watch the last 3 seconds", "you have to see the end", "pure reflexes",
        "they did NOT see this coming", "{s} went full sweat mode", "the confidence on {s}",
        "this round was insane", "{s} has no business doing this", "the clip that broke chat",
        "{s} almost threw this", "best play of the stream", "{s} said watch this",
    ],
    "irl": [
        "this got awkward fast", "{s} didn't expect that reaction", "chat couldn't believe this happened",
        "strangers were NOT ready", "{s} really did this in public", "this went left real quick",
        "nobody saw this coming", "the way she responded", "the way he responded",
        "{s} had to leave after this", "this is why {s} is a menace", "he said it with his whole chest",
        "security showed up after this", "the reaction at the end", "{s} got exposed live",
        "this stranger was too real", "{s} found out the hard way", "this was not planned",
        "the confidence on {s}", "it all went wrong here", "{s} pushed it too far",
        "they were not prepared for {s}", "chat was screaming", "the most {s} moment ever",
        "this is peak IRL streaming", "wait till you hear what she said", "wait till you hear what he said",
    ],
    "talk": [
        "{s} said this with a straight face", "{s} went off on this", "this take is crazy",
        "{s} didn't hold back", "chat was NOT ready for this", "{s} told the whole story",
        "the way {s} explained this", "{s} exposed everything", "this answer changed everything",
        "{s} got real for a second", "nobody expected this answer", "{s} shut it down",
        "this conversation went left", "the honesty from {s}", "{s} had chat in shambles",
        "hot take incoming", "{s} said what everyone was thinking", "this got heated",
    ],
}

TITLES = {
    "gaming": ["{s} said WHAT? 😳", "{s} was locked in 🔥", "{s}'s craziest moment 💀", "this {s} clip is unreal 🤯",
               "{s} cooked everyone 🔥", "{s} in disbelief 😳", "nah {s} is different 💀", "{s} on another level"],
    "irl": ["{s} IRL went left 💀", "{s} in public is crazy 😭", "only {s} 😭", "{s} did NOT think this through 💀",
            "{s} caught off guard 😳", "the {s} experience 😭", "{s} IRL moments 💀", "{s} couldn't stop laughing 😂"],
    "talk": ["{s} spoke facts 💯", "{s} got real 😳", "{s} on this topic 💀", "{s} went off 🔥",
             "{s} said it 😳", "{s} explains 🤯"],
}

QUESTIONS = {
    "gaming": ["Rate this play 1-10 👇", "Clean or lucky? 👇", "What would you have done here? 👇",
               "Would you have clutched this? 👇", "Best moment of the stream? 👇", "{s} fans, where you at? 👇",
               "Skill or luck? 👇", "Who else saw this live? 👇"],
    "irl": ["Would you have reacted the same? 👇", "Who was wrong here? 👇", "Rate this 1-10 👇",
            "What would you have done? 👇", "Funniest part? 👇", "Who else saw this live? 👇",
            "Was this too far? 👇", "{s} fans, where you at? 👇"],
    "talk": ["Agree or disagree? 👇", "Is {s} right? 👇", "What's your take? 👇", "Facts or cap? 👇",
             "Would you say the same? 👇", "Who else saw this live? 👇"],
}

TAGS = {"gaming": "#gaming #fyp #streamer", "irl": "#irl #irlstream #fyp #streamer",
        "talk": "#streamer #fyp #clips"}
EMOJI = ["😳", "💀", "🔥", "😂", "🤯", "😭"]


# ------------------------------------------------------------------ history (no repeats)
def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", t.lower()).strip()


def load_history() -> list:
    try:
        with open(HISTORY_FILE, encoding="utf-8") as f:
            return json.load(f)[-200:]
    except Exception:
        return []


def save_history(hist: list) -> None:
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(hist[-200:], f)
    except Exception:
        pass


def _opening(t: str, streamer: str) -> str:
    g = _norm(t).replace(_norm(streamer), "S") if streamer else _norm(t)
    return " ".join(g.split()[:2])


def _fresh(hook: str, hist: list, used: set, streamer: str) -> bool:
    n = _norm(hook)
    if n in used or n in hist:
        return False
    # same opening as a very recent hook (three "STREAMER couldn't..." in a row) = repetitive
    recent = [_opening(h, streamer) for h in hist[-12:]]
    return _opening(hook, streamer) not in recent


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" .,!?-\"'")


# ------------------------------------------------------------------ quotes from the transcript
def best_quotes(words: list[dict], peak_t: float, limit: int = 5) -> list[str]:
    """Rank short phrases the streamer said by how 'hooky' they are."""
    if not words:
        return []
    phrases, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        gap = (words[i + 1]["start"] - w["end"]) if i + 1 < len(words) else 9
        if gap >= 0.35 or re.search(r"[.!?]$", w["word"].strip()):
            phrases.append(cur)
            cur = []
    if cur:
        phrases.append(cur)
    scored = []
    for ph in phrases:
        for size in range(3, 8):
            for st in range(0, max(1, len(ph) - size + 1)):
                seg = ph[st:st + size]
                if len(seg) < 3:
                    continue
                toks = [re.sub(r"[^a-z']", "", w["word"].lower()) for w in seg]
                text = _clean(" ".join(w["word"].strip() for w in seg))
                if not text or toks[0] in BAD_STARTS or toks[-1] in BAD_ENDS:
                    continue
                hype = sum(t in HYPE_WORDS for t in toks)
                filler = sum(t in FILLER for t in toks)
                punct = 1 if re.search(r"[!?]", " ".join(w["word"] for w in seg)) else 0
                near = max(0.0, 1 - abs(seg[0]["start"] - peak_t) / 8)
                whole = 0.8 if (st == 0 and size == len(ph)) else 0.0   # a complete phrase reads better
                score = 1.4 * hype + 1.2 * punct + 1.5 * near + whole - 0.6 * filler - 0.15 * abs(size - 5)
                if score > 0.8:
                    scored.append((score, text))
    scored.sort(reverse=True)
    out, seen = [], []
    for _, t in scored:
        k = _norm(t)
        if not any(k in s or s in k for s in seen):
            out.append(t)
            seen.append(k)
        if len(out) >= limit:
            break
    return out


def _good_fan_title(hint: str, streamer: str) -> bool:
    if not hint:
        return False
    low = hint.lower()
    return 2 <= len(hint.split()) <= 9 and low not in (streamer.lower(), "clip") and \
        not re.fullmatch(r"(clip|stream|highlight|moment)s?\s*\d*", low) and not low.startswith("http")


# ------------------------------------------------------------------ main entry
def write_copy(streamer: str, words: list[dict], peak_t: float, hashtags: str,
               seed: str, used: set | None = None, disclosure_tag: str = "",
               hook_hint: str | None = None, question: bool = True,
               category: str = "gaming", history: list | None = None) -> dict:
    cat = category if category in CATEGORIES else "gaming"
    rnd = random.Random(seed)
    used = used if used is not None else set()
    hist = history if history is not None else []

    candidates = []
    hint = _clean(re.sub(r"[^\w\s'!?.,-]", "", hook_hint or ""))
    if _good_fan_title(hint, streamer):
        candidates.append(("fan", hint))
    quotes = best_quotes(words, peak_t)
    candidates += [("quote", q) for q in quotes]
    tmpl = [t.format(s=streamer) for t in HOOKS[cat]]
    rnd.shuffle(tmpl)
    candidates += [("template", t) for t in tmpl]

    kind, hook = next(((k, t) for k, t in candidates if _fresh(t, hist, used, streamer)), candidates[0])
    used.add(_norm(hook))
    hist.append(_norm(hook))

    # Title says something DIFFERENT from the on-screen hook
    quote = quotes[0] if quotes else None
    titles = [t.format(s=streamer) for t in TITLES[cat]]
    rnd.shuffle(titles)
    if kind != "quote" and quote and _norm(quote) != _norm(hook):
        title = f'{streamer}: "{quote[:1].upper() + quote[1:]}" {rnd.choice(EMOJI)}'
    else:
        title = next((t for t in titles if _norm(t) not in hist[-40:]), titles[0])
        hist.append(_norm(title))

    tags = " ".join(dict.fromkeys((hashtags.strip() + " " + TAGS[cat]).split()))
    lead = f"{disclosure_tag.strip()} " if disclosure_tag.strip() else ""
    q = rnd.choice(QUESTIONS[cat]).format(s=streamer) if question else ""
    shown = f'"{hook}"' if kind == "quote" else hook   # quotes read as something said
    youtube_title = f"{title} #shorts"[:100]
    youtube_desc = (f"{lead}{shown} {rnd.choice(EMOJI)}\n" + (f"{q}\n" if q else "")
                    + f"Full stream on {streamer}'s channel.\n\n{tags} #shorts")
    tiktok_caption = (f"{lead}{title}" + (f" {q}" if q else "") + f" {tags}")[:2000]
    return {
        "hook": shown,
        "hook_kind": kind,
        "quote": quote,
        "category": cat,
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
