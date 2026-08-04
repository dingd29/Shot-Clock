# Possession Value

The NBA doesn't publish a shot clock. Not per shot, anyway. You get six coarse buckets of
per-player, per-game averages, which is enough to make a chart and not much else.

This reconstructs it. Play-by-play records the game clock at every event and every event that
resets the shot clock, so you can walk a period in order, track when the current possession
started and with how many seconds, and recover the clock at any shot in between. That gives
2,018,360 shots from 2015-16 through 2024-25, each with a shot clock attached, and it opens up
questions you can't ask from bucket averages.

```bash
make install
make backfill   # 10 seasons of play-by-play + shot detail
make validate   # reconstruction vs NBA's published splits
make score      # train xPTS, grade every player
make app        # dashboard
```

## Does the reconstruction work?

It builds a field that isn't in the source data, so the only thing that makes it believable is
matching numbers the NBA publishes separately.

| Check | Result |
|---|---|
| Mean absolute bucket-share error | 1.20 pp |
| Mean absolute bucket eFG error | 1.04 pp |
| Per-player FGA agreement (R², 3,148 cells) | 0.973 |
| Per-player FG% agreement (R²) | 0.646 |
| Shots with a usable clock | 96.0% |

About 4% of possessions need a reset the play-by-play doesn't record. Those get NaN rather than
an invented 24, because 84% of them would land in one bucket and skew it badly.

The inbound delay is calibrated on shot-clock violations, where the true clock is 0 by
definition. That signal is independent of the published aggregates, which keeps those clean as
a test. It finds one delay worth applying, 2.0 seconds after a made basket, and returns the
same 2.0 in all ten seasons.

## What the shot clock is worth

Not what I expected going in. It's useful at exactly one scale.

| Question | Shot clock's contribution |
|---|---|
| Will this shot go in? | Almost nothing. 6.0% of model gain, third of four groups. |
| Will this possession score? | A lot. Continuation value runs 0.36 to 0.81 points. |
| Will this team win? | Almost nothing. 0.050% of log loss over 5.35M events. |

A possession is about 1% of a game's scoring, so information at possession scale washes out
above and below it. The reconstruction earns its keep as a measurement tool rather than as a
feature you bolt onto a model. The stopping result below only exists because a continuation
value can be computed at all, and you can't compute one without a shot clock.

Full write-up in [`reports/findings.md`](reports/findings.md), method in
[`METHODOLOGY.md`](METHODOLOGY.md).

## Shooting as an option

The clearest result here. Offenses lower their shot standard less than half as fast as an
expiring clock calls for.

Shooting is an exercise decision: take what's in front of you, or hold an option whose value
decays. Framing it that way gets around a problem the raw efficiency curve can't, because it
conditions on the decision (a shot was taken at second *t* worth *q*) rather than on the
outcome.

Continuation value falls from 0.81 points at 23 seconds to 0.36 at 1 second. The standard
offenses actually accept falls by only about 37 to 54% of that, whichever quantile you use to
define the threshold. It holds in all ten seasons and in competitive games alone, so it isn't a
garbage-time artifact. Read it as an upper bound on the shortfall rather than a point estimate:
continuation value is estimated on the chances that declined to shoot, a group that worsens as
the clock falls, and that biases the ratio down. See the caveats in the findings.

Exercise is broadly sound otherwise. Taken shots beat continuation value by 0.39 points on
average and only 5.8% fall below it. The *level* of the threshold isn't identified, since the
quantile you pick flips the sign of "too aggressive" versus "too patient", so only the shape is
claimed. Team variation is real but modest: a raw spread of 0.33 to 0.67 is 42% signal against a
permutation null, putting the honest range around 0.41 to 0.55.

## What didn't hold up

Some of the more useful things here are ideas that didn't survive testing.

Creation overlap, a measure of whether players want the ball at the same moments, doesn't
predict offensive underperformance. Not across 270 team-seasons, not across 3,512 five-man
lineups. Run head to head against a plain box-score usage measure, its t-statistic drops from
1.98 to −0.35 and R² improves by one ten-thousandth. Usage does the same work and anyone can
compute it from a box score.

A per-player version of the stopping result correlates 0.984 with mean late-clock shot quality.
It's that quantity under a different name, so it ranks who finishes rather than who decides.

Three follow-up hypotheses were [registered before
testing](reports/preregistration_exploration.md) with an exploration and holdout split. None
confirmed. One cleared its significance test on exploration at +0.065 and came back at +0.001 on
held-out seasons, which is the kind of false positive the protocol exists to catch.

The 2018-19 rule change, which cut the reset to 14 seconds after an offensive rebound, doesn't
have a measurable effect on scoring that I can defend. The point estimate is −0.016 points per
chance and t = −2.4, which looks fine until you notice there are only nine season clusters: an
exact wild cluster bootstrap puts it at p = 0.12. The rule's effect on chance *length* is
unambiguous, but that was never in doubt.

Two things made this worth keeping anyway. The NBA changed its play-by-play timestamping in
2017-18, one season before the rule, so any before-and-after comparison spanning that season is
contaminated. And the change lands almost entirely on offensive rebounds (+14pp) rather than
defensive ones (+0.7pp), which are the treated and control arms, so dropping the bad season
doesn't rescue the design either.

## The efficiency curve

- The `4-0` bucket reports 0.933 points per attempt for a region that actually runs 0.989 down
  to 0.831.
- Efficiency drops 0.216 from 7 seconds to 0, same sign across every possession-start type.
  This is descriptive. Possessions alive at 5 seconds are selected on everything earlier having
  failed, so it isn't a causal estimate of time pressure.
- Early-clock efficiency is mostly transition. At 20 seconds only about 7% of shots come from a
  half-court start against 34% off live-ball turnovers.
- Buzzer-beater heaves are excluded, and that matters more than it sounds. A third of shots at
  1 second or less on the shot clock also have under 3 seconds of *game* clock. Leaving them in
  makes the late-clock drop look 36% steeper than it is.
- The curves replicate across all ten seasons (0s to 7s rise of 0.211 ± 0.022).

## Applications to the Sixers

Here's the part I actually care about.

Philadelphia added LeBron James and Jaylen Brown this offseason, next to Joel Embiid and Tyrese
Maxey. I've spent most of the summer trying not to get carried away about it, and having a
possession model sitting right there felt like a good excuse to check whether the excitement
survives contact with data.

The first question was fit. Four high-usage creators sharing a floor is the classic superteam
worry, and the shot clock gives a way to ask it properly: when in a possession does each player
generate offense, and how much do those windows overlap?

They overlap a lot. Volume-weighted, the top four score 0.973 similarity, the 99th percentile of
random four-player groups. LeBron and Jaylen Brown sit at 0.988. Embiid is the only one whose
creation profile looks different from the others.

That turns out not to predict anything. Across 270 team-seasons, controlling for the same
players' prior-season quality, one of nine specifications reaches significance and it has the
wrong sign: more overlap, *better* offense. That's what the construction produces on its own,
since similar players concentrate their shots early in the clock and early-clock possessions
score better. The five-man retest doesn't rescue the idea either.

So the "too many ball-handlers" worry, at least as measured here, isn't where the risk sits.
Defense and availability are: three of the four grade negative defensively, and Embiid played 38
games last season.

## The projection

Scoped separately from everything above, on purpose. It leans on DARKO, someone else's impact
metric, and it produces a headline number more precise-looking than its inputs support.

The mapping from player impact to team rating is fitted against observed 2025-26 ratings, giving
a slope of 1.433 ± 0.103. That slope is contemporaneous, so it can't be applied forward as it
stands: a team's rating is only about 59% persistent year to year, and composing the two gives
the 0.84 actually used. Simulating all 30 teams with conference brackets over 20,000 seasons:

**Philadelphia projects to 46.1 wins (33 to 59), a 3.5% title chance, and 9th in the league.**

Colder than I wanted. Their 2025-26 base was 18th, LeBron at 41 plus Brown minus Paul George is
roughly +2 DPM of talent, and it displaces bench minutes rather than replacing bad starters. New
York, Oklahoma City and San Antonio sit three to four points ahead and take half of simulated
titles between them. Embiid's availability is the biggest single lever: projecting the roster to
70 games each is worth about half a point of rating and 1.3 wins.

Read the interval rather than the point. The slope is fitted at n = 30 on one season, the DARKO
snapshot postdates the season it's scored against, aging is swept rather than applied, and the
rating uncertainty parameter moves the favourite's title odds between 17% and 25%. The 80% win
interval spans 26 games.

An independent review found three defects in this layer after it was first tagged, all of them
fixed before opening night and all recorded in the pre-registration's amendment log: a playoff
field that was fixed across every simulation, the forward-slope problem above, and a circular
margin scale. The pre-amendment projection is committed beside the corrected one and both are
scored all season.

## Pre-registered

The 2026-27 projection is committed before opening night with a timestamped tag:
[PREREGISTRATION.md](PREREGISTRATION.md). Everything else here is a backtest.

The scoring harness is already built and running (`make scorecard`), which was the point of
writing it before the season starts. Predictions are read from the committed file rather than
recomputed, both baselines are named in advance, and results append to a log so the running
record lives in git history.

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
    stopping            continuation value and the exercise boundary
    winprob             does the clock help predict game outcomes?
    ratings, aging      SRS from game results; paired-change aging curves
    dpm_calibration     player impact -> observed rating, fitted
    league, simulate    all thirty rosters -> win totals -> title odds
    scorecard           scoring the pre-registered projection
app/          Streamlit dashboard + CVD-validated chart theme
reports/      findings and generated tables
tests/        golden sequences, invariants, bounds, and estimator recovery
```

Every stage is a `make` target: `data`, `clock`, `validate`, `backfill`, `train`, `score`,
`lineups`, `synergy`, `stopping`, `winprob`, `project`, `scorecard`, `app`.

## Notes on method

Splits are by season, never random, and asserted in code. A random split leaks, since shots from
one possession would land on both sides.

Rates are volume-weighted, computed from summed makes and attempts rather than averaged across
players.

Feature value is measured by ablation rather than permutation importance. `CLOCK_ELAPSED` is
exactly `24 − SHOT_CLOCK`, so permuting either one leaves its substitute in place and makes both
look worthless.

Standard errors are clustered where the variation actually lives: on team-season for lineups
(3,512 lineups come from 300 clusters and share players), on season for the rule change (nine
clusters, not a million chances). Treating lineups as independent inflated one t-statistic from
2.9 to 5.0.

Where an answer moves with a defensible choice, the whole specification curve is reported rather
than one cell.

Known ceiling: no public feed carries shot-level defender proximity, so this is a shot-selection
model rather than a contested-ness model.
