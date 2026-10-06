# Ticket-ranking survey

What five raters answer, and what the evaluator compares `ranking/priority.py` with. Built by `pairs.py` (seed 2026).
Frozen once raters have answered: rebuilding after a change to `settings.py` would pick other pairs.
Raters get `blind_survey.json` and the text of `RATER_INSTRUCTIONS.md`, never this card or `answer_key.json`.

## How it was built

- **Tickets:** 200 synthetic ones at random points in the Makati box. Kind (blocked_sidewalk 31, broken_streetlight 27, flooded_drain 33, open_manhole 33, other 37, pothole 39),
  people reporting 1 to 12 (mostly 1 to 3), people saying it is gone 0 to 5 (mostly 0), days open 0 to 30, foot traffic from
  `exposure.foot_traffic` on the real OpenStreetMap places, and a danger note (a short quote) on 34.
- **Splits first:** tickets 60/20/20 with `common.splits.group_split`, then pairs only inside one split. Each ticket's split is in the key.
- **Pairs, stratified with `priority.score`** (used to choose, never shown). `clear`: more than 15 points apart. `close`: less than 5 apart.
  `trade_off`: one ticket is a clearly more dangerous kind of hazard (danger part 0.18 or more higher), the other leads by 0.4 or more
  (0 to 1 scale) on people reporting, foot traffic or waiting. Half the trade-offs are pairs where the score puts the less dangerous kind first,
  and the less dangerous kinds take turns, so "other" is not most of them. No ticket is in more than 5 pairs; no pair shows two identical descriptions.
- **Swap repeats:** 40 pairs return once with A and B swapped, under a new id, at least a quarter of the file from the original, spread over
  splits and strata. They measure position bias; `swap_of` in the key maps each repeat to its original.
- **A and B order** is random, exactly balanced in each split and stratum (half the pairs show the higher score as A).
- **Ids** (`t001`, `p001`) are positions in a random order: they say nothing about split, stratum or repeats.

## Counts (pairs exclude the repeats)

| split | tickets | clear | close | trade_off | pairs | swap repeats |
|---|---|---|---|---|---|---|
| train | 120 | 48 | 48 | 48 | 144 | 24 |
| validation | 40 | 16 | 16 | 16 | 48 | 8 |
| test | 40 | 16 | 16 | 16 | 48 | 8 |
| all | 200 | 80 | 80 | 80 | 240 | 40 |

## What raters see

One dashboard row per ticket, for example:

> Pothole. Next to SM Supermarket, a very busy area. 1 person reported it. Open for 5 days. 2 people say it is gone. A reporter wrote: "A jeepney nearly overturned on it."

- the kind of hazard in words;
- the nearest named place within 150 m ("Next to" within 50 m, else "Near"; a bare bus stop or station name gets its noun) and a busy label from
  foot traffic ("a quiet side street" under 0.25, "a moderately busy street" up to 0.65, "a very busy area" above); with no named place that close, the busy label alone;
- how many people reported it, how long it has been open, and "N people say it is gone" or "Everyone agrees it is still there";
- the danger note as a quote, when there is one.

No priority score, band, foot-traffic number, coordinates, category code, split or stratum. Two tasks: A, B or tie with a confidence of 1 to 3 on every pair,
and an urgency of 1 to 5 on every ticket.

## Caveats

- Synthetic tickets and English-only notes written to show danger, so a note is a strong cue.
- 115 tickets have a named place within 150 m (school 43, bus 41, health 14, mall 12, doctor 2, rail 2, market 1); the rest show only the busy label.
- The busy label has three levels, so two tickets with the same label can differ a lot in foot traffic, which the score uses as a number. The named place is the nearest one,
  while foot traffic counts every place within 300 m: a spot next to a quiet bus stop can still be labelled a very busy area.
- "Other issue" has no hazard type; the score treats it as the least dangerous kind. The score stops counting waiting after 14 days, but raters see up to 30.
