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

## What the shot clock is actually worth

This is the project's own answer to the question it was built to ask, and it is not the answer
it set out to find.

| Question | Where the shot clock lands |
|---|---|
| Will *this shot* go in? | **Negligible** — 0.00136 log loss, the smallest group in the ablation |
| Will *this possession* score? | **Large** — continuation value spans 0.36 → 0.81 points, a 2.2× range |
| Will *this team* win? | **Negligible** — 0.034% of log loss over 5.34M events |

The shot clock is **possession-scale information**. A possession is about 1% of a game's
scoring, so it washes out at the scale below and the scale above. Reconstructing it did not buy
predictive edge at either end — and three separate results say so, not one.

**Its value is as a measurement instrument, not a feature.** The finding below exists only
because a continuation value can be computed at all, and nobody without a reconstructed clock
can compute one.

Full write-up: [`reports/findings.md`](reports/findings.md). Method and audit trail:
[`METHODOLOGY.md`](METHODOLOGY.md).

## The finding that needed the instrument

**Offenses relax their shot standard only about half as fast as the expiring clock warrants.**

Shooting is American option exercise: take the shot in hand, or hold an option whose value
decays. Framing it that way is what dissolves the selection problem the efficiency curve
cannot escape — it conditions on the **decision** (a shot was taken at second *t* worth *q*)
rather than on the outcome.

- Continuation value `V(t)` falls from **0.81 points at 23 seconds to 0.36 at 1 second**.
- The standard offenses actually accept falls by only **55–65%** of that (relaxation ratio
  0.52–0.67 at every quantile tested).
- Holds in **all ten seasons**, every upper bound below 1.0, and in competitive games alone —
  so it is not garbage time.
- Exercise is otherwise sound: taken shots beat continuation value by **+0.39 points** on
  average and only 7.0% fall below it.

**The boundary's *level* is not identified** and no claim rests on it — which quantile you call
the threshold flips the sign of "too aggressive" versus "too patient". Only the shape is
claimed.

Team variation is real but small: a raw spread of 0.41–0.84 is **37% signal** against a
permutation null, so the honest range is ~0.52–0.68.

## Results that came out negative

These are here because they are the reason to trust the rest.

- **The project's headline hypothesis failed.** Creation overlap — who wants the ball *when*,
  computable only from the reconstruction — does not predict offensive underperformance at team
  level *or* five-man lineup level. Raced head-to-head against the plain box-score usage
  measure, its t-statistic falls **2.89 → 0.49** and R² improves by one ten-thousandth. The
  expensive feature is a worse version of something anyone can compute.
- **The per-player version of the stopping result is tautological.** Mean surplus correlates
  **0.984** with mean late-clock shot quality — it is that quantity renamed. Reported as a
  failure because it looks enough like a skill ranking to be published as one.
- **The 2018-19 rule change cost offenses ~1.8% of second-chance efficiency** (−0.016 points
  per chance, t = −2.5) — the league removed up to ten seconds and almost nothing happened.
  Getting there meant finding that **the NBA changed its play-by-play timestamping in
  2017-18**, one season before the rule; dropping that season cut the standard error fourfold
  and turned an apparent null into a small real effect.
- **Three pre-registered follow-ups, none confirmed.** Hypotheses, directions and decision
  rules were [committed before the analysis](reports/preregistration_exploration.md), with an
  exploration/holdout split. One failed outright, one is uninformative, one is marginal. The
  failure is the instructive part: it cleared its permutation null on exploration (+0.065) and
  came back at **+0.001** on held-out seasons — a false positive that would have survived every
  check applied elsewhere in this repo.
- **An earlier, friendlier claim was withdrawn.** Possession context was reported as worth
  about as much as shot location. Grouping action type with location — a dunk encodes "at the
  rim" — geometry is worth **3.8×** more. What survives is 13.6% of model gain.

## The descriptive curve

- **NBA's buckets hide the steepest part.** The `4-0` bucket reports 0.933 points per attempt
  for a region running 0.989 → 0.831.
- **Efficiency declines −0.216 from 7s to 0s**, same sign across every possession-start type.
  Stated **descriptively**: possessions surviving to 5 seconds are selected on everything
  earlier having failed, so this is not a causal estimate of time pressure.
- **Early-clock efficiency is mostly transition.** At 20 seconds only ~7% of shots come from a
  half-court start against ~34% off live-ball turnovers. The clock is a proxy for transition.
- **Buzzer-beater heaves are excluded**, and finding that mattered: a third of shots at ≤1s on
  the shot clock also have under 3 seconds of *game* clock, and leaving them in made the
  late-clock collapse look **36% steeper** than it is.
- The curves **replicate in all ten seasons** (0s→7s rise 0.211 ± 0.022).

## The Sixers question, and a hypothesis that failed

The project's motivating question was whether Philadelphia's 2026 additions (LeBron, Jaylen
Brown alongside Embiid and Maxey) would fit, and the hypothesis was that four high-usage
creators would suffer from wanting the ball at the same moments.

**The descriptive half holds.** Their creation profiles are genuinely redundant — the big
four score 0.973 volume-weighted overlap, the **99th percentile** of random four-player
groups. LeBron and Jaylen Brown sit at 0.988. Embiid is the only differentiated creator.

**The causal half does not**, at either level. Across 270 team-seasons — controlling for the
same players' prior-season quality and season fixed effects — overlap does not significantly
predict efficiency, and among top-3 creators the sign is *positive*. The five-man retest
(4,233 lineup-seasons, 1.11M chances) does not rescue it: the pooled estimate is significant
but does not survive restricting to lineups that actually played. And it loses its head-to-head
against plain usage, as above.

**So Philadelphia should not be marked down for offensive fit.** The defensible concerns are
defence and availability — three of the four stars grade negative defensively, and Embiid
played 38 games in 2025-26.

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

**Philadelphia projects to 49.2 wins (37-61), a 2.1% title chance, and 9th in the league.**

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
[PREREGISTRATION.md](PREREGISTRATION.md). Everything else here is a backtest; that one is not.

**The scoring harness is already built and running** (`make scorecard`) — before the season,
which is the only time it can be written honestly. Predictions are read from the committed
file and never recomputed, both baselines are named in advance, and results append to
`reports/scorecard_log.csv` so the running record lives in git history. Amendments made
between commitment and opening night are logged in the document itself.

## Reviewing this

[`REVIEW_CONTEXT.md`](REVIEW_CONTEXT.md) maps every claim to the code and the committed
artifact behind it, states what can be checked without rebuilding data (all 24 report CSVs are
in the repo; no parquet is), and lists the weak points in my own words rather than leaving them
to be found.

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
