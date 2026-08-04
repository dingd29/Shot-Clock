# Findings: shot clock and shot efficiency

2024-25 regular season. 210,394 shots with a reconstructed shot clock (95.8% of all FGA).
Points per attempt (PPA) counts field-goal points only — free throws are excluded, since
`shotdetail` contains no FT rows. Method and validation: [METHODOLOGY.md](../METHODOLOGY.md).

**Buzzer-beater heaves are excluded throughout findings 1-3** — shots with under 3 seconds of
*game* clock left in the period, 1.85% of attempts. They are not shot-clock decisions, and a
third of all shots at 1 second or less on the shot clock are one. Leaving them in made the
late-clock collapse look **36% steeper than it is**; see the note in finding 2. Every number
below is on the excluded-heaves basis, flagged in the data as `GAME_CLOCK_EXPIRING`.

---

## 1. NBA's published buckets hide the steepest part of the curve

NBA publishes six shot-clock ranges. Their widths are wildly mismatched to where efficiency
actually changes, so the reported bucket average conceals very different amounts of variation.

| Bucket | Bucket PPA | Within-bucket range | Spread |
|---|---|---|---|
| 24-22 | 1.243 | 0.954 – 1.365 | **0.411** |
| 22-18 | 1.216 | 1.149 – 1.313 | 0.164 |
| 18-15 | 1.122 | 1.111 – 1.131 | 0.020 |
| 15-7 | 1.096 | 1.047 – 1.132 | 0.085 |
| 7-4 | 1.037 | 1.009 – 1.049 | 0.040 |
| **4-0** | 0.933 | **0.831 – 0.989** | **0.158** |

The `4-0` bucket reports a single number, 0.933, for a region where true efficiency falls
from 0.989 to 0.831 — a **17% swing collapsed into one figure**, and the second-widest spread
of the six. Meanwhile `18-15` spans a range of just 0.020 and is genuinely well summarised by
its average.

(With heaves left in, `4-0` reads 0.879 over a 0.708–0.989 range. Almost the entire apparent
extra spread was buzzer-beaters, which is the point of excluding them.)

A team studying its own late-clock offense from the published splits cannot distinguish a
possession that dies with 4 seconds left from one that dies with 1. Those are very different
outcomes.

## 2. Efficiency declines steeply into the late clock — descriptively

**PPA falls from 1.047 at 7 seconds to 0.831 at 0 seconds, a drop of 0.216.** Stated
carefully, because two things have to be said about that number.

**What it is not: a causal estimate of time pressure.** Possessions surviving to 5 seconds are
selected on everything earlier having failed — the pass that was not there, the drive that was
cut off. Conditioning on how the possession *started* does not address selection on what
happened *during* it, and no version of this curve can. The honest statement is descriptive:
*conditional on possession-start type, observed efficiency declines as the clock runs down.*
Whether time pressure degrades shot quality, or bad possessions are simply the ones that last,
is **not identified here**. Finding 3 makes exactly this argument about the early-clock end of
the curve, and finding 2 is held to the same standard. The identification strategy is the
optimal-stopping model in the open items — conditioning on the *decision* rather than the
*outcome* is what dissolves the selection problem.

**What it is: a lower bound on the descriptive decline.** Two measurement biases push in
opposite directions, and the net is conservative:

- *Heaves inflated it.* Buzzer-beaters are now excluded, which cut the 0s→7s figure from
  0.339 to **0.216** — 36% of the apparent collapse was end-of-period garbage, not late-clock
  offense.
- *Clock error attenuates what remains.* Every documented reconstruction error biases clocks
  **high** (missed resets rather than invented ones — METHODOLOGY §2, §4), so genuinely-late
  shots are placed one bucket early, flattening the true decline. eFG is biased high by
  1.78pp, worst late.
- *Excluding free throws attenuates it too.* Late clock draws **fewer** fouls, not more: 2.1%
  of chances produce a free throw at 0s against 13.6% at 20s (see Caveats).

So 0.216 is a floor on the descriptive decline once heaves are removed, not a possibly-inflated
figure.

**It holds across every possession-start type, though not uniformly:**

| Start type | PPA at 7s | PPA at 0s | Drop | n at 0s |
|---|---|---|---|---|
| After made FG | 1.043 | 0.886 | −0.157 | 1,203 |
| After turnover | 1.016 | 0.750 | −0.266 | 180 |
| After defensive rebound | 1.020 | 0.671 | −0.349 | 292 |
| After offensive rebound | 1.091 | 0.489 | −0.603 | 176 |

The sign is the same everywhere, which is what rules out the decline being an artifact of one
start type. The *magnitude* varies four-fold and the three smallest groups have under 300
attempts at 0s, so the ordering should not be over-read. (An earlier version of this table
described the collapse as appearing "identically" across start types; that was true only with
heaves included, which flattened the differences by adding near-zero attempts everywhere.)

**The shot mix moves as the clock runs out.** Teams end up off the rim and in the mid-range:

| Clock | Rim share | Mid share | 3PT share |
|---|---|---|---|
| 23s | 65.3% | 11.3% | 23.4% |
| 15s | 26.1% | 29.3% | 44.6% |
| 5s | 20.6% | 38.3% | 41.1% |
| 0s | 17.4% | **44.6%** | 38.0% |

Rim attempts fall by nearly three quarters, and the mid-range share nearly quadruples.

*This table also validates the heave exclusion.* With buzzer-beaters left in, the 3PT share at
0s read **50.1%** and had to be explained away as desperation launches. Excluding them the
spike disappears — 3PT share at 0s is 38.0%, *below* its 15s peak — and the pattern is a clean
monotone shift from rim to mid-range. The previous explanation was correct about what those
shots were; removing them makes the explanation unnecessary.

## 3. Early-clock efficiency is mostly transition, not "shooting early"

This is where the naive reading of the curve goes wrong. Raw PPA rises steeply above ~18
seconds, which looks like an argument for shooting earlier. It is not.

**Controlling for how the possession started removes most of the effect.** For possessions
beginning after a made basket — a dead-ball, half-court start — PPA is essentially flat from
12 seconds to 21 seconds (1.097 → 1.107). The apparent early-clock advantage is driven by
*which possessions are able to produce a shot that early*:

| Clock | After made FG | After turnover | After def. rebound |
|---|---|---|---|
| 5s | 57.7% | 9.9% | 22.0% |
| 20s | **7.5%** | **34.3%** | **54.5%** |

Shares are **among the four main possession starts** (made FG, turnover, defensive rebound,
offensive rebound), which is worth stating because the denominators differ: those four are 99%
of attempts at 20 seconds but only 75% at 5 seconds, the remainder being made free throws and
defensive fouls. Comparing the rows without that caveat compares different bases.

At 20 seconds remaining, only 7.5% of shots come from a half-court inbound start, while 34%
come off live-ball turnovers. Those are fast breaks against a broken defense. The clock is a
*proxy* for transition, not a cause of efficiency.

**The 4.2% of shots dropped for low clock confidence do not explain this.** The drop is not
random — it concentrates at the high-clock end, exactly where this finding lives — so the
objection is fair and gets a test rather than an argument. Restoring every dropped shot at its
chance's start value, over the region at or above 20 seconds:

| Basis | n | Half-court | Transition |
|---|---|---|---|
| Dropped (default) | 17,319 | 7.4% | **84.0%** |
| Imputed at chance start | 26,421 | 10.5% | **81.3%** |
| Worst case: every unclassifiable shot counted as half-court | 26,421 | 38.6% | **55.8%** |

86% of the dropped shots carry an `inferred_*` start type — the reconstruction could not tell
how the chance began — so they contribute no start type of their own and imputation barely
moves the split. The third row is the stress test: hand *every* ambiguous attempt to the
half-court side, the most adverse assumption available, and transition still leads by 17
points. The conclusion is not an artifact of the missingness.

*Reproduce:* `possval.clock.validate.low_confidence_sensitivity(2024)`.

**Practical implication:** "shoot earlier in the clock" is not supported by this data. What is
supported is "generate live-ball turnovers and defensive rebounds," because those create the
transition opportunities that produce early-clock shots in the first place.

## 4. The 14-second reset leaves a visible fingerprint

Shots at exactly 14 seconds are anomalous: 15,251 attempts (7.2% of all shots, the single
largest one-second bucket) with a rim share of **42.4%**, against 26.1% at 15 seconds and
24.4% at 12 seconds.

These are putbacks. The 2018-19 rule resets the clock to 14 after an offensive rebound, so
every immediate second-chance attempt lands on that exact value.

*This is a consistency check, not independent validation, and the distinction matters.* The
reconstruction only applies `max(remaining, 14)` from 2018-19 onward, so the spike moving to
14 in that season is partly guaranteed by construction — pre-2018 the same putbacks are
recorded at 24. What it confirms is that the rule flag fires in the right seasons, which is
worth confirming but is a weaker claim than the bucket-share and per-player agreement in
METHODOLOGY §4. The genuinely independent robustness result is finding 4c.

## 4b. The 2018-19 rule change, and a feed artifact that nearly hid inside it

The rule change is a natural experiment with a structure that is rare in basketball data,
because the treatment is assigned by a rule rather than by anyone's choice:

- **Treated** — chances starting with an *offensive* rebound. Reset cut from 24s to 14s.
- **Control** — chances starting with a *defensive* rebound. Untouched.

Both are live-ball rebound starts, so they share the era's pace, spacing and officiating
drift. Outcomes come from the **raw feed** — durations from game-clock differences, points
from descriptions — never from the reconstruction, which implements the rule being tested and
would otherwise recover it by construction.

### First, the artifact

**The NBA changed how it timestamps play-by-play in 2017-18**, one season before the rule.
The share of events immediately following a rebound that carry the *identical* game clock as
that rebound:

| Season | 2015-16 | 2016-17 | **2017-18** | 2018-19 | … | 2024-25 |
|---|---|---|---|---|---|---|
| Identical clock after a rebound | 15.1% | 14.7% | **18.7%** | 18.5% | | 17.8% |

It steps once and stays. Because chance duration here is measured from game-clock differences,
and because the change lands specifically on the events that begin a *treated* chance, 2017-18
measures shorter second chances for reasons that have nothing to do with basketball.

That season is also the only one carrying the new timestamping *and* the old 24-second reset,
which is why it surfaced as an outlier three separate ways before the cause was found: an
anomalous DiD baseline, **3.1% of shots landing at exactly 24 seconds against ~0.5% in every
other season**, and a 14-second fingerprint appearing a year early. It is dropped from the
design. Doing so cuts the standard error on the long-chance effect more than fourfold.

### The experiment

931,897 chances across nine seasons, 199,857 treated, standard errors clustered on season.

| Outcome | DiD | SE | t |
|---|---|---|---|
| P(chance lasts past 14s) | **−0.0223** | 0.0016 | **−13.77** |
| Chance duration (seconds) | **−0.202** | 0.042 | **−4.81** |
| Points per chance | −0.0159 | 0.0063 | −2.52 |

**The rule bound almost entirely on the tail.** The share of second chances running past 14
seconds collapses the year it takes effect and never returns:

| | 2015-16 | 2016-17 | **2018-19** | 2019-20 | … | 2024-25 |
|---|---|---|---|---|---|---|
| Off. rebound (treated) | 9.1% | 8.2% | **1.4%** | 1.3% | | 1.4% |
| Def. rebound (control) | 27.8% | 26.8% | 21.6% | 22.2% | | 22.6% |

An 83% drop against a control that drifts gently, and the event study is textbook: the
treated-minus-control gap sits at −0.0007 and 0.000 in the two pre-seasons, then steps to
−0.016 and stays between −0.020 and −0.029 for seven years. The 1.4% that survives is not
error — a team rebounding early enough keeps a clock above 14, since the reset is
`max(remaining, 14)`.

Mean duration fell only 0.20 seconds, because second chances already averaged 6.1 seconds
before the rule. The 24-second allowance was mostly optionality, and most of it went
unexercised.

### Did it cost offenses anything? Probably a little

**−0.016 points per chance, about −1.8% of second-chance efficiency, and this is the weakest
of the three results.** It is negative in all seven post-rule seasons, which is not nothing.
But with 2017-18 removed the pre-period is two seasons, and those two differ from each other
by 0.014 — nearly the size of the estimate. One post-season (2022-23, −0.030) carries much of
the average.

So: suggestive, not established. **An earlier version of this section reported no effect at
all**, which was wrong for an instructive reason — the contaminated season inflated the
standard error enough to bury a real signal. Removing bad data made a null into a finding,
which is the opposite of the usual direction and worth stating plainly.

*Reproduce:* `python -m possval.pipeline rulechange`.

---

## 4c. The curves replicate in all ten seasons

Findings 1-3 are cut on 2024-25. The backfill makes them testable across the whole sample,
and this is the check that matters most, because a shape derived from one season could be an
era artifact — spacing, pace and three-point rate all moved substantially over these years.

They are not. Every season's efficiency curve has the same shape:

| | 2015-16 | 2017-18 | 2020-21 | 2022-23 | 2024-25 |
|---|---|---|---|---|---|
| PPA at 0s | 0.788 | 0.793 | 0.791 | 0.845 | 0.831 |
| PPA at 7s | 0.963 | 1.010 | 1.038 | 1.046 | 1.047 |
| PPA at 20s | 1.284 | 1.172 | 1.263 | 1.297 | 1.254 |
| **Rise, 0s → 7s** | 0.176 | 0.218 | 0.247 | 0.201 | **0.216** |

Across all ten seasons the 0s→7s rise averages **0.211 with a standard deviation of 0.022**,
and the 7s→20s rise averages 0.238 (SD 0.047). Excluding heaves makes the late-clock figure
*more* stable, not less — the standard deviation falls from 0.035 to 0.022 while the mean
drops, because buzzer-beater frequency varied by season and was adding noise as well as bias.

Correlating each season's centred curve against 2024-25's gives **r ≥ 0.967 for every season
under the 14-second rule** (2018-19 onward), rising to 0.99. Pre-2018 seasons sit lower, at
0.82–0.91, which is expected rather than troubling: the 14-second reset changes the shape of
the curve around 14 seconds, so a pre-rule season *should* correlate less well with a post-rule
one. That the split falls exactly at the rule is itself a check.

The whole curve drifts *upward* over the decade — league efficiency rose, as it did on every
other measure — but the shape does not move. The late-clock collapse is not a property of one
season's offensive environment.

---

## 5. Creation overlap does not predict offensive underperformance — at team level or lineup level

This was the project's headline hypothesis, and **it failed.**

The reconstruction makes it possible to measure a player's *creation profile*: the
distribution of his attempts over (shot-clock bucket × zone). Two players "overlap" when
their profiles have the same shape — both want the ball at the same moments. The hypothesis
was that high overlap costs a team offense, because four creators cannot all use the same
possessions.

**The descriptive half holds up.** Philadelphia's projected core is genuinely redundant:

| Pair | Creation similarity |
|---|---|
| LeBron ↔ Jaylen Brown | **0.988** |
| LeBron ↔ Maxey | 0.980 |
| Brown ↔ Maxey | 0.975 |
| Embiid ↔ Brown | 0.951 |
| Embiid ↔ KCP | 0.836 |

Volume-weighted, the big four score **0.973 — the 99th percentile** of random four-player
groups (league mean 0.895, p90 0.958). Embiid is the only differentiated creator; LeBron,
Brown and Maxey are close to interchangeable in *when* they generate offense.

**The causal half does not.** Testing whether overlap predicts efficiency across 270
team-seasons (2016-17 → 2024-25), controlling for the same players' prior-season scoring
quality and season fixed effects:

| Core size | Effect of +1 SD overlap on team xPTS/attempt | t |
|---|---|---|
| Top 3 creators | **+0.0029** | +1.62 |
| Top 4 creators | +0.0020 | +1.23 |
| Top 8 creators | −0.0001 | −0.03 |

No specification reaches significance, and at the star level **the sign is positive** — the
opposite of the hypothesis. The control behaves exactly as it should (prior quality t = 9.9,
model R² = 0.53-0.61), so this is a real null rather than a broken test.

**The obvious objection — and the retest that answers it.** A team's top creators do not
share the floor for all their minutes, so a real five-on-five effect could average away
across a season and leave the team-season test showing nothing. That objection is testable,
and testing it required on-court lineups: 5.57M events across ten seasons, resolved from
substitution sequences, giving **4,233 five-man lineup-seasons with at least 100 chances
together — 1,112,380 chances in total.**

The retest does not rescue the hypothesis. It also does not cleanly confirm the null, and
the reason is worth stating precisely, because a single number here would be a choice about
which answer to believe:

| Specification | n | Effect of +1 SD overlap (pts/chance) | 95% CI | t |
|---|---|---|---|---|
| Season FE, unclustered | 4,233 | +0.0064 | +0.0039, +0.0090 | +5.01 |
| Season FE, clustered by team-season | 4,233 | +0.0064 | +0.0031, +0.0098 | +3.77 |
| Team-season FE, clustered | 4,233 | +0.0076 | +0.0024, +0.0127 | +2.89 |
| Team-season FE, ≥200 chances | 1,650 | +0.0068 | −0.0007, +0.0143 | +1.78 |
| Team-season FE, ≥400 chances | 599 | −0.0024 | −0.0145, +0.0096 | −0.39 |
| Team-season FE, ≥800 chances | 205 | −0.0192 | −0.0512, +0.0127 | −1.18 |

Three things happened on the way down that table, and each is a correction of a real error:

1. **Clustering.** 4,233 lineups come from 300 team-seasons and share players wholesale — one
   starter appears in dozens of rows. Treating them as independent inflated t from 2.89 to
   5.01. The naive number was never the right one.
2. **Team-season fixed effects.** Without them the coefficient is identified partly by good
   teams having high-overlap lineups, which is confounded: the front offices that assemble
   talent also assemble modern shot diets. Comparing only lineups fielded by the same team in
   the same year strips that out. The effect survives this.
3. **Restricting to lineups that actually played.** Here it does not survive. The estimate
   loses significance by 200 chances and changes sign by 400.

That last row is the one that matters, and it must not be oversold: a formal test of
heterogeneity — overlap interacted with log chances — comes back at **t = −0.56**, so the
drift across thresholds is *within noise*. The honest reading is not "the effect reverses
among real lineups." It is that **the positive pooled estimate is not robust**, and the
sample of heavily-used lineups is too small to say anything sharp.

**What this can and cannot rule out.** For the heavily-used lineups the Sixers question
actually concerns (≥800 chances, roughly a starting unit's season), the interval is
−0.051 to +0.013 points per chance — **−5.9% to +1.5% of league-average efficiency.** So:

- A large redundancy penalty is excluded. The 10–15% offensive haircut that naive
  diminishing-returns adjustments apply to multi-creator teams is outside this interval at
  every level of aggregation tested.
- A modest penalty — a few percent among the most-used lineups — is entirely consistent with
  this data and cannot be ruled out. Distinguishing it would need far more high-usage
  lineup-seasons than ten years of basketball contains.

Two explanations also remain live and are untouched by either test. Coaches may already
solve redundancy by staggering minutes, in which case the null reflects successful adaptation
rather than an absent problem. And the Sixers' overlap (0.973) sits **outside the observed
team-season range** (max 0.961), so applying any fitted coefficient to them is extrapolation.

**The head-to-head, which the novel feature loses.** The point of building creation profiles
was a specific, falsifiable claim: that *when* players want the ball carries information that
the standard *how much* measure does not. Every public diminishing-returns adjustment is some
version of summed usage. The incumbent here is that measure — the five players' combined shot
attempts per 100 on-court chances — raced against creation overlap on identical rows:

| Model | Usage sum | Creation overlap | R² |
|---|---|---|---|
| Usage only (incumbent) | **+0.0135** (t=9.27) | — | 0.2755 |
| Creation overlap only | — | +0.0076 (t=2.89) | 0.2604 |
| **Both** | **+0.0133** (t=8.37) | **+0.0013 (t=0.49)** | 0.2756 |

Coefficients are points per chance per +1 SD, team-season fixed effects, clustered.

**Creation overlap adds nothing.** Its coefficient collapses by 83% and its t-statistic from
2.89 to 0.49 the moment usage is in the model, while usage barely moves. R² rises from 0.2755
to 0.2756 — one ten-thousandth. The two correlate 0.33 within a team-season, and on this
evidence overlap's standalone effect *was* that shared component. The expensive feature — the
one requiring a shot clock that exists in no public feed — is a worse version of a measure
anyone can compute from a box score.

That is the answer to the question the project posed, and it is a negative one. It is reported
as the headline result rather than buried, because the alternative would have been to report
the standalone t=2.89 and not run the race.

*Two caveats that cut against over-reading even the incumbent.* Both measures are
contemporaneous with the outcome, so neither is causal — the race is fair because both share
the weakness, but "usage sum predicts efficiency" is not "wanting the ball more helps."
And the positive sign almost certainly reflects talent rather than usage: players who take
more shots per chance are players who do not turn the ball over, and prior-season points per
attempt (the control) does not capture that — it correlates just 0.03 with usage sum.

**The implication for the projection is a change of subject.** The evidence for a
Philadelphia risk is not offensive fit — it is defense and availability. Three of the four
stars are negative defenders by DARKO (Brown −1.27, Maxey −0.91, LeBron −0.27), Embiid is
the only plus defender in the starting five, and the bench sits below league median. That
concern is untouched by both results, and it is where the projection should focus.

*Reproduce:* `python -m possval.pipeline lineup-test --first 2015 --last 2024`, which writes
`reports/lineup_overlap_specifications.csv`.

## 6. Philadelphia 2026-27: a projection, and why its level is soft

**Rating layer works.** Least-squares SRS over 11,968 games reproduces reality: home win rate
0.5649, mean home margin +2.19, and 2024-25 tops out at OKC **+12.66** — the team that won the
title with a historic point differential — with WAS (−12.13) at the bottom. Out of sample,
predicting each season from the previous season's ratings beats the base rate by **4.4% log
loss** (0.6554 vs 0.6854).

*Scores are summed from scoring events, not read off the feed's `SCORE` column.* That column
carries stale trailing rows — game 22300902 ends "112 - 118" and then logs a spurious
"15 - 26" — which left **4.8% of 2015-16 games with a wrong final score**, some off by more
than 100 points. Event-summed totals match the score string's running maximum on 96–100% of
games and reproduce published league scoring averages exactly (2015-16: 205.4 combined
points per game; 2024-25: 227.7). The correction moves individual team ratings by up to 0.53
points and the league mean by 0.06 — small in aggregate because the errors largely cancel,
which is precisely why it survived unnoticed.

*A useful negative result along the way:* explicitly shrinking stale ratings toward the mean
does nothing once the logistic scale is refit — the two are the same parameter, and log loss
is identical from shrink 1.0 down to 0.5 while the fitted scale tracks 12.75 → 6.50. Team
ratings correlate 0.587 year over year.

**The DPM→rating mapping is now calibrated**, which is what previously blocked quoting a
title number. 2025-26 is the one season where both halves exist: observed team ratings from
`nbastatsv3`, and a DARKO snapshot covering the players who produced them. Regressing the
first on the second across all 30 teams:

**slope 1.433 ± 0.103, intercept +0.23, r = 0.935, residual SD 2.15.**

Two things fall out. The textbook identity — team rating = minutes-weighted DPM — is
**compressed by 43%**, and 1.0 sits more than four standard errors away, so this is not a
detail. And the fitted intercept replaces the old rotation-size guess entirely: because the
fit uses every player's actual 2025-26 minutes, the centering that used to swing the
projection by 2.3 points is now estimated rather than assumed.

*A trap avoided.* Calibrating offence and defence separately against points scored and
allowed gives slopes of 0.90 and 1.78 — apparently showing DARKO compresses defensive spread
twice as hard, which for an offence-heavy roster like Philadelphia's would matter enormously.
It is an artifact. Both targets are per-game and pace-contaminated, and a fast team looks
better on offence and worse on defence for reasons that cancel in its net rating. Against a
common target the slopes are 1.47 and 1.31 and cannot be distinguished (F = 1.09, p = 0.31).
Using the split would have put Philadelphia at +2.80 instead of +5.11 — a 2.3-point error
biting hardest on exactly the roster shape this project exists to evaluate.

**The projection.** All 30 teams are projected, because a title probability is not a property
of one team. Each roster starts from 2025-26 minutes valued at current DARKO; the trade moves
LeBron and Brown to Philadelphia and Paul George to Boston; minutes are re-fitted to the 240
a game actually provides. 20,000 simulated seasons, conference brackets, uncertainty of 3.95
points per team.

| Scenario | Rating | Wins | 80% interval | Title | League rank |
|---|---|---|---|---|---|
| Minutes as played (injuries repeat) | +2.50 | **47.1** | 34-60 | 1.5% | 11th |
| Health-adjusted (70 games each) | +3.49 | **49.0** | 36-61 | **2.1%** | 9th |

**The superteam is a 47-49 win team with roughly a 2% title chance.** That is the headline,
and it is much colder than the premise. Three things drive it:

1. **The base was mediocre.** Philadelphia's 2025-26 SRS was −0.31, 18th in the league. The
   trade is an upgrade on a middling team, not an addition to a contender.
2. **The upgrade is smaller than it sounds.** LeBron (1.31 DPM, age 41) plus Brown (1.78)
   minus Paul George (1.07) is about +2 DPM of talent, and it displaces *bench* minutes
   rather than replacing bad starters.
3. **Three teams are far ahead.** New York (+10.5), Oklahoma City (+10.7) and San Antonio
   (+8.8) occupy a tier Philadelphia is six points below. Those three take 72% of titles.

**Availability is the largest single lever on this roster.** Embiid played 38 games in
2025-26. Projecting every player to 70 games is worth a full point of rating and doubles the
lower tail — the entire difference between the two scenarios above is his health and Brown's.

**How much of this is model and how much is knowledge.** The title odds are acutely sensitive
to how uncertain the ratings are, and that parameter is not observable:

| Rating uncertainty | Best team's title odds | Philadelphia | Top-3 share |
|---|---|---|---|
| 2.15 (calibration residual — a floor) | 38.5% | 0.8% | 87% |
| **3.95 (year-over-year, used)** | **30.2%** | **2.0%** | **73%** |
| 5.00 | 26.0% | 2.7% | 65% |

3.95 is the residual from predicting each season's SRS from the previous season's over ten
seasons — the amount a team actually moves in a year. The 2.15 floor would be right only if
the roster snapshot were the whole story; it is not, and quoting it would have made the
favourites look far more certain than any honest reading supports.

**No aging is applied, and that is a refusal rather than an oversight.** Aging DPM needs a
DPM aging curve, which needs DARKO across multiple seasons; only one snapshot exists. The
curve this project *can* fit is on shot efficiency, and its support collapses precisely where
the question lives — 12 player-seasons at age 38, one at 41. Applying an extrapolated curve to
the single player it matters most for would dress an assumption up as a measurement.

The sweep answers the question instead:

| LeBron's DPM decline | Philadelphia rating | League rank |
|---|---|---|
| 0.0 (as modelled) | +3.49 | 9th |
| 0.5 | +3.08 | 9th |
| 1.0 | +2.67 | 11th |
| 2.0 (implausibly steep) | +1.86 | 14th |

**The conclusion does not depend on it.** Even a two-point collapse — far beyond any plausible
one-year fall — leaves Philadelphia a mid-table playoff team rather than moving it toward or
away from contention. Embiid's decline sweeps almost identically.

**What this projection does not know.** Only the Philadelphia trade is modelled — the other
29 rosters are frozen at their 2025-26 shape, so any rival's offseason is invisible. And the
calibration's DARKO snapshot postdates the season it was scored against, so its residual is
optimistic. These odds describe a league that will not exist on opening night.

*Reproduce:* `python -m possval.pipeline project --games 70`, which writes
`reports/league_projection_2026_27.csv`.

---

## Caveats

- **Buzzer-beater heaves are excluded** from findings 1-3 (game clock under 3 seconds, 1.85%
  of shots), flagged as `GAME_CLOCK_EXPIRING`. The threshold is a judgment call but the result
  does not rest on it: sweeping it over ten seasons, the 0s→7s rise is 0.212 at a 2-second cut
  and 0.206 at 8 seconds, against 0.342 with no cut. Essentially the whole contamination is
  sub-2-second heaves.
- **The free-throw caveat was backwards, and is now measured.** Findings 1-3 exclude free
  throws, because `shotdetail` carries no FT rows. This was recorded as a reason finding 2
  might *overstate* the late-clock penalty, on the assumption that late clock draws more
  fouls. It draws fewer: the share of chances producing a free throw falls from 13.6% at 20
  seconds to **2.1% at 0 seconds**. Free throws are 15.4% of a chance's value at 20s and only
  10.4% at 0s, so including them makes the decline **steeper**, not shallower — the rise from
  0s to 7s is +0.527 on field goals alone against +0.589 with free throws counted, and from
  7s to 20s, +0.397 against +0.519. **Finding 2 understates the late-clock penalty by roughly
  a quarter.** (Chance-level and therefore not directly comparable to the shot-level curve;
  the direction and rough size are the point.)
- Chance-level analyses — the rule-change experiment, the lineup work — *do* include free
  throws, via `event_points`. Shot-level findings do not. The two units are labelled
  throughout and should not be read off the same axis.
- Shots at exactly 24 seconds (n=906, PPA 0.954) are an edge case: tips and putbacks landing
  on the reset instant. Small sample, treated as noise.
- 4.2% of shots have no reconstructed clock (low-confidence chances) and are excluded rather
  than imputed. See METHODOLOGY.md §2.
- The curves in findings 1-3 are 2024-25; finding 4c re-cuts them per season across all ten.
- **The decline in finding 2 is descriptive, not causal**, and no amount of conditioning on
  possession-start type makes it causal — selection happens *within* the chance. The
  identification strategy is an optimal-stopping model: compare the value of shooting now
  against the continuation value of holding, which conditions on the decision rather than the
  outcome. That work is next.
