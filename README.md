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
   number, 0.879 points per attempt, for a region where efficiency actually runs from 0.989
   down to 0.708 — a 28% swing collapsed into a single figure.
2. **The late-clock collapse is real**, −0.339 points per attempt from 7s to 0s, and holds
   across every possession-start type. Rim attempts fall by three quarters as teams get
   forced into contested mid-range jumpers.
3. **Early-clock efficiency is mostly transition, not "shooting early."** Controlling for how
   the possession began flattens the curve from 12s to 21s. At 20s remaining, only ~7% of
   shots come from a half-court start against ~34% off live-ball turnovers. The clock is a
   proxy for transition, not a cause of efficiency.
4. **Possession context is worth about as much as shot location** in the xPTS model — 6.2% of
   total model gain against 7.6% for every location feature combined, by ablation.
5. **Usage overlap does not predict offensive underperformance — a null result.** See below.

## The Sixers question, and a hypothesis that failed

The project's motivating question was whether Philadelphia's 2026 additions (LeBron, Jaylen
Brown alongside Embiid and Maxey) would fit, and the hypothesis was that four high-usage
creators would suffer from wanting the ball at the same moments.

**The descriptive half holds.** Their creation profiles are genuinely redundant — the big
four score 0.973 volume-weighted overlap, the **99th percentile** of random four-player
groups. LeBron and Jaylen Brown sit at 0.988. Embiid is the only differentiated creator.

**The causal half does not.** Across 270 team-seasons, controlling for the same players'
prior-season quality and season fixed effects, overlap does not significantly predict
efficiency — and among top-3 creators the sign is *positive*, the opposite of the
hypothesis. The control behaves correctly (t = 9.9), so this is a real null.

It is reported as a null. On this evidence there is no basis for projecting Philadelphia down
for offensive fit; the defensible concern is defense and availability, where three of the
four stars grade negative.

## Layout

```
src/possval/
  ingest/     bulk download of pre-scraped archives, retried and length-verified
  clock/      the state machine, its rules, calibration, and the validation harness
  features/   shot-level features with strict no-leakage shooter priors
  models/     xPTS, Shot Quality Grade, creation profiles, the overlap test
app/          Streamlit dashboard + CVD-validated chart theme
reports/      findings
tests/        golden sequences, invariants, and bounds
```

## Notes on method

- **Splits are by season, never random**, and asserted in code. A random split leaks: shots
  from one possession would land on both sides.
- **Rates are volume-weighted**, always computed from summed makes and attempts.
- Feature value is measured by **ablation**, not permutation importance — `CLOCK_ELAPSED` is
  exactly `24 − SHOT_CLOCK`, so permuting either left its perfect substitute in place and
  made both look worthless.
- The late-clock leaderboard is **shrunk**: only 21.6% of its raw spread is signal.
- **Known ceiling:** no public feed carries shot-level defender proximity, so this is a
  shot-*selection* model, not a contested-ness model.
