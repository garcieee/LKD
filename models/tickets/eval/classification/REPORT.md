# Classification evaluation: the category hint and the danger flag

Status: finished. Gold was scored once per configuration (six lines in `gold_runs.log`). Every number below is in `models/tickets/eval/results/classification_*.json`; figures are the `classification_*.png` beside them. Plan and targets: `models/tickets/EVALUATION.md`.

**Read this first.** An AI agent wrote both note sets (train and gold), in a clean imitation of Makati texting. Real residents will be messier, so every score here is better than what the app will see. The gold set is hard on purpose and still has only 2 emoji in 400 notes. Slices hold 16 to 25 notes, so gaps under about 0.15 inside a slice are noise (the gold notes say the same).

## 1. Verdict

| Target (gold, EVALUATION.md) | list v0 | list v1 | list v1 + normalisation | Naive Bayes | logistic regression | hybrid |
|---|---|---|---|---|---|---|
| Category macro-F1 at least 0.80 | met 0.814 (interval spans 0.80) | met 0.830 (spans 0.80) | met 0.853 | met 0.912 | met 0.918 | met 0.895 |
| Precision at least 0.90 while answering at least 60% (validation-chosen setting) | met 0.929 at 0.738 (interval spans 0.90) | met 0.925 at 0.765 (spans 0.90) | met 0.927 at 0.782 (spans 0.90) | met 0.990 at 0.728 | met 0.969 at 0.733 | met 0.945 at 0.770 |
| Danger recall at least 0.90 and precision at least 0.60, at the F2-best validation threshold | **missed**: recall 0.722, precision 0.854 | **missed**: recall 0.804, precision 0.812 | **missed**: recall 0.825, precision 0.792 | met: recall 0.948, precision 0.730 | **missed**: recall 0.876 (interval spans 0.90), precision 0.885 | met: recall 0.948, precision 0.829 |
| Danger PR-AUC at least 0.85 | **missed** 0.723 | **missed** 0.770 | **missed** 0.778 | met 0.943 | met 0.955 | met 0.962 |

"Met" is the point estimate reaching the target. Where I wrote that the interval spans the target, the 95% bootstrap interval includes it, so the data cannot say the target is truly met. For NB and the hybrid every "met" has its whole interval above the target.

- **Decision rule (word list stays unless a learned model beats its macro-F1 by at least 0.05, interval clear of zero).** Applied as written (7-class macro-F1 of the plain prediction: the list at its shipped thresholds, a model's argmax) the word list does **not** stay. Naive Bayes, logistic regression and the hybrid beat v0 and v1 by 0.065 to 0.104, every interval above zero. Against the list with normalisation, NB (+0.059) and LR (+0.065) still win, the hybrid (+0.042) does not. **Caveat that matters:** the plain macro-F1 counts every abstention of the list as "none", and 85% of the list's errors are abstentions. At a matched operating point no learned model beats the best list (v1 with normalisation) by 0.05 (differences -0.010 to +0.013, all intervals span zero). At the operating points all six configurations answer 73 to 78% of notes at precision 0.925 to 0.990 (lists 0.925 to 0.929, models 0.945 to 0.990). Un-thresholded, the models answer 83 to 87% of notes at precision 0.91 to 0.92, the lists 69 to 73% at 0.96 to 0.97. List v1 with normalisation at its shipped thresholds answers 73.3% at precision 0.969, exactly what LR gets at its chosen point. So for the category hint the models win by answering more notes, not by being more accurate on the notes the lists answer.
- **Danger is not close.** Every learned model beats every list on PR-AUC by +0.165 to +0.239, intervals far above zero. Only NB and the hybrid meet the recall and precision target.
- **Practical reach.** If only 30% of reports carry a note, the best configurations give a correct hint to about 22% of all reports (hybrid 0.218, interval 0.206 to 0.231). A perfect classifier could reach 25.8% (30% times the 86% of gold notes that name a hazard). The note rate, not the model, is the limit.
- **Recommendation (section 8):** ship the hybrid (logistic regression on tf-idf plus the v0 list scores) for both helpers, after a 30 to 60 note check on real notes; keep list v1 with normalisation as the rules-only fallback.

## 2. What was run and how

| Step | File | Output |
|---|---|---|
| Word list v1 from train notes only | `tune_lexicon.py` | `lexicon_v1.json`, `LEXICON_CHANGES.md`, `results/classification_lexicon.json` |
| Normalisation variants on validation | `variants.py` | `results/classification_variants.json` |
| Learned baselines, settings chosen on validation | `baselines.py` | `results/classification_learned.json` |
| Baseline v0, every configuration on validation, operating points frozen | `evaluate.py` | `results/classification_validation.json`, `classification_final_config.json`, `*_validation_*.png` |
| Validation repeated on 10 other splits (diagnostic) | `evaluate.py --robustness 10` | `results/classification_robustness.json` |
| The final exam, report and error analysis | `final_gold.py` | `gold_runs.log`, `results/classification_gold*.json`, `*_gold_*.png` |

**Split.** `common.splits.group_split` on the 80 families, fractions 0.75/0.25, seed 4: train 1,120 notes in 60 families, validation 380 notes in 20 families. Seed 4 is the first seed where validation holds at least 2 families of every category and at least 4 danger families (seeds 0 to 3 leave a category with one family or none; `test_evaluate.py` re-checks this). The seed was never chosen by a score. Validation families per category: pothole 2, open_manhole 3, flooded_drain 3, broken_streetlight 3, blocked_sidewalk 2, other 2, none 5; 5 danger families (82 danger notes, 21.6%). Category and danger are constant inside a family, so validation is really 20 scenarios.

**Gold rule.** Nothing opened, printed or sampled a gold row before the exam. Only `final_gold.py` names the gold file (a test checks the other modules); it appends `timestamp, name` (plus `forced`) to `gold_runs.log` before it reads the notes and refuses a name already in the log. The log has exactly six lines: `lexicon_v0`, `lexicon_v1`, `lexicon_v1+repeats+prefix+suffix+typo1_strict`, `naive_bayes`, `logistic_regression`, `hybrid`. I rehearsed the whole script twice on a stand-in file built from validation notes, with a throwaway log in a temporary folder. The pre-existing `test_schema.py` parses the gold file for validity on every test run; it prints nothing. I read `NOTES_GOLD.md` only after the exam.

**After the exam I changed only reporting code.** `final_gold.py` gained the by-category and by-language tables and shorter figure labels, and `--report` was re-run from the saved predictions (no re-scoring, the log is unchanged, every number in the earlier output is identical). SHA-256 of everything that decides a prediction was recorded before the exam and is unchanged (first 12 hex digits): `evaluate.py` 8eb4bf69c569, `baselines.py` 42e989d3b946, `variants.py` 35f3201b065e, `tune_lexicon.py` 19ee1e9b5793, `lexicon_v1.json` 8cfcf0eeab59, `classification_final_config.json` 77c74f01e4db, `resources/lexicon.json` 6935f74af7b2, `classify.py` 4af38a1bd9e8, `settings.py` b2500745307b. `final_gold.py` was a6fdb44a4d7a at the exam and is 5425adc1246f now (report code only). The gold result is **not contaminated** by my definition; the soft spot is in section 9.

**Learned models are refitted on train plus validation** (all 80 families) with the settings chosen on validation, before the gold run. The word lists are fixed files. Probability thresholds were chosen on validation from the train-only models and carried to the refitted ones, which is why coverage on gold differs from 60%.

**Intervals.** 1,000 bootstrap resamples over notes (`common.metrics.bootstrap_ci`, seed 0); comparisons use `paired_bootstrap_diff` on the same resamples. On validation, where notes in a family are alike, I also resampled whole families (`family_bootstrap` in `evaluate.py`), which is the honest width there.

## 3. Task 1: baseline, the shipped list v0, on validation

Category, hint at the shipped thresholds (min score 1.0, margin 0.5); no hint counts as "none".

| 7-class macro-F1 | accuracy | coverage (notes with a hint) | precision of hints shown |
|---|---|---|---|
| 0.745 (family interval 0.602 to 0.850) | 0.739 | 0.497 | 0.958 |

Per class (precision, recall, notes): pothole 0.96, 0.54, 41; open_manhole 0.93, 0.98, 53; flooded_drain 0.95, 0.67, 54; broken_streetlight 1.00, 0.57, 53; blocked_sidewalk 1.00, 0.72, 32; other 0.95, 0.38, 47; none 0.52, 1.00, 100. Confusion matrix (rows true, columns predicted, in the order pothole, open_manhole, flooded_drain, broken_streetlight, blocked_sidewalk, other, none):

```
pothole              22   0   1   0   0   0  18
open_manhole          0  52   0   0   0   0   1
flooded_drain         0   4  36   0   0   0  14
broken_streetlight    0   0   0  30   0   0  23
blocked_sidewalk      0   0   0   0  23   1   8
other                 1   0   1   0   0  18  27
none                  0   0   0   0   0   0 100
```

The list is precise and incomplete: 91 of its 99 errors are a hazard note that got no hint. **It cannot reach 60% coverage by any threshold**: the widest setting (min score 1.0, margin 0.0, ties broken by lexicon order) answers 55.3% at precision 0.895.

Danger, the score `classify.danger_score` (prevalence 0.216): PR-AUC 0.774, ROC-AUC 0.880. At the shipped threshold (score at least 1.0): precision 0.877, recall 0.780, F1 0.826, F2 0.798. The F1-best and the F2-best thresholds are both 1.0 (same numbers). Recall at precision 0.60: 0.780. Precision at recall 0.90: 0.216, which is the base rate: recall 0.90 is only reached by flagging every note.

## 4. Task 2: improving the word list, train notes only

`tune_lexicon.py` has one rule used both ways. A term (word, phrase, negator, boundary word) is judged when it is in at least 5 train notes across at least 3 families; its precision is the share of those notes that carry its class (the category; danger for a danger word, counted only where classify.py would not cancel it; not-danger for a negator; danger for a boundary word). Add a new term at precision 0.9 or more. Remove a v0 term when it is judged and at most 0.1 of its notes carry its class. Everything between stays and is logged as weak. Two guards only ever remove candidates: a phrase may not contain a term the list already has, and may not start or end with a function word. Every change, its evidence and its effect on validation: `LEXICON_CHANGES.md`.

**What changed.** 29 terms added, 1 removed, no negator or boundary word touched.
- pothole: hole, butas, lumalaki, laki. open_manhole: takip. flooded_drain: linisin.
- broken_streetlight: patay, lamp, dead, meralco, bulb, umiilaw, light pole. blocked_sidewalk: daanan, parked, kotse, madaanan, materials, nakaparadang, space.
- danger: baka, could, batang, walking, bka, pauwi, will, aso, scary.
- removed from `other`: basura (9 train notes in 4 families, none labelled other, because the train garbage notes are clogged drains).
- Largest single effects on validation: hole +0.0245 macro-F1, butas +0.0181, lamp +0.0121; baka +0.0265 PR-AUC, bka +0.0176, batang +0.0103. The removal of basura cost -0.0296 (validation has garbage notes labelled other).
- Some terms passed the bar by luck of the train families (walking, will, could, space, laki, materials are generic words). Expect noise from them on real notes.
- The 3-family bar cannot learn a rare theme: `other` got no additions, and `other` is the list's weakest class (gold recall 0.62).

| Validation | category macro-F1 (shipped thresholds) | danger PR-AUC |
|---|---|---|
| v0 | 0.745 | 0.774 |
| v1 | 0.784 (+0.038) | 0.845 (+0.071) |
| v1 plus removing every weak term (the literal "remove below 0.9" rule) | 0.692 | 0.798 |

**How the removal rule was chosen, plainly.** I first coded removal as "judged and precision below 0.9". That removed 30 v0 terms including sidewalk (precision 0.8974), manhole, baha, poste, hurt and fell, and validation macro-F1 fell to about 0.70 (below v0). I then switched to the symmetric reading above. That switch followed a validation result, so v1 is partly shaped by validation; the literal-rule number stays in `classification_lexicon.json` and in the log, and every v1 change still stands on train evidence alone. The 29 weak terms cost real recall when removed (sidewalk -0.040 macro-F1, poste -0.032, baha -0.023, manhole -0.020; hurt -0.026 PR-AUC, fell -0.022): a word can be the best cue its class has at precision 0.8.

### Normalisation variants (validation, on v1; the v0 rows are in the json)

`variants.py` puts a text step in front of the unchanged classify functions (punctuation is kept, so negation reach is unchanged): `repeats` squeezes runs of one letter in the note and in the list's words; `typo1` rewrites a word one edit away from a list word of 6+ letters when exactly one fits; `typo1_strict` wants 7+ letters and the same first letter; `typo1_naive` drops the length floor (a control); `prefix` strips a leading mag-/nag-/na- and `suffix_ng` a trailing -ng when what is left is a list word. A list word is never rewritten.

| Variant | macro-F1 | change | coverage | hint precision | danger PR-AUC | change | words rewritten |
|---|---|---|---|---|---|---|---|
| none (v1) | 0.7836 | | 0.555 | 0.953 | 0.8449 | | |
| repeats | 0.7836 | +0.0000 | 0.555 | 0.953 | 0.8449 | +0.0000 | 373 |
| typo1 | 0.7965 | +0.0130 | 0.568 | 0.954 | 0.8364 | -0.0085 | 39 |
| typo1_strict | 0.7949 | +0.0113 | 0.563 | 0.958 | 0.8397 | -0.0052 | 13 |
| typo1_naive | 0.7787 | -0.0049 | 0.587 | 0.919 | 0.7496 | **-0.0953** | 213 |
| prefix | 0.7860 | +0.0024 | 0.558 | 0.953 | 0.8449 | +0.0000 | 2 |
| suffix_ng | 0.7836 | +0.0000 | 0.555 | 0.953 | 0.8449 | +0.0000 | 1 |
| repeats+prefix+suffix | 0.7860 | +0.0024 | 0.558 | 0.953 | 0.8449 | +0.0000 | 376 |
| repeats+prefix+suffix+typo1 | 0.7981 | +0.0145 | 0.574 | 0.950 | 0.8397 | -0.0052 | 408 |
| **repeats+prefix+suffix+typo1_strict** | 0.7972 | +0.0137 | 0.566 | 0.958 | 0.8449 | +0.0000 | 385 |

- **Which help, by how much (validation):** only typo matching moves anything (+0.011 to +0.013 macro-F1; family-bootstrap interval of the strict combination minus v1: +0.003 to +0.027). Prefix adds +0.002, suffix and repeats nothing: train and validation hold no elongated words (8 tokens with three equal letters, all genuine Filipino doubling like "maaayos"), 2 prefix hits and 1 suffix hit.
- **The naive typo rule is harmful** (-0.095 PR-AUC): "bahay" becomes "baha", "lang" becomes "lane", "night" and "right" become "light". Even the guarded rule makes false friends: rains to drains, through to though, nearby to nearly, sparking to parking, marked to parked, sensor to senior. That is why `typo1_strict` (same first letter, 7+ letters) was preferred.
- **Carried to gold:** the variant with the largest macro-F1 plus PR-AUC gain, `repeats+prefix+suffix+typo1_strict` (+0.0137 and 0.0000), as `lexicon_v1+repeats+prefix+suffix+typo1_strict`. Only this combination was scored on gold, so the gold effect cannot be split by step.
- **On gold** (section 6): +0.023 macro-F1 over v1 (interval +0.009 to +0.041), PR-AUC +0.008 (interval -0.011 to +0.030); the `typo` slice goes from 0.60 to 0.80 accuracy. The steps cut both ways: "asong" becoming "aso" fixed "matandang" (elderly) in one note and turned a stray-dog nuisance note into a danger flag in another.
- **Recommendation:** worth adding to classify.py if the list stays in use (section 8). Pure Python, about 60 lines.

## 5. Tasks 3 and 4: learned baselines and operating points

Features: tf-idf of word 1-2 grams plus tf-idf of character 3-5 grams (inside word edges), on the text as `classify.tokens` normalises it. Each model is fitted twice, once for the 7-class category and once for danger. Chosen on validation (macro-F1 for the category, PR-AUC for danger):

| Model | Category | Danger |
|---|---|---|
| Naive Bayes | complement, alpha 0.3 | multinomial, alpha 0.03 (binary complement and multinomial score identically) |
| Logistic regression | C = 10,000 (macro-F1 rises with C: 0.705 at 3, 0.760 at 1,000, 0.795 at 3,000, 0.802 at 10,000 and 30,000) | C = 100 |
| Hybrid | C = 30, list-score weight 2.0 | C = 30, weight 0.5 |

The hybrid is logistic regression whose input also holds the v0 list's six category scores and its danger score. v0, not v1, on purpose: v1's terms were picked on the very train notes the model fits, which would leak. The category model needing almost no regularisation is a sign that 20 validation families are a thin basis for choosing C.

**Operating points, from validation only** (`classification_final_config.json`). Category: the most precise setting that still answers at least 60% of validation notes. Danger: the F2-best threshold (the one the target uses), and the one for recall 0.90.

| Configuration | Hint setting | Validation coverage / precision there | Danger F2-best threshold | Danger recall-0.90 threshold |
|---|---|---|---|---|
| list v0 | score 1.0, margin 0.0 (**60% not reached**) | 0.553 / 0.895 | 1.0 | 0.0 (flags everything) |
| list v1 | score 1.0, margin 0.0 | 0.611 / 0.901 | 1.0 | 0.0 |
| list v1 + normalisation | score 1.0, margin 0.0 | 0.624 / 0.903 | 1.0 | 0.0 |
| Naive Bayes | max prob 0.531 | 0.608 / 0.857 | 0.030 | 0.113 |
| logistic regression | max prob 0.897 | 0.603 / 0.926 | 0.189 | 0.221 |
| hybrid | max prob 0.636 | 0.629 / 0.937 | 0.095 | 0.182 |

**Validation table** (default prediction; brackets are family-bootstrap intervals; the last column is at the F2-best threshold, precision / recall). These numbers are optimistic for the learned models because their settings were picked on this set.

| Configuration | macro-F1 | accuracy | coverage / precision (default) | coverage / precision (chosen point) | danger PR-AUC | ROC-AUC | precision / recall |
|---|---|---|---|---|---|---|---|
| list v0 | 0.745 [0.602, 0.850] | 0.739 | 0.497 / 0.958 | 0.553 / 0.895 | 0.774 [0.580, 0.887] | 0.880 | 0.877 / 0.780 |
| list v1 | 0.784 [0.667, 0.900] | 0.792 | 0.555 / 0.953 | 0.611 / 0.901 | 0.845 [0.681, 0.914] | 0.929 | 0.878 / 0.878 |
| list v1 + normalisation | 0.797 [0.677, 0.911] | 0.805 | 0.566 / 0.958 | 0.624 / 0.903 | 0.845 [0.681, 0.914] | 0.929 | 0.878 / 0.878 |
| Naive Bayes | 0.639 [0.518, 0.809] | 0.666 | 0.924 / 0.644 | 0.608 / 0.857 | 0.938 [0.841, 0.974] | 0.976 | 0.731 / 0.963 |
| logistic regression | 0.802 [0.697, 0.905] | 0.808 | 0.808 / 0.779 | 0.603 / 0.926 | 0.956 [0.849, 0.988] | 0.983 | 0.904 / 0.915 |
| hybrid | 0.831 [0.727, 0.920] | 0.832 | 0.779 / 0.818 | 0.629 / 0.937 | 0.971 [0.912, 0.991] | 0.988 | 0.849 / 0.963 |

**How much to trust validation.** The family intervals are wide: macro-F1 gaps between lists and models cross zero (hybrid minus v1 +0.048 [-0.032, +0.134]); PR-AUC gaps do not (+0.126 [+0.074, +0.248]). To see whether one split misled me I repeated the recipe on the splits of seeds 0 to 9 (v1 rebuilt from each train half, models re-chosen on each validation half; no seed rule; `classification_robustness.json`). Mean macro-F1: v0 0.771, v1 0.815, NB 0.746, LR 0.851, hybrid 0.867 (SD 0.05 to 0.10). Mean PR-AUC: v0 0.790, v1 0.830, NB 0.932, LR 0.937, hybrid 0.958. v1 beats v0 on macro-F1 in 10 of 10 splits and on PR-AUC in 9; the hybrid beats v1 in 8 of 10 (macro-F1) and 10 of 10 (PR-AUC). Validation macro-F1 is pulled down by validation's 26% "none" notes (gold has 14%): every configuration scores higher on gold than on validation.

## 6. Tasks 5 and 6: the gold exam

Gold: 400 notes, 97 danger (24.25%), 211 in 11 difficulty slices. Brackets are 95% bootstrap intervals over notes.

### Category hint

Default prediction (the list at the shipped thresholds, a model's argmax; this is the macro-F1 the decision rule reads):

| Configuration | macro-F1 | accuracy | coverage | precision of hints |
|---|---|---|---|---|
| list v0 | 0.814 [0.773, 0.849] | 0.802 [0.762, 0.843] | 0.693 [0.647, 0.735] | 0.960 [0.935, 0.982] |
| list v1 | 0.830 [0.787, 0.865] | 0.830 [0.790, 0.868] | 0.718 [0.672, 0.760] | 0.965 [0.943, 0.986] |
| list v1 + normalisation | 0.853 [0.816, 0.886] | 0.848 [0.812, 0.882] | 0.733 [0.690, 0.775] | 0.969 [0.948, 0.987] |
| Naive Bayes | 0.912 [0.879, 0.939] | 0.920 [0.892, 0.945] | 0.870 [0.837, 0.900] | 0.914 [0.883, 0.941] |
| logistic regression | 0.918 [0.890, 0.944] | 0.922 [0.897, 0.948] | 0.860 [0.828, 0.892] | 0.922 [0.892, 0.948] |
| hybrid | 0.895 [0.862, 0.925] | 0.895 [0.863, 0.925] | 0.833 [0.795, 0.868] | 0.916 [0.886, 0.946] |

At the validation-chosen operating point (the target's view; "correct hints" is the share of ALL reports that get a right hint if 30% carry a note):

| Configuration | Setting | coverage | precision of hints | macro-F1 | correct hints, share of all reports |
|---|---|---|---|---|---|
| list v0 | score 1, margin 0 | 0.738 [0.693, 0.777] | 0.929 [0.897, 0.957] | 0.824 [0.782, 0.860] | 0.206 [0.191, 0.219] |
| list v1 | score 1, margin 0 | 0.765 [0.720, 0.805] | 0.925 [0.896, 0.953] | 0.835 [0.791, 0.870] | 0.212 [0.198, 0.226] |
| list v1 + normalisation | score 1, margin 0 | 0.782 [0.740, 0.820] | 0.927 [0.899, 0.954] | 0.859 [0.821, 0.893] | 0.217 [0.204, 0.230] |
| Naive Bayes | max prob 0.531 | 0.728 [0.688, 0.767] | 0.990 [0.976, 1.000] | 0.848 [0.809, 0.883] | 0.216 [0.204, 0.229] |
| logistic regression | max prob 0.897 | 0.733 [0.690, 0.772] | 0.969 [0.950, 0.987] | 0.855 [0.819, 0.886] | 0.213 [0.200, 0.225] |
| hybrid | max prob 0.636 | 0.770 [0.728, 0.807] | 0.945 [0.917, 0.970] | 0.871 [0.837, 0.904] | 0.218 [0.206, 0.231] |

Coverage on gold is 0.73 to 0.78 for every configuration, above the 60% the validation rule aimed for: gold has fewer "none" notes and more explicit hazard words than validation. Per-class precision, recall and F1 with intervals for every configuration are in `classification_gold.json`. Logistic regression, the best category model:

| class | notes | precision | recall | F1 |
|---|---|---|---|---|
| pothole | 82 | 0.93 [0.87, 0.99] | 0.87 [0.78, 0.94] | 0.90 [0.84, 0.95] |
| open_manhole | 50 | 0.98 [0.93, 1.00] | 0.94 [0.87, 1.00] | 0.96 [0.91, 0.99] |
| flooded_drain | 62 | 0.90 [0.82, 0.96] | 0.97 [0.92, 1.00] | 0.93 [0.88, 0.97] |
| broken_streetlight | 62 | 1.00 [1.00, 1.00] | 0.94 [0.86, 0.99] | 0.97 [0.93, 0.99] |
| blocked_sidewalk | 54 | 0.94 [0.88, 1.00] | 0.94 [0.88, 1.00] | 0.94 [0.90, 0.98] |
| other | 34 | 0.73 [0.60, 0.86] | 0.88 [0.76, 0.97] | 0.80 [0.69, 0.89] |
| none | 56 | 0.93 [0.85, 0.98] | 0.93 [0.86, 0.98] | 0.93 [0.87, 0.97] |

For the list with normalisation the weak classes are `other` (recall 0.62) and `none` (precision 0.51: every missed hazard note lands in "none"); for the hybrid `pothole` and `flooded_drain` precision (0.87, 0.89).

### Danger flag

At the F2-best validation threshold (the target's view):

| Configuration | threshold | PR-AUC | ROC-AUC | precision | recall | F1 | F2 |
|---|---|---|---|---|---|---|---|
| list v0 | score 1.0 | 0.723 [0.641, 0.802] | 0.846 [0.804, 0.890] | 0.854 [0.776, 0.927] | 0.722 [0.636, 0.802] | 0.782 [0.716, 0.845] | 0.745 [0.669, 0.816] |
| list v1 | score 1.0 | 0.770 [0.694, 0.840] | 0.883 [0.841, 0.923] | 0.812 [0.732, 0.886] | 0.804 [0.724, 0.877] | 0.808 [0.744, 0.865] | 0.806 [0.736, 0.871] |
| list v1 + normalisation | score 1.0 | 0.778 [0.702, 0.846] | 0.891 [0.850, 0.929] | 0.792 [0.707, 0.867] | 0.825 [0.747, 0.892] | 0.808 [0.742, 0.862] | 0.818 [0.749, 0.874] |
| Naive Bayes | 0.030 | 0.943 [0.909, 0.971] | 0.974 [0.954, 0.988] | 0.730 [0.658, 0.805] | 0.948 [0.901, 0.989] | 0.825 [0.772, 0.875] | 0.895 [0.853, 0.932] |
| logistic regression | 0.189 | 0.955 [0.927, 0.979] | 0.978 [0.962, 0.991] | 0.885 [0.821, 0.939] | 0.876 [0.812, 0.935] | 0.881 [0.831, 0.923] | 0.878 [0.825, 0.928] |
| hybrid | 0.095 | 0.962 [0.928, 0.988] | 0.980 [0.960, 0.995] | 0.829 [0.756, 0.895] | 0.948 [0.904, 0.989] | 0.885 [0.837, 0.930] | 0.922 [0.884, 0.957] |

At the validation threshold for recall 0.90: hybrid 0.182 gives precision 0.918 [0.862, 0.967], recall 0.918 [0.857, 0.970]; NB 0.113 gives 0.817 and 0.918; LR 0.221 gives 0.895 and 0.876; every list needs threshold 0 (flag everything): precision 0.242, recall 1.0. Danger does not just follow the category: for the hybrid, recall and precision inside `pothole` are 0.89 and 0.81 (19 danger of 82), inside `flooded_drain` 0.92 and 0.86, inside `none` 1.00 and 0.82, while the gold notes warn that 56% of `open_manhole` notes are danger.

### Comparisons (paired bootstrap, A minus B)

| A - B | macro-F1 (default) | macro-F1 (at operating point) | danger PR-AUC |
|---|---|---|---|
| list v1 - list v0 | +0.016 [-0.002, +0.033] | +0.012 [-0.008, +0.029] | +0.048 [+0.006, +0.090] |
| list v1 + normalisation - list v1 | +0.023 [+0.009, +0.041] | +0.023 [+0.009, +0.042] | +0.008 [-0.011, +0.030] |
| list v1 + normalisation - list v0 | +0.039 [+0.018, +0.061] | +0.035 [+0.012, +0.056] | +0.055 [+0.006, +0.101] |
| Naive Bayes - list v1 | +0.082 [+0.038, +0.124] | +0.013 [-0.029, +0.058] | +0.172 [+0.104, +0.241] |
| logistic regression - list v1 | +0.088 [+0.050, +0.126] | +0.020 [-0.020, +0.058] | +0.185 [+0.118, +0.256] |
| hybrid - list v1 | +0.065 [+0.031, +0.099] | +0.036 [+0.006, +0.068] | +0.192 [+0.133, +0.256] |
| Naive Bayes - list v1 + normalisation | +0.059 [+0.022, +0.096] | -0.010 [-0.052, +0.032] | +0.165 [+0.095, +0.233] |
| logistic regression - list v1 + normalisation | +0.065 [+0.031, +0.102] | -0.003 [-0.040, +0.034] | +0.177 [+0.114, +0.247] |
| hybrid - list v1 + normalisation | +0.042 [+0.011, +0.073] | +0.013 [-0.013, +0.040] | +0.184 [+0.125, +0.247] |
| Naive Bayes - list v0 | +0.098 [+0.054, +0.141] | +0.024 [-0.020, +0.073] | +0.220 [+0.144, +0.295] |
| logistic regression - list v0 | +0.104 [+0.065, +0.143] | +0.032 [-0.008, +0.073] | +0.233 [+0.159, +0.308] |
| hybrid - list v0 | +0.081 [+0.047, +0.113] | +0.048 [+0.022, +0.076] | +0.239 [+0.173, +0.304] |
| hybrid - logistic regression | -0.023 [-0.054, +0.003] | +0.016 [-0.016, +0.050] | +0.006 [-0.015, +0.027] |
| hybrid - Naive Bayes | -0.017 [-0.050, +0.018] | +0.023 [-0.014, +0.062] | +0.019 [-0.010, +0.050] |
| logistic regression - Naive Bayes | +0.006 [-0.025, +0.040] | +0.007 [-0.031, +0.043] | +0.013 [-0.006, +0.035] |

The three learned models cannot be told apart on either task (every pairwise interval spans zero). Version 1 over v0 is a small, partly clear gain (PR-AUC yes, macro-F1 no); normalisation is the clearer list improvement.

### Difficulty slices (category accuracy at the default prediction; notes / danger notes in brackets)

| Slice | list v0 | list v1 | list v1 + norm | NB | LR | hybrid |
|---|---|---|---|---|---|---|
| (no slice) (189 / 42) | 0.90 | 0.93 | 0.93 | 0.97 | 0.95 | 0.97 |
| caps-rant (20 / 6) | 0.95 | 0.90 | 0.95 | 0.95 | 0.95 | 1.00 |
| code-switch (20 / 5) | 0.85 | 0.85 | 0.85 | 1.00 | 1.00 | 1.00 |
| implicit (25 / 8) | **0.32** | **0.40** | **0.40** | 0.76 | 0.68 | **0.44** |
| keyboard-artifact (16 / 4) | 0.88 | 0.94 | 0.94 | 1.00 | 1.00 | 0.94 |
| long (16 / 7) | 0.69 | 0.88 | 0.88 | 0.88 | 0.94 | 0.94 |
| multi-hazard (20 / 4) | **0.35** | **0.50** | **0.50** | 0.75 | 0.75 | **0.40** |
| negation (20 / 5) | 0.90 | 0.90 | 0.90 | 0.90 | 1.00 | 0.95 |
| other-language (16 / 5) | 0.69 | 0.69 | 0.69 | 0.75 | 0.81 | 0.88 |
| past (20 / 4) | 0.90 | 0.85 | 0.85 | 0.90 | 0.95 | 0.95 |
| sarcasm (18 / 4) | 0.89 | 0.83 | 0.89 | 0.78 | 0.89 | 0.89 |
| typo (20 / 3) | 0.55 | 0.60 | 0.80 | 1.00 | 0.95 | 0.90 |

Danger recall at the F2-best threshold by slice (danger notes in brackets; precision is in `classification_gold.json`):

| Slice | list v0 | list v1 | list v1 + norm | NB | LR | hybrid |
|---|---|---|---|---|---|---|
| (no slice) (42) | 0.76 | 0.88 | 0.88 | 0.98 | 0.95 | 1.00 |
| caps-rant (6) | 0.67 | 0.67 | 0.83 | 0.83 | 0.67 | 0.83 |
| code-switch (5) | 0.80 | 0.80 | 0.80 | 1.00 | 1.00 | 1.00 |
| implicit (8) | 0.75 | 0.88 | 0.88 | 1.00 | 1.00 | 1.00 |
| keyboard-artifact (4) | 0.75 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| long (7) | 0.86 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| multi-hazard (4) | **0.25** | **0.25** | **0.25** | 0.75 | 0.75 | 0.75 |
| negation (5) | 0.80 | 0.80 | 0.80 | 1.00 | 0.80 | 1.00 |
| other-language (5) | **0.40** | **0.40** | **0.40** | 0.80 | 0.60 | 0.80 |
| past (4) | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| sarcasm (4) | **0.25** | **0.25** | 0.50 | 0.75 | **0.25** | 0.50 |
| typo (3) | 1.00 | 1.00 | 1.00 | 1.00 | 0.67 | 1.00 |

Each slice has an interval in the json; with 3 to 8 danger notes per slice, treat this table as direction only. By language, category accuracy for the list with normalisation is 0.83 (English), 0.86 (Taglish), 0.85 (Tagalog); for the hybrid 0.85, 0.92, 0.91; NB is best on English (0.96).

## 7. Task 7: error analysis (after the exam, on the saved predictions)

**Top confusions (default prediction).**
- Lists: errors are abstentions. v1 with normalisation: 61 errors, 52 of them a hazard note with no hint (pothole 15, other 12, flooded_drain 10, broken_streetlight 9, open_manhole 3, blocked_sidewalk 3), 8 a wrong hazard (broken_streetlight to blocked_sidewalk 3), 1 a hint on a "none" note. For v0 and v1, 68 of 79 and 58 of 68 errors are abstentions.
- Learned models: errors are wrong hazards, with few abstentions. LR (31 errors, 4 abstentions): pothole to other 7, pothole to flooded_drain 2, broken_streetlight to blocked_sidewalk 2, other to flooded_drain 2, none to other 2. Hybrid (42 errors, 14 abstentions): pothole to none 6, open_manhole to flooded_drain 3, flooded_drain to none 3, broken_streetlight to blocked_sidewalk 3. NB (32 errors): none to pothole 4, pothole to open_manhole 3, other to broken_streetlight 3, other to blocked_sidewalk 3.
- Full confusion matrices (rows true, columns pothole, open_manhole, flooded_drain, broken_streetlight, blocked_sidewalk, other, none) are in the json for every configuration.

**Slices that break each model.** Implicit notes (only the consequence is named) and multi-hazard notes break everything: the lists get 0.32 to 0.50, the hybrid 0.44 and 0.40, LR 0.68 and 0.75, NB 0.76 and 0.75. The hybrid is worse than plain LR mainly on these two slices, my guess being that the list scores it carries latch onto whichever hazard word appears anywhere. Typos break the lists (0.55, 0.60; normalisation lifts v1 to 0.80) but not the models (0.90 to 1.00, character n-grams). Other languages (Cebuano, Ilocano, Hiligaynon) hurt the lists and NB most (0.69 to 0.75). For danger, the lists miss multi-hazard (recall 0.25), sarcasm (0.25) and other-language notes (0.40); every model misses sarcasm (0.25 to 0.75).

### 15 mistakes of the best category model (logistic regression, macro-F1 0.918; a random draw of its 31 errors, seed 0)

"hyb" is the hybrid. Reasons are my guesses from reading the notes.

| id (slice) | true, predicted | note | Why (guess) | What would fix it |
|---|---|---|---|---|
| gd-0039 (plain) | pothole, flooded_drain | "Cracked open na naman ang semento sa kanto ng Zobel at Pasong Tamo, ilang beses na tinapalan." | No hazard word: "semento", "tinapalan" (patched) and "cracked" are road-surface words the model never saw. Only hyb right | Road-surface vocabulary in train notes and, with evidence, in the list |
| gd-0044 (multi-hazard) | other, blocked_sidewalk | "Sidewalk is also blocked and the lights flicker, but what we want addressed first is the garbage truck that never comes..." | The writer's "main problem" cue is invisible to n-grams; two hazard words outvote the one that matters. All six miss | Give weight to hazard words after cues like "first", "pinakamalaking problema", "but"; more multi-hazard train notes |
| gd-0094 (caps-rant) | none, flooded_drain | "ANO BA NAMAN YAN?!? SINASAYANG NIYO LANG ANG ORAS NAMIN, STILL NO ACTION!!!" | A complaint with no hazard looks like train complaints from flood families; the model must pick a class. The lists, NB and hyb get it right | Abstain below a confidence floor; more hazard-free complaints in train |
| gd-0110 (plain) | pothole, other | "Road surface along Kamagong St is falling apart near the intersection, there are about five holes within one block." | "holes" (plural) and "falling apart" read like the train `other` family of unfinished roadwork. All six miss | Strip plurals; train contrast between roadwork and potholes |
| gd-0111 (other-language) | pothole, other | "Dako ang buho sa dalan sa atubangan sa eskwelahan, kinahanglan nang ayuhon." | Cebuano "buho" (hole) never seen. All six miss | Cebuano, Ilocano and Hiligaynon terms with native review; the slice stays weak without them |
| gd-0124 (implicit) | pothole, other | "Lumubog ang gulong at humampas ang underside ng kotse namin sa semento ... may tumutulo nang langis ngayon." | Consequence only: a sunken wheel and a scraped underside need world knowledge. All six miss | Out of reach for n-grams; abstaining is the right behaviour |
| gd-0140 (plain) | pothole, other | "A motorcycle skidded on the broken asphalt near the Guadalupe bridge and the rider hit the curb, he was limping..." | "broken asphalt", not "pothole" or "hole"; an incident story. Lists (via "asphalt"), NB and hyb right | List terms count: the hybrid keeps them |
| gd-0198 (plain) | pothole, flooded_drain | "Naglalaglagan ang aspalto sa kalsada namin sa Singkamas tuwing umuulan, parang binubungkal." | "tuwing umuulan" (whenever it rains) is a flood cue in train; the hazard word "aspalto" is rare. Lists and hyb right through the list word "aspalto" | Down-weight rain phrases; keep list features |
| gd-0220 (plain) | pothole, other | "Ang sakit sa mata ng sirang kalsada sa Bangkal, parang binomba, sana mapalitan na ng bagong semento." | Figurative; "sirang kalsada" is in the v0 list, which plain LR does not use. Lists and hyb right | Same as above |
| gd-0230 (sarcasm) | none, other | "Wow, three months and counting. Truly the most responsive city ever." | A complaint without a hazard; `other` absorbs generic complaints. NB, LR and hyb miss, the lists are right | Confidence floor; sarcastic hazard-free train notes |
| gd-0293 (plain) | pothole, open_manhole | "Pothole the size of a manhole cover on Chino Roces, right where the jeepneys turn." | A comparison names a manhole cover; a bag of words cannot tell a simile from the hazard. Only NB right | Treat a hazard word after "size of" or "parang" as a comparison; prefer the subject noun |
| gd-0307 (implicit) | blocked_sidewalk, flooded_drain | "I am late for work again because the usual path for pedestrians on Arnaiz is full of crates and wooden benches." | No "sidewalk"; "path for pedestrians" and the crates are unseen. Only NB right | Synonyms ("path", "pedestrian") and more implicit train notes |
| gd-0319 (other-language) | pothole, none | "May buho sa dalan malapit sa simbahan sang Guadalupe, palihog ayuha." | "buho" unseen again; "simbahan" (church) is a house-lookalike word in train. All six miss | Same as gd-0111 |
| gd-0366 (plain) | broken_streetlight, blocked_sidewalk | "Two of the four lamps in the Ayala Triangle walkway are not working." | "walkway" is the place but a strong blocked-sidewalk cue; "lamps ... not working" is the hazard. Only NB right | Separate place words from the hazard noun; more lamp-in-a-walkway notes |
| gd-0389 (typo) | open_manhole, none | "open manhoel on Jupiter, a boy fell in this morning, pls send help" | The swapped letters defeat the word features, and "a boy fell in, send help" reads like the train none-class accident notes. **List v1 with normalisation and NB are right** (one swap away from "manhole") | Typo normalisation for the list; typo augmentation for the model |

### 15 mistakes of the best danger model (hybrid, PR-AUC 0.962; 3 missed and 12 false alarms, a random draw)

At its F2-best threshold (0.095) the hybrid misses 5 of 97 danger notes and raises 19 false alarms. Scores are the model's probability.

| id (slice) | note (shortened) | Why (guess) | What would fix it |
|---|---|---|---|
| gd-0032 (multi-hazard), missed, 0.017 | "...ang pinakamalaking problema is yung lubak na nagpatumba na ng dalawang motor ngayong linggo." | The harm is a causative verb ("nagpatumba": made two motorbikes fall) that no train note or list term has. All six miss | Verb stems for falls (tumba) and crash words; more motorbike-fall notes |
| gd-0141 (sarcasm), missed, 0.030 | "Thanks to the pothole on Gil Puyat I now know exactly how it feels to be launched from a catapult, three stitches on my chin as a souvenir." | Irony hides the injury; "stitches" unseen. All six miss | Injury words (stitches, sprain) checked on fresh notes; sarcasm is hard for bags of words |
| gd-0174 (caps-rant), missed, 0.010 | "...MAY MATANDANG NAKAKAPIT SA POSTE PARA HINDI MATANGAY!!!" | An elderly person clinging to a pole in a flood. "matandang" is matanda plus the linker -ng; only the list with the -ng step flags it | The -ng step; "matangay" (swept away) |
| gd-0046 (plain), false alarm, 0.182 | "Ang tagal nang walang ilaw dito sa Rockwell Drive, di na namin makita ang gate pag gabi, please naman." | Darkness alone. Train labels count an unlit hazard at night as danger, gold labels do not (section 9). NB flags it too | A label-convention gap, not a model slip |
| gd-0067 (plain), false alarm, 0.112 | "Please help us." | "help" occurs in train danger notes ("pls send help"); the F2 threshold (0.095) is low. NB and LR flag it too | Raise the threshold (the recall-0.90 point 0.182 clears it) or add hazard-free pleas |
| gd-0086 (code-switch), false alarm, 0.217 | "Nag-flicker yung ilaw sa poste kagabi tapos namatay na completely, can we request a replacement po?" | "namatay" (went off, also died) is a v0 danger term at train precision 0.40; the hybrid carries it, so do the lists | Guard "namatay": require a person word near it |
| gd-0105 (implicit), false alarm, 0.713 | "A huge branch fell across the street this morning and nothing could get through for an hour..." | "fell" (train precision 0.67) and "could" fire; every configuration flags it | "fell" and "could" only near a person or vehicle |
| gd-0118 (plain), false alarm, 0.145 | "Hit a pothole on Gil Puyat last night and now my front wheel wobbles, going to the shop tomorrow." | Vehicle damage only (gold: false); "hit" and "last night" look like crash notes. NB, LR, hyb flag it | Property-damage words (wheel, tyre, rim) as a negative cue |
| gd-0179 (negation), false alarm, 0.131 | "Hindi naman ako nasaktan or nadisgrasya, pero nakakaasar na talaga yung mga lubak sa Pasong Tamo." | Negated harm with "or": the harm words are cues. NB and hyb flag it; the lists do not (neither word is in them) | Negation scope over "or"; more negated-harm notes |
| gd-0240 (plain), false alarm, 0.097 | "I was told to send this through the app." | Marginal: 0.002 over the threshold. NB flags it too | A threshold slightly higher |
| gd-0272 (long), false alarm, 0.125 | "Our street in Bangkal has had no working lights for almost four months ..." | "almost" (v0 term, train precision 0.53) in its duration sense. Lists and hyb flag it | "almost" only before "fell", "hit"; not alone |
| gd-0321 (plain), false alarm, 0.214 | "Nakaharang yung mga bike at scooter sa sidewalk sa tapat ng coffee shop, hindi na makalusot ang mga naglalakad." | Pedestrians blocked, no harm stated; NB, LR and hyb flag it ("walking" is a train cue) | Train non-danger blocked-sidewalk notes with pedestrians |
| gd-0328 (implicit), false alarm, 0.975 | "Pinaglalaruan na lang ng mga bata sa amin ang tubig sa kalsada, may bangka-bangkaan pa sa harap ng bahay namin ..." | Kids and water. Train says "deep water for kids" is danger, gold says only waist-deep or deeper. The lists and hyb flag it (NB and LR do not) | A label-convention gap (section 9) |
| gd-0346 (caps-rant), false alarm, 0.105 | "ANG DAMING ASONG GALA SA KANTO NAMIN, NAGKAKALAT NG BASURA AT NAG-IINGAY SA GABI, NAKAKAINIS NA!!!" | Stray dogs as a nuisance; in train every stray-dog family was a bite scenario, and "aso" is a v1 danger term. The -ng step turns "asong" into "aso". v1 with normalisation and hyb flag it | Non-danger stray-dog notes; bite and attack verbs rather than the noun |
| gd-0350 (keyboard-artifact), false alarm, 0.102 | "The pothole on Makati Ave is getting wider by the day.. someone please fix it Sent from my iPhone" | "someone" is a train cue ("someone will get hurt"); 0.007 over the threshold. Only hyb flags it | A slightly higher threshold |

Of the hybrid's 19 false alarms, 7 sit in plain notes, 4 in implicit, 3 in negation, 2 in long. In this draw 7 of the 12 false alarms score under 0.15 against a threshold of 0.095: the recall-oriented threshold turns any faint cue into an alarm, and the 5 validation danger families gave it little room to be set well.

### Practical view

With a note on 30% of reports, the share of ALL reports that get a correct hint at the validation-chosen points is 0.206 (v0), 0.212 (v1), 0.217 (v1 with normalisation), 0.216 (NB), 0.213 (LR), 0.218 (hybrid). About 1 to 2 reports in 100 would get a wrong hint (hybrid 1.3, LR 0.7, NB 0.2; lists about 1.6). At the plain prediction LR and NB reach 0.24 correct (precision 0.92). The ceiling is 0.258. For the other 70% of reports no model here helps: that needs the photo.

## 8. Task 8: recommendations

**Ship: the hybrid, for both helpers**, after the real-notes check in `EVALUATION.md` ("thirty to sixty real notes"). It is the only configuration besides NB that passes all four gold targets with every interval clear of the target, it has the best danger PR-AUC (0.962), and it was the most consistent across the ten validation splits (best on average on both tasks). Why not the others: logistic regression is a hair better on category (0.918 against 0.895, interval spans zero) but misses the danger recall target (0.876, interval spans 0.90); Naive Bayes also passes all four and is the simplest to port to pure Python, so it is the fallback if code size matters; the lists cannot meet the danger targets. If the team keeps rules only, ship **list v1 with normalisation**, not v0: it beats v0 on gold macro-F1 by +0.039 (interval +0.018 to +0.061) and PR-AUC by +0.055 (+0.006 to +0.101), and meets both category targets (not the danger targets).

**Thresholds for `settings.py`** (all from validation; the learned ones are new constants, there is no probability threshold in settings.py today):
- Hybrid: `HINT_MIN_PROB = 0.64` (gold: coverage 0.770, precision 0.945) and `DANGER_MIN_PROB = 0.095`, the F2-best point (gold: precision 0.829, recall 0.948). The recall-0.90 point 0.18 is the more balanced alternative (gold: precision 0.918, recall 0.918); I did not pick it because the pre-registered rule names F2. Re-derive both on the model refitted for release, with cross-validation over all 80 families, because probabilities move when the data changes.
- Rules only (list v1 with normalisation): validation asked for `HINT_MIN_SCORE = 1.0`, `HINT_MIN_MARGIN = 0.0` and `DANGER_MIN_SCORE = 1.0`. Margin 0.0 breaks ties by list order, which is arbitrary; the validation rule wanted it only because the list reached 55.5% coverage on validation at the shipped 0.5. On gold the shipped 0.5 already answers 73.3% at precision 0.969. That is a post-hoc observation, not a tested setting, so I would keep the shipped 0.5 unless real notes show coverage under 60%.

**Changes worth making in classify.py** (not made):
1. A pure-Python weighted scorer for a linear model: tokens, word 1-2 grams and character 3-5 grams, tf-idf with idf values from a JSON file the caller loads (as it already does for the lexicon), a dot product per class and a sigmoid for danger. This keeps the folder pure. Test it against `baselines.py`, the reference, on a fixed sample.
2. The normalisation steps, if the list is used or kept as hybrid input: squeeze repeated letters, strip mag-/nag-/na- and -ng when what is left is a list word, one-edit matching only for list words of 7+ letters with the same first letter and a single candidate. Gold gain +0.023 macro-F1 (clear), none on danger. Do not use the unguarded edit-distance rule: it cost 0.095 PR-AUC on validation.
3. Guard the weak danger words, which cause most list false alarms: "almost" (train precision 0.53), "fell" (0.67), "namatay" (0.40), "natumba" (0.60), "hurt" (0.80). Deleting them cost validation PR-AUC (0.006 to 0.026), so require a person or vehicle word nearby, or use phrases, instead. Untested.
4. Negators: add "nobody" and "nothing", and the texting spellings "walng", "wla", "hndi". They appear in train notes, but the rule counts only notes where the negator stands before a firing danger word and found fewer than 5. Untested.
5. Do not read the gold errors above as a to-do list for the word list and then re-score on this gold set: any term named from them (semento, buho, matangay, stitches) needs fresh notes to be checked.

## 9. Limits and things to know

- **Synthetic data, one voice.** Scores overstate real ones. The models may be learning the writer's style (they win most on the implicit, typo and code-switch slices); only real notes can say.
- **Validation is thin.** 20 families, 5 of them danger. Hyperparameters and operating points were chosen on it, so the validation table is optimistic for the learned models, and validation macro-F1 even ranked NB last (0.639) while NB was second on gold (0.912). The 10-split check shows the same ranking noise (macro-F1 SD 0.05 to 0.10).
- **v1 was partly shaped by validation** through the removal rule (section 4), and the normalisation variant was picked on validation sums that differ by about 0.01 (a few notes). On gold the variant did help, but only the combination was scored, so I cannot say which step helped.
- **Label conventions differ between the two sets.** `NOTES_TRAIN.md` counts "an unlit hazard at night with people passing" and "deep water for kids" as danger; `NOTES_GOLD.md` says darkness alone is false and only waist-deep or deeper water counts. Some false alarms (gd-0046, gd-0328) are that gap, not model error, so gold precision for danger is understated relative to what the train labels teach.
- **Danger tracks category in gold:** 56% of `open_manhole` notes are danger against 15 to 26% elsewhere. I checked per category: the hybrid keeps real discrimination inside `pothole`, `flooded_drain` and `none` (section 6).
- **Soft spot in the gold rule.** After the exam I looked at which gold notes each model got wrong, as allowed, and the word-list suggestions above come from them. Nothing was changed or re-scored because of it.
- **Text only.** No photo, no GPS, no "urgent" taps; `has_danger` also counts those.
- **Not done:** isolating each normalisation step on gold (it would need more gold runs); calibration of the probabilities; real notes.

## 10. Tests, figures and how to reproduce

`models/.venv/bin/pytest models/tickets/eval/classification -q -p no:warnings` runs 68 tests (the 10 existing in `test_schema.py` plus 58 new). `test_evaluate.py` covers whole families, the seed rule, the vectorised hint equal to `classify.category_hint` at five settings, coverage and precision on a hand-made case, operating points and danger thresholds. `test_tune_lexicon.py` covers the evidence rule on tiny sets, one add, one remove and one keep per rule, negators judged before danger words, boundary words, and `lexicon_v1.json` reproduced from the train half. `test_variants.py` runs every variant on hand-made words, the guarded and naive typo rule, and the selection rule. `test_baselines.py` covers shapes, class order, an unseen class and the hybrid features. `test_final_gold.py` covers: a second scoring is refused unless forced, every scoring is logged, the log line is written before the notes are read, a refused scoring reads nothing, the real gold file needs the real log, only `final_gold.py` names the gold file, and the report runs from saved predictions. The whole `models` suite passes (586).

Figures in `models/tickets/eval/results/`: `classification_validation_danger.png`, `classification_validation_selective.png`, `classification_gold_macro_f1.png`, `classification_gold_pr_auc.png`, `classification_gold_danger.png`, `classification_gold_selective.png`, `classification_gold_slices.png`.

```
models/.venv/bin/python -m models.tickets.eval.classification.tune_lexicon
models/.venv/bin/python -m models.tickets.eval.classification.variants
models/.venv/bin/python -m models.tickets.eval.classification.baselines
models/.venv/bin/python -m models.tickets.eval.classification.evaluate            # add --robustness 10 for the split check
models/.venv/bin/python -m models.tickets.eval.classification.final_gold          # refuses a second run; --report redoes the tables from saved predictions
```

---

