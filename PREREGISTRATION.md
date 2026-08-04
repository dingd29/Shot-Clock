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
| Net rating | **+2.0** points per game |
| Wins | **46.1**, 80% interval **33-59** |
| Title probability | **3.5%** |
| League rank | **9th of 30** |
| Conference rank | 4th in the East |

If they win 55+ games or reach the Conference Finals, this was too cold and the reason is
worth finding.

## Amendments

Recorded rather than made silently, the season has not started, so refining the model is
legitimate, but changing a pre-registered number without saying so is the exact failure this
document exists to prevent.

- **3 August 2026**, the schedule was upgraded from a balanced round robin to a sample under
  the NBA's real structure (4 games vs division rivals, 4 vs six conference opponents, 3 vs
  the other four, 2 inter-conference). The published calendar is still not out; only the
  opponent draw is sampled. Philadelphia moves 49.0 → 49.2 wins, title unchanged at 2.1%,
  rank unchanged at 9th.

- **4 August 2026**, regenerated after an independent review found three defects in the
  projection code. No 2026-27 game had been played. The original numbers are preserved at the
  `projection-2026-27-original` tag and the corrected ones carry `projection-2026-27`; both are
  scored, so the correction cannot flatter itself. What changed:

  1. **The playoff field was fixed across all 20,000 simulations.** Seeding was taken once from
     mean wins, which made the sixteen teams an assumption rather than an outcome and pinned
     **14 of 30 teams at exactly 0.000** title probability, including a +0.27 team whose 80%
     interval reached 55 wins. The field is now rebuilt inside every simulation. Two teams
     remain at zero.
  2. **The DPM-to-rating slope was in-sample.** The 1.433 slope is fitted on a DARKO snapshot
     taken *after* the season it is regressed on, so it measures how much DARKO shrinks its own
     within-season estimates. That is the right correction for reproducing 2025-26 and the
     wrong one for projecting 2026-27, where a team's rating is about 59% persistent year to
     year. A forward shrink of 0.587 is now applied and its derivation stated.
  3. **The margin scale was circular.** 7.0 was defended by noting a +12.7 team projected to 60
     wins where Oklahoma City won 68, but the +12.7 was computed from those same 68 wins. A
     split-half fit (ratings on odd games, scored on even), corrected for the noise that
     half-season ratings add, gives **7.5**.

  Net effect on Philadelphia: rating +3.5 → **+2.0**, wins 49.2 → **46.1**, title 2.1% →
  **3.5%**. Wins fall because the ratings are shrunk toward the mean; the title probability
  *rises* because shrinking everyone compresses the gap to the top three, whose combined share
  drops from 72% to 50%. Every figure below is post-amendment.

## The rest of the league

Contenders, by projected title probability:

| Team | Rating | Wins | 80% interval | Title |
|---|---|---|---|---|
| NYK | +6.2 | 55.5 | 43-67 | 19.6% |
| OKC | +6.3 | 55.8 | 43-67 | 18.3% |
| SAS | +5.2 | 53.4 | 41-65 | 12.4% |
| DEN | +3.5 | 48.9 | 36-62 | 6.0% |
| CLE | +3.0 | 48.3 | 35-61 | 5.6% |
| HOU | +2.9 | 48.0 | 35-61 | 4.9% |
| BOS | +2.6 | 47.4 | 34-60 | 4.8% |
| TOR | +2.3 | 46.5 | 33-60 | 4.1% |
| **PHI** | **+2.0** | **46.1** | **33-59** | **3.5%** |

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
3. **Three teams are a tier above.** New York, Oklahoma City and San Antonio are three to four
   points clear and take 50% of simulated titles between them.
4. **Usage redundancy isn't the problem.** The idea that four high-usage creators cost each
   other efficiency doesn't hold at team level, doesn't replicate at lineup level, and loses
   to a plain usage measure. Philadelphia shouldn't be marked down for offensive fit. Defense
   and availability are the real concerns.

## What would make this wrong

Stated in advance, so none of it can be claimed as foresight afterwards:

- **Embiid's health.** He played 38 games in 2025-26. The projection assumes 70. The
  as-played scenario (+1.5, 44.8 wins, 2.9% title, 11th) is the downside, and reality could be
  lower still.
- **Rosters are frozen.** Only the Philadelphia trade is modelled. Every other team's
  offseason is invisible to this, and 29 of 30 rows describe a league that no longer exists.
- **No aging.** Not applied, because no DPM aging curve is fittable from a single DARKO
  snapshot. Swept instead: a two-point LeBron decline moves Philadelphia to 14th, so the
  conclusion does not depend on it.
- **The calibration is one season, n = 30**, against a DARKO snapshot that had already seen
  the season it was scored on. Its residual is a floor, not an estimate, and its *slope* needs
  the forward shrink described in the amendment above. The clean version needs a back-dated
  DARKO pull, which does not exist here.
- **Rating uncertainty is assumed, not measured.** 3.95 comes from year-over-year SRS
  movement. Title odds are sensitive to it, though less so than before the ratings were
  shrunk: the favourite runs 25.3% at 2.15, 18.9% at 3.95 and 17.0% at 5.0, and Philadelphia
  2.9% / 3.7% / 3.8% over the same sweep. More uncertainty helps them, since they are chasing.

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
observation; a 3.5% forecast is not refuted by Philadelphia winning, nor confirmed by their
losing. That asymmetry is why the game-level numbers above are the real test and the title
line is a derived output.

The harness is built and running now (`make scorecard`), which is the point: a scoring rule
written after seeing results is a choice of the flattering one. It currently reports zero games
and will score from game one.

Three things are fixed in advance:

- **Predictions are read from the committed file**, `reports/league_projection_2026_27.csv`,
  never recomputed. The pre-amendment version is committed beside it as
  `league_projection_2026_27_original.csv` and scored as a fourth row all season, so the
  correction described above can be checked rather than taken on trust. Regenerating them at scoring time would let a later model version grade
  itself, which is the exact failure a pre-registration exists to prevent, the code raises
  rather than rebuilding if the file is missing.
- **Both baselines are named now.** Prior-season SRS is the one that matters: the projection
  layer only earns its keep if modelling rosters beats carrying last year's team strength
  forward. "Home team always" (56.5%) is the floor below which it has said nothing at all.
- **Results append, never overwrite.** `reports/scorecard_log.csv` accumulates one row per
  run, so the running record is in git history and a bad month cannot quietly disappear.

Validated by dry run on 2024-25: scoring contemporaneous ratings returns Brier 0.2003 against
0.2323 for prior-season SRS and 0.2485 for the trivial baseline. Each model is graded at its own
margin scale, 7.5 for the projection and 10.5 for the prior-season baseline; grading both at 7.5
made the baseline overconfident (0.2404) and handed the projection an edge it had not earned.
That dry run is an *upper* bound on what the real thing can do: it feeds the projection ratings
fitted on the season being scored, which is exactly the circularity the projection itself cannot
enjoy. `tests/test_scorecard.py` pins all of it.

*Reproduce:* `make project` to rebuild the projection, `make scorecard` to grade it.
