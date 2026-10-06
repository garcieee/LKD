# Evaluating the ticketing models

**Status: plan.** Written and committed before any result exists, so the targets below cannot be bent to fit the numbers. If a target changes, it changes in a dated note at the bottom, never silently. Results land in `eval/results/` and in the Results section at the end.

## What is evaluated

| Model | Decides | Kind | Where |
|---|---|---|---|
| Same-place matcher | does a new report join an existing ticket? | pair decision, then clusters | `matching/` |
| Priority score | which of two tickets comes first? | ranking | `ranking/priority.py` |
| Belief | is the hazard still there? | probability | `ranking/lifecycle.py` |
| Category hint | which category does the note describe? | 6-class text | `classification/` |
| Danger flag | does the note describe danger to people? | binary text | `classification/` |
| Quality flag | should staff look at this report first? | rules on fields the phone sends | `classification/`: unit tests only |
| Foot traffic | how many people walk past? | score | `ranking/exposure.py`: sanity checks only, there is no ground truth |

## Metrics, and why these

- **Rare positives** (duplicates among nearby pairs, danger notes): the headline is **PR-AUC** (average precision), with ROC-AUC beside it. On imbalanced data a ROC curve can look excellent while most alarms are false (Saito and Rehmsmeier, 2015).
- **Every classifier:** **precision, recall and F1** at the chosen operating point. Where a miss is the costly mistake (danger notes) we also report **F2**; where a wrong call is (merging two hazards) we also report **F0.5**.
- **Clusters (tickets):** pairwise F1 can look too good, so we add **B-cubed** and the **adjusted Rand index** (see the practitioner's guide to entity-resolution evaluation).
- **Ranking:** **pairwise accuracy** (the same number as AUC over pairs), **Kendall tau-b**, **NDCG@10**, Spearman rho.
- **Probabilities:** **Brier score**, **ECE** (10 bins) and a reliability curve.
- **Every test number carries a bootstrap 95% interval** (1,000 resamples). The test sets are small, so a score without an interval is not reported.

## Data

| Data | Real? | Used for | Size | Caveat |
|---|---|---|---|---|
| Chicago 311: potholes 2024-25, street lights out, sidewalks, water on street 2025 | real | matcher | about 144k rows, 29 MB csv | The duplicate flag comes from the city's own address-buffer rule, not independent truth. Coordinates are geocoded addresses, not phone GPS. Chicago is not Makati |
| Simulated hazards and reporters | synthetic, exact truth | matcher | generated | GPS error follows Merry and Bettinger (7-13 m mean error in a city) and GPS.gov (4.9 m open sky) |
| Notes in Taglish and English | synthetic, agent-written | category hint, danger flag | about 1,500 train and validation, about 300 gold | Scores will overstate real ones |
| OpenStreetMap places | real | foot traffic | 719 places | OSM coverage is uneven |
| Ticket pairs with judgments from 5 LLM raters | synthetic tickets, proxy labels | priority | about 240 pairs | LLM judges agree with people about 80% of the time, as often as people agree with each other (Zheng et al., 2023), but show position bias (Shi et al., 2024) |
| Votes | simulated | belief | generated | assumes honest voters |

The raw Chicago download stays out of git (`eval/data/raw/`). Only small derived files and results are committed. Cite the City of Chicago data portal and check its terms before redistributing anything.

## Splits (no leakage)

- **Chicago, by time:** train 2024-01 to 2025-06, validation 2025-07 to 2025-09, test 2025-10 to 2025-12. Pairs are built inside one split and no ticket crosses a boundary. A second test holds out whole grid blocks (about 20%) to check that the result carries to other places.
- **Simulation, by district:** 60/20/20 across simulated districts. A **profile-shift test** tunes on open-sky and city profiles and tests on tall-building canyons.
- **Notes, by template family:** train and validation never share a family. The **gold set** is written by a different agent that never sees the training notes or the word lists, and is opened only for the final run.
- **Priority:** tickets are split 60/20/20 first and pairs are formed inside each split.
- **Belief:** separate simulation seeds for train, validation and test.

## Rules of the procedure

1. Tune on train, choose the operating point on validation, run the test split once per final configuration. Each run records its config, seeds and git commit in `eval/results/`.
2. Every model is compared with a simple baseline (fixed radius, severity only, word list only, always 0.8). The simple one stays unless the complex one wins with the 95% interval of the paired difference clear of zero.
3. Metrics, splits and simulators have unit tests. The tests run after every change, not once at the end.
4. Agents write only inside their own folder and never touch git. The maintainer reviews, runs the tests and commits.

## Targets (pre-registered)

**Same-place matcher** (test split)

| Setting | Target |
|---|---|
| Simulation, open sky (accuracy about 5 m) | precision at least 0.95, recall at least 0.90 |
| Simulation, city (about 10 m) | precision at least 0.90, recall at least 0.85, PR-AUC at least 0.92, B-cubed F1 at least 0.90 |
| Simulation, tall-building canyon (about 20 m) | no target. Deliverable: the reported-accuracy cutoff above which auto-merge is switched off and the app only suggests. Rule: switch off where validation precision is below 0.85 |
| Chicago (real) | no absolute target, because the labels are the city's rule. Deliverables: share of city-flagged duplicates inside our radius; share of our merges the city did not flag; distance and time-gap quantiles of the city's duplicate pairs next to our radius; fixed against accuracy-aware radius on the same pairs |
| Cost | A wrong merge is assumed to cost 3 times a wrong split (also shown at 1:1 and 5:1). Pick the radius that minimises expected cost on validation |

**Priority score** (test pairs where the raters agree)

- Pairwise accuracy at least 0.80, and at least 0.90 times the leave-one-rater-out agreement (the ceiling a human could reach).
- Kendall tau-b at least 0.60 and NDCG@10 at least 0.85 against the panel's mean urgency.
- Beats severity-only and the dashboard's current order (unresolved, then severity, then oldest), with the 95% interval of the difference above zero.
- Weights fitted by Bradley-Terry replace the hand weights only if they win on validation by at least 3 points of pairwise accuracy and stay non-negative. Otherwise the hand weights stay, because they are easier to explain.

**Belief:** ECE at most 0.05, Brier score below the always-0.8 baseline, ROC-AUC at least 0.75 once there are 3 votes.

**Category hint** (gold set, notes that are not empty): macro-F1 at least 0.80, and precision at least 0.90 while answering at least 60% of notes (the rest abstain). The word list stays unless a learned model (Naive Bayes or logistic regression on tf-idf) beats its macro-F1 by at least 0.05 with the interval clear of zero.

**Danger flag** (gold set): recall at least 0.90 and precision at least 0.60 at the F2-best threshold chosen on validation. PR-AUC at least 0.85 for any model that produces a score.

**Foot traffic:** the ranking of 500 random Makati points must barely move when the scale changes by half or double (Spearman rho at least 0.95), and the busiest spots must be places a person would call busy.

## Who does what

| Agent | Owns | Delivers |
|---|---|---|
| matching-real | `eval/matching/chicago/` | the download, pair sets, split manifests, distance and time statistics, results |
| matching-sim | `eval/matching/synthetic/` | simulator, datasets for the three GPS profiles, results |
| notes-train | `eval/classification/data/notes_train.jsonl` | about 1,500 labelled notes |
| notes-gold | `eval/classification/data/notes_gold.jsonl` | about 300 hard notes, written blind |
| lifecycle | `eval/lifecycle/` | vote simulator, calibration results |
| pairs and 5 raters | `eval/ranking/` | ticket pairs, judgments from an engineer, a barangay captain, a wheelchair user, a commuter and a paramedic |
| classification-eval | `eval/classification/` | baselines, thresholds, results |
| ranking-eval | `eval/ranking/` | agreement, fits, ablations, results |
| maintainer | `eval/common/`, `settings.py`, `resources/`, this file | shared metric code with tests, review, commits |

Run the tests: `server/.venv/bin/pytest models` for the rules, `models/.venv/bin/pytest models/tickets/eval` for the evaluation code (needs numpy, scipy and scikit-learn).

## What real validation still needs

Nothing here replaces people. Before anyone relies on these numbers: (1) five teammates report the same pothole and two neighbouring hazards from different spots, to measure real split and merge rates; (2) five to ten people answer the same ticket pairs the LLM raters saw; (3) thirty to sixty real notes from real people go through the classifiers.

## Results

To be filled as each evaluation finishes.

## Sources

- Saito and Rehmsmeier (2015), [The precision-recall plot is more informative than the ROC plot on imbalanced datasets](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4349800/)
- [A practitioner's guide to evaluating entity resolution results](https://arxiv.org/pdf/1509.04238)
- Zheng et al. (2023), [Judging LLM-as-a-judge with MT-Bench and Chatbot Arena](https://arxiv.org/abs/2306.05685)
- Shi et al. (2024), [Judging the judges: a systematic study of position bias in LLM-as-a-judge](https://arxiv.org/html/2406.07791v9)
- Merry and Bettinger (2019), [Smartphone GPS accuracy study in an urban environment](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6638960/)
- [GPS.gov: GPS accuracy](https://archive.gps.gov/systems/gps/performance/accuracy/)
- [City of Chicago 311 service requests](https://data.cityofchicago.org/): how duplicates are flagged for [potholes](https://catalog-beta.data.gov/dataset/311-service-requests-pot-holes-reported-historical)
