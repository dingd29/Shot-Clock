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

## Open items

- Golden + property tests for the state machine.
- Backfill 2015-16 → 2025-26; re-run calibration per season (rule changes, feed changes).
- xPTS shot-quality model; then player creation profiles for the synergy layer.
