# Methodology

Audit log for the possession-value project. Each section states what was done, why, and how
it was checked. Numbers are reproducible via `make validate`.

---

## 1. Data sources

| Dataset | Source | Grain | Coverage |
|---|---|---|---|
| `nbastats` | [shufinskiy/nba_data](https://github.com/shufinskiy/nba_data) | one row per PBP event | 1996-2024 |
| `shotdetail` | same | one row per FGA | 1996-2025 |
| `official_shotclock_2024_25.csv` | nba.com/stats, scraped Nov 2025 | player × shot-clock bucket, per game | 2024-25 |
| DARKO DPM | [Google Sheet](https://docs.google.com/spreadsheets/d/1mhwOLqPu2F9026EQiVxFPIN1t9RGafGpl-dokaIsm9c) | player | current |

Season keys are **start years**: `2024` = the 2024-25 season.

Bulk archives replaced the repo's original 900-line Selenium scraper, which drove a headless
Chrome session against nba.com per shot-clock bucket. The archives are the same underlying
stats.nba.com responses, already collected: a full 10-season backfill is a few hundred MB of
HTTP instead of thousands of rate-limited, markup-dependent requests.

2024-25 loaded: **1,230 games, 574,360 PBP events, 219,527 shots.**
Join key: `shotdetail.GAME_EVENT_ID` ↔ `nbastats.EVENTNUM`, within `GAME_ID`. Match rate 100%.

---

## 2. Shot clock reconstruction

**Problem.** No public NBA feed contains a per-shot shot clock. It is recoverable because
play-by-play records the game clock at every event plus every event that resets the clock.

**Terminology** (follows pbpstats): a *possession* ends when the ball changes teams; a
*chance* is one shot-clock interval. An offensive rebound starts a new chance inside the
same possession.

### Reset rules

| Trigger | New clock |
|---|---|
| Period start, made FG, defensive rebound, turnover, made final FT, offensive foul | 24 |
| Offensive rebound, non-shooting defensive foul, kicked ball | `max(remaining, 14)` |
| Technical foul, substitution, timeout, replay | no change |

**The 14-second reset is `max`, not `min`.** Per NBA Rule 7 §II, a frontcourt reset raises
the clock to 14 only if fewer than 14 seconds remain; with 14+ remaining it is left alone. A
team rebounding two seconds into a possession keeps its ~22 seconds rather than being
penalised down to 14. Implementing this as `min` is the most common way to get it wrong.

Pre-2018-19 seasons reset to a full 24 (`FOURTEEN_SECOND_RULE_SEASON = 2018`).

### Four corrections found by inspecting traces

Each was found by reading actual event sequences, and each measurably improved validation.

1. **Shooting fouls do not return the ball.** They award free throws. The feed's action codes
   cannot distinguish a personal foul in the penalty (offense goes to the line) from one that
   isn't (offense retains with a frontcourt reset). Resolved with a one-event lookahead:
   whether free throws *actually follow* is the ground truth.

2. **Team rebounds between free throws are dead-ball bookkeeping**, not live boards. Tracked
   with a `rebound_is_live` flag set only by a missed FG or a missed *final* FT.

3. **Phantom rebounds before shot-clock violations.** When the clock expires, the feed often
   logs a team rebound to the offense immediately before the violation turnover. Treating it
   as live handed the offense a fresh 14 seconds at the exact moment its clock hit zero —
   worth **+16s of error** at those events. Detected by lookahead to a type-5/action-11 event.

4. **Non-monotone game clocks.** 4,203 events (0.7%) carry a `PCTIMESTRING` that moves
   *backwards*; substitutions are the worst offenders, sometimes logged minutes from the
   surrounding play. Since the game clock never increases within a period, it is repaired by
   clamping to a running minimum. Flagged in `GAME_CLOCK_REPAIRED`.

### Invariants enforced

- `0 ≤ SHOT_CLOCK ≤ 24`
- clock never exceeds the value its chance started at
- clock never exceeds the game clock remaining (end-of-period truncation)

### Confidence and missingness

Chances where a reset had to be *invented* — the clock ran below zero, or a shot came from
the team we believed was on defense — are flagged `low` and their clock is set to **NaN**.

This matters: low-confidence rows were **84.3%** concentrated in the `24-22` bucket, because
inventing a reset means fabricating a 24. Emitting NaN costs ~4% of shots and keeps the rest
trustworthy; fabricating would corrupt the bucket distribution far more than dropping does.

**Usable: 210,394 of 219,529 shots (95.8%).**

---

## 3. Inbound-delay calibration

**Problem.** The shot clock starts when the inbound pass is *touched*, not when the dead-ball
event is logged. Ignoring this makes dead-ball possessions look longer than they were and
pushes reconstructed clocks too low.

**Independent calibration target.** At a shot-clock-violation turnover (type 5, action 11)
the true clock is **exactly 0** by definition. 1,828 such events in 2024-25.

Running the reconstruction with the underflow guard disabled gives an *uncensored* error at
those events. (With the guard on, the sample is censored: possessions where our clock ran out
early get converted into `inferred_reset` and disappear from their own category.)

Measured median error, no delays applied:

| Chance start | n | median error (s) | → delay |
|---|---|---|---|
| `after_made_fg` | 725 | **−2.0** | **2.0** |
| `after_made_ft` | 217 | 0.0 | 0 |
| `after_turnover` | 170 | 0.0 | 0 |
| `after_def_foul` | 164 | 0.0 | 0 |
| `def_rebound` (live ball) | 252 | +1.0 | n/a |
| `off_rebound` (live ball) | 214 | +2.0 | n/a |

Exactly one delay is non-zero: **2.0s after a made field goal**, from the largest sample. That
is the physically expected time to retrieve the ball and touch the inbound pass.

> **Why this is not circular.** Calibration uses only shot-clock violations. It never touches
> the official NBA aggregates, so those remain a clean holdout for validation. Fitting the
> delay to the bucket distribution we are trying to reproduce would invalidate the test.

Residual `off_rebound` error (+2.0) is expected and not corrected: the 14-second reset
requires the shot to have **hit the rim**, which the feed does not record. Offensive rebounds
of airballs get no reset in reality but do in our model.

---

## 4. Validation

Against `official_shotclock_2024_25.csv` — NBA's own published splits, never used in fitting.

### League-wide bucket distribution

| Bucket | Recon share | Official share | Δ pp | eFG Δ pp |
|---|---|---|---|---|
| 24-22 | 2.02% | 3.33% | −1.31 | +2.66 |
| 22-18 | 14.87% | 14.48% | +0.40 | +0.43 |
| 18-15 | 14.13% | 16.41% | −2.28 | +1.42 |
| 15-7 | 48.42% | 47.40% | +1.02 | +1.34 |
| 7-4 | 10.94% | 9.25% | +1.69 | +2.24 |
| 4-0 | 9.62% | 9.13% | +0.49 | +2.56 |

**Mean absolute share error: 1.20 pp. Mean absolute eFG error: 1.78 pp.**

### Per-player agreement (3,148 player × bucket cells)

| Metric | Value |
|---|---|
| FGA/game R² | **0.973** |
| FGA/game MAE | 0.167 |
| FGA/game correlation | 0.987 |
| FG% R² (≥20 FGA) | 0.646 |
| FG% MAE | 4.66 pp |

The reference file is *per game*, so reconstructed totals are divided by games played.

### Improvement trajectory

| Metric | Initial | +phantom fix, NaN | +calibrated delay |
|---|---|---|---|
| FGA R² | 0.941 | 0.949 | **0.973** |
| FG% R² | 0.350 | 0.568 | **0.646** |
| Mean abs share error (pp) | ~2.6 | ~2.0 | **1.20** |

### Known residual error

- `18-15` under-represented by 2.3pp; `7-4` over by 1.7pp. Some elapsed time is still
  over-counted on chances we do not model a delay for.
- eFG is biased **high** by 1.8pp on average, worst in late-clock buckets — consistent with
  some genuinely-late shots being placed one bucket early.
- All documented error sources (unlogged kicked balls and deflections, unlogged clock
  corrections, 1-second game-clock quantisation) bias reconstructed clocks *high*: we miss
  resets rather than inventing them.

---

## 5. Ten-season backfill

2015-16 → 2024-25 reconstructed: **2,013,170 shots**. Calibration is re-run per season, since
the 14-second rule arrives in 2018-19 and feed conventions drift.

The `after_made_fg` delay came back at **2.0s in every season**, which is a useful robustness
signal — an artefact of one season's data would not reproduce across ten.

2017-18 initially failed on a truncated GitHub response (`ChunkedEncodingError`). The
downloader now retries with backoff and verifies `Content-Length`, writing to a `.partial`
file that is renamed only on success, so a truncated download can never masquerade as a
complete archive.

---

## 6. xPTS: expected points per attempt

Predicts P(make), converted to expected points via the attempt's value (2 or 3). And-1 free
throws are excluded — the model values the field goal; foul-drawing is a separate skill and
is modelled at possession level.

**Ladder**, so the gain from flexibility is measured rather than assumed:
league mean → logistic regression → gradient-boosted trees → isotonic calibration.

**Splits are by season, never random**, and `SeasonSplit.assert_ordered` enforces it. A random
split leaks: shots from the same possession land on both sides, and shooter priors are season
aggregates. Train 2015-2022, validate 2023-24, test **2024-25**.

Shooter priors use a cumulative-then-shifted join so a season's own shots never inform its own
prior, with empirical-Bayes shrinkage (strength 50) toward the zone's league rate.

Backend is sklearn's `HistGradientBoostingClassifier` rather than LightGBM: same algorithm,
no `libomp` system dependency, so the repo clones and runs anywhere.

### Out-of-sample results (2024-25, n=210,396)

| Model | Log loss | Brier | AUC | vs league mean |
|---|---|---|---|---|
| League mean | 0.6914 | 0.2491 | 0.500 | — |
| Logistic | 0.6539 | 0.2309 | 0.646 | 5.4% |
| GBM | 0.6273 | 0.2202 | 0.676 | **9.3%** |
| GBM + isotonic | 0.6274 | 0.2201 | 0.676 | 9.3% |

Calibration tracks the diagonal across the full range (0.20 → 0.93 predicted). Isotonic barely
moves aggregate metrics but matters downstream, where possession value and win probability
need calibrated probabilities rather than merely ranked ones.

### Feature value: ablation, not permutation importance

Permutation importance was initially misleading here. `CLOCK_ELAPSED` is exactly
`24 − SHOT_CLOCK`; permuting either left its perfect substitute in place, so both looked
worthless. `CLOCK_ELAPSED` was dropped and feature groups are valued by **refitting without
them** — "what if I never had this information", which is the question that matters for a
feature we went to trouble to construct.

| Removed | Log-loss cost | Share of total model gain |
|---|---|---|
| Action type | 0.00892 | 13.9% |
| Game state | 0.00812 | 12.7% |
| Location (distance, x/y, angle, zones) | 0.00484 | 7.6% |
| **Shot clock + chance start type** | **0.00396** | **6.2%** |
| Shooter prior | 0.00184 | 2.9% |
| Shot clock alone | 0.00136 | 2.1% |

Possession context is worth roughly as much as *every shot-location feature combined* —
and location is what every public xPTS model already has. Shot clock alone is smaller because
chance start type partially substitutes for it; the two are correlated by construction, since
transition possessions carry a high clock.

**Known ceiling:** no public feed carries shot-level defender proximity. This is a
shot-*selection* model, not a contested-ness model, and the "making" residual below absorbs
the ability to score over tight contests.

---

## 7. Shot Quality Grade

Splits scoring into two near-orthogonal components:

- **Selection** — mean xPTS per attempt. What quality of look does he generate or accept?
- **Making** — (actual PTS − xPTS) per 100 attempts. How much does he beat the model?

Face validity: the selection leaders are all rim-running centres (Jaxson Hayes 1.504, Gobert
1.463, Gafford 1.397), which is what a metric measuring "only takes dunks" should produce.
Gobert pairs the second-best selection with −12.5 making, the exact profile of a player who
misses shots he should make.

### Late-clock specialists, and why shrinkage was required

Ranking players on raw (making late ≤7s) − (making early >15s) produced a leaderboard of
small-sample rookies. Decomposing the variance shows why: **only 21.6% of the observed spread
is signal; 78.4% is sampling noise.** A player with 80 late attempts carries a standard error
near 13 points per 100.

Ranking now uses a James-Stein shrunk estimate, `raw × signal_var / (signal_var + SE²)`. The
resulting list — Curry, Kyrie Irving, Chris Paul, Kawhi Leonard, Bam Adebayo — matches the
bail-out-creator archetype, which the raw list did not.

---

## 8. Creation profiles and the overlap test

**Profile.** Per player, the distribution of attempts over (shot-clock bucket × zone), 18
cells, Laplace-smoothed so no cell is zero. Requires the reconstruction; not computable from
public data.

**Overlap.** Pairwise similarity is `1 − JS divergence` between two profiles. Jensen-Shannon
was chosen over KL because it is symmetric, bounded in [0,1], and finite when a player has
zero attempts in a cell — none of which KL gives. Group overlap is the mean pairwise
similarity weighted by the product of attempt volumes, since redundancy between two stars
costs more than the same redundancy between two bench players.

> A bug worth recording: `profiles["FGA"] = totals` silently became `('FGA','')` under
> MultiIndex columns, so the "exclude FGA" filter never matched and a raw attempt count was
> fed into the divergence. Similarity came out at −212. `tests/test_creation.py` now asserts
> the [0,1] bound, symmetry, and unit diagonal — any measure with known bounds should assert
> them.

**The causal test.** Unit: team-season (270, 2016-17 → 2024-25). Outcome: team xPTS per
attempt (shot quality generated) and points per attempt. Treatment: volume-weighted overlap
among top-N creators. Control: the same players' **prior-season** points per attempt,
volume-weighted, plus season fixed effects. The prior-season control is what makes this a
test rather than a correlation — good teams have good players, and good players may cluster
in usage.

**Result: null.** See `reports/findings.md` §5. No specification is significant; at top-3 the
sign is positive. Not reported as anything else.

### The lineup-level retest

The stated weakness of the team-season test was that a five-on-five effect could average away
over a season. That is now tested directly rather than left as a caveat.

**Lineups.** `nba_on_court` reads each period's substitutions backwards to recover who started
it, then walks forward. Run over ten seasons: ~5.57M events, 7 unresolved games out of ~12,300.
Not trusted blindly — `validate_lineups` asserts ten distinct players and five per side on
every row (100%), and independently the shooter is among the ten on-court players on 100% of
shots. `lineups_for_season` raises if more than 2% of games fail, because a silently truncated
lineup table would poison every downstream regression while looking healthy.

**Unit.** Lineup-season with ≥100 offensive chances: 4,233 rows, 1,112,380 chances.
Points come from `event_points`, which reads shot value and free-throw result off the
play-by-play description (the feed has no column for either). Weighted least squares with
weight `sqrt(chances)`.

**Three specification choices, each of which changes the answer**, so all six are reported as
a specification curve (`reports/lineup_overlap_specifications.csv`) rather than one number:

1. *Clustering by team-season.* 4,233 lineups come from 300 team-seasons and share players
   wholesale. Treating them as independent inflates t from 2.89 to 5.01. Cluster-robust
   sandwich SEs with the standard finite-cluster correction.
2. *Team-season fixed effects.* Without them the coefficient is partly identified by good
   teams having high-overlap lineups — confounded, since the same front offices assemble both
   talent and modern shot diets. The effect survives this (t = 2.89).
3. *Minimum chances.* It does not survive here: significance is gone by 200 chances and the
   sign flips by 400.

**Result: the pooled positive estimate is not robust.** A formal heterogeneity test (overlap ×
log chances) returns t = −0.56, so the drift across thresholds is within noise and must not be
reported as a reversal. What the data supports is a bound: among heavily-used lineups the 95%
interval is −5.9% to +1.5% of league-average efficiency, which excludes the 10–15% haircut
that naive diminishing-returns adjustments apply, but cannot exclude a penalty of a few percent.

Two diagnostics support the estimator rather than the effect. A placebo shuffling overlap
within team-season gives mean t = +0.20 (2 of 20 draws exceed |t| > 1.96, about nominal), so
the estimator is not manufacturing significance. And efficiency rises monotonically with usage
(0.833 pts/chance at 100–150 chances to 0.889 at 800+) while within-team overlap correlates
+0.048 with usage — controlling for log chances shrinks the coefficient by 27% (t 2.89 → 2.26),
so part of the pooled effect is coaches playing their better lineups more.

Limitations that keep alternatives alive: overlap is measured from realised usage, so it partly
reflects coaching decisions rather than player preference; coaches may already solve redundancy
by staggering minutes, in which case the null reflects adaptation rather than absence; and
Philadelphia's 0.973 is outside the observed team range (max 0.961), making any application to
them an extrapolation.

---

## 9. Player projection inputs

**DARKO** (free, daily Google Sheet, 530 players) supplies offensive/defensive impact as the
projection baseline. Bootstrapping rather than fitting our own RAPM is deliberate: RAPM is a
solved problem and the largest available time sink, while this project's contribution lives
in the possession layer. EPM was the alternative and is paywalled; BPM and nbarapm.com are
free cross-checks. Fetches go through `requests` — `pandas.read_csv(url)` fails on macOS with
a certificate error because it uses urllib.

**Aging curves** are fitted here rather than taken from DARKO, precisely because DARKO's own
aging prior is the component most likely to mislead at the extreme this project cares about.

Method is the **delta (paired-change)** approach: for players appearing in consecutive
seasons at ages *a* and *a+1*, average the change, weighted by the smaller of the two
samples. Fitting mean performance *by age* instead would be dominated by selection — only
good players are still in the league at 36.

Change in points per attempt, 1,780 player-seasons:

| Age | Δ pts/att | n pairs |
|---|---|---|
| 21→22 | +0.039 | 45 |
| 24→25 | +0.013 | 154 |
| 27→28 | +0.005 | 118 |
| 31→32 | +0.001 | 61 |
| 33→34 | +0.023 | 36 |
| 37→38 | +0.021 | 11 |

**Two things this table says out loud.** First, the deltas turn *positive* again at 33→34 and
37→38, which is not a late-career renaissance — it is survivorship bias. A player who falls
off a cliff is released and never records the second season of the pair, so observed declines
at old ages are biased toward zero. Every curve here is optimistic at the tail and is treated
as an upper bound.

Second, and decisive for this project: support collapses at exactly the ages needed.

| Age | Player-seasons in sample |
|---|---|
| 38 | 12 |
| 39 | 5 |
| 40 | 2 |
| **41** | **1** |

**LeBron is effectively the entire sample at 41.** Any aging adjustment applied to him is
extrapolation with no independent support, and `project_metric` returns an explicit
`extrapolated` flag rather than a bare number so this cannot be quietly forgotten downstream.

---

## 10. Ratings and simulation

**Game results** come from play-by-play, **summed from scoring events** rather than read off
the `SCORE` column. Points per event come from `event_points`, which parses shot value and
free-throw result out of the description text (the feed carries a column for neither); the
scoring side is given by which of `HOMEDESCRIPTION`/`VISITORDESCRIPTION` is populated, an
assignment that is never ambiguous — no scoring event fills both or neither.

> **Why not the `SCORE` column.** It was the original source, taking the last value per game,
> and it was wrong on **4.8% of 2015-16 games**, some by more than 100 points. The column
> carries stale trailing rows: game 22300902 reaches "112 - 118" and then logs "15 - 26" as
> its final entry. The errors largely cancel across a season — league mean rating moved 0.06,
> worst team 0.53 — which is exactly why nothing downstream looked broken.
>
> Three independent checks that the replacement is right. Event-summed totals match the score
> string's running *maximum* (immune to stale rows, since scores only increase) on 96–100% of
> games. At event level, score increments equal derived points on 99.77% of 145,245 scoring
> events, and the exceptions come in offsetting pairs (+3 then −1) — the column lagging, not
> the parse. And season scoring averages reproduce published figures: 205.4 combined points
> per game in 2015-16, 227.7 in 2024-25. `game_results` keeps the string as a cross-check and
> raises if agreement within ±5 points falls below 90% of games.

For the record, `SCORE` is written `"VISITOR - HOME"` — verified empirically rather than
assumed, by checking which number moved after a known team's basket (in game 22400002 a Miami
basket incremented the first, a Detroit basket the second).

**Team ratings** use a least-squares Simple Rating System: every game asserts
`margin = rating_home − rating_away + home_advantage`, solved across the season at once so
schedule strength is adjusted for. The system is rank-deficient (a constant added to every
rating leaves margins unchanged), so ratings are pinned to sum to zero.

Face validity over 11,968 games: home win rate 0.5649, mean home margin +2.19, and 2024-25
runs OKC +12.66 down to WAS −12.13.

**Out-of-sample game prediction** (season *T* from season *T−1* ratings, 10,738 games):
log loss 0.6554 against a 0.6854 base rate — a 4.4% improvement.

> **Shrinkage is the logistic scale.** Explicitly regressing stale ratings toward the mean
> changes nothing once the scale is refit: log loss is identical from shrink 1.0 to 0.5 while
> the fitted scale tracks 12.75 → 6.50. They are the same parameter. Ratings correlate 0.587
> year over year.

**Simulation** injects `rating_sd` — uncertainty in the ratings themselves, redrawn per
simulation — because without it the win distribution reflects only game-level coin-flip noise
and comes out far too narrow. The dominant uncertainty in a projection is whether the ratings
are right, not how the coin lands.

### The calibration gap, which bounds what can be claimed

The roster→rating mapping is `sum(DPM × minutes) / 48`. It is **theoretical, not fitted**, and
it fails an important check: a plus-minus metric must average zero over minutes actually
played, so an average team must map to 0. It does not, and the error depends on an assumption
the data cannot settle, since DARKO carries no minutes column:

| Rotation size assumed | Mean DPM | Implied league-average team |
|---|---|---|
| 300 | +0.498 | +2.49 |
| 350 | +0.259 | +1.29 |
| 400 | +0.035 | +0.18 |

`project_team` therefore returns `centered` under each assumption rather than a single
number, and the spread is treated as uncertainty in the level rather than averaged away.

**No title probability is quoted.** The simulator computes one, but a title number derived
from an uncalibrated level would be false precision. Ingesting 2025-26 results via
`nbastatsv3` would let the mapping be calibrated against observed team ratings in the same
season — impossible today, because the DARKO snapshot (July 2026) postdates the game data
(2024-25). That is the highest-value next step.

---

## Open items

- **Calibrate the DPM→rating mapping** against 2025-26 results (`nbastatsv3`). Blocks any
  credible title probability.
- Real NBA schedule instead of a balanced round robin, before quoting seeding odds —
  strength of schedule genuinely differs by conference.
- Free-throw points are excluded from PPA; joining FT events to chances would quantify how
  much this understates late-clock possessions.
- Five-man lineup data (`nba_on_court`) to retest the overlap null at the level where
  redundancy would actually bite.
- Pre-register the projection with a timestamped tag before opening night (Oct 2026).
