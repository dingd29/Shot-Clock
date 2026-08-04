# Pre-registered projection: 2026-27 NBA season

**Committed 1 August 2026.** The season tips in October 2026. Nothing below has seen a single
game of it.

Everything else in this repo is a backtest. A prediction published before the outcome is the
one thing that can't be fitted after the fact, so this is recorded with a git tag and will be
scored as the season runs whether or not it holds up.

## The claim

The model has Philadelphia ninth in the league. Colder than I'd like.

| | Projection |
|---|---|
| Net rating | **+3.5** points per game |
| Wins | **49.2**, 80% interval **37-61** |
| Title probability | **2.1%** |
| League rank | **9th of 30** |
| Conference rank | 5th in the East |

If they win 55+ games or reach the Conference Finals, this was too cold and the reason is
worth finding.

## Amendments

Recorded rather than made silently, the season has not started, so refining the model is
legitimate, but changing a pre-registered number without saying so is the exact failure this
document exists to prevent.

- **3 August 2026**, the schedule was upgraded from a balanced round robin to a sample under
  the NBA's real structure (4 games vs division rivals, 4 vs six conference opponents, 3 vs
  the other four, 2 inter-conference). The published calendar is still not out; only the
  opponent draw is sampled. Philadelphia moves 49.0 → **49.2** wins, title unchanged at 2.1%,
  rank unchanged at 9th. Every figure below is post-amendment.

## The rest of the league

Contenders, by projected title probability:

| Team | Rating | Wins | 80% interval | Title |
|---|---|---|---|---|
| NYK | +10.5 | 63.9 | 54-73 | 29.2% |
| OKC | +10.7 | 64.1 | 54-73 | 28.7% |
| SAS | +8.8 | 60.7 | 50-71 | 14.3% |
| DEN | +6.0 | 54.0 | 42-66 | 5.0% |
| CLE | +5.2 | 53.0 | 41-65 | 4.8% |
| HOU | +5.0 | 52.4 | 40-64 | 3.5% |
| BOS | +4.4 | 51.4 | 39-63 | 3.2% |
| TOR | +4.0 | 50.2 | 37-63 | 2.7% |
| **PHI** | **+3.5** | **49.2** | **37-61** | **2.1%** |

Full table: [`reports/league_projection_2026_27.csv`](reports/league_projection_2026_27.csv).

## Why the model lands here

A market can price them differently and one of us will be wrong for a reason. The claim isn't
that the market is inefficient, since title futures are sharp. It's that the case for
Philadelphia as a contender requires believing something specific, and the model doesn't:

1. **Their base was 18th.** Philadelphia's 2025-26 SRS was −0.31. The trade upgrades a
   middling team; it does not add to a contender.
2. **The upgrade is roughly +2 DPM.** LeBron (1.31, age 41) plus Jaylen Brown (1.78) minus
   Paul George (1.07), and it displaces *bench* minutes rather than replacing bad starters.
   Star acquisitions are worth less to a team whose starters are already decent.
3. **Three teams are a tier above.** New York, Oklahoma City and San Antonio are five to
   seven points clear and take 72% of simulated titles between them.
4. **Usage redundancy isn't the problem.** The idea that four high-usage creators cost each
   other efficiency doesn't hold at team level, doesn't replicate at lineup level, and loses
   to a plain usage measure. Philadelphia shouldn't be marked down for offensive fit. Defense
   and availability are the real concerns.

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

- **Game level**, Brier score and log loss on every game, against a naive
  last-season-rating baseline and the trivial home-team-always baseline. ~1,230 observations,
  the only place with enough data to say anything statistically. *A market baseline is named
  here in an earlier draft and is not built:* it needs closing odds or Kalshi prices archived
  per game, which this repo does not collect. Claiming one without the data would be worse
  than not having it, so the naive rating baseline is the bar.
- **Win totals**, absolute error against all 30 final records.
- **Calibration**, do teams given a 30% chance win about 30% of the time, across the buckets.

The title probability is not scored directly and cannot be. One championship is one
observation; a 2.1% forecast is not refuted by Philadelphia winning, nor confirmed by their
losing. That asymmetry is why the game-level numbers above are the real test and the title
line is a derived output.

The harness is built and running now (`make scorecard`), which is the point: a scoring rule
written after seeing results is a choice of the flattering one. It currently reports zero games
and will score from game one.

Three things are fixed in advance:

- **Predictions are read from the committed file**, `reports/league_projection_2026_27.csv`,
  never recomputed. Regenerating them at scoring time would let a later model version grade
  itself, which is the exact failure a pre-registration exists to prevent, the code raises
  rather than rebuilding if the file is missing.
- **Both baselines are named now.** Prior-season SRS is the one that matters: the projection
  layer only earns its keep if modelling rosters beats carrying last year's team strength
  forward. "Home team always" (56.5%) is the floor below which it has said nothing at all.
- **Results append, never overwrite.** `reports/scorecard_log.csv` accumulates one row per
  run, so the running record is in git history and a bad month cannot quietly disappear.

Validated by dry run on 2024-25: scoring contemporaneous ratings returns Brier 0.2005 against
0.2404 for prior-season SRS and 0.2485 for the trivial baseline, and feeding the baseline in as
the projection reproduces the baseline's numbers exactly, the identity check that catches
mis-wired plumbing. `tests/test_scorecard.py` pins all of it.

*Reproduce:* `make project` to rebuild the projection, `make scorecard` to grade it.
