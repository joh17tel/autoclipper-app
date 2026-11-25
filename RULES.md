# AutoClipper clip rules (selection + editing)

These are the rules the app follows when picking and editing clips. Each finished clip gets a
**self-check** (`retention` in meta.json, shown as warnings on the clip card). The self-learner
then compares self-check scores and payoff timing against your real views (Insights tab).

## What the platforms reward (researched Nov 2026)
- Shorts: the first ~2 seconds decide distribution (swipe-away rate). Payoff expected by ~10s.
- TikTok: completion rate + rewatches are the strongest signals; ~70% completion is the bar to break out.
- Loops/rewatches boost ranking; word-by-word burned-in captions raise completion.
- Pauses feel slow fast in talking content; jump cuts between sentences are expected.

## Rubric (self-check, 0–100)
| Rule | Penalty |
|---|---|
| Nothing grabs attention in first 2s (no hook text, no talking by 1.5s, no cold open) | −25 |
| First words after 2.5s (no cold open) | −10 |
| Payoff after 10s (no cold open) | −25 |
| Clip over 35s | −10 |
| More than 12s after the payoff (ending drags) | −15 |
| 2+ pauses over 2s left in the clip | −10 |

## Editing rules
- Cold open ON: flash the payoff first, then the build-up (25% of clips experiment with OFF).
- Cold open OFF: start the clip so the payoff lands by `max_payoff_seconds` (10s).
- Cut dead air: gaming ≥1.2s, IRL/talk ≥0.7s (`dead_air_seconds_talk`).
- Hook text on screen for the first 3s; quotes from the clip beat templates; no repeats.
- End on a finished sentence shortly after the reaction (5–9s), never mid-word.
- Trending-on-Reddit moments are clipped first (web research).
- Pacing: a small 6% jump-zoom on each new phrase (at least 2.5s apart, away from the peak zoom),
  so the picture changes every few seconds.
- Same moment never made twice: Reddit and viewer clips are matched by clip ID.

## Posting order (Clips -> posting plan)
priority = proven-ness x freshness x self-check x rule issues
- Proven: trending on Reddit 1.6x (+ upvotes), viewer clip 1.3x (+ views), auto-detected 1.0x
- Freshness half-life: trending 18h, viewer clip 36h, auto 60h. Over 7 days old = skipped
- Each failed brief check (hashtag, disclosure) = x0.7

## Self-tuning (v6.8.0)
Once a day the app runs research -> self-critique -> rule update on its own (`autoclipper/rules.py`):
1. **Self-critique:** reviews clips made since the last rule change. A warning on 40%+ of them (6+ clips) tightens the matching rule.
2. **Your views:** payoff timing, time after payoff and hook style vs real views. Needs 4+ newly measured clips each time.
3. **Web:** title length and question-style of your streamers' top clips vs the rest (YouTube), plus Reddit buzz.

Each rule moves one small step per day inside a safe range. Every change is logged in `rules.json`
(date, old -> new, why, evidence) and shown in Insights, which also has a Reset button.
Your own views win over web signals. Campaign briefs win over everything.

| Rule | Default | Range |
|---|---|---|
| Payoff deadline (no cold open) | 10s | 6–14 |
| Build-up before the moment | 18s | 10–22 |
| Reaction after the moment | 9s | 4–12 |
| Dead air cut, gaming / talk | 1.2s / 0.7s | 0.6–2.0 / 0.4–1.2 |
| Max clip length | 30s | 15–45 |
| Max hook words | 9 | 4–12 |
| Question-hook preference | 1.0× | 0.6–1.6× |

## Changelog
- 2026-11-25 (v6.9.0): Posting plan ranks by freshness + proof + self-check instead of alternating
  sources (trending moments lose value within a day; old ranking mixed upvotes with detection scores).
  Added phrase jump-zooms (2026 guides: visual change every 1-5s keeps retention). Cross-source dedupe
  so the same Twitch/Kick clip isn't made twice.
- 2026-11-25 (v6.8.0): The system now rewrites its own rules daily (self-critique + your views + web), bounded and logged.
- 2026-11-25 (v6.7.0): Added self-check rubric (retention score + warnings per clip), payoff-by-10s rule
  when there's no cold open, 0.7s dead-air cut for IRL/talk. Why: 2026 research is consistent that the first
  2s and ~70% completion decide reach; the old setup let payoff land at ~18s on no-cold-open clips.
  Learner now tracks "payoff timing" and "self-check score" against real views, so these rules get
  validated or overturned by your data.
- 2026-11-25 (v6.6.0): Web research: Reddit trending moments clipped first; buzz words feed hook picking.
