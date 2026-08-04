# Handoff: review findings, as a work order

Output of an independent blind review (2026-08-04). Ordered by priority. Each item states the
file, the symptom, the measurement behind it, and what **not** to touch while you are in there.

**Read §0 before doing anything. Then do §1 and §2. Do not action §4.**

Line numbers are deliberately omitted — `reports/findings.md` was rewritten mid-review and
they drift. Anchor on the quoted strings.

---

## 0. Two things to settle before any code moves

### 0.1 The pre-registration is tagged. Fixing §6 changes it.

`reports/league_projection_2026_27.csv` is the frozen prediction. `scorecard.frozen_projection()`
loads it and its docstring says it "must not be regenerated to score itself — recover it from the
`projection-2026-27` tag."

Items **2.4, 2.5 and 2.6 below all change that file.** Regenerating it silently is the single
worst thing that could happen to this repo: it converts a pre-registered forecast into a forecast
that was quietly edited after commit, which is the exact failure the pre-registration exists to
rule out.

**Do not regenerate it.** The options are a decision for the author, not for an implementer:

- (a) leave the tag alone, publish an erratum in `findings.md` §6 describing the defects, and add a
  **second, separately-named** corrected forecast scored alongside the original; or
- (b) retag before opening night with the corrections applied and the reason recorded.

Until that is chosen, fix the *code* in `league.py` / `dpm_calibration.py` / `simulate.py` behind
a flag or on a branch, and leave the committed CSV untouched.

### 0.2 `data/processed/` is present in this working copy

`REVIEW_CONTEXT.md` says no data is committed and nothing can be regenerated. True of a clone,
false here — the parquet tree is on disk. That means:

| Command | Cost | Safe to rerun |
|---|---|---|
| `make test` | 5s | yes |
| `make stopping` | ~4 min | yes (rewrites `reports/stopping_*.csv`) |
| `make winprob` | ~3 min | yes |
| `make ablate` | ~4 min | yes |
| `make score` | ~1 min | yes (rewrites `shots_scored.parquet`) |
| `make project` | minutes | **NO — see 0.1** |
| `make backfill` | hours | avoid |

Verify claims against the data rather than reasoning about them. Every measurement quoted below
was produced this way and can be reproduced.

---

## 1. Prose–artifact reconciliation (text only, no reruns, do first)

The repo invites this check explicitly ("whether the prose matches the tables are all checkable
from a clone"). It currently fails on the flagship finding.

### 1.1 §4d tables are stale in BOTH `findings.md` and `METHODOLOGY.md`

Source of truth: `reports/stopping_relaxation.csv`, `reports/stopping_continuation_value.csv`,
`reports/stopping_robustness.csv`. Only the `boundary_drop` row currently matches.

| Where | Printed | Committed CSV |
|---|---|---|
| `findings.md` "`V(t)`, value of holding" row, first cell | 0.361 | **0.3746** |
| same row, second cell (3s) | 0.465 | 0.4679 |
| "P(shoot this second)" 1s / 3s | 53% / 31% | **52% / 30%** |
| "`V(t)` falls over the same range" | 0.447 ×5 | **0.4332** ×5 |
| "Relaxation ratio" row | .63 .67 .52 .57 .55 | **.649 .696 .537 .591 .567** |
| "Excess demand at 1-3s vs 8-23s" | .144 .147 .170 .173 .166 | **.137 .139 .163 .165 .158** |
| "All games" robustness row | 0.52 – 0.67 / +0.160 | **0.537 – 0.696 / +0.152** |
| "Competitive (\|margin\| ≤ 10)" | 0.56 – 0.71 / +0.148 | **0.586 – 0.731 / +0.139** |
| "Blowouts (\|margin\| > 10)" | 0.46 – 0.58 / +0.184 | **0.464 – 0.587 / +0.179** |
| "Ratio mean 0.61, SD 0.087" | mean 0.61 | **mean 0.641** (SD 0.087 is correct) |
| `METHODOLOGY.md` "**0.52-0.67 across every quantile" | 0.52-0.67 | **0.537-0.696** |
| `METHODOLOGY.md` "(mean 0.61, SD 0.087)" | 0.61 | **0.641** |

Downstream prose that must move with them:

- "**Offenses lower their standard by only about 55 to 65%**" → 54 to 70%.
- "excess late demand +0.14 to +0.17" → +0.14 to +0.16.
- "the continuation value in 4d runs 0.36 to 0.81, a 2.2× range" → 0.37 to 0.81, 2.16×
  (appears in `findings.md` §4f and in `models/winprob.py`'s module docstring).

The per-season SD of 0.087 reproduces exactly from the midpoints of the ten season rows in
`stopping_robustness.csv`, which is how we know these came from an earlier `V(t)` run rather
than being typos: the mean should be 0.641.

**Do not** rerun `make stopping` to "make the CSVs match the prose." The CSVs are correct; the
prose is stale. Edit the prose.

### 1.2 §4f cites a fine ablation row against coarse groups

`findings.md`: "Negligible, 0.00136 log loss, smallest group in the ablation" — and the same
claim in `models/winprob.py`'s module docstring ("removing it costs 0.00136 log loss, the
smallest group tested").

`0.00136` is `shot clock alone`, an `ABLATION_GROUPS_FINE` row. `METHODOLOGY.md` §6 and
`xpts.py`'s own comment both state the fine rows overlap the coarse blocks and are "not
comparable across groups." The comparable coarse figure is the **possession block at 0.00396
(13.6% of gain)** — third of four, and not the smallest (shooter prior is 0.00184).

Fix the number in both places, or add the caveat. As written the headline contradicts the
project's own stated discipline two sections earlier.

### 1.3 Dangling cross-references

- `findings.md` §4f: "The ablation in finding 4 asked whether..." — `findings.md` has no ablation
  section. `winprob.py` says "the ablation in §6"; §6 is the projection.
- `reports/ablation.csv` is committed and never reported in `findings.md`.
- The xPTS model's own out-of-sample metrics (log loss 0.6273, AUC 0.676, 9.3% over league mean)
  appear only in `METHODOLOGY.md`. Every downstream number depends on that model.
- `.review/REVIEW_CONTEXT.md` artifact table promises `reports/exploration_h*.log`. **They do not
  exist.** It also says "All 24 report artifacts are committed"; there are 21 files in `reports/`.

### 1.4 Smaller drift (label as separate runs or reconcile)

- §5 "≥800 chances" row prints −0.0192 / −0.0512 / +0.0127; `lineup_overlap_specifications.csv`
  has −0.0190 / −0.0505 / +0.0125.
- §6 sensitivity table prints 30.2% / 2.0% / 73% for `rating_sd = 3.95`;
  `league_projection_2026_27.csv` gives 29.2% / 2.065% / 72.2% for what is presented as the same
  configuration. (`METHODOLOGY.md` repeats 30.2%.)

---

## 2. Code defects (each verified against the data on disk)

### 2.1 `SCORE_MARGIN` is a post-outcome feature — **highest severity**

`src/possval/features/shots.py`, `attach_game_state`. The pbp `SCOREMARGIN` column is populated on
**100% of made-FG rows and 0% of missed-FG rows** (measured, 2024-25). The function merges it at
the shot's own `GAME_EVENT_ID` and then forward-fills, so a made shot's margin already contains
that shot's own points.

Measured on 2024-25 `shots_scored.parquet`:

```
IS_HOME 1   margin(made) − margin(missed) = +2.437
IS_HOME 0   margin(made) − margin(missed) = −2.405
```

It is currently near-harmless **only by accident**: `IS_HOME` is in `features/shots.NUMERIC` and
in `shots_scored.parquet`, but absent from `xpts.GBM_NUMERIC`, so the ± cancels. Fitting the leak
directly (HistGBM, train ≤2022, test 2024):

```
base (league mean)          log loss 0.69144
SCORE_MARGIN alone          AUC 0.505   log loss 0.69113
SCORE_MARGIN + IS_HOME      AUC 0.564   log loss 0.68461   <- 0.0068 of pure leakage
```

0.0068 is **five times** the entire reported value of the reconstructed shot clock (0.00136), and
1.7× the whole possession block (0.00396).

**Fix:** shift the margin by one event within game before the merge — the shot should see the
score *before* it. Then rerun `make score` and `make ablate`.

**Consequence to report:** the "game state" ablation block (0.00812, 27.9% of gain) is not a clean
estimate as published. Expect it to fall.

**Do not** add `IS_HOME` to `GBM_NUMERIC` as a "fix" — that turns the latent leak into a live one.

### 2.2 `compare_league_wide` sums a per-game file as if it were totals

`src/possval/clock/validate.py`, `compare_league_wide`. `official_shotclock_2024_25.csv` is
per-game — the module docstring says so, and `compare_per_player` divides by `GP` accordingly.
`compare_league_wide` does not: it sums official per-game rates against reconstructed totals.

Measured, GP-weighting the official side:

```
mean |share error|   1.198 pp -> 1.188 pp   (unaffected)
mean |eFG error|     1.777 pp -> 1.054 pp   (40% of it was the aggregation)
```

**Consequence:** the "eFG is biased high by 1.8pp on average, worst in late-clock buckets"
line in `METHODOLOGY.md` §4 "Known residual error", and the "eFG is biased high by 1.78pp"
sentence in `findings.md` §2, both need the corrected number. A residual bias does remain
(+1.05pp, positive in five of six buckets), so the *interpretation* survives; the magnitude and
the mechanism attribution do not.

**Fix:** multiply the official `FGA`/`FGM`/`FG3M` by `GP` before the groupby in
`compare_league_wide`. Add a regression test asserting the two axes use the same weighting.

### 2.3 `team_possessions` counts events, not offensive rebounds

`src/possval/models/synergy.py`: `orb = df[df.CHANCE_START_TYPE == "off_rebound"]` then
`.groupby("OFF_TEAM_ID").size()` — that counts **every event inside** an off-rebound chance.

Measured 2024-25: 1,955 per team as coded, against 1,144 actual off-rebound chances.
`POSS = FGA − ORB + TOV + 0.44·FTA` comes out at **87.5 per game instead of 97.4** (~11% low),
inflating `ORTG_FG` by ~11%.

**Fix:** `drop_duplicates(["GAME_ID", "CHANCE_ID"])` before the count.

**Also:** `synergy.py` has no CLI entry point and no committed CSV — `make synergy` runs
`lineup-test`, which is `lineup_synergy.py`. Finding 5's team-season table (270 team-seasons,
top-3/4/8 cores) therefore cannot be reproduced from the repo, and which outcome column produced
it (`PTS_PER_FGA`, `PTS_VS_XPTS`, or the broken `ORTG_FG`) cannot be determined. Add a
`cmd_synergy` and a committed artifact, or move the table's provenance into the text.

### 2.4 The playoff bracket is frozen across all simulations — **see §0.1**

`src/possval/models/league.py`, `project_league`: `ordered = wins.mean().sort_values(...)`. The
16-team field is identical in all 20,000 simulations. The comment claims the opposite ("so a team
that under- or over-performs its rating carries that into the bracket") — averaging removes
exactly that.

In the committed CSV, **14 of 30 teams have title probability exactly 0.00000**, including PHX
(+0.27 rating, 80% interval to 55 wins) and MIA (+0.06, to 54).

**Fix:** seed per simulation inside the loop, or return per-sim win vectors and seed from each.
Bubble teams gain a few tenths of a point; the fixed field loses the same.

### 2.5 The DPM→rating slope is in-sample, applied forward — **see §0.1**

`src/possval/models/dpm_calibration.py`. The July-2026 DARKO snapshot postdates the 2025-26 season
it is regressed on, so **slope 1.433 measures how much DARKO shrinks its own within-season
estimates.** Un-shrinking by 1.433 is right for reproducing that season and wrong for projecting
the next. The forward slope is approximately 0.587 (the repo's own YoY SRS correlation, cited in
`findings.md` §6) × 1.433 ≈ 0.84.

Measured, re-running `project_league` with ratings scaled by 0.587 (6,000 sims, all else equal):

```
                      as published    forward-shrunk
PHI title                  2.05%           3.47%
PHI wins                    49.4            46.5
top-3 share                72.1%           51.9%
```

`METHODOLOGY.md` currently says the fit *statistics* are optimistic. The **slope** is the
contaminated part, and that is not stated anywhere.

**Fix path:** the only clean version is to regress 2025-26 SRS on a DARKO snapshot taken *before*
2025-26. If no back-dated snapshot exists, apply an explicit shrink with the factor and its
derivation stated in the text rather than leaving 1.433 undefended.

### 2.6 The margin scale is circular, and the scorecard handicaps its own baseline — **see §0.1**

`src/possval/models/simulate.py`: `CONTEMPORANEOUS_MARGIN_SCALE = 7.0`, justified by "a +12.7 team
came out at 60 wins rather than the 68 Oklahoma City actually won." That +12.7 was computed *from*
those 68 wins. The `METHODOLOGY.md` §10 backtest ("win-total MAE 3.15, correlation 0.949") is
circular the same way. A split-half fit (SRS on odd games, scored on even) gives the honest value.

Separately and independently fixable: `scorecard.score_games` calls `win_probability(...)` with the
default scale for **all three** models, so the prior-season-SRS baseline is graded at 7.0 — though
`simulate.py` documents **10.5** as the correct scale for prior-season ratings. That biases the
pre-registered comparison toward the projection.

**Fix (safe, does not touch the frozen CSV):** pass `scale=PRIOR_SEASON_MARGIN_SCALE` for the
naive baseline in `score_games`. Do this one now; it changes no published number, only future
scorecard rows.

### 2.7 `srs_ratings.parquet` has no producer

Read by `league.py`, `dpm_calibration.py` and `scorecard.py`. Written by nothing in `src/` or the
Makefile. `ratings.season_ratings()` computes it and is called by nobody. After `make clean`,
`make project` and `make scorecard` cannot run.

**Fix:** add a `ratings` pipeline command (`all_game_results` → `season_ratings` → write) and a
`make ratings` target, and put it in the dependency order in `REVIEW_CONTEXT.md`'s reproduction
table.

### 2.8 One-sided game-clock repair, with a test that passes on the broken case

`src/possval/clock/reconstruct.py`: `running_min_gc` is updated for **every** event, including
`INERT` ones, before the `if etype in R.INERT: continue`. A single spuriously *low* timestamp
therefore drags the minimum down and mis-times every following event until real time catches up.

Measured 2024-25: **379 isolated downward dips >5s** (median 12s), 44 of them on
substitutions/timeouts — the events the docstring names as the worst offenders.

Running the repo's own `test_non_monotone_game_clock_is_repaired` fixture with one real shot
appended:

```
EVENTNUM PCTIME  GAME_CLOCK SHOT_CLOCK REPAIRED CHANCE_START_TYPE CONFIDENCE
       3   4:39       279.0        NaN    False    inferred_reset        low
       4  11:38       698.0        NaN     True    inferred_reset        low   <- real rebound, clamped to 279
       5  11:20       680.0       24.0     True       def_rebound       high   <- real shot, wrong clock, HIGH confidence
```

The test passes because it asserts only `REPAIRED.any()` and `max <= 24`.

**Fix:** (a) do not let `INERT` events update `running_min_gc`; (b) detect isolated dips — an event
whose clock is far below both its predecessor and its successors — and discard that event's
timestamp rather than clamping everything after it; (c) tighten the test to assert the *following*
event's clock, not just that a repair happened.

### 2.9 `PRIOR_PPA` in the lineup panel is not a prior

`src/possval/pipeline.py`, `cmd_lineup_test`: `prior` is built from `shots.groupby(["PLAYER_ID",
"SEASON"])` over **all** seasons including the outcome season, then collapsed to one scalar per
player. `lineup_synergy`'s module docstring says "individual quality enters as the summed
prior-season scoring of the five players"; `build_lineup_panel` takes the **mean**.

So the only quality control in the specification curve and the head-to-head is contemporaneous and
season-invariant. (`synergy.py`'s team-season version uses `season − 1` correctly, so this looks
like drift.)

**Fix:** build per (PLAYER_ID, SEASON) from strictly prior seasons, matching `synergy.py`. Rerun
`make synergy` (i.e. `lineup-test`) and update `reports/lineup_overlap_*.csv` and §5.

### 2.10 `team_relaxation_null` does not do what its docstring says

`src/possval/models/stopping.py`: docstring says labels are "permuted across chances and shots at
the real group sizes"; the code uses `rng.choice(teams, n)` — i.i.d. with replacement, which
equalises group sizes and destroys the game/season clustering of real team samples. It also
shuffles `panel` and `shots` independently, so a null "team's" chances and its shots come from
unrelated draws.

The 37% signal share in §4e rests on this, from 20 draws, with no interval, and the repo's own
sensitivity (10 draws → 43%) shows it is still moving at 20.

**Fix:** permute by shuffling the existing team label vector (`rng.permutation`) rather than
resampling; permute chances and shots with the same mapping; raise `n_draws` and report a spread.
Either fix the docstring or fix the code — currently they disagree.

### 2.11 `aging.attach_age` is off by about two years

`src/possval/models/aging.py`: `out["AGE"] = out.PLAYER_ID.map(lookup) - (current_season - out.SEASON)`
with `current_season = seasons.SEASON.max()` = 2024, and `lookup` from a **July 2026** DARKO
snapshot. A player's 2024-25 age is therefore set to his mid-2026 age.

`METHODOLOGY.md` §9's support table (12 player-seasons at 38, 5 at 39, 2 at 40, 1 at 41) is really
about ages ~36–39. The decision not to apply aging is unaffected; the stated justification is off
by two years and should be corrected or recomputed.

### 2.12 Heaves are not excluded from the late-clock leaderboards

`src/possval/pipeline.py`, `cmd_score`: `grade_by_clock(test)` and `late_clock_specialists(test)`
receive the unfiltered frame, so buzzer-beater heaves sit in the ≤7s bucket — contradicting the
exclusion established in `features/shots.EXPIRING_SECONDS`, applied everywhere else, and for which
`GAME_CLOCK_EXPIRING` is carried into `shots_scored.parquet` specifically.

**Fix:** filter `GAME_CLOCK_EXPIRING == 0` before both calls, matching `cmd_stopping`.

### 2.13 Technical and flagrant free throws flip possession

`src/possval/clock/reconstruct.py`, `FREE_THROW` branch. Any terminal made FT triggers
`begin_chance(gc, FULL_CLOCK, "after_made_ft", other_team(shooter))`. After a technical the ball
returns to the team that had it and the shot clock *resumes*; after a flagrant set the fouled team
retains it.

Measured 2024-25: 879 technical and 117 flagrant terminal made FTs. 0.17% of events, partly
self-healing via the `inferred_change` guard, at the cost of extra low-confidence drops. Low
priority — fix by detecting "Technical" / "Flagrant" in the description and suppressing the
possession flip and the reset.

---

## 3. Missing checks worth adding (cheap, in rough value order)

1. **Seed variance on the ablation.** Nine single-seed refits with a random early-stopping split,
   and every claim turns on differences of ~1e-3. Run 5 seeds, report a spread.
2. **Seed variance on the winprob comparison.** The bootstrap holds both fitted models fixed, so
   "reliably non-zero" on a 1.6e-4 effect is conditional on one `random_state`.
3. **Is the 2017-18 feed shift symmetric across treated and control?** `timestamp_granularity`
   shows the after-rebound identical-clock share steps 14.9% → 18.7% in 2017-18 and stays at
   17.8–18.8% *forever after*. Dropping 2017-18 makes the feed regime perfectly collinear with
   treatment. The DiD survives only if the shift hits off-rebound and def-rebound chances equally.
   Split `after_rebound_identical_pct` by rebound type — one function, decides whether §4b holds.
4. **Wild-cluster bootstrap for §4b.** G = 9; `_cluster_ols` applies only G/(G−1) and the reported
   *t* is read against a normal. t = −2.52 vs t₈ critical 2.31.
5. **`START_SC` clip diagnostic.** 86.5% of chances land on the 24 clip (measured), so the
   derivation's failure mode — a dropped low-confidence chance making `PREV_GC` non-adjacent — is
   invisible. Report how often the pre-clip value exceeded 24 + the 2s inbound delay.
6. **Extend `low_confidence_sensitivity` beyond finding 3.** The same non-random 4.2% drop
   underlies finding 2's curve, `V(t)`, and every creation profile; only finding 3 is tested.
7. **More seasons of official aggregates.** External validation currently covers 2024-25 only.
   Scraping two or three more, including one pre-2018 (different reset rule, currently no external
   check at all), hardens the foundation everything stands on.
8. **`offensive_lineups` majority vote.** Which five are on offense is decided from a single
   player's modal team (`HOME_PLAYER1`), with no fallback for traded players.

---

## 4. DO NOT ACT — discuss first

These are research objections, not defects. There is no patch. An agent attempting one will move
published numbers for reasons nobody can later reconstruct. Raise them; do not fix them.

**4.1 `V(t)` is adversely selected, and the bias falls on the shape.** `V(t)` averages the outcomes
of chances that *declined* at `t` — possessions where nothing was available — and that group gets
worse as the clock falls. From `stopping_continuation_value.csv`: 94% of live chances continue past
17s, only **48% past 1s**. So `V(t)` is biased down, increasingly so late, which makes it fall
faster than the true option value and pushes the relaxation ratio below 1 mechanically. This is
the §2 selection argument applied to §4d's own estimator, and it lands on the *shape*, which is
the only thing §4d claims is identified. Addressing it means changing what `V(t)` is, not fixing a
line of code.

**4.2 The synthetic validation of the relaxation ratio bypasses `V(t)`.**
`test_relaxation_ratio_is_one_when_the_boundary_tracks_value` hands `relaxation` a hand-written
`values` frame and never calls `continuation_value`. Same for
`test_boundary_recovers_a_known_threshold` (constant `V_CONT = 0.7`). The tests validate the ratio
arithmetic given a correct `V(t)`; they cannot detect bias in the contested component. The claim
in `findings.md` and `METHODOLOGY.md` that "the measured ~0.5 is a deviation, not a property of the
estimator" is broader than the tests support. **Softening that sentence is a text change and is in
scope; writing a new test that "proves" it is not** — the right test requires 4.1 resolved first.

**4.3 `V(t)` omits offensive-rebound continuation.** A chance ending in a missed shot the offense
rebounds scores 0 `PTS_FG`, but the *possession* continues with real value. Off-rebound chances are
10.2% of the panel. The free-throw omission is quantified and signed (+0.084); this larger one is
not mentioned. Whether to fold it in changes the definition of a chance's value — a design
decision.

**4.4 Creation overlap is mechanically entangled with its outcome.** `OVERLAP` is a similarity
between two players' distributions over (shot-clock bucket × zone), measured in the **same season**
as `PTS_PER_CHANCE`. Two players who both concentrate early in the clock score high similarity, and
early-clock chances are more efficient — finding 2. A positive coefficient is what the construction
produces before any redundancy story, and team-season FE does not break the channel. Separately, JS
divergence from finite samples is biased up by ~(cells−1)/(2n ln 2), which with 18 cells and a
150-attempt floor varies across the sample and correlates with usage; the +1 Laplace smoothing
pushes the same way. No correction and no check that `OVERLAP` is uncorrelated with attempt volume.

**4.5 The uncorrected +2.0s `off_rebound` residual sits on the treated arm of §4b.**
`METHODOLOGY.md` §3 records it and attributes it to airballs. `off_rebound` is the treated group in
the rule-change DiD, whose outcome is a game-clock difference and whose estimate is 0.202s. Needs a
bound, not a footnote — but the fix is a modelling decision about rim contact, not a patch.

**4.6 The six "deliberate, please don't fix" items in `REVIEW_CONTEXT.md` stand.** NaN over a
fabricated 24, violation-based delay calibration, ablation over permutation importance, clustering,
FG-points-only, and specification curves are all the right calls. Two caveats to raise with the
author, not to action: the FG-points-only conservativeness argument audits one omission and not
the other (4.3); and the §4b clustering is *under*-corrected, not over (§3.4).

---

## 5. Suggested order

1. §0.1 — get the pre-registration decision before touching `league.py` or the frozen CSV.
2. §1 — all prose reconciliation. Text only, no reruns, no risk.
3. §2.6 second half (scorecard baseline scale), §2.7 (`srs_ratings` producer), §2.12 (heave
   filter), §2.10 (null docstring/code). All small, none touches a published headline.
4. §2.1 (`SCORE_MARGIN`) → `make score` → `make ablate` → update §6 ablation prose in
   `METHODOLOGY.md`. Expect the game-state block to fall.
5. §2.2 (validation aggregation) → update the eFG-bias numbers in both documents.
6. §2.3, §2.9 → rerun `lineup-test`, update §5 and its CSVs.
7. §2.8 (clock repair) → this changes the reconstruction, so everything downstream moves. Do it
   last, on a branch, and diff the validation table before and after.
8. §2.4, §2.5 — only once §0.1 is settled.
9. §3 — additions, once the above is stable.
10. §4 — raise, do not action.
