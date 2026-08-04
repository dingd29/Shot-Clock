# Possession Value

Reconstructs the **NBA shot clock** — a field that exists in no public feed — from
play-by-play, validates it against NBA's own published aggregates, and uses it to model shot
quality and player fit.

```bash
make install
make backfill   # 10 seasons of play-by-play + shot detail
make validate   # reconstruction vs NBA's published splits
make score      # train xPTS, grade every player
make app        # dashboard
```

## Why this exists

NBA publishes shot-clock splits only as six coarse buckets of per-player, per-game averages.
That is enough to make a dashboard and nothing else — you cannot build a shot-quality model,
a possession-value model, or a fit model on top of it.

But the shot clock *is* recoverable. Play-by-play records the game clock at every event and
every event that resets the clock, so walking a period in order while tracking "when did the
current chance start, and with how many seconds" yields the clock at any shot in between.

**2,013,170 shots across 2015-16 → 2024-25**, each with a reconstructed shot clock.

## Does the reconstruction work?

It invents a field that is not in the source data, so the only thing that makes it credible
is reproducing numbers NBA publishes independently.

| Check | Result |
|---|---|
| Mean absolute bucket-share error | **1.20 pp** |
| Per-player FGA agreement (R², 3,148 cells) | **0.973** |
| Per-player FG% agreement (R²) | 0.646 |
| Shots with a usable clock | 95.8% |

Chances where a reset had to be *invented* are flagged low-confidence and emit **NaN rather
than a fabricated 24** — they were 84% concentrated in a single bucket, and imputing them
would have corrupted the distribution far more than dropping them does.

The inbound delay is calibrated against **shot-clock violations**, where the true clock is
exactly 0 by definition. That signal is deliberately independent of the official aggregates,
which stay a clean holdout. It finds one non-zero delay — 2.0s after a made basket, the
physical time to inbound — and returns the same 2.0s in all ten seasons.

## Findings

Full write-up in [`reports/findings.md`](reports/findings.md); method and audit trail in
[`METHODOLOGY.md`](METHODOLOGY.md).

1. **NBA's buckets hide the steepest part of the curve.** The `4-0` bucket reports one
   number, 0.933 points per attempt, for a region where efficiency actually runs from 0.989
   down to 0.831 — a 17% swing collapsed into a single figure.
2. **Efficiency declines steeply into the late clock** — −0.216 points per attempt from 7s to
   0s, same sign across every possession-start type, with rim attempts falling by nearly three
   quarters and the mid-range share nearly quadrupling. Reported **descriptively**: possessions
   surviving to 5 seconds are selected on everything earlier having failed, so this is not a
   causal estimate of time pressure. Getting there needs the optimal-stopping model.
   *Buzzer-beater heaves are excluded* — a third of shots at ≤1s on the shot clock also have
   under 3 seconds of game clock, and leaving them in made the collapse look 36% steeper.
3. **Early-clock efficiency is mostly transition, not "shooting early."** Controlling for how
   the possession began flattens the curve from 12s to 21s. At 20s remaining, only ~7% of
   shots come from a half-court start against ~34% off live-ball turnovers. The clock is a
   proxy for transition, not a cause of efficiency.
4. **Possession context carries 13.6% of xPTS model gain** by ablation — from two features
   that exist in no public feed. Shot geometry is worth 3.8× more, and saying so matters: an
   earlier version compared possession context against *location alone* while explaining shot
   clock's small solo number by substitution. Action type substitutes for location the same
   way, so the groups are now coarse enough to contain their own substitutes and the older,
   friendlier claim is withdrawn.
5. **The 2018-19 rule change cost offenses about 1.8% of second-chance efficiency**
   (−0.016 points per chance, t = −2.5) — a difference-in-differences over 932k chances,
   offensive rebounds treated, defensive rebounds control. The 83% collapse in long second
   chances (9.1% → 1.4%) is reported as the **first stage**, not the result: it is close to
   mechanically implied by the reset. Getting there meant finding that **the NBA changed its play-by-play timestamping in
   2017-18**, one season before the rule: events immediately after a rebound sharing that
   rebound's exact clock jump from 14.7% to 18.7% and stay. Dropping the contaminated season
   cut the standard error fourfold and turned an apparent null on efficiency into a small
   negative effect.
6. **Teams relax their shot standard only half as fast as the clock demands.** Reframing
   shooting as **American option exercise** — shoot now, or hold an option whose value decays —
   gives the one result here that conditions on the *decision* rather than the outcome, which
   is what dissolves the selection problem in findings 1-3. The continuation value `V(t)` runs
   from 0.81 points at 23 seconds to 0.36 at 1 second, and offenses lower their accepted
   standard by only ~55-65% of that collapse (relaxation ratio 0.52-0.67 at every quantile
   tested). Exercise is otherwise sound: taken shots beat continuation value by +0.39 points
   on average and only 7.0% fall below it. *The boundary's **level** is not identified* — which
   quantile you call the threshold flips the sign — so only the shape is claimed.
7. **The efficiency curves replicate in all ten seasons** — the 0s→7s rise is 0.211 ± 0.022,
   and within the 14-second-rule era each season's curve shape correlates r ≥ 0.967 with
   2024-25's.
8. **Creation overlap does not predict offensive underperformance**, at team level or lineup
   level — and loses its head-to-head against a plain usage measure. See below.
All eight findings are about possessions and shots — the layer built here. A separate
projection layer sits on top of it and is scoped in its own section below, deliberately kept
out of this list.

## The Sixers question, and a hypothesis that failed

The project's motivating question was whether Philadelphia's 2026 additions (LeBron, Jaylen
Brown alongside Embiid and Maxey) would fit, and the hypothesis was that four high-usage
creators would suffer from wanting the ball at the same moments.

**The descriptive half holds.** Their creation profiles are genuinely redundant — the big
four score 0.973 volume-weighted overlap, the **99th percentile** of random four-player
groups. LeBron and Jaylen Brown sit at 0.988. Embiid is the only differentiated creator.

**The causal half does not.** Across 270 team-seasons, controlling for the same players'
prior-season quality and season fixed effects, overlap does not significantly predict
efficiency — and among top-3 creators the sign is *positive*, the opposite of the hypothesis.
The retest at five-man lineup level (4,233 lineup-seasons, 1.11M chances) does not rescue it
either: the pooled estimate is positive and significant but does not survive restricting the
sample to lineups that actually played.

**And the feature loses its head-to-head.** Raced against the incumbent measure every public
model already uses — the five players' combined shot demand — creation overlap adds nothing.
Its t-statistic falls from 2.89 to **0.49** once usage is in the model, and R² improves by one
ten-thousandth. The expensive feature, the one requiring a shot clock that exists in no public
feed, turns out to be a worse version of something computable from a box score. That is
reported as the headline result rather than buried.

---

## The projection layer, and what it does not rest on

**This section is scoped separately on purpose.** Everything above is built from possessions
and validated against data this repo produces. The projection is a different kind of object:
it depends on **someone else's impact metric** (DARKO), and it emits a headline number more
precise-looking than its inputs support. It is kept because the pre-registration is the one
result that cannot be fitted after the fact — not because the point estimate is strong.

**Calibrated.** The DPM→rating mapping is fitted against observed 2025-26 ratings:
**slope 1.433 ± 0.103** — the textbook identity compresses spread by 43%, and 1.0 is over four
standard errors away. Simulating all 30 teams (conference brackets, 20,000 seasons,
year-over-year rating uncertainty of 3.95):

**Philadelphia projects to 49.0 wins (36-61), a 2.1% title chance, and 9th in the league.**

**Read the interval, not the point.** The slope is fitted at n = 30 on a single season; the
DARKO snapshot postdates the season it is scored against, so its residual is a floor rather
than an estimate; aging is omitted by design and swept instead; and `rating_sd` is chosen by a
defensible but discretionary argument that moves the favourite's title odds between 26% and
39%. The 80% win interval spans 25 games. Anyone reading 2.1% as a precise quantity is reading
it wrong, and the [pre-registration](PREREGISTRATION.md) says so in advance.

The superteam is not one. Their 2025-26 base was 18th (SRS −0.31); LeBron at 41 plus Brown
minus Paul George is about +2 DPM, and it displaces bench minutes rather than bad starters.
New York, Oklahoma City and San Antonio sit six points ahead and take 72% of titles. The
largest single lever is Embiid's availability — he played 38 games, and projecting the roster
to 70 games each is worth a full point of rating.

## Pre-registered

The 2026-27 projection is committed before opening night, with a timestamped tag:
[PREREGISTRATION.md](PREREGISTRATION.md). Everything else here is a backtest; that one is not,
and it will be scored on game-level Brier and log loss as the season runs.

## Layout

```
src/possval/
  ingest/     bulk download of pre-scraped archives, retried and length-verified
  clock/      the state machine, its rules, calibration, and the validation harness
  features/   shot features with no-leakage shooter priors; on-court lineups
  models/
    xpts, grade         expected points per attempt; selection vs making
    creation, synergy   creation profiles and the team-season overlap test
    lineup_synergy      the lineup-level retest and the head-to-head
    rulechange          2018-19 as a difference-in-differences
    ratings, aging      SRS from game results; paired-change aging curves
    dpm_calibration     DPM -> observed rating, fitted
    league, simulate    all thirty rosters -> win totals -> title odds
app/          Streamlit dashboard + CVD-validated chart theme
reports/      findings and generated tables
tests/        golden sequences, invariants, bounds, and estimator recovery
```

Every stage is a `make` target: `data`, `clock`, `validate`, `backfill`, `train`, `score`,
`lineups`, `synergy`, `project`, `app`.

## Notes on method

- **Splits are by season, never random**, and asserted in code. A random split leaks: shots
  from one possession would land on both sides.
- **Rates are volume-weighted**, always computed from summed makes and attempts.
- Feature value is measured by **ablation**, not permutation importance — `CLOCK_ELAPSED` is
  exactly `24 − SHOT_CLOCK`, so permuting either left its perfect substitute in place and
  made both look worthless.
- The late-clock leaderboard is **shrunk**: only 21.6% of its raw spread is signal.
- **Standard errors are clustered where the variation lives** — on team-season for lineups
  (4,233 lineups come from 300 clusters and share players), on season for the rule change
  (nine clusters, not a million chances). Treating lineups as independent had inflated a
  t-statistic from 2.9 to 5.0.
- **Specification curves, not single numbers**, wherever the answer moves with defensible
  choices. The lineup-overlap effect is significant pooled and not significant once the
  sample is restricted to lineups that actually played; reporting one cell would have been a
  choice about which answer to believe.
- **Known ceiling:** no public feed carries shot-level defender proximity, so this is a
  shot-*selection* model, not a contested-ness model.
