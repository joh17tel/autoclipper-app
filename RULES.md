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

## Changelog
- 2026-11-25 (v6.7.0): Added self-check rubric (retention score + warnings per clip), payoff-by-10s rule
  when there's no cold open, 0.7s dead-air cut for IRL/talk. Why: 2026 research is consistent that the first
  2s and ~70% completion decide reach; the old setup let payoff land at ~18s on no-cold-open clips.
  Learner now tracks "payoff timing" and "self-check score" against real views, so these rules get
  validated or overturned by your data.
- 2026-11-25 (v6.6.0): Web research: Reddit trending moments clipped first; buzz words feed hook picking.
