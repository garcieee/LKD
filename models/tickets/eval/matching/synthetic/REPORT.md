# The same-place matcher on simulated Makati

A simulation study of `models/tickets/matching/` (`geo.match_radius_m`, `match.find_match`): how often does a new report join the right ticket, when hazards, reporters and phone GPS error are simulated with exact truth? Plan, metrics and pre-registered targets: `models/tickets/EVALUATION.md`. Everything is a simulation: it says what the matcher does in the world of section 2, not in Makati (section 11 lists what that world leaves out).

Numbers: `models/tickets/eval/results/matching_synthetic_*.json`; the tables below are generated from them by `report_tables.py`. Code: `simulator.py`, `evaluate.py`, `sensitivity.py`, `recommended.py`, `interval_check.py`, `figures.py`; 42 tests in `tests/`.

## 1. The answers

1. **Targets (test split, 18 checks): 10 met, 8 missed.** Every miss is precision-type (6 precision, 2 PR-AUC); every recall and ticket-level target is met. Open sky: recall 0.96 (target 0.90) met; precision 0.92 / 0.90 / 0.86 at 20 / 60 / 150 hazards per km2 (target 0.95) missed. City: recall 0.97 (0.85) met; B-cubed F1 0.944 / 0.937 / 0.923 (0.90) met; PR-AUC 0.922 / 0.902 / 0.856 (0.92) met only at 20, interval touching the line; precision 0.84 / 0.80 / 0.72 (0.90) missed. The misses come from hazards bunching up: with unclustered hazards the open-sky and city precision targets hold at 20 and 60 per km2 and fail at 150 (section 9). The targets did not say how clustered hazards are; this result leans on that assumption hardest.
2. **The shipped rule does not stay, on this world's evidence, for a precision-weighted objective.** Re-tuned z (1.7, one value for all cells, picked on validation) beats it on F0.5, 95% interval of the paired difference clear of zero, in 11 of 12 test cells and in all 3 canyon cells when tuned on open sky and city only (profile shift). A logistic regression wins in 12 of 12, a fixed 25 m radius in 8 of 12 (it loses in open sky). But accuracy-awareness is not what wins: the best fixed radius ties or beats the accuracy-aware rule even with z tuned (6.4). At equal cost for a wrong merge and a wrong split (1:1) the shipped z is about right.
3. **Online replay, shipped rule:** B-cubed F1 0.954 / 0.951 / 0.947 (open sky), 0.944 / 0.937 / 0.923 (city), 0.924 / 0.912 / 0.888 (canyon) at 20 / 60 / 150 per km2. About 11 wrong merges or wrong splits per 100 reports (36 per 1,000 are splits no radius can avoid, caused by wrong categories).
4. **Auto-merge cutoff: 5 m.** Auto-merge only when the new report's reported accuracy is 5 m or better (largest accuracy at which validation precision is still at least 0.85, pooled over densities and profiles; 5 m at 60 and 150 per km2, 10 m at 20). **Above it the app should only suggest, never auto-merge.** Test split: auto-merge precision 0.774 [0.766, 0.783] without the cutoff, 0.903 [0.896, 0.910] with it; 83% of true duplicate pairs are left to suggestions. If z is also lowered to 2.0 the cutoff moves to 10 m (15 m at 20 per km2) and auto-merge keeps 44% of true pairs at precision 0.900 [0.894, 0.906].
5. **Cost (wrong merge = 3 wrong splits):** cheapest radius on validation is a **fixed 20 m**; cheapest accuracy-aware z is **2.0**. Test, per 1,000 reports: shipped 216 [210, 222]; fixed 20 m 194 [189, 198] (saves 22 [19, 26]); z 2.0 199 [194, 204] (saves 17 [14, 19]). At 1:1 the shipped rule (110) is as cheap as anything; at 5:1 fixed 20 m costs 248 against 322.
6. **Where it breaks:** recall falls under 0.85 when phones report half their true error (city 0.79, canyon 0.74) and when people stand 15 m or more from the hazard (open sky 0.84 at 15 m, 0.44 at 30 m). Precision falls toward under-confident phones, clustered and dense hazards (section 9).
7. **Recommended for `settings.py` (not edited):** a new auto-merge accuracy cutoff of 5 m (10 m if z is lowered), and `MATCH_Z` 3.03 to 2.0 if a wrong merge really costs about 3 wrong splits. Both lean on assumptions this simulation cannot check: confirm with the Chicago results and a field test first (section 10).

## 2. The simulated world

Deterministic from a seed. A patch is 3 km by 3 km around Ayala (14.5547, 121.0244), drawn in metres and converted to degrees (the matcher's haversine agrees with the plane to 6e-5). The three GPS profiles of a seed share hazards, reporters and random numbers, so a difference between profiles is GPS error alone.

| Piece | The simulation | The matcher assumes | Chosen by |
|---|---|---|---|
| Density | 20, 60, 150 hazards per km2 (Poisson count) | | task |
| Layout | Thomas cluster process: 50% of hazards in clusters (Poisson, mean 3 per parent, Gaussian spread 25 m per axis), 50% uniform | | **my guess** for share and size; swept in 9 |
| Categories | the five real ones: pothole .35, streetlight .25, drain .15, sidewalk .15, manhole .10; never "other" | | my guess |
| Reports per hazard | 1 + geometric, mean 1.6 (37.5% duplicates, as Chicago potholes); heavy tail: Zipf exponent 1.95 up to 50, mean 2.94 | | task |
| Wrong category | 6% of reporters, uniform among the other four | the picked category | task |
| Stand-off | 1 to 10 m from the hazard, uniform distance, random bearing (4.3 m per axis) | Gaussian, 3 m per axis | task, deliberately different |
| GPS error | independent per report, isotropic Gaussian, per-axis sigma: open sky 3.3 m, city 6.6 m, canyon 80% 9 m / 20% 25 m | independent Gaussian, sigma = accuracy / 1.51 | task |
| Reported accuracy | 1.51 x true sigma x lognormal(0, 0.35); median 5.0 / 10.1 / 15.2 m (mean 5.4 / 10.7 / 19.8 m) | accuracy / 1.51 is the sigma | task |
| Arrival | hazards appear over 30 days, a reporter notices after an exponential 2 days; nothing is ever fixed | | my guess |
| Truth | the hazard id of every report | | |

`tests/test_simulator.py` checks the empirical GPS error quantiles against the configured sigmas (including the canyon mixture), stand-off, report counts, category error, density, clustering and the degree conversion.

## 3. How it was evaluated

- **Cells:** 3 profiles x 3 densities, each 64,800 hazards over independent patches (360, 120, 48), 935,136 reports in all.
- **Splits:** districts are 0.005 degree blocks (about 550 m). `common.splits.block_split` sends 60/20/20 of districts to train / validation / test by hazard position, so a hazard and all its reports share a split. Pairs and the replay are built inside one split.
- **Pairs:** for each report, earlier reports of the same *reported* category within 150 m, labelled same hazard or not; score minus `geo.match_ratio`; shipped decision `match_ratio <= 1`. Same-hazard pairs with different reported categories are never candidates (about 11.5% of true pairs), so pair recall is geometric recall; the replay sees those splits.
- **Replay:** reports through `match.find_match` in arrival order, open tickets in a grid index (`geo.box`), a ticket moving to its most accurate report as `match.anchor_after` says. Other radius rules run the *same* `find_match` with other settings (`MATCH_MIN_M = MATCH_MAX_M = r` for a fixed radius, another `MATCH_Z`). Scored with `cluster_pairs`, `bcubed`, `ari`.
- **Cost:** on the final partition, per report: a wrong merge makes its ticket hold a second hazard, a wrong split puts its hazard into a second ticket. Cost per 1,000 reports = ratio x merges + splits. `floor` = splits wrong categories force on every rule.
- **Tuning:** tune on train, choose on validation, report on test once. A: each cell on its own districts. B: one z and one model for all cells (what the app could ship). C: profile shift, tuned on open sky and city, scored on canyon test districts. The "ceiling" (boosted trees on the same four inputs) is a diagnostic.
- **Intervals:** percentile bootstrap, 1,000 resamples (`common.metrics.bootstrap_ci`, `paired_bootstrap_diff`), resampling **districts**, not pairs (4.3).
- **Seeds:** developed on seeds 1000 and validation data. The final run (seeds 2024) was made once (`evaluate --final`, 460 s; refuses to run twice). Sweeps use seeds 7000 and tune nothing. `recommended.py` regenerates the final data and looks at the test split once more, for the single configuration of section 10, cutoff chosen on validation.

## 4. Findings per profile and density

### 4.1 Pair level, shipped rule, test split ("all three together" pools the profiles at one density)

| density | profile | pairs | positive | precision | recall | F1 | F0.5 | PR-AUC | ROC-AUC |
|---|---|---|---|---|---|---|---|---|---|
| 20 | open sky | 21463 | 0.54 | 0.921 [0.912, 0.931] | 0.961 [0.957, 0.966] | 0.941 [0.936, 0.946] | 0.929 [0.921, 0.937] | 0.958 [0.950, 0.966] | 0.969 [0.965, 0.973] |
| 20 | city | 21469 | 0.54 | 0.839 [0.825, 0.852] | 0.973 [0.969, 0.977] | 0.901 [0.892, 0.909] | 0.863 [0.851, 0.874] | 0.922 [0.912, 0.932] | 0.939 [0.933, 0.945] |
| 20 | canyon | 21436 | 0.54 | 0.762 [0.746, 0.778] | 0.938 [0.932, 0.943] | 0.841 [0.830, 0.851] | 0.791 [0.778, 0.806] | 0.854 [0.841, 0.868] | 0.877 [0.868, 0.886] |
| 20 | all three together | 64368 | 0.54 | 0.836 [0.823, 0.848] | 0.958 [0.953, 0.961] | 0.893 [0.885, 0.900] | 0.858 [0.847, 0.868] | 0.909 [0.898, 0.919] | 0.929 [0.923, 0.935] |
| 60 | open sky | 29817 | 0.37 | 0.896 [0.884, 0.908] | 0.960 [0.955, 0.964] | 0.927 [0.920, 0.934] | 0.908 [0.898, 0.918] | 0.948 [0.939, 0.956] | 0.980 [0.977, 0.982] |
| 60 | city | 29803 | 0.37 | 0.795 [0.780, 0.810] | 0.972 [0.968, 0.975] | 0.874 [0.865, 0.884] | 0.825 [0.812, 0.838] | 0.902 [0.890, 0.913] | 0.958 [0.954, 0.962] |
| 60 | canyon | 29685 | 0.37 | 0.694 [0.679, 0.711] | 0.941 [0.934, 0.947] | 0.799 [0.788, 0.810] | 0.733 [0.719, 0.748] | 0.819 [0.806, 0.833] | 0.914 [0.909, 0.920] |
| 60 | all three together | 89305 | 0.37 | 0.787 [0.773, 0.801] | 0.958 [0.954, 0.962] | 0.864 [0.855, 0.873] | 0.816 [0.804, 0.829] | 0.886 [0.875, 0.897] | 0.951 [0.947, 0.955] |
| 150 | open sky | 50162 | 0.22 | 0.862 [0.851, 0.874] | 0.961 [0.957, 0.965] | 0.909 [0.902, 0.915] | 0.880 [0.871, 0.890] | 0.926 [0.916, 0.935] | 0.986 [0.985, 0.988] |
| 150 | city | 50051 | 0.22 | 0.720 [0.705, 0.735] | 0.972 [0.969, 0.976] | 0.828 [0.817, 0.837] | 0.760 [0.746, 0.773] | 0.856 [0.843, 0.869] | 0.970 [0.968, 0.973] |
| 150 | canyon | 49934 | 0.22 | 0.589 [0.573, 0.605] | 0.945 [0.940, 0.950] | 0.726 [0.713, 0.738] | 0.637 [0.622, 0.652] | 0.735 [0.719, 0.753] | 0.935 [0.931, 0.939] |
| 150 | all three together | 150147 | 0.22 | 0.708 [0.693, 0.722] | 0.960 [0.956, 0.963] | 0.815 [0.805, 0.824] | 0.747 [0.734, 0.759] | 0.831 [0.818, 0.844] | 0.964 [0.962, 0.966] |

- Recall is flat at 0.94 to 0.97 in every cell: it depends on GPS error and stand-off, not on how many hazards are around.
- Precision falls with GPS error (open sky to canyon: minus 0.16, 0.20, 0.27 at 20, 60, 150 per km2) and with density (open sky 0.92 to 0.86, city 0.84 to 0.72, canyon 0.76 to 0.59). The shipped radius grows with the error (about 19 m, 31 m, 40 to 60 m) and a bigger circle holds more same-category neighbours.
- PR-AUC (open sky 0.926 to 0.958, canyon 0.735 to 0.854) falls the same way: ranking pairs by match ratio is no cure.

### 4.2 Online replay, shipped rule, test split

| density | profile | reports | tickets / hazards | B-cubed P | B-cubed R | B-cubed F1 | pairwise F1 | ARI |
|---|---|---|---|---|---|---|---|---|
| 20 | open sky | 20883 | 13613 / 12854 | 0.977 [0.975, 0.979] | 0.932 [0.928, 0.936] | 0.954 [0.951, 0.956] | 0.870 [0.862, 0.879] | 0.870 [0.862, 0.879] |
| 20 | city | 20883 | 13158 / 12854 | 0.953 [0.949, 0.956] | 0.935 [0.931, 0.939] | 0.944 [0.941, 0.947] | 0.847 [0.837, 0.856] | 0.847 [0.837, 0.856] |
| 20 | canyon | 20883 | 13009 / 12854 | 0.928 [0.923, 0.932] | 0.921 [0.917, 0.925] | 0.924 [0.921, 0.928] | 0.793 [0.783, 0.803] | 0.793 [0.783, 0.803] |
| 60 | open sky | 20877 | 13690 / 13093 | 0.969 [0.966, 0.972] | 0.933 [0.930, 0.937] | 0.951 [0.949, 0.953] | 0.860 [0.852, 0.868] | 0.860 [0.852, 0.868] |
| 60 | city | 20877 | 13147 / 13093 | 0.939 [0.935, 0.943] | 0.936 [0.932, 0.939] | 0.937 [0.935, 0.940] | 0.825 [0.815, 0.835] | 0.825 [0.815, 0.835] |
| 60 | canyon | 20877 | 12739 / 13093 | 0.901 [0.896, 0.906] | 0.923 [0.919, 0.927] | 0.912 [0.908, 0.915] | 0.760 [0.749, 0.771] | 0.760 [0.749, 0.771] |
| 150 | open sky | 20965 | 13606 / 13116 | 0.961 [0.958, 0.964] | 0.932 [0.929, 0.936] | 0.947 [0.944, 0.949] | 0.848 [0.839, 0.856] | 0.848 [0.839, 0.856] |
| 150 | city | 20965 | 12789 / 13116 | 0.913 [0.909, 0.918] | 0.933 [0.930, 0.937] | 0.923 [0.920, 0.927] | 0.791 [0.780, 0.800] | 0.791 [0.780, 0.800] |
| 150 | canyon | 20965 | 12129 / 13116 | 0.859 [0.853, 0.866] | 0.920 [0.915, 0.924] | 0.888 [0.884, 0.893] | 0.706 [0.693, 0.719] | 0.706 [0.693, 0.719] |

- B-cubed F1 (0.89 to 0.95) is kinder than pair precision: most reports are alone or in small tickets, so a wrong merge touches few reports.
- Ticket counts hide errors: city at 60 per km2 has 13,147 tickets for 13,093 hazards while 11 in 100 reports are involved in a wrong merge or split. Do not read ticket counts as a quality signal.
- Pairwise F1 and ARI agree to three digits, as they must when clusters are tiny against the number of reports.

### 4.3 Are the intervals honest?

`interval_check.py`: 60 independent samples the size of one test split (city, 60 per km2), truth from a pool of 400 patches.

| number | truth | district intervals hold it | pair intervals hold it | mean width, district / pair |
|---|---|---|---|---|
| precision | 0.795 | 0.95 | 0.52 | 0.067 / 0.033 |
| recall | 0.971 | 0.93 | 0.93 | 0.017 / 0.015 |

Resampling pairs one by one gives precision intervals half as wide that hold the truth in 52% of samples, not 95%. Every interval here resamples districts.

## 5. Pre-registered targets (test split)

"Met" = point estimate reaches the target; "clear" = the 95% interval is on the same side of the target.

| profile | metric | density | target | value | result | interval |
|---|---|---|---|---|---|---|
| open sky | precision | 20 | >= 0.95 | 0.921 [0.912, 0.931] | MISSED | clear |
| open sky | precision | 60 | >= 0.95 | 0.896 [0.884, 0.908] | MISSED | clear |
| open sky | precision | 150 | >= 0.95 | 0.862 [0.851, 0.874] | MISSED | clear |
| open sky | recall | 20 | >= 0.90 | 0.961 [0.957, 0.966] | MET | clear |
| open sky | recall | 60 | >= 0.90 | 0.960 [0.955, 0.964] | MET | clear |
| open sky | recall | 150 | >= 0.90 | 0.961 [0.957, 0.965] | MET | clear |
| city | precision | 20 | >= 0.90 | 0.839 [0.825, 0.852] | MISSED | clear |
| city | precision | 60 | >= 0.90 | 0.795 [0.780, 0.810] | MISSED | clear |
| city | precision | 150 | >= 0.90 | 0.720 [0.705, 0.735] | MISSED | clear |
| city | recall | 20 | >= 0.85 | 0.973 [0.969, 0.977] | MET | clear |
| city | recall | 60 | >= 0.85 | 0.972 [0.968, 0.975] | MET | clear |
| city | recall | 150 | >= 0.85 | 0.972 [0.969, 0.976] | MET | clear |
| city | PR-AUC | 20 | >= 0.92 | 0.922 [0.912, 0.932] | MET | touches |
| city | PR-AUC | 60 | >= 0.92 | 0.902 [0.890, 0.913] | MISSED | clear |
| city | PR-AUC | 150 | >= 0.92 | 0.856 [0.843, 0.869] | MISSED | clear |
| city | B-cubed F1 | 20 | >= 0.90 | 0.944 [0.941, 0.947] | MET | clear |
| city | B-cubed F1 | 60 | >= 0.90 | 0.937 [0.935, 0.940] | MET | clear |
| city | B-cubed F1 | 150 | >= 0.90 | 0.923 [0.920, 0.927] | MET | clear |

Canyon has no target; its deliverable is the cutoff (7). The Chicago row is the other agent's.

## 6. Does anything beat the shipped rule?

Same test pairs, F0.5 at each rule's own operating point, paired difference (rule minus shipped) with a district-resampled interval from `paired_bootstrap_diff`. Rules: fixed 10, 15, 25, 40, 60 m; shipped (`MATCH_Z` 3.03); the same rule with z tuned on train and picked by validation F0.5 (grid 1.5 to 4.0 by 0.1); a logistic regression on distance, both reported accuracies and their ratio; boosted trees as a ceiling.

### 6.1 Tally over cells

Cells where the interval of the F0.5 difference is wholly above zero ("better"), wholly below ("worse") or holds zero ("unclear"). With about 100 comparisons a stray clear interval is expected by chance: read patterns, not single cells. "Mixed" cells (all profiles at one density) are in B.

| rule | tuned per cell (9 cells) | tuned once (12 cells) | profile shift (3 cells) |
|---|---|---|---|
| boosted trees (ceiling) | 9 better / 0 worse / 0 unclear | 12 better / 0 worse / 0 unclear | 2 better / 1 worse / 0 unclear |
| fixed 10 m | 0 better / 9 worse / 0 unclear | 0 better / 12 worse / 0 unclear | 0 better / 3 worse / 0 unclear |
| fixed 15 m | 3 better / 4 worse / 2 unclear | 5 better / 5 worse / 2 unclear | 0 better / 3 worse / 0 unclear |
| fixed 25 m | 5 better / 3 worse / 1 unclear | 8 better / 3 worse / 1 unclear | 2 better / 0 worse / 1 unclear |
| fixed 40 m | 3 better / 6 worse / 0 unclear | 3 better / 9 worse / 0 unclear | 3 better / 0 worse / 0 unclear |
| fixed 60 m | 0 better / 9 worse / 0 unclear | 0 better / 12 worse / 0 unclear | 0 better / 3 worse / 0 unclear |
| logistic | 9 better / 0 worse / 0 unclear | 12 better / 0 worse / 0 unclear | 2 better / 0 worse / 1 unclear |
| z tuned | 8 better / 0 worse / 1 unclear | 11 better / 0 worse / 1 unclear | 3 better / 0 worse / 0 unclear |

### 6.2 The variant table, 60 hazards per km2, tuned once, test split

**open sky**

| rule | precision | recall | F0.5 | PR-AUC | F0.5 minus shipped |
|---|---|---|---|---|---|
| boosted trees (ceiling) | 0.905 [0.894, 0.916] | 0.959 [0.954, 0.963] | 0.915 [0.906, 0.924] | 0.949 [0.941, 0.958] | +0.007 [+0.005, +0.010] |
| fixed 10 m | 0.954 [0.945, 0.962] | 0.571 [0.560, 0.582] | 0.841 [0.834, 0.848] | 0.951 [0.942, 0.959] | -0.067 [-0.075, -0.059] |
| fixed 15 m | 0.933 [0.924, 0.943] | 0.854 [0.846, 0.862] | 0.916 [0.909, 0.924] | 0.951 [0.942, 0.959] | +0.008 [+0.003, +0.014] |
| fixed 25 m | 0.862 [0.848, 0.875] | 0.997 [0.996, 0.998] | 0.886 [0.874, 0.897] | 0.951 [0.942, 0.959] | -0.022 [-0.026, -0.018] |
| fixed 40 m | 0.746 [0.729, 0.762] | 1.000 [1.000, 1.000] | 0.786 [0.771, 0.800] | 0.951 [0.942, 0.959] | -0.122 [-0.132, -0.112] |
| fixed 60 m | 0.629 [0.612, 0.646] | 1.000 [1.000, 1.000] | 0.679 [0.663, 0.695] | 0.951 [0.942, 0.959] | -0.229 [-0.240, -0.217] |
| logistic | 0.910 [0.900, 0.921] | 0.946 [0.940, 0.950] | 0.917 [0.908, 0.926] | 0.949 [0.940, 0.958] | +0.009 [+0.007, +0.012] |
| shipped | 0.896 [0.884, 0.908] | 0.960 [0.955, 0.964] | 0.908 [0.898, 0.918] | 0.948 [0.939, 0.956] | - |
| z tuned (1.7) | 0.933 [0.924, 0.942] | 0.855 [0.848, 0.864] | 0.916 [0.909, 0.924] | 0.951 [0.942, 0.958] | +0.008 [+0.004, +0.014] |

**city**

| rule | precision | recall | F0.5 | PR-AUC | F0.5 minus shipped |
|---|---|---|---|---|---|
| boosted trees (ceiling) | 0.865 [0.852, 0.877] | 0.894 [0.887, 0.901] | 0.870 [0.860, 0.881] | 0.904 [0.893, 0.915] | +0.046 [+0.040, +0.051] |
| fixed 10 m | 0.931 [0.919, 0.942] | 0.333 [0.323, 0.344] | 0.685 [0.674, 0.696] | 0.909 [0.898, 0.920] | -0.140 [-0.155, -0.125] |
| fixed 15 m | 0.912 [0.901, 0.924] | 0.595 [0.583, 0.606] | 0.824 [0.815, 0.834] | 0.909 [0.898, 0.920] | -0.000 [-0.010, +0.009] |
| fixed 25 m | 0.858 [0.845, 0.871] | 0.920 [0.913, 0.926] | 0.870 [0.859, 0.881] | 0.909 [0.898, 0.920] | +0.045 [+0.040, +0.050] |
| fixed 40 m | 0.750 [0.734, 0.766] | 0.998 [0.997, 0.999] | 0.789 [0.775, 0.804] | 0.909 [0.898, 0.920] | -0.035 [-0.040, -0.030] |
| fixed 60 m | 0.633 [0.617, 0.651] | 1.000 [1.000, 1.000] | 0.683 [0.668, 0.700] | 0.909 [0.898, 0.920] | -0.141 [-0.149, -0.133] |
| logistic | 0.875 [0.862, 0.888] | 0.850 [0.842, 0.859] | 0.870 [0.859, 0.880] | 0.908 [0.896, 0.919] | +0.045 [+0.039, +0.051] |
| shipped | 0.795 [0.780, 0.810] | 0.972 [0.968, 0.975] | 0.825 [0.812, 0.838] | 0.902 [0.890, 0.913] | - |
| z tuned (1.7) | 0.885 [0.872, 0.898] | 0.745 [0.735, 0.756] | 0.853 [0.843, 0.863] | 0.903 [0.892, 0.914] | +0.029 [+0.021, +0.036] |

**canyon**

| rule | precision | recall | F0.5 | PR-AUC | F0.5 minus shipped |
|---|---|---|---|---|---|
| boosted trees (ceiling) | 0.820 [0.806, 0.834] | 0.659 [0.647, 0.672] | 0.782 [0.771, 0.793] | 0.833 [0.820, 0.847] | +0.049 [+0.039, +0.058] |
| fixed 10 m | 0.892 [0.876, 0.908] | 0.169 [0.160, 0.177] | 0.480 [0.466, 0.495] | 0.825 [0.812, 0.839] | -0.252 [-0.273, -0.232] |
| fixed 15 m | 0.873 [0.860, 0.888] | 0.339 [0.328, 0.350] | 0.664 [0.652, 0.677] | 0.825 [0.812, 0.839] | -0.069 [-0.085, -0.053] |
| fixed 25 m | 0.828 [0.814, 0.842] | 0.638 [0.625, 0.650] | 0.781 [0.770, 0.793] | 0.825 [0.812, 0.839] | +0.048 [+0.038, +0.058] |
| fixed 40 m | 0.741 [0.725, 0.756] | 0.864 [0.855, 0.873] | 0.762 [0.749, 0.776] | 0.825 [0.812, 0.839] | +0.030 [+0.025, +0.035] |
| fixed 60 m | 0.638 [0.622, 0.655] | 0.962 [0.956, 0.967] | 0.684 [0.669, 0.700] | 0.825 [0.812, 0.839] | -0.049 [-0.053, -0.045] |
| logistic | 0.807 [0.792, 0.822] | 0.681 [0.668, 0.693] | 0.778 [0.767, 0.790] | 0.803 [0.788, 0.820] | +0.046 [+0.037, +0.054] |
| shipped | 0.694 [0.679, 0.711] | 0.941 [0.934, 0.947] | 0.733 [0.719, 0.748] | 0.819 [0.806, 0.833] | - |
| z tuned (1.7) | 0.771 [0.756, 0.787] | 0.743 [0.733, 0.754] | 0.765 [0.753, 0.779] | 0.799 [0.784, 0.814] | +0.033 [+0.026, +0.039] |

**all three together (a mixed fleet)**

| rule | precision | recall | F0.5 | PR-AUC | F0.5 minus shipped |
|---|---|---|---|---|---|
| boosted trees (ceiling) | 0.867 [0.855, 0.879] | 0.837 [0.831, 0.844] | 0.861 [0.851, 0.871] | 0.911 [0.901, 0.921] | +0.045 [+0.040, +0.050] |
| fixed 10 m | 0.936 [0.927, 0.946] | 0.357 [0.350, 0.366] | 0.707 [0.700, 0.716] | 0.900 [0.890, 0.910] | -0.109 [-0.121, -0.096] |
| fixed 15 m | 0.914 [0.904, 0.925] | 0.596 [0.587, 0.605] | 0.826 [0.818, 0.834] | 0.900 [0.890, 0.910] | +0.010 [+0.001, +0.019] |
| fixed 25 m | 0.852 [0.838, 0.865] | 0.851 [0.845, 0.857] | 0.852 [0.841, 0.862] | 0.900 [0.890, 0.910] | +0.035 [+0.031, +0.040] |
| fixed 40 m | 0.746 [0.730, 0.762] | 0.954 [0.951, 0.957] | 0.780 [0.766, 0.793] | 0.900 [0.890, 0.910] | -0.036 [-0.041, -0.032] |
| fixed 60 m | 0.633 [0.617, 0.651] | 0.987 [0.985, 0.989] | 0.682 [0.667, 0.698] | 0.900 [0.890, 0.910] | -0.134 [-0.140, -0.127] |
| logistic | 0.868 [0.855, 0.880] | 0.826 [0.818, 0.833] | 0.859 [0.849, 0.869] | 0.879 [0.867, 0.891] | +0.043 [+0.038, +0.048] |
| shipped | 0.787 [0.773, 0.801] | 0.958 [0.954, 0.962] | 0.816 [0.804, 0.829] | 0.886 [0.875, 0.897] | - |
| z tuned (1.7) | 0.861 [0.849, 0.873] | 0.781 [0.773, 0.790] | 0.844 [0.835, 0.854] | 0.884 [0.873, 0.895] | +0.028 [+0.022, +0.033] |

F0.5 minus shipped at the other densities (tuned once). The last two rows compare with the best fixed radius (25 m, picked on validation).

| 20 per km2: rule | open sky | city | canyon | all three together |
|---|---|---|---|---|
| logistic | +0.005 [+0.003, +0.007] | +0.030 [+0.025, +0.035] | +0.017 [+0.009, +0.024] | +0.025 [+0.020, +0.029] |
| z tuned | -0.001 [-0.005, +0.003] | +0.011 [+0.005, +0.018] | +0.018 [+0.011, +0.024] | +0.012 [+0.007, +0.017] |
| fixed 25 m | -0.019 [-0.023, -0.016] | +0.033 [+0.029, +0.038] | +0.007 [-0.002, +0.016] | +0.017 [+0.013, +0.021] |
| shipped minus best fixed | +0.019 [+0.016, +0.023] | -0.033 [-0.038, -0.029] | -0.007 [-0.016, +0.002] | -0.017 [-0.021, -0.013] |
| z tuned minus best fixed | +0.018 [+0.012, +0.024] | -0.022 [-0.026, -0.017] | +0.011 [+0.004, +0.017] | -0.005 [-0.008, -0.001] |

| 150 per km2: rule | open sky | city | canyon | all three together |
|---|---|---|---|---|
| logistic | +0.015 [+0.012, +0.018] | +0.075 [+0.068, +0.082] | +0.083 [+0.075, +0.091] | +0.073 [+0.068, +0.079] |
| z tuned | +0.018 [+0.013, +0.023] | +0.064 [+0.056, +0.073] | +0.056 [+0.049, +0.062] | +0.053 [+0.048, +0.059] |
| fixed 25 m | -0.030 [-0.035, -0.026] | +0.068 [+0.063, +0.074] | +0.089 [+0.081, +0.098] | +0.062 [+0.057, +0.066] |
| shipped minus best fixed | +0.030 [+0.026, +0.035] | -0.068 [-0.074, -0.063] | -0.089 [-0.098, -0.081] | -0.062 [-0.066, -0.057] |
| z tuned minus best fixed | +0.048 [+0.042, +0.055] | -0.004 [-0.010, +0.002] | -0.034 [-0.041, -0.026] | -0.008 [-0.013, -0.004] |

Profile-shift test (z = 1.9 and the logistic model tuned on open sky and city, scored on canyon test districts), F0.5 minus shipped:

| rule | 20 per km2 | 60 per km2 | 150 per km2 |
|---|---|---|---|
| z tuned | +0.021 [+0.015, +0.026] | +0.033 [+0.027, +0.038] | +0.052 [+0.046, +0.058] |
| logistic | +0.002 [-0.007, +0.011] | +0.038 [+0.028, +0.048] | +0.079 [+0.070, +0.088] |
| fixed 25 m | +0.007 [-0.002, +0.016] | +0.048 [+0.038, +0.058] | +0.089 [+0.081, +0.098] |
| z tuned minus best fixed (25 m) | +0.014 [+0.007, +0.021] | -0.015 [-0.023, -0.007] | -0.037 [-0.045, -0.029] |

What was tuned (z picked on validation, the train optimum beside it; logistic threshold). The best fixed radius was 25 m in every cell except open sky (15 m).

| tuning | z (validation) | z (train) | logistic threshold |
|---|---|---|---|
| A canyon@150 | 1.6 | 1.6 | 0.53 |
| A canyon@20 | 2.0 | 2.0 | 0.63 |
| A canyon@60 | 1.8 | 1.8 | 0.60 |
| A city@150 | 1.9 | 1.8 | 0.57 |
| A city@20 | 2.1 | 2.2 | 0.66 |
| A city@60 | 2.1 | 2.0 | 0.60 |
| A open_sky@150 | 2.1 | 1.6 | 0.54 |
| A open_sky@20 | 2.5 | 2.6 | 0.67 |
| A open_sky@60 | 2.5 | 2.4 | 0.67 |
| B: all cells | 1.7 | 1.8 | 0.66 |
| C: open sky and city | 1.9 | 2.0 | 0.66 |

Figures: `matching_synthetic_zcurve.png` (F0.5 against z), `matching_synthetic_variants.png` (the differences, all cells).

### 6.3 What this says

- **Yes, several rules beat the shipped one**, interval clear of zero. z tuned: better in 8 of 9 cells tuned per cell, 11 of 12 tuned once, all 3 profile-shift cells, never worse. Logistic regression: 9 of 9, 12 of 12, 2 of 3. The gain is +0.008 in open sky, +0.03 in city and canyon at 60 per km2, about +0.06 at 150. The validation optimum for z is 1.6 to 2.5 in every cell and 1.7 for all together; the curve is flat from about 1.5 to 2.3 and falls beyond.
- **Fixed 25 m beats the shipped rule in city and canyon, loses in open sky; fixed 10, 40, 60 m lose nearly everywhere.** No fixed radius is good everywhere, the argument for adapting at all.
- **The tuned z survives profile shift** (table above); the logistic regression extrapolates worse where the canyon's accuracies lie beyond what it saw.
- **The shipped rule is a recall rule:** it keeps pair recall at 0.96 and gives up precision (city, 60 per km2: 0.795, against 0.885 for z 1.7). F0.5 and a 3:1 cost weigh precision; at 1:1 the shipped z is about right (8).

### 6.4 Does listening to the phone's accuracy pay at all?

EVALUATION.md rule 2 asks whether a complex rule beats the simple baseline. Against the best fixed radius (25 m, picked on validation):

- Shipped minus best fixed, 60 per km2: city -0.045 [-0.050, -0.040], canyon -0.048 [-0.058, -0.038], all three together -0.035 [-0.040, -0.031]; open sky +0.022 [+0.018, +0.026] only because 25 m is a poor radius there (15 m is the best for open sky alone).
- z tuned minus best fixed: all three together -0.005 [-0.008, -0.001], -0.008 [-0.012, -0.004], -0.008 [-0.013, -0.004] at 20, 60, 150 per km2. Canyon at 20 per km2: +0.011 [+0.004, +0.017].
- On cost at 3:1 a fixed radius also wins (8): the cheapest fixed radius saves 5 [3, 7] more per 1,000 reports than the cheapest z; at 1:1 the accuracy-aware rule is cheaper by 6 [5, 7].
- The ceiling beats the best fixed radius by at most 0.015 F0.5: the accuracies carry a little information, but the shipped way of using it (a radius that grows with the error) points the wrong way when precision matters: noisier pairs get a bigger circle and lower precision (7).

**Verdict:** something does beat the shipped rule with the interval clear of zero (re-tuned z, a logistic regression, a plain 25 m radius in noisy cells). In this world the accuracy-aware design has no measurable edge over a well-chosen fixed radius when a wrong merge costs more than a wrong split. If wrong merges and splits cost the same, the shipped rule stays.

## 7. The auto-merge accuracy cutoff

Bin the reported accuracy of the new report (5, 10, 15, 20, 30, 40 m), take the shipped rule's merges on the **validation** split, find precision per bin, and switch auto-merge off above the last edge before precision first falls under 0.85. Profiles pooled (the app does not know the profile).

**all densities: cutoff 5 m**

| reported accuracy, m | merges | precision |
|---|---|---|
| 0 to 5 | 18084 | 0.91 [0.90, 0.92] |
| 5 to 10 | 41619 | 0.84 [0.83, 0.85] |
| 10 to 15 | 31239 | 0.75 [0.74, 0.76] |
| 15 to 20 | 14083 | 0.71 [0.69, 0.72] |
| 20 to 30 | 7994 | 0.65 [0.63, 0.67] |
| 30 to 40 | 3398 | 0.62 [0.60, 0.65] |
| above 40 | 3981 | 0.63 [0.60, 0.65] |

**density 20: cutoff 10 m; density 60: cutoff 5 m; density 150: cutoff 5 m**

| reported accuracy, m | 20 per km2 | 60 per km2 | 150 per km2 |
|---|---|---|---|
| 0 to 5 | 0.93 [0.92, 0.94] | 0.91 [0.90, 0.92] | 0.89 [0.87, 0.90] |
| 5 to 10 | 0.87 [0.86, 0.88] | 0.85 [0.84, 0.86] | 0.80 [0.79, 0.81] |
| 10 to 15 | 0.81 [0.79, 0.82] | 0.77 [0.76, 0.79] | 0.69 [0.67, 0.71] |
| 15 to 20 | 0.76 [0.74, 0.78] | 0.74 [0.72, 0.76] | 0.64 [0.62, 0.66] |
| 20 to 30 | 0.71 [0.68, 0.74] | 0.68 [0.65, 0.70] | 0.59 [0.56, 0.61] |
| 30 to 40 | 0.71 [0.66, 0.75] | 0.65 [0.61, 0.69] | 0.55 [0.51, 0.59] |
| above 40 | 0.73 [0.69, 0.76] | 0.66 [0.62, 0.70] | 0.53 [0.49, 0.57] |

Precision falls steadily with reported accuracy everywhere. The 5 to 10 m bin sits on the 0.85 line at 60 per km2 (0.85 [0.84, 0.86]), passes at 20 (0.87) and fails at 150 (0.80). Pooled answer: **5 m**; per density 10, 5, 5 m. On the **test** split:

| scope | cutoff | auto-merge precision | shipped precision | auto-merge recall | shipped recall | true pairs left to suggestions | withheld merges that were right |
|---|---|---|---|---|---|---|---|
| all densities | 5 m | 0.90 [0.90, 0.91] | 0.77 [0.77, 0.78] | 0.16 [0.16, 0.17] | 0.96 [0.96, 0.96] | 0.83 [0.82, 0.83] | 0.75 [0.74, 0.76] |
| density 20 | 10 m | 0.89 [0.88, 0.90] | 0.84 [0.82, 0.85] | 0.52 [0.51, 0.52] | 0.96 [0.95, 0.96] | 0.46 [0.45, 0.47] | 0.78 [0.76, 0.80] |
| density 60 | 5 m | 0.91 [0.90, 0.92] | 0.79 [0.77, 0.80] | 0.16 [0.16, 0.17] | 0.96 [0.95, 0.96] | 0.83 [0.82, 0.83] | 0.77 [0.75, 0.78] |
| density 150 | 5 m | 0.87 [0.86, 0.89] | 0.71 [0.69, 0.72] | 0.16 [0.16, 0.17] | 0.96 [0.96, 0.96] | 0.83 [0.82, 0.83] | 0.68 [0.67, 0.70] |

- **Above the cutoff the app should suggest only, never auto-merge:** leave the report un-merged (new ticket) and show staff and the reporter the nearby same-category tickets (`match.possible_duplicates`, which lists out to twice the radius and so contains the true pair every time here). The merges held back were right 75% of the time, so most review work would have been fine merges, but a quarter would have been wrong merges.
- A report with no accuracy gets `DEFAULT_ACCURACY_M` = 15 m, above the cutoff, so it never auto-merges either.
- At z = 3.03 the cutoff is expensive: auto-merge recall falls from 0.96 to 0.16. The reason is the radius, not the cutoff: precision at the shipped radius is only 0.77 overall.
- Binning by the worse of the report's and the ticket's accuracy gives a 10 m cutoff with 39% auto-merge recall at precision 0.89 (`matching_synthetic_cutoff.json`, `acc_worst`).

Where the cutoff would sit if z were lowered (validation precision per bin; tuned z = 1.7):

| scope | rule | cutoff | to 5 m | to 10 m | to 15 m | to 20 m | to 30 m | to 40 m | above 40 m |
|---|---|---|---|---|---|---|---|---|---|
| all densities | shipped z | 5 m | 0.91 | 0.84 | 0.75 | 0.71 | 0.65 | 0.62 | 0.63 |
| all densities | tuned z 1.7 | 15 m | 0.93 | 0.91 | 0.86 | 0.83 | 0.78 | 0.69 | 0.64 |
| density 20 | shipped z | 10 m | 0.93 | 0.87 | 0.81 | 0.76 | 0.71 | 0.71 | 0.73 |
| density 20 | tuned z 1.7 | 20 m | 0.95 | 0.93 | 0.89 | 0.86 | 0.81 | 0.74 | 0.74 |
| density 60 | shipped z | 5 m | 0.91 | 0.85 | 0.77 | 0.74 | 0.68 | 0.65 | 0.66 |
| density 60 | tuned z 1.7 | 15 m | 0.93 | 0.91 | 0.86 | 0.84 | 0.79 | 0.71 | 0.67 |
| density 150 | shipped z | 5 m | 0.89 | 0.80 | 0.69 | 0.64 | 0.59 | 0.55 | 0.53 |
| density 150 | tuned z 1.7 | 10 m | 0.92 | 0.88 | 0.81 | 0.78 | 0.74 | 0.63 | 0.54 |

The two changes together on the **test** split, z = 2.0 (cheapest accuracy-aware z at 3:1 on validation) with the cutoff found on validation for that rule (`recommended.py`). Its shipped-z rows reproduce the table above exactly, which also shows the final data regenerate bit for bit.

| scope | rule | cutoff | auto-merge precision | auto-merge recall | precision with no cutoff | recall with no cutoff | true pairs left to suggestions |
|---|---|---|---|---|---|---|---|
| all densities | shipped z 3.03 | 5 m | 0.903 [0.896, 0.910] | 0.164 [0.161, 0.167] | 0.774 [0.766, 0.783] | 0.958 [0.956, 0.960] | 0.83 [0.82, 0.83] |
| all densities | z 2.0 | 10 m | 0.900 [0.894, 0.906] | 0.444 [0.440, 0.448] | 0.834 [0.828, 0.842] | 0.841 [0.837, 0.845] | 0.46 [0.46, 0.46] |
| density 20 | shipped z 3.03 | 10 m | 0.890 [0.880, 0.901] | 0.517 [0.511, 0.524] | 0.836 [0.823, 0.848] | 0.958 [0.953, 0.961] | 0.46 [0.45, 0.47] |
| density 20 | z 2.0 | 15 m | 0.907 [0.898, 0.917] | 0.653 [0.646, 0.662] | 0.882 [0.871, 0.893] | 0.843 [0.835, 0.851] | 0.22 [0.21, 0.22] |
| density 60 | shipped z 3.03 | 5 m | 0.908 [0.896, 0.921] | 0.164 [0.159, 0.169] | 0.787 [0.773, 0.801] | 0.958 [0.954, 0.962] | 0.83 [0.82, 0.83] |
| density 60 | z 2.0 | 10 m | 0.908 [0.897, 0.919] | 0.444 [0.436, 0.451] | 0.844 [0.831, 0.857] | 0.838 [0.831, 0.846] | 0.46 [0.45, 0.46] |
| density 150 | shipped z 3.03 | 5 m | 0.875 [0.862, 0.888] | 0.163 [0.158, 0.168] | 0.708 [0.693, 0.722] | 0.960 [0.956, 0.963] | 0.83 [0.82, 0.83] |
| density 150 | z 2.0 | 10 m | 0.867 [0.854, 0.878] | 0.441 [0.433, 0.448] | 0.781 [0.768, 0.795] | 0.842 [0.835, 0.848] | 0.46 [0.46, 0.47] |

Precision against automation on validation, all densities, so another precision floor can be chosen:

| auto-merge only up to | shipped z: precision / recall | z 2.0: precision / recall |
|---|---|---|
| 5 m | 0.908 / 0.166 | 0.933 / 0.150 |
| 10 m | 0.860 / 0.519 | 0.907 / 0.446 |
| 15 m | 0.824 / 0.758 | 0.883 / 0.653 |
| 20 m | 0.808 / 0.859 | 0.872 / 0.745 |
| 30 m | 0.797 / 0.911 | 0.863 / 0.794 |
| 40 m | 0.792 / 0.933 | 0.857 / 0.814 |
| no cutoff | 0.787 / 0.958 | 0.847 / 0.839 |

## 8. Cost of wrong merges and wrong splits

Per 1,000 reports, online replay. The cheapest radius on **validation**, per ratio (rows: pooled over all cells, then per profile, then per density):

| scope | wrong merge costs | cheapest rule | cheapest fixed radius | cheapest z | shipped (validation) | cheapest (validation) |
|---|---|---|---|---|---|---|
| all | 1 split | z 3.1 | fixed 30 m | z 3.1 | 107 | 107 |
| all | 3 splits | fixed 20 m | fixed 20 m | z 2.0 | 210 | 187 |
| all | 5 splits | fixed 20 m | fixed 20 m | z 1.5 | 312 | 236 |
| open sky | 3 splits | fixed 20 m | fixed 20 m | z 3.0 | 122 | 116 |
| city | 3 splits | fixed 25 m | fixed 25 m | z 2.2 | 200 | 165 |
| canyon | 3 splits | fixed 30 m | fixed 30 m | z 1.7 | 307 | 256 |
| density 20 | 3 splits | z 2.5 | fixed 25 m | z 2.5 | 167 | 159 |
| density 60 | 3 splits | fixed 25 m | fixed 25 m | z 2.1 | 202 | 185 |
| density 150 | 3 splits | fixed 20 m | fixed 20 m | z 1.7 | 260 | 208 |

(All 21 rows, including 1:1 and 5:1 per profile and density, are in `matching_synthetic_cost.json`.)

Test split, all cells pooled. Cost = ratio x merges + splits; "saving" = shipped cost minus this rule's cost (positive: cheaper). `floor` = the splits wrong categories force on every rule.

| rule | wrong merges | wrong splits | cost 1:1 | cost 3:1 | cost 5:1 | saving at 3:1 |
|---|---|---|---|---|---|---|
| fixed 10 m | 10.2 [9.4, 10.9] | 236.1 [233.3, 238.8] | 246 [243, 249] | 267 [263, 270] | 287 [282, 292] | -51 [-57, -45] |
| fixed 15 m | 18.2 [17.1, 19.2] | 161.3 [159.0, 163.7] | 180 [177, 182] | 216 [212, 220] | 252 [247, 258] | -0 [-5, +4] |
| fixed 20 m | 27.0 [25.8, 28.3] | 112.6 [110.6, 114.4] | 140 [137, 142] | 194 [189, 198] | 248 [241, 254] | +22 [+19, +26] |
| fixed 25 m | 36.6 [35.0, 38.3] | 84.5 [82.8, 86.3] | 121 [119, 124] | 194 [190, 199] | 267 [260, 276] | +21 [+19, +24] |
| fixed 30 m | 46.7 [45.0, 48.6] | 68.9 [67.3, 70.5] | 116 [113, 118] | 209 [203, 215] | 303 [293, 312] | +6 [+4, +9] |
| fixed 40 m | 68.3 [66.1, 70.6] | 53.7 [52.2, 55.2] | 122 [119, 125] | 259 [252, 266] | 395 [384, 407] | -43 [-46, -40] |
| fixed 60 m | 109.8 [106.8, 113.1] | 44.1 [42.6, 45.7] | 154 [151, 158] | 374 [364, 384] | 593 [578, 610] | -158 [-164, -152] |
| floor | 0.0 | 36.5 [35.0, 37.9] | 36 [35, 38] | 36 [35, 38] | 36 [35, 38] | - |
| shipped (z 3.03) | 53.0 [51.2, 54.8] | 56.6 [55.0, 58.2] | 110 [107, 112] | 216 [210, 222] | 322 [312, 331] | - |
| z 1.5 | 27.7 [26.5, 29.0] | 121.3 [119.2, 123.5] | 149 [147, 152] | 204 [200, 209] | 260 [254, 267] | +11 [+7, +15] |
| z 1.7 (tuned, B) | 30.6 [29.3, 31.9] | 108.6 [106.5, 110.6] | 139 [137, 142] | 200 [196, 205] | 262 [255, 269] | +15 [+12, +18] |
| z 2.0 | 35.5 [34.1, 36.9] | 92.4 [90.6, 94.4] | 128 [125, 130] | 199 [194, 204] | 270 [263, 278] | +17 [+14, +19] |
| z 3.1 | 54.3 [52.4, 56.2] | 55.6 [54.0, 57.2] | 110 [107, 113] | 218 [213, 225] | 327 [317, 337] | -3 [-3, -2] |

Cheapest accuracy-aware z against cheapest fixed radius (both picked on validation), cost saved per 1,000 reports: 1:1 +6 [+5, +7]; 3:1 -5 [-7, -3]; 5:1 -12 [-15, -10].

Shipped-rule cost by cell (3:1, test; floor 35 to 38) and some alternatives:

| density | profile | floor | shipped | fixed 10 m | fixed 15 m | fixed 25 m | fixed 40 m | fixed 60 m | z 1.7 |
|---|---|---|---|---|---|---|---|---|---|
| 20 | open sky | 38 | 109 [102, 115] | 188 | 121 | 122 | 193 | 274 | 120 |
| 20 | city | 38 | 165 [156, 174] | 267 | 202 | 147 | 191 | 271 | 176 |
| 20 | canyon | 38 | 236 [224, 248] | 330 | 292 | 241 | 230 | 275 | 232 |
| 60 | open sky | 35 | 126 [118, 134] | 190 | 129 | 139 | 231 | 355 | 129 |
| 60 | city | 35 | 196 [186, 206] | 266 | 209 | 163 | 230 | 351 | 189 |
| 60 | canyon | 35 | 299 [286, 312] | 325 | 292 | 252 | 276 | 358 | 267 |
| 150 | open sky | 36 | 146 [138, 154] | 201 | 144 | 174 | 308 | 486 | 144 |
| 150 | city | 36 | 261 [249, 273] | 285 | 228 | 206 | 308 | 487 | 212 |
| 150 | canyon | 36 | 402 [386, 418] | 349 | 326 | 304 | 361 | 505 | 335 |

- **Pre-registered answer (3:1): a fixed 20 m radius**, 194 [189, 198] against the shipped 216 [210, 222]: saving 22 [19, 26] per 1,000 reports (10%). The cheapest accuracy-aware z is 2.0, 199 [194, 204] (saves 17 [14, 19]); the curve is flat for z from 1.6 to 2.5 (`matching_synthetic_cost.png`).
- At 1:1 the shipped rule (110 [107, 112]) is as cheap as the cheapest (z 3.1, 110 [107, 113]). At 5:1 fixed 20 m costs 248 [241, 254] against the shipped 322 [312, 331].
- A tighter radius turns wrong merges into wrong splits: per 1,000 reports the shipped rule makes 53 wrong merges and 57 wrong splits; z 2.0 makes 35 and 92; fixed 20 m makes 27 and 113 (36 splits are the floor).
- **The best radius depends on density, much less on profile:** cheapest z at 3:1 is 2.5 at 20 per km2, 2.1 at 60, 1.7 at 150, and at 20 per km2 the shipped rule is already among the cheapest (170 against 166). At 150 per km2 the shipped rule costs 270 [258, 280] and z 1.7 saves 39 [33, 45] (14%); at 20 per km2 z 1.7 would cost 6 [2, 11] more. A radius that shrinks with the number of open same-category tickets nearby (known to the app at decision time) is the direction this points to. Not tested here.

## 9. Where does the shipped rule break? (sensitivity)

Shipped rule only (nothing tuned), around the base world at 60 per km2 (30 patches, 16,200 hazards per point), same seeds at every point, all splits pooled, 300 resamples per interval (intervals in `matching_synthetic_sensitivity.json`). Cells: pair precision / recall by profile; city B-cubed F1 and 3:1 cost; the cutoff the same bin rule gives with profiles pooled (0 = even the best bin is under 0.85, none = no bin is).

**accuracy_scale** (the phone reports this many times its true accuracy; below 1 = over-confident)

| scale | open sky P / R | city P / R | canyon P / R | city B-cubed F1 | city cost 3:1 | cutoff m |
|---|---|---|---|---|---|---|
| 0.5 | 0.93 / 0.86 | 0.88 / 0.79 | 0.77 / 0.74 | 0.918 | 180 | 5 |
| 0.7 | 0.92 / 0.91 | 0.85 / 0.90 | 0.72 / 0.87 | 0.932 | 177 | 5 |
| 1.0 (base) | 0.90 / 0.96 | 0.78 / 0.97 | 0.68 / 0.94 | 0.937 | 202 | 5 |
| 1.4 | 0.86 / 0.99 | 0.70 / 1.00 | 0.63 / 0.96 | 0.928 | 259 | 5 |
| 2.0 | 0.78 / 1.00 | 0.63 / 1.00 | 0.62 / 0.96 | 0.912 | 329 | 0 |
| 3.0 | 0.68 / 1.00 | 0.61 / 1.00 | 0.61 / 0.96 | 0.904 | 363 | 0 |

**accuracy_spread** (sigma of the lognormal noise on the reported accuracy)

| spread | open sky P / R | city P / R | canyon P / R | city B-cubed F1 | city cost 3:1 | cutoff m |
|---|---|---|---|---|---|---|
| 0.0 | 0.91 / 0.96 | 0.81 / 0.98 | 0.69 / 0.95 | 0.941 | 192 | 5 |
| 0.35 (base) | 0.90 / 0.96 | 0.78 / 0.97 | 0.68 / 0.94 | 0.937 | 202 | 5 |
| 0.7 | 0.86 / 0.96 | 0.74 / 0.95 | 0.66 / 0.92 | 0.926 | 237 | 5 |
| 1.0 | 0.81 / 0.96 | 0.72 / 0.94 | 0.66 / 0.90 | 0.920 | 256 | 0 |

**standoff_max_m** (people stand 1 to this many metres from the hazard; the matcher assumes about 4 m)

| stand-off up to | open sky P / R | city P / R | canyon P / R | city B-cubed F1 | city cost 3:1 | cutoff m |
|---|---|---|---|---|---|---|
| 3 | 0.90 / 1.00 | 0.78 / 0.99 | 0.68 / 0.95 | 0.942 | 193 | 5 |
| 5 | 0.90 / 1.00 | 0.78 / 0.99 | 0.68 / 0.95 | 0.941 | 195 | 5 |
| 10 (base) | 0.90 / 0.96 | 0.78 / 0.97 | 0.68 / 0.94 | 0.937 | 202 | 5 |
| 15 | 0.89 / 0.84 | 0.78 / 0.93 | 0.68 / 0.93 | 0.928 | 217 | 5 |
| 20 | 0.87 / 0.69 | 0.77 / 0.88 | 0.67 / 0.90 | 0.916 | 239 | 5 |
| 30 | 0.81 / 0.44 | 0.74 / 0.72 | 0.66 / 0.82 | 0.886 | 293 | 0 |

**clustering** (share of hazards in clusters, mean hazards per cluster)

| clustered | open sky P / R | city P / R | canyon P / R | city B-cubed F1 | city cost 3:1 | cutoff m |
|---|---|---|---|---|---|---|
| 0 (uniform) | 0.97 / 0.96 | 0.93 / 0.97 | 0.86 / 0.95 | 0.958 | 102 | 30 |
| 25%, 3 | 0.93 / 0.96 | 0.85 / 0.97 | 0.75 / 0.94 | 0.948 | 151 | 10 |
| 50%, 3 (base) | 0.90 / 0.96 | 0.78 / 0.97 | 0.68 / 0.94 | 0.937 | 202 | 5 |
| 80%, 6 | 0.79 / 0.96 | 0.62 / 0.97 | 0.49 / 0.95 | 0.901 | 363 | 0 |

**popularity** (reports per hazard)

| reports per hazard | open sky P / R | city P / R | canyon P / R | city B-cubed F1 | city cost 3:1 | cutoff m |
|---|---|---|---|---|---|---|
| geometric, mean 1.6 (base) | 0.90 / 0.96 | 0.78 / 0.97 | 0.68 / 0.94 | 0.937 | 202 | 5 |
| heavy tail, mean 2.94 | 0.97 / 0.96 | 0.94 / 0.97 | 0.91 / 0.94 | 0.888 | 162 | none |

**uniform_density** (no clustering at all, hazards per km2: the main run's densities without the bunching)

| density | open sky P / R | city P / R | canyon P / R | city B-cubed F1 | city cost 3:1 | cutoff m |
|---|---|---|---|---|---|---|
| 20 | 0.99 / 0.96 | 0.97 / 0.97 | 0.95 / 0.94 | 0.966 | 64 | none |
| 60 | 0.97 / 0.96 | 0.93 / 0.97 | 0.86 / 0.95 | 0.958 | 102 | 30 |
| 150 | 0.94 / 0.96 | 0.84 / 0.97 | 0.70 / 0.94 | 0.945 | 166 | 10 |

Figures: `matching_synthetic_sensitivity.png` (recall and precision against three settings), `matching_synthetic_sensitivity_grid.png` (city, phone accuracy and stand-off together).

- **Over-confident phones break recall.** At half the true error recall is 0.86, 0.79, 0.74 (open sky, city, canyon); at 0.7 still 0.91, 0.90, 0.87. Under-confident phones break precision instead: at 1.4 times the true error city precision is 0.70, at 2 times 0.63, recall 1.00. The shipped rule trusts the phone's accuracy completely; a fixed radius does not. In sample, the best fixed radius beats the shipped rule by 0.03 to 0.21 F0.5 once phones are off by a factor 1.4 or more.
- **Noise in the reported accuracy hurts precision, not recall:** city precision 0.81 without noise, 0.78 at the assumed 0.35, 0.72 at 1.0.
- **Stand-off:** the shipped 3 m per axis has room: recall is flat up to a stand-off of 10 m (4.3 m per axis), then falls. Open sky breaks first because its radius is smallest: 0.84 at 15 m, 0.69 at 20 m, 0.44 at 30 m; city 0.93, 0.88, 0.72; canyon 0.93, 0.90, 0.82. With over-confident phones as well, city recall is 0.39 at (half the true error, stand-off up to 30 m) and 0.58 at (half, 20 m).
- **Clustering is the main driver of precision** (city: 0.93 uniform, 0.85, 0.78 in the base world, 0.62 at 80% clustered in groups of 6); recall does not move. With unclustered hazards the open-sky and city precision targets hold at 20 and 60 per km2 (open sky 0.991, 0.970 [0.965, 0.974]; city 0.975, 0.928 [0.919, 0.934]) and fail at 150 (open sky 0.938 [0.931, 0.944] against 0.95; city 0.837 [0.827, 0.847] against 0.90).
- **Heavy-tailed popularity flatters pair metrics:** pair precision rises (0.97 / 0.94 / 0.91) because true pairs grow with the square of the reports per hazard, while B-cubed F1 falls (0.888 in the city against 0.937). Use the replay for decisions in such a world.
- **Density** is in the main run: precision falls and cost rises with density in every profile.

## 10. Recommended changes to `settings.py`

Not edited. Each leans on assumptions this simulation cannot check; the first is the stronger.

1. **Add an auto-merge accuracy cutoff, 5 m** (new setting, e.g. `AUTO_MERGE_MAX_ACCURACY_M`): auto-merge only when the new report's reported accuracy is at most this; above it create a new ticket and suggest candidates. Evidence: validation precision of the shipped merges falls from 0.91 (up to 5 m) through 0.84, 0.75, 0.71, 0.65, 0.62 as accuracy worsens, in every profile and density; on the test split auto-merges within 5 m are 0.903 [0.896, 0.910] precise against 0.774 [0.766, 0.783] without the cutoff. Cost: 83% of true duplicate pairs go to suggestions. With z lowered as below, use **10 m**.
2. **`MATCH_Z` 3.03 to 2.0**, if a wrong merge really costs about 3 wrong splits. Evidence: cheapest accuracy-aware z on validation at 3:1; on test it saves 17 [14, 19] per 1,000 reports (8%), cutting wrong merges from 53 to 35 and raising wrong splits from 57 to 92; F0.5 +0.028 [+0.022, +0.033] for a mixed fleet at 60 per km2; the direction holds on the canyon when tuned on the other two profiles. The curve is flat from 1.6 to 2.5, so 2.5 is a safe half step. Do not make the change if wrong merges and splits cost the same (1:1 optimum 3.1), if hazards are close to unclustered (optimum 2.5 to 3.4), or if phones' accuracy is over-confident (9).
3. **No change to `STAND_OFF_SIGMA_M`, `MATCH_MIN_M`, `MATCH_MAX_M`, `DEFAULT_ACCURACY_M`.** The simulation's stand-off is larger than the matcher's on purpose, so tuning to it would be circular; recall only breaks for stand-offs of 15 m and more.
4. **Worth testing, not recommended yet:** a radius that shrinks with the number of open same-category tickets near the report (best z 2.5, 2.1, 1.7 at 20, 60, 150 per km2), and a plain fixed radius of about 20 m, which costs less than every accuracy-aware setting at 3:1 and 5:1.

The real-data checks in EVALUATION.md matter more than these numbers: the Chicago results say how often a radius merges requests the city did not flag (a direct measure of the clustering that drives precision here), and the five-teammate field test measures real stand-off and GPS error.

## 11. Limitations: what this simulation assumes and leaves out

The first three move the conclusions most.

1. **Hazard clustering (my guess):** half the hazards in clusters of about 3, 25 m spread, no streets. It sets the precision of every rule (9). Real hazards lie along roads, and same-category neighbours along a street (lamps, drains, potholes on a bad stretch) can be 20 to 40 m apart, the hard case for the radius.
2. **Independent, zero-mean, isotropic Gaussian GPS error** per report, with a reported accuracy right on average. Real canyon error is correlated between phones at one spot, biased and heavy-tailed; phones report 0, missing or rounded accuracy; miscalibration is per device, not one global factor.
3. **Stand-off uniform on 1 to 10 m; hazards are points.** Real hazards have extent (a flooded street, a blocked sidewalk) and people stand where the camera reaches.
4. **Category:** fixed weights, 6% wrong picks uniform among the other four, never "other". Real wrong picks are structured, and a wrong "other" would only add splits.
5. **Reports:** independent people, geometric or Zipf counts; no repeated reports by one phone, no bursts, no spam, no photos.
6. **Time:** nothing is fixed or reopened (`REOPEN_WINDOW_DAYS` untested), hazards persist 30 days, arrival order is random.
7. **The replay is the shipped logic** (a ticket sits at its most accurate report, a new report is compared with that spot only); the engine is a stub, so the real flow may differ. A ticket's category is its first report's.
8. **Pair metrics weigh popular hazards by their pairs**, so they look better than ticket-level metrics in a heavy-tailed world (9). The replay is the decision-grade number.
9. **The 3:1 cost ratio is assumed;** 1:1 and 5:1 bracket it. The true cost of staff time to undo a merge or a split is unknown.
10. **Common random numbers:** the three profiles share hazards, so they are not independent samples (intervals resample districts jointly across them). Patches are independent 3 km worlds, not neighbours.
11. **Tuning grids:** z on a 0.1 grid, fixed radii from a fixed list; boosted trees and logistic regression are diagnostics; the logistic regression's four features follow the task statement.
12. **Intervals are sampling intervals,** validated once (city, 60 per km2); they do not cover uncertainty about these assumptions. That is what section 9 is for.
13. **Scope:** no Makati data, no real phones. Where this and the Chicago evaluation disagree, trust the real data about the radius and this simulation about the mechanism.

## 12. Files and how to reproduce

`models/tickets/eval/matching/synthetic/`: `simulator.py`, `evaluate.py` (pairs, replay, rules, intervals, cutoff, cost, the run), `sensitivity.py`, `recommended.py`, `interval_check.py`, `figures.py`, `report_tables.py`, `tests/` (42 tests, about 30 s). `models/tickets/eval/results/`: `matching_synthetic_{main,variants,cutoff,cost,sensitivity,recommended,interval_check}.json` and `matching_synthetic_{curves,variants,zcurve,cutoff,cost,sensitivity,sensitivity_grid}.png`. Big intermediates are never written.

From the repository root (`models/.venv`):

```
models/.venv/bin/pytest models/tickets/eval/matching/synthetic -q -p no:warnings
models/.venv/bin/python -m models.tickets.eval.matching.synthetic.evaluate           # development run: dev seeds, validation only, into eval/data/cache/
models/.venv/bin/python -m models.tickets.eval.matching.synthetic.evaluate --final   # the one final run, about 8 minutes on 10 cores
models/.venv/bin/python -m models.tickets.eval.matching.synthetic.sensitivity        # about 4 minutes
models/.venv/bin/python -m models.tickets.eval.matching.synthetic.recommended        # needs the final cost file
models/.venv/bin/python -m models.tickets.eval.matching.synthetic.interval_check
models/.venv/bin/python -m models.tickets.eval.matching.synthetic.report_tables      # regenerates every table above from the JSON
```
