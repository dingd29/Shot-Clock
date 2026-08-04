# Pre-registered projection: 2026-27 NBA season

**Committed 1 August 2026.** The season tips in October 2026. Nothing below has seen a single
game of it.

This document exists because every other number in this repository is a backtest, and a
backtest is a claim about how carefully its author avoided fooling themselves. A prediction
published before the outcome is the one result that cannot be fitted after the fact. It is
recorded here with a git tag so the timestamp is checkable, and it will be scored as the
season runs whether or not it holds up.

## The headline claim

**Philadelphia is not a superteam.** The model projects them ninth in the league.

| | Projection |
|---|---|
| Net rating | **+3.5** points per game |
| Wins | **49.0**, 80% interval **36-61** |
| Title probability | **2.1%** |
| League rank | **9th of 30** |
| Conference rank | 5th in the East |

If Philadelphia wins 55+ games or reaches the Conference Finals, this projection was too
cold and the reason will be worth finding.

## The rest of the league

Contenders, by projected title probability:

| Team | Rating | Wins | 80% interval | Title |
|---|---|---|---|---|
| NYK | +10.5 | 63.1 | 53-73 | 30.1% |
| OKC | +10.7 | 63.1 | 53-72 | 28.0% |
| SAS | +8.8 | 59.7 | 48-70 | 14.2% |
| DEN | +6.0 | 54.0 | 42-66 | 5.2% |
| CLE | +5.2 | 52.4 | 40-64 | 4.8% |
| HOU | +5.0 | 52.1 | 40-64 | 3.5% |
| BOS | +4.4 | 50.8 | 38-63 | 3.2% |
| TOR | +4.0 | 50.1 | 37-62 | 2.4% |
| **PHI** | **+3.5** | **49.0** | **36-61** | **2.1%** |

Full table: [`reports/league_projection_2026_27.csv`](reports/league_projection_2026_27.csv).

## The mechanism, which is the part worth disagreeing with

A market can price Philadelphia differently and one of us will be wrong for a reason. The
claim is not "the market is inefficient" — title futures are sharp. It is that **the case for
Philadelphia as a contender requires believing something specific**, and the model does not:

1. **Their base was 18th.** Philadelphia's 2025-26 SRS was −0.31. The trade upgrades a
   middling team; it does not add to a contender.
2. **The upgrade is roughly +2 DPM.** LeBron (1.31, age 41) plus Jaylen Brown (1.78) minus
   Paul George (1.07), and it displaces *bench* minutes rather than replacing bad starters.
   Star acquisitions are worth less to a team whose starters are already decent.
3. **Three teams are a tier above.** New York, Oklahoma City and San Antonio are five to
   seven points clear and take 72% of simulated titles between them.
4. **The usage-redundancy story is not the problem.** The hypothesis this project was built
   to test — that four high-usage creators cost each other efficiency — failed at team level,
   failed to replicate at lineup level, and lost its head-to-head against a plain usage
   measure. Philadelphia should not be marked down for offensive fit. The defensible concerns
   are defence and availability.

## What would make this wrong

Stated in advance, so none of it can be claimed as foresight afterwards:

- **Embiid's health.** He played 38 games in 2025-26. The projection assumes 70. The
  as-played scenario (+2.50, 47.1 wins, 11th) is the downside, and reality could be lower
  still.
- **Rosters are frozen.** Only the Philadelphia trade is modelled. Every other team's
  offseason is invisible to this, and 29 of 30 rows describe a league that no longer exists.
- **No aging.** Not applied, because no DPM aging curve is fittable from a single DARKO
  snapshot. Swept instead: a two-point LeBron decline moves Philadelphia to 14th, so the
  conclusion does not depend on it.
- **The calibration is one season, n = 30**, against a DARKO snapshot that had already seen
  the season it was scored on. Its residual is a floor, not an estimate.
- **Rating uncertainty is assumed, not measured.** 3.95 comes from year-over-year SRS
  movement. Title odds are acutely sensitive to it: the favourite runs 38.5% at 2.15 and
  26.0% at 5.0.

## How this will be scored

Weekly through the season, against outcomes, published as they come:

- **Game level** — Brier score and log loss on every game, against a market baseline and a
  naive last-season-rating baseline. ~1,230 observations, the only place with enough data to
  say anything statistically.
- **Win totals** — absolute error against all 30 final records.
- **Calibration** — do teams given a 30% chance win about 30% of the time, across the buckets.

The title probability is not scored directly and cannot be. One championship is one
observation; a 2.1% forecast is not refuted by Philadelphia winning, nor confirmed by their
losing. That asymmetry is why the game-level numbers above are the real test and the title
line is a derived output.

**The harness is built and running now, before opening night** — `make scorecard`, or
`python -m possval.pipeline scorecard --season 2026`. That timing is the point: a scoring rule
written after seeing results is not a scoring rule, it is a choice of the flattering one. It
currently reports zero games and will score from game one.

Three things are fixed in advance:

- **Predictions are read from the committed file**, `reports/league_projection_2026_27.csv`,
  never recomputed. Regenerating them at scoring time would let a later model version grade
  itself, which is the exact failure a pre-registration exists to prevent — the code raises
  rather than rebuilding if the file is missing.
- **Both baselines are named now.** Prior-season SRS is the one that matters: the projection
  layer only earns its keep if modelling rosters beats carrying last year's team strength
  forward. "Home team always" (56.5%) is the floor below which it has said nothing at all.
- **Results append, never overwrite.** `reports/scorecard_log.csv` accumulates one row per
  run, so the running record is in git history and a bad month cannot quietly disappear.

Validated by dry run on 2024-25: scoring contemporaneous ratings returns Brier 0.2005 against
0.2404 for prior-season SRS and 0.2485 for the trivial baseline, and feeding the baseline in as
the projection reproduces the baseline's numbers exactly — the identity check that catches
mis-wired plumbing. `tests/test_scorecard.py` pins all of it.

*Reproduce:* `make project` to rebuild the projection, `make scorecard` to grade it.
