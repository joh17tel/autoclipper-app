"""Campaign profiles: drop a campaign's brief + materials in a folder, and every
clip for that campaign follows its rules.

    campaigns/
      Clix_Pool/
        brief.txt | brief.md | brief.pdf     <- paste/save the FULL brief here
        materials/
          logo.png                            <- optional: watermark on every clip
          footage/                            <- optional: campaign-provided videos to clip
          examples/                           <- optional: reference clips (sets target length)
        campaign.yaml                         <- auto-written from the brief; edit to fix anything

The brief reader catches the common, checkable rules (hashtags, @tags, length,
platforms, captions/text bans, disclosure wording, source channels). Anything it
can't turn into a setting is listed under `rules_to_follow_manually` so you
see it on the clips page while posting.
"""
import glob
import os
import re
import statistics

import yaml

BRIEF_NAMES = ("brief.txt", "brief.md", "brief.pdf", "brief.docx")
AUTO_MARK = "# AUTO-GENERATED from the brief."

PLATFORM_WORDS = {
    "tiktok": ["tiktok", "tik tok"],
    "youtube": ["youtube", "yt shorts", "shorts"],
    "instagram": ["instagram", "reels", " ig "],
    "x": ["twitter", " x (", "x/twitter", "on x"],
}

DISCLOSURE_TAGS = ["#ad", "#sponsored", "#partner", "#paidpartnership", "#advertisement", "#promo"]


# ------------------------------------------------------------------ reading
def read_brief(folder: str) -> tuple[str, str | None]:
    for name in BRIEF_NAMES:
        p = os.path.join(folder, name)
        if not os.path.exists(p):
            continue
        try:
            if name.endswith(".pdf"):
                from pypdf import PdfReader
                return "\n".join((pg.extract_text() or "") for pg in PdfReader(p).pages), p
            if name.endswith(".docx"):
                import zipfile
                with zipfile.ZipFile(p) as z:
                    xml = z.read("word/document.xml").decode("utf-8", "ignore")
                xml = re.sub(r"</w:p>", "\n", xml)
                return re.sub(r"<[^>]+>", "", xml), p
            with open(p, encoding="utf-8", errors="ignore") as f:
                return f.read(), p
        except Exception as e:
            print(f"   (couldn't read {name}: {e})")
    return "", None


# ------------------------------------------------------------------ parsing
def _seconds(num: str, unit: str) -> int:
    n = float(num)
    return int(n * 60) if unit.lower().startswith("m") else int(n)


def _vod_url(url: str) -> str:
    u = url.rstrip("/.,)")
    m = re.match(r"https?://(www\.)?twitch\.tv/([A-Za-z0-9_]+)$", u)
    if m:
        return f"https://www.twitch.tv/{m.group(2)}/videos?filter=archives"
    m = re.match(r"https?://(www\.)?kick\.com/([A-Za-z0-9_\-]+)$", u)
    if m:
        return f"https://kick.com/{m.group(2)}/videos"
    m = re.match(r"https?://(www\.)?youtube\.com/(@[A-Za-z0-9_.\-]+)$", u)
    if m:
        return f"https://www.youtube.com/{m.group(2)}/streams"
    return u


def parse_brief(text: str) -> dict:
    """Pull checkable rules out of a free-text brief."""
    t = " " + re.sub(r"[ \t]+", " ", text) + " "
    low = t.lower()
    out: dict = {}

    # hashtags / @tags the brief asks for
    tags = []
    for h in re.findall(r"(?<![\w&])#[A-Za-z0-9_]{2,}", t):
        if h.lower() not in [x.lower() for x in tags] and h.lower() not in DISCLOSURE_TAGS:
            tags.append(h)
    if tags:
        out["hashtags"] = tags
    mentions = []
    for m in re.findall(r"(?<![\w.])@[A-Za-z0-9_.]{2,}", t):
        m = m.rstrip(".")
        if "@" + m[1:].lower() not in [x.lower() for x in mentions] and "." not in m[1:]:
            mentions.append(m)
    if mentions:
        out["mentions"] = mentions

    # length rules
    rng = re.search(r"(\d+)\s*(?:-|–|to)\s*(\d+)\s*(s\b|sec|second|min)", low)
    if rng:
        out["min_seconds"] = _seconds(rng.group(1), rng.group(3))
        out["max_seconds"] = _seconds(rng.group(2), rng.group(3))
    mn = re.search(r"(?:at least|minimum(?: of)?|min\.?|longer than|no shorter than)\s*(\d+)\s*(s\b|sec|second|min)", low)
    if mn:
        out["min_seconds"] = _seconds(mn.group(1), mn.group(2))
    mx = re.search(r"(?:under|max(?:imum)?(?: of)?|no longer than|shorter than|up to|less than)\s*(\d+)\s*(s\b|sec|second|min)", low) \
        or re.search(r"(\d+)\s*(s\b|sec|seconds?|min\w*)\s*(?:or less|max)", low)
    if mx:
        out["max_seconds"] = _seconds(mx.group(1), mx.group(2))

    # platforms
    plats = [p for p, words in PLATFORM_WORDS.items() if any(w in low for w in words)]
    if plats:
        out["platforms"] = plats

    # captions / on-screen text
    if re.search(r"(no|don'?t (add|use|include)|without) (captions|subtitles)", low):
        out["captions"] = False
    elif re.search(r"(captions|subtitles) (are )?(required|must|needed)|(must|need to|required to) (have|include|add) (captions|subtitles)", low):
        out["captions"] = True
    if re.search(r"no (on[- ]screen )?text( overlays?)?\b|don'?t (add|put) (any )?text|no titles? on (the )?video", low):
        out["hook_on_video"] = False
    if re.search(r"no (zooms?|zoom effects?|effects)", low):
        out["zoom_on_peak"] = False
    if re.search(r"no (re-?ordering|teasers?|flash[- ]?forwards?|cold opens?)|(keep|post) (it )?(unedited|in order|chronological)", low):
        out["cold_open"] = False
    # "no personal watermarks" = don't add YOUR branding (campaign logo is still fine)
    if re.search(r"no (third[- ]party )?(watermarks?|logos?)\b", low) and \
            not re.search(r"no (personal|your own|own) (watermarks?|logos?)", low):
        out["watermark_allowed"] = False

    # disclosure wording
    for tag in DISCLOSURE_TAGS:
        if re.search(re.escape(tag) + r"\b", low):
            out["disclosure_tag"] = tag
            break
    if "paid partnership" in low:
        out["disclosure_text"] = "Paid partnership"
    elif "sponsored" in low:
        out["disclosure_text"] = "Sponsored"

    # source channels (only stream/VOD sites)
    srcs = []
    for u in re.findall(r"https?://[^\s<>\"')]+", t):
        if re.search(r"twitch\.tv|kick\.com|youtube\.com/@|youtube\.com/(c|channel)/", u):
            v = _vod_url(u)
            if v not in srcs:
                srcs.append(v)
    if srcs:
        out["sources"] = srcs

    # lines with rules a machine can't check -> show them while posting
    manual = []
    pieces = []
    for raw_line in text.splitlines():
        raw_line = re.sub(r"^\s*([\-•\*\u2022]|\d+[.)])\s*", "", raw_line)  # strip bullets/numbers
        pieces += re.split(r"(?<=[.!?])\s+(?=[A-Z])", raw_line)
    for line in pieces:
        l = line.strip()
        if 12 <= len(l) <= 220 and re.search(
                r"\b(must|do not|don'?t|never|avoid|required|requirement|only|banned|not allowed|prohibited|make sure)\b", l, re.I):
            if l not in manual:
                manual.append(l)
    if manual:
        out["rules_to_follow_manually"] = manual[:15]
    return out


def example_length(folder: str) -> float | None:
    """Median length of reference clips in materials/examples."""
    from .layout import probe_duration
    vids = [p for ext in ("mp4", "mov", "webm", "mkv") for p in glob.glob(os.path.join(folder, f"*.{ext}"))]
    lens = [d for d in (probe_duration(v) for v in vids) if d > 0]
    return round(statistics.median(lens), 1) if lens else None


# ------------------------------------------------------------------ campaign files
def _write_yaml(path: str, data: dict) -> None:
    header = (f"{AUTO_MARK} Edit anything below; delete the first line to stop it\n"
              "# being re-generated when brief.* changes. Settings here override config.yaml.\n")
    with open(path, "w", encoding="utf-8") as f:
        f.write(header)
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True, width=100)


def build_campaign_yaml(folder: str) -> dict:
    name = os.path.basename(os.path.normpath(folder))
    text, brief_path = read_brief(folder)
    rules = parse_brief(text) if text else {}
    data: dict = {"name": name, "enabled": True}
    # the name used in hooks/titles when clipping campaign footage (no streamer)
    first_tag = (rules.get("hashtags") or [None])[0]
    data["subject"] = first_tag.lstrip("#").capitalize() if first_tag else name.replace("_", " ")

    data["streamers"] = [{"name": re.sub(r".*/(@?)([^/]+)/(videos|streams).*", r"\2", s) or name,
                          "url": s, "facecam": "auto"} for s in rules.get("sources", [])]
    if rules.get("hashtags"):
        data["hashtags"] = rules["hashtags"]
    if rules.get("mentions"):
        data["mentions"] = rules["mentions"]
    if rules.get("platforms"):
        data["platforms"] = rules["platforms"]
    for k in ("min_seconds", "max_seconds", "captions", "hook_on_video", "zoom_on_peak", "cold_open"):
        if k in rules:
            data[k] = rules[k]

    ex = example_length(os.path.join(folder, "materials", "examples"))
    if ex and "max_seconds" not in data and "min_seconds" not in data:
        data["target_seconds"] = ex  # match the reference clips

    disc = {"enabled": True}
    if rules.get("disclosure_tag"):
        disc["caption_tag"] = rules["disclosure_tag"]
    if rules.get("disclosure_text"):
        disc["on_screen_text"] = rules["disclosure_text"]
    data["disclosure"] = disc

    logo = next((p for p in glob.glob(os.path.join(folder, "materials", "logo.*"))
                 if p.lower().endswith((".png", ".jpg", ".jpeg"))), None)
    if logo and rules.get("watermark_allowed", True):
        data["watermark"] = {"file": os.path.relpath(logo, folder).replace("\\", "/"),
                             "position": "top-right", "size": 0.18, "opacity": 0.9}
    if rules.get("rules_to_follow_manually"):
        data["rules_to_follow_manually"] = rules["rules_to_follow_manually"]
    data["_brief"] = os.path.basename(brief_path) if brief_path else "none found - add brief.txt"
    _write_yaml(os.path.join(folder, "campaign.yaml"), data)
    return data


def load_campaign(folder: str) -> dict:
    """Read campaign.yaml, (re)building it from the brief when needed."""
    y = os.path.join(folder, "campaign.yaml")
    _, brief = read_brief(folder)
    rebuild = not os.path.exists(y)
    if not rebuild and brief:
        with open(y, encoding="utf-8") as f:
            first = f.readline()
        rebuild = first.startswith(AUTO_MARK) and os.path.getmtime(brief) > os.path.getmtime(y)
    if rebuild:
        print(f"   reading brief for campaign '{os.path.basename(folder)}'")
        return build_campaign_yaml(folder)
    with open(y, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def merged_cfg(cfg: dict, camp: dict, folder: str) -> dict:
    """Global config + campaign overrides."""
    m = dict(cfg)
    for k in ("captions", "hook_on_video", "zoom_on_peak", "cold_open", "clips_per_hour",
              "max_clips_per_stream", "min_clips_per_stream"):
        if k in camp:
            m[k] = camp[k]
    d = dict(cfg.get("disclosure") or {})
    d.update(camp.get("disclosure") or {})
    m["disclosure"] = d

    # fit clip length to the brief: build-up 65%, reaction 35%
    cold = 1.4 if m.get("cold_open", True) else 0.0
    default_len = cfg["clip_before_peak"] + cfg["clip_after_peak"] + cold
    target = camp.get("target_seconds") or default_len
    lo, hi = camp.get("min_seconds"), camp.get("max_seconds")
    if lo:
        target = max(target, lo + 1)
    if hi:
        target = min(target, hi - 1)
    if target != default_len:
        body = max(6.0, target - cold)
        m["clip_before_peak"] = int(round(body * 0.65))
        m["clip_after_peak"] = max(3, int(round(body * 0.35)))

    wm = camp.get("watermark")
    if wm and wm.get("file"):
        wm = dict(wm)
        wm["file"] = os.path.join(folder, wm["file"])
        m["watermark"] = wm if os.path.exists(wm["file"]) else None
    else:
        m["watermark"] = None

    m["campaign"] = {
        "name": camp.get("name") or os.path.basename(folder),
        "platforms": camp.get("platforms") or ["tiktok", "youtube"],
        "min_seconds": lo, "max_seconds": hi,
        "hashtags": camp.get("hashtags") or [],
        "mentions": camp.get("mentions") or [],
        "manual_rules": camp.get("rules_to_follow_manually") or [],
    }
    return m


def campaign_tags(m: dict, channel_tags: str = "") -> str:
    c = m.get("campaign") or {}
    parts = (channel_tags or "").split() + list(c.get("hashtags", [])) + list(c.get("mentions", []))
    seen, out = set(), []
    for p in parts:
        if p.lower() not in seen:
            seen.add(p.lower())
            out.append(p)
    return " ".join(out)


def footage_files(folder: str) -> list[str]:
    d = os.path.join(folder, "materials", "footage")
    return sorted(p for ext in ("mp4", "mov", "mkv", "webm") for p in glob.glob(os.path.join(d, f"*.{ext}")))


def discover(root: str = "campaigns") -> list[str]:
    if not os.path.isdir(root):
        return []
    return sorted(os.path.join(root, d) for d in os.listdir(root)
                  if os.path.isdir(os.path.join(root, d)) and not d.startswith(("_", ".")))


# ------------------------------------------------------------------ compliance
def check_clip(meta: dict, m: dict) -> list[dict]:
    """Checks each finished clip against the campaign's rules."""
    c = m.get("campaign") or {}
    checks = []
    L = meta.get("length_sec") or 0
    lo, hi = c.get("min_seconds"), c.get("max_seconds")
    if lo or hi:
        ok = (not lo or L >= lo) and (not hi or L <= hi)
        checks.append({"ok": ok, "text": f"Length {L}s (brief: {lo or 0}–{hi or '∞'}s)"})
    caption = meta.get("tiktok_caption", "") + " " + meta.get("youtube_description", "")
    for tag in c.get("hashtags", []) + c.get("mentions", []):
        checks.append({"ok": tag.lower() in caption.lower(), "text": f"Caption has {tag}"})
    d = m.get("disclosure") or {}
    if d.get("enabled"):
        tag = d.get("caption_tag", "#ad")
        checks.append({"ok": meta.get("tiktok_caption", "").lower().startswith(tag.lower()),
                       "text": f"Disclosure {tag} at start of caption"})
    if m.get("hook_on_video") is False:
        checks.append({"ok": True, "text": "No title text on video (brief)"})
    return checks
