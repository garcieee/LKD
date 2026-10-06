# Evaluating the ticketing models

**Status: plan, with results added on 2026-10-06.** The plan was written and committed before any result existed, so the targets below could not be bent to fit the numbers. If a target changes, it changes in a dated note at the bottom, never silently. Results are in `eval/results/` and summarised in the Results section at the end.

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

Every evaluation ran on 2026-10-06. The targets above were not edited after any result existed; the dated notes under "Amendments" only say how a vague target was read. Each model has a report with its method, intervals and caveats. This section is the scorecard, what it means for the code, and what the team still has to decide. "Met" means the point estimate reached the target. Where the 95% bootstrap interval crosses the target, the table says so.

**Read every number as a stand-in.** The matcher was tested on a simulation and on Chicago, the priority score on five AI raters, belief on simulated votes, and the note classifiers on notes an AI wrote. None of it is Makati and none of it is people. "What real validation still needs" above lists the three small tests that would change that.

| Model | Report | Tested on |
|---|---|---|
| Same-place matcher | [simulated Makati](eval/matching/synthetic/REPORT.md), [real Chicago 311](eval/matching/chicago/REPORT.md) | a simulation with exact truth; a different city whose duplicate flag is the city's own rule |
| Priority score | [ranking](eval/ranking/REPORT.md) | 240 ticket pairs judged by five AI raters |
| Belief | [lifecycle](eval/lifecycle/REPORT.md) | simulated votes |
| Category hint, danger flag | [classification](eval/classification/REPORT.md) | 1,500 training and 400 gold notes, written by AI agents |
| Foot traffic | "Foot traffic check" below | 719 OpenStreetMap places, no ground truth |

### Scorecard

| Target | Result | Verdict |
|---|---|---|
| **Matcher, simulation** (test split, 18 checks) | 10 met, 8 missed; every miss is a precision or PR-AUC target | |
| Open sky: recall at least 0.90 | 0.96 | Met |
| Open sky: precision at least 0.95 | 0.92 / 0.90 / 0.86 at 20 / 60 / 150 hazards per km² | Missed |
| City: recall at least 0.85, B-cubed F1 at least 0.90 | 0.97; 0.944 / 0.937 / 0.923 | Met |
| City: PR-AUC at least 0.92 | 0.922 / 0.902 / 0.856 | Met at 20 per km² only, and the interval touches the line |
| City: precision at least 0.90 | 0.84 / 0.80 / 0.72 | Missed |
| Canyon: the reported accuracy above which auto-merge is off | 5 m. Auto-merge precision 0.774 without the cutoff, 0.903 with it; 83% of true pairs are then left to suggestions | Delivered |
| Cost: the radius with the lowest expected cost, a wrong merge costing 3 wrong splits | Per 1,000 reports: fixed 20 m 194, accuracy-aware with z = 2.0 199, shipped 216. At 1:1 the shipped rule is as cheap as any | Delivered. The shipped rule is not the cheapest at 3:1 |
| **Matcher, Chicago** (no absolute target) | The 44.5 m radius reaches 55% of pothole duplicates, 89% of street-light, 99.7% of sidewalk and 72% of water duplicates; Chicago pothole duplicates sit a median 37 m and 17 days from their parent. Shipped F1 0.583 against 0.617 for the best radius (difference -0.034 [-0.046, -0.022]); no fixed radius wins clearly; time adds nothing | Delivered |
| **Priority** (test, the 46 pairs with a majority label) | | |
| Pairwise accuracy at least 0.80 | 0.783 [0.652, 0.891] | Missed, by one pair |
| At least 0.90 times the human ceiling | 0.862 [0.727, 0.988] | Missed |
| Kendall tau-b at least 0.60 | 0.584 [0.421, 0.729] (0.664 on all 200 tickets) | Missed |
| NDCG@10 at least 0.85 | 0.945 [0.867, 0.988] | Met |
| Beats severity only, and the dashboard's current order | +0.315 [0.185, 0.446] and +0.337 [0.196, 0.468] | Met |
| Fitted weights replace the hand weights (at least +3 points on validation) | +4.2 points | The rule says replace. **Not applied**, see Amendments |
| **Belief** (test) | | |
| ECE at most 0.05 | 0.25 to 0.29 at every vote count | Missed, by about five times |
| Brier below always-0.8 | lower at every vote count (-0.071 at 1 vote, -0.156 at 3) | Met |
| ROC-AUC at least 0.75 at 3 votes | 0.925 [0.922, 0.929] | Met |
| **Category hint** (gold, 400 notes) | | |
| Macro-F1 at least 0.80 | list v0 0.814, list v1 0.830 (both intervals span 0.80), list v1 with normalisation 0.853, Naive Bayes 0.912, logistic regression 0.918, hybrid 0.895 | Met by all six |
| Precision at least 0.90 while answering at least 60% of notes | 0.925 to 0.990, answering 73% to 78% | Met by all six (the lists' intervals span 0.90) |
| A learned model replaces the list only if it wins by 0.05 | On plain macro-F1 the learned models win by 0.065 to 0.104 over the lists as shipped. At matched coverage the difference is -0.010 to +0.013 | Depends on the reading, see Amendments |
| **Danger flag** (gold) | | |
| Recall at least 0.90 and precision at least 0.60 | Lists: recall 0.72 to 0.83. Naive Bayes 0.948 / 0.730 and hybrid 0.948 / 0.829. Logistic regression recall 0.876 | Lists missed; Naive Bayes and hybrid met; logistic regression missed |
| PR-AUC at least 0.85 | Lists 0.723 to 0.778; Naive Bayes 0.943, logistic regression 0.955, hybrid 0.962 | Lists missed; learned models met |
| **Foot traffic** | | |
| Order of 500 random points when the scale is halved or doubled: Spearman rho at least 0.95 | 0.9976 halved, 0.9905 doubled, 0.9881 between the two | Met |
| The busiest spots are places a person would call busy | Transit stops, hospital and clinic clusters, a mall, a school (below) | A judgment by the maintainer alone |
| **Quality flag** | unit tests only (`tests/test_classify.py`) | |

### What it means for the product

- **Matching finds the repeats and pays for it in wrong merges.** In open sky and city conditions recall is 0.96 to 0.97 and precision 0.72 to 0.92, falling as hazards get denser and GPS worse (0.69 in canyons at 60 hazards per km²). That is the case for the 5 m auto-merge cutoff: above it, suggest, do not merge.
- **The priority queue puts the right tickets on top** (NDCG@10 0.945, and +0.337 pairwise accuracy over the dashboard's old order). It disagrees with the AI panel mostly on near-ties and on flooded drains, which it picks over another hazard 62% of the time against the panel's 27%.
- **Belief is a ranking aid, not a probability.** It orders tickets well (ROC-AUC 0.925 at 3 votes) but never gets confident (ECE 0.25 to 0.29). With reporters only, the usual case, it never changes a rank: the gate stays open.
- **A word list is enough for the category hint and not for danger.** All six configurations meet the category targets; only Naive Bayes and the hybrid meet the danger targets. If 30% of reports carry a note, about 22% of all reports would get a correct hint, against 25.8% for a perfect classifier. The note rate, not the model, is the limit.
- **Foot traffic keeps its order** when its scale changes. Its values are assumptions with no ground truth.

### Nothing in the shipped code changed

No value in `settings.py`, no word list in `resources/` and nothing under `matching/`, `ranking/` or `classification/` was changed because of these results. The last commit to any of them (`f153c80`) came before the first result existed. Every recommendation is below as a decision with its evidence and a default, so the team can say yes or no to each.

### Decisions for the team

| Decision | What the evidence says | Default until you decide |
|---|---|---|
| **"Likely gone" line**, `LIKELY_GONE_BELOW` 0.45 to 0.60 | The flag catches 0.472 of gone hazards instead of 0.151, at precision 0.981 and 1.1% of still-there votes flagged. Nothing reads the flag yet (`engine.py` is a stub). A 4 to 4 tie would now be flagged "verify" | Keep 0.45. Change it when the engine is wired; update `test_lifecycle.py` and `test_settings.py` with it |
| **Safety floors and "gone" taps** | The floors are multiplied by the gate, so a lone open manhole scores 67.0 (High), 49.1 after one wrong "gone" tap and 36.4 (Low) after two ([lifecycle report](eval/lifecycle/REPORT.md), section 4) | Decide whether a manhole may fall to Low on two taps. Not changed |
| **Cost of a wrong merge against a wrong split** | The matcher's radius depends on it. At 3:1 a fixed 20 m radius is cheapest (194 against 216 per 1,000 reports); at 1:1 the shipped rule is fine; at 5:1 a fixed 20 m costs 248 against 322. The 3:1 is the plan's assumption, not a finding | Ask who fixes a wrong merge, and how easily. Radius and `MATCH_Z` not changed |
| **Auto-merge cutoff**, 5 m reported accuracy | Raises auto-merge precision from 0.774 to 0.903, but leaves 83% of true pairs to suggestions | Not built. The engine is a stub, so nothing auto-merges yet |
| **Flooded-drain severity**, 0.85 to 0.65 | The one change whose validation interval excludes zero (+0.083 [0.021, 0.167]). The evidence is five AI personas; real Makati staff may disagree. The floor of 48 stays | Keep 0.85 until a person from the city answers |
| **Weights** | The pre-registered rule says replace (+4.2 points), but the gain is all in near-tie pairs. Both fits put foot traffic at 0.26 to 0.31 against the hand 0.18 | Keep the hand weights. Re-run the rule on pairs drawn without looking at the score |
| **Which classifier** | The report recommends the hybrid (logistic regression on tf-idf plus the list scores) after a check on 30 to 60 real notes, and list v1 with normalisation as the rules-only fallback. The hybrid needs a pure-Python scorer (word and character n-gram tf-idf with the idf values in a JSON file, a dot product per class) tested against `baselines.py`, or scikit-learn on the server | Ship nothing new yet. `lexicon_v1.json` is not swapped into `resources/lexicon.json` |
| **Reopening a fixed ticket** | In the Chicago replay 37% of pothole merges and 45% of street-light merges join a ticket that was already fixed. Allowing that, as shipped, lowers pairwise F1 against the city's tickets by 0.155 (potholes), 0.217 (street lights) and 0.196 (water). The city's labels cannot say whether it is right | A staff policy: reopen, or open a new ticket. Not changed |
| **Duplicate OSM nodes** in `places.json` | A station with several OSM nodes counts several times. Counting same-kind places within 30 m once removes 90 of 719 places, changes the order of the 500 points very little (rho 0.989) and lowers their median from 0.42 to 0.39 | Keep `places.json`. If it changes, re-run the ranking evaluation, whose foot-traffic values came from it |

### Foot traffic check

Written and run by the maintainer after the other results ([`eval/ranking/exposure_check.py`](eval/ranking/exposure_check.py), numbers in `eval/results/ranking_exposure_check.json`). Five hundred random points in the Makati box were scored with `EXPOSURE_SCALE` halved, as shipped and doubled: Spearman rho against the shipped order is 0.9976 and 0.9905. The order moves only where points hit the 0.1 floor (15% of points at half the scale, 20% as shipped, 30% at double). The 500 points have a median of 0.42 and a 90th percentile of 0.81.

The ten busiest spots on a 50 m grid, at least 400 m apart, are five transit stops (One Ayala, EDSA, Magallanes, San Andres, Paco), three hospital and clinic clusters, a mall with clinics beside it, and a school. Most of them a person would call busy. The doubtful ones are San Andres and Paco, which rank high largely because each has three rail nodes within 10 m, so one station scores as three, and the clinic clusters, because every clinic pulls with weight 1.0 and a street of clinics ranks beside a transit hub. With same-kind places within 30 m counted once, three of the ten change: EDSA, San Andres and Paco drop out and Boni, Guadalupe and Salcedo Saturday Market come in. Someone who knows Makati should read both lists in the json.

### How the numbers were produced

- **Chicago:** while building, the agent ran the evaluation with 20 bootstrap resamples and so saw test tables. The one design change that followed, the 60 m cap, came from how the data was built (an empty 60 to 100 m ring), not from a test number. The final runs use 1,000 resamples and were repeated on the final code with identical numbers.
- **Simulated matching:** the final run (seeds 2024) was made once and refuses to run twice. One later script looked at the test split again for a single configuration, the cutoff chosen on validation. Sweeps use other seeds and tune nothing.
- **Belief:** test seeds were used once at the end and nothing changed after. The sweeps use the test seeds too and tune nothing.
- **Priority:** the hand weights were never fitted to any pair. The survey was built from the score's own gaps, which makes a third of its pairs near-ties, against 15% of all ticket pairs.
- **Notes:** the gold notes were written by an agent that never saw the training notes or the word lists. Each of the six final configurations scored gold once, and `gold_runs.log` has six lines. The agent changed its term-removal rule to a symmetric one after seeing validation scores, not gold. After the exam it edited only report code (hashes are in the report). Gold scores are higher than validation partly because of the class mix.
- **All AI-written data** (notes, ticket judgments) is a proxy. Real residents write messier notes, and real people are noisier than AI raters, who followed their own urgency scores in 96% to 99% of pairs.
- **Reproduce:** each report ends with its commands. `models/.venv/bin/pytest models` runs all 589 tests; the rule tests alone run with `server/.venv/bin/pytest models/tickets/tests`.

### Not tested at all

The accuracy-aware part of the matcher on real phone GPS (Chicago coordinates are geocoded addresses), the engine and storage (still stubs), the share of reports that will carry a note, and anything with a real Makati resident in the loop.

## Amendments

Nothing above was edited after results existed. These notes say how an unclear target was read, or what was done that the plan did not say. Each is also in the report it belongs to.

- **2026-10-06, how bunched hazards are.** The plan did not say. The simulator puts half of the hazards in clusters (a guess, swept). The matcher's precision misses lean on it: with unclustered hazards the open-sky and city precision targets hold at 20 and 60 hazards per km² and fail only at 150.
- **2026-10-06, the 3:1 cost.** The plan assumed a wrong merge costs 3 wrong splits and also showed 1:1 and 5:1. The answer changes with the ratio (see Decisions), so 3:1 is an assumption to confirm, not a result.
- **2026-10-06, Chicago negatives.** A near non-duplicate is an open ticket within 60 m that the city did not name as the parent, and the city's rule may have missed it, so hard-set precision is not a false-merge rate. No variant merges beyond 60 m, the matcher's own cap.
- **2026-10-06, priority: which pairs and which weights.** "Test pairs where the raters agree" was read as every test pair with a majority label (46 of 48). On the 4-of-5 and unanimous subsets the 0.80 target is reached on the point estimate and the ceiling ratio is still missed; both are in the report. The weights rule says replace, but the fitted weights' gain sits in near-ties and the survey over-samples them, so the hand weights stay until the rule is re-run on unbiased pairs.
- **2026-10-06, belief: counting votes.** "3 votes" means three taps after the first report. If the reporter counts as a vote, the row is the 2-vote row and no verdict changes.
- **2026-10-06, category hint: classes and the 0.05 rule.** The plan says 6-class; the scorer uses seven: the five real categories, "other", and "none" for a note that names no hazard. The replace-the-list rule was run on plain macro-F1, where each abstention of the list counts as "none", and again at matched coverage. The first says replace and the second says keep, because the learned models win by answering more notes, not by being more accurate on the notes the lists answer. Both are in the report.
- **2026-10-06, foot traffic.** The plan said "sanity checks only". The check was written and run after the other results, so no result could have steered it.

## Sources

- Saito and Rehmsmeier (2015), [The precision-recall plot is more informative than the ROC plot on imbalanced datasets](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4349800/)
- [A practitioner's guide to evaluating entity resolution results](https://arxiv.org/pdf/1509.04238)
- Zheng et al. (2023), [Judging LLM-as-a-judge with MT-Bench and Chatbot Arena](https://arxiv.org/abs/2306.05685)
- Shi et al. (2024), [Judging the judges: a systematic study of position bias in LLM-as-a-judge](https://arxiv.org/html/2406.07791v9)
- Merry and Bettinger (2019), [Smartphone GPS accuracy study in an urban environment](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6638960/)
- [GPS.gov: GPS accuracy](https://archive.gps.gov/systems/gps/performance/accuracy/)
- [City of Chicago 311 service requests](https://data.cityofchicago.org/): how duplicates are flagged for [potholes](https://catalog-beta.data.gov/dataset/311-service-requests-pot-holes-reported-historical)
