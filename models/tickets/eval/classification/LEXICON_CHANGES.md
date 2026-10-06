# Lexicon changes: v0 to v1

Written by `tune_lexicon.py`; do not edit by hand. Every change below comes from the TRAIN split only (1120 notes, 60 families, seed 4). Validation (380 notes) was used only to put a number on each change after it was decided.

## The rule
A term is judged when it is in at least 5 train notes across at least 3 families. Its precision is the share of the notes it applies to that carry its class: the category; danger (a danger word counts only where classify.py would not cancel it); not-danger for a negator; danger for a boundary word. **Add** a new term when it is judged and its precision is at least 0.9. **Remove** a v0 term when it is judged and at least 0.9 of its notes are NOT of its class (precision at most 0.1). A term that is not judged stays. A judged term in between stays too and is listed as weak below. Guards on new terms only: a phrase may not contain a term the list already has, and may not start or end with a function word.

**Effect** = the change on its own against v0, on validation: macro-F1 of the category hint at the shipped thresholds for a category list, PR-AUC of the danger score for the danger list, negators and boundary words. For a weak term it is what removing it would do. Terms interact, so effects do not add up to the totals.

## Totals on validation
| | category macro-F1 (shipped thresholds) | danger PR-AUC |
|---|---|---|
| v0 | 0.7452 | 0.7737 |
| v1 (this log) | 0.7836 | 0.8449 |
| change | +0.0384 | +0.0711 |
| v1 and also removing every weak term (the literal remove-below-0.9 rule, a check only) | 0.6915 | 0.7980 |

## What the rule did to each list
| list | v0 terms | judged and qualified | judged, weak (kept) | not judged (kept) | removed | added |
|---|---|---|---|---|---|---|
| negators | 13 | 3 | 0 | 10 | 0 | 0 |
| boundaries | 8 | 0 | 0 | 8 | 0 | 0 |
| danger | 68 | 14 | 6 | 48 | 0 | 9 |
| pothole | 24 | 3 | 0 | 21 | 0 | 4 |
| open_manhole | 15 | 4 | 2 | 9 | 0 | 1 |
| flooded_drain | 30 | 4 | 4 | 22 | 0 | 1 |
| broken_streetlight | 26 | 4 | 7 | 15 | 0 | 7 |
| blocked_sidewalk | 21 | 4 | 5 | 12 | 0 | 7 |
| other | 22 | 0 | 5 | 16 | 1 | 0 |

## Every change
| change | list | term | train notes | families | precision | effect on validation |
|---|---|---|---|---|---|---|
| remove | other | basura | 9 | 4 | 0.00 | macro-f1 -0.0296 |
| add | blocked_sidewalk | daanan | 10 | 8 | 0.90 | macro-f1 +0.0000 |
| add | blocked_sidewalk | parked | 10 | 5 | 1.00 | macro-f1 +0.0033 |
| add | blocked_sidewalk | kotse | 8 | 5 | 1.00 | macro-f1 +0.0000 |
| add | blocked_sidewalk | madaanan | 7 | 5 | 1.00 | macro-f1 +0.0000 |
| add | blocked_sidewalk | materials | 7 | 5 | 1.00 | macro-f1 -0.0009 |
| add | blocked_sidewalk | nakaparadang | 6 | 4 | 1.00 | macro-f1 +0.0000 |
| add | blocked_sidewalk | space | 5 | 4 | 1.00 | macro-f1 +0.0000 |
| add | broken_streetlight | patay | 27 | 9 | 1.00 | macro-f1 +0.0074 |
| add | broken_streetlight | lamp | 16 | 9 | 0.94 | macro-f1 +0.0121 |
| add | broken_streetlight | dead | 10 | 6 | 1.00 | macro-f1 +0.0074 |
| add | broken_streetlight | meralco | 10 | 4 | 1.00 | macro-f1 -0.0017 |
| add | broken_streetlight | bulb | 8 | 5 | 1.00 | macro-f1 +0.0000 |
| add | broken_streetlight | light pole | 7 | 5 | 1.00 | macro-f1 +0.0074 |
| add | broken_streetlight | umiilaw | 7 | 4 | 1.00 | macro-f1 +0.0000 |
| add | danger | baka | 16 | 8 | 0.94 | pr-auc +0.0265 |
| add | danger | could | 9 | 7 | 1.00 | pr-auc +0.0015 |
| add | danger | batang | 7 | 4 | 1.00 | pr-auc +0.0103 |
| add | danger | walking | 7 | 4 | 1.00 | pr-auc +0.0088 |
| add | danger | bka | 6 | 4 | 1.00 | pr-auc +0.0176 |
| add | danger | pauwi | 6 | 3 | 1.00 | pr-auc +0.0000 |
| add | danger | will | 6 | 5 | 1.00 | pr-auc +0.0068 |
| add | danger | aso | 5 | 3 | 1.00 | pr-auc +0.0000 |
| add | danger | scary | 5 | 4 | 1.00 | pr-auc +0.0000 |
| add | flooded_drain | linisin | 8 | 6 | 1.00 | macro-f1 +0.0000 |
| add | open_manhole | takip | 42 | 8 | 0.93 | macro-f1 +0.0000 |
| add | pothole | hole | 34 | 15 | 1.00 | macro-f1 +0.0245 |
| add | pothole | butas | 30 | 15 | 0.97 | macro-f1 +0.0181 |
| add | pothole | lumalaki | 10 | 4 | 1.00 | macro-f1 +0.0032 |
| add | pothole | laki | 6 | 3 | 1.00 | macro-f1 +0.0000 |

## Weak v0 terms: judged, precision below 0.9, kept
These were not removed because the evidence against them is not strong (precision above 0.1). The effect column is what removing each would have cost.
| change | list | term | train notes | families | precision | effect on validation |
|---|---|---|---|---|---|---|
| would remove | blocked_sidewalk | sidewalk | 78 | 16 | 0.90 | macro-f1 -0.0398 |
| would remove | blocked_sidewalk | nakaharang | 28 | 12 | 0.75 | macro-f1 +0.0000 |
| would remove | blocked_sidewalk | tindahan | 10 | 7 | 0.50 | macro-f1 -0.0012 |
| would remove | blocked_sidewalk | harang | 7 | 5 | 0.43 | macro-f1 +0.0000 |
| would remove | blocked_sidewalk | paninda | 6 | 5 | 0.83 | macro-f1 +0.0000 |
| would remove | broken_streetlight | poste | 51 | 13 | 0.80 | macro-f1 -0.0316 |
| would remove | broken_streetlight | walang ilaw | 21 | 9 | 0.86 | macro-f1 +0.0000 |
| would remove | broken_streetlight | madilim | 19 | 10 | 0.79 | macro-f1 +0.0000 |
| would remove | broken_streetlight | dark | 15 | 9 | 0.73 | macro-f1 +0.0000 |
| would remove | broken_streetlight | lamp post | 8 | 5 | 0.88 | macro-f1 +0.0000 |
| would remove | broken_streetlight | no light | 6 | 5 | 0.67 | macro-f1 +0.0000 |
| would remove | broken_streetlight | streetlights | 6 | 3 | 0.83 | macro-f1 -0.0052 |
| would remove | danger | almost | 17 | 13 | 0.53 | pr-auc -0.0063 |
| would remove | danger | hurt | 10 | 8 | 0.80 | pr-auc -0.0255 |
| would remove | danger | fell | 9 | 7 | 0.67 | pr-auc -0.0222 |
| would remove | danger | mapanganib | 8 | 7 | 0.88 | pr-auc +0.0000 |
| would remove | danger | namatay | 5 | 3 | 0.40 | pr-auc +0.0000 |
| would remove | danger | natumba | 5 | 4 | 0.60 | pr-auc -0.0015 |
| would remove | flooded_drain | baha | 55 | 10 | 0.76 | macro-f1 -0.0227 |
| would remove | flooded_drain | clogged | 17 | 6 | 0.76 | macro-f1 +0.0000 |
| would remove | flooded_drain | flooded | 12 | 6 | 0.83 | macro-f1 -0.0032 |
| would remove | flooded_drain | flood | 11 | 5 | 0.73 | macro-f1 -0.0045 |
| would remove | open_manhole | manhole | 155 | 9 | 0.79 | macro-f1 -0.0198 |
| would remove | open_manhole | manhole cover | 22 | 7 | 0.82 | macro-f1 +0.0009 |
| would remove | other | puno | 21 | 9 | 0.33 | macro-f1 +0.0126 |
| would remove | other | kable | 13 | 4 | 0.62 | macro-f1 +0.0000 |
| would remove | other | wires | 10 | 3 | 0.70 | macro-f1 +0.0000 |
| would remove | other | wire | 6 | 3 | 0.83 | macro-f1 +0.0000 |
| would remove | other | aso | 5 | 3 | 0.80 | macro-f1 +0.0000 |

No negator and no boundary word was added or removed: no word before a danger word cancelled it with precision 0.9, and no word between a negator and a danger word marked a danger note with precision 0.9 on enough notes.
