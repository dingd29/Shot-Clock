# Findings

2024-25 regular season unless noted. 210,394 shots with a reconstructed shot clock, 95.8% of
all field-goal attempts. Points per attempt (PPA) counts field-goal points only, since the shot
detail feed has no free-throw rows. Method and validation in [METHODOLOGY.md](../METHODOLOGY.md).

Buzzer-beater heaves are excluded throughout sections 1 to 3. Those are shots with under 3
seconds of *game* clock left in the period, 1.85% of attempts, flagged as `GAME_CLOCK_EXPIRING`.
A third of all shots at 1 second or less on the shot clock are one of these, and they aren't
shot-clock decisions. Section 2 has the size of the effect.

---

## 1. Where the published buckets lose information

The NBA publishes six shot-clock ranges. Their widths don't match where efficiency actually
changes, so some bucket averages describe their contents well and others hide a lot.

| Bucket | Bucket PPA | Within-bucket range | Spread |
|---|---|---|---|
| 24-22 | 1.243 | 0.954 – 1.365 | 0.411 |
| 22-18 | 1.216 | 1.149 – 1.313 | 0.164 |
| 18-15 | 1.122 | 1.111 – 1.131 | 0.020 |
| 15-7 | 1.096 | 1.047 – 1.132 | 0.085 |
| 7-4 | 1.037 | 1.009 – 1.049 | 0.040 |
| 4-0 | 0.933 | 0.831 – 0.989 | 0.158 |

`4-0` reports one number, 0.933, for a region running from 0.989 down to 0.831. `18-15` spans
0.020 and is well summarised by its average. A team studying its own late-clock offense from the
published splits can't tell a possession dying with 4 seconds left from one dying with 1, and
those are different things.

(With heaves included, `4-0` reads 0.879 over a 0.708 to 0.989 range. Nearly all of that extra
spread is buzzer-beaters.)

## 2. Efficiency and time remaining

PPA falls from 1.047 at 7 seconds to 0.831 at 0, a drop of 0.216. Two things need saying about
that number.

**It isn't a causal estimate of time pressure.** Possessions surviving to 5 seconds are selected
on everything earlier having failed: the pass that wasn't there, the drive that got cut off.
Conditioning on how the possession *started* doesn't address selection on what happened during
it, and no version of this curve can. The honest statement is descriptive: conditional on
possession-start type, observed efficiency declines as the clock runs down. Whether time pressure
degrades shot quality, or bad possessions are simply the ones that last, isn't identified here.
Section 7 is the attempt to get at it properly.

**It's a lower bound on the descriptive decline.** Three measurement issues pull in different
directions and the net is conservative.

Heaves inflated it. Excluding buzzer-beaters cut the 0s-to-7s figure from 0.339 to 0.216, so 36%
of the apparent collapse was end-of-period garbage rather than late-clock offense.

Clock error attenuates what remains. Every documented reconstruction error biases clocks high,
since the failure mode is a missed reset rather than an invented one (METHODOLOGY §2, §4), which
places genuinely-late shots one bucket early and flattens the true decline.

Excluding free throws attenuates it too. Late clock draws fewer fouls, not more: 2.1% of chances
produce a free throw at 0 seconds against 13.6% at 20. See Caveats.

**The decline holds across every possession-start type, though not uniformly:**

| Start type | PPA at 7s | PPA at 0s | Drop | n at 0s |
|---|---|---|---|---|
| After made FG | 1.043 | 0.886 | −0.157 | 1,203 |
| After turnover | 1.016 | 0.750 | −0.266 | 180 |
| After defensive rebound | 1.020 | 0.671 | −0.349 | 292 |
| After offensive rebound | 1.091 | 0.489 | −0.603 | 176 |

Same sign everywhere, which rules out the decline being an artifact of one start type. The
magnitude varies four-fold and the three smallest groups have under 300 attempts at 0 seconds, so
don't read much into the ordering.

**The shot mix moves as the clock runs out.** Teams end up off the rim and in the mid-range:

| Clock | Rim share | Mid share | 3PT share |
|---|---|---|---|
| 23s | 65.3% | 11.3% | 23.4% |
| 15s | 26.1% | 29.3% | 44.6% |
| 5s | 20.6% | 38.3% | 41.1% |
| 0s | 17.4% | 44.6% | 38.0% |

Rim attempts fall by nearly three quarters and the mid-range share nearly quadruples. This table
also validates the heave exclusion: with buzzer-beaters in, the 3PT share at 0 seconds reads 50.1%
and has to be explained away as desperation launches. Excluding them the spike disappears (38.0%,
below its 15-second peak) and what's left is a clean monotone shift from rim to mid-range.

## 3. Early-clock efficiency is mostly transition

This is where a naive reading of the curve goes wrong. Raw PPA rises steeply above about 18
seconds, which looks like an argument for shooting earlier. It isn't.

Controlling for how the possession started removes most of the effect. For possessions beginning
after a made basket, a dead-ball half-court start, PPA is nearly flat from 12 to 21 seconds (1.097
→ 1.107). The apparent early-clock advantage comes from *which* possessions can produce a shot
that early:

| Clock | After made FG | After turnover | After def. rebound |
|---|---|---|---|
| 5s | 57.7% | 9.9% | 22.0% |
| 20s | 7.5% | 34.3% | 54.5% |

Shares are among the four main possession starts (made FG, turnover, defensive rebound, offensive
rebound). Worth stating because the denominators differ: those four are 99% of attempts at 20
seconds but only 75% at 5 seconds, the rest being made free throws and defensive fouls.

At 20 seconds only 7.5% of shots come from a half-court inbound start while 34% come off live-ball
turnovers. Those are fast breaks against a broken defense. The clock is a proxy for transition
rather than a cause of efficiency.

So "shoot earlier in the clock" isn't supported here. "Generate live-ball turnovers and defensive
rebounds" is, because those create the transition opportunities that produce early-clock shots.

**The 4.2% of shots dropped for low clock confidence don't explain this.** The drop isn't random,
it concentrates at the high-clock end, which is exactly where this finding lives. So the objection
is fair and gets a test. Restoring every dropped shot at its chance's start value, over the region
at or above 20 seconds:

| Basis | n | Half-court | Transition |
|---|---|---|---|
| Dropped (default) | 17,319 | 7.4% | 84.0% |
| Imputed at chance start | 26,421 | 10.5% | 81.3% |
| Every unclassifiable shot counted as half-court | 26,421 | 38.6% | 55.8% |

86% of the dropped shots carry an `inferred_*` start type, meaning the reconstruction couldn't
tell how the chance began, so they contribute no start type of their own and imputation barely
moves the split. The third row hands every ambiguous attempt to the half-court side, the most
adverse assumption available, and transition still leads by 17 points.

Reproduce: `possval.clock.validate.low_confidence_sensitivity(2024)`.

### What the shot model leans on

The shot model behind the expected-points figures used here reaches log loss 0.6351 and AUC 0.663
on 2024-25, trained through 2022-23, an 8.2% improvement on predicting the league mean for every
shot. Every downstream number depends on it, so it's worth being explicit about which features
carry it. Each group is valued by refitting without it, averaged over five seeds:

| Removed | Log-loss cost | SD over seeds | Share of gain |
|---|---|---|---|
| Geometry (location + action type) | 0.01658 | 0.00012 | 83.1% |
| Shooter prior | 0.00199 | 0.00006 | 10.0% |
| Possession (shot clock + chance start) | 0.00110 | 0.00012 | 5.5% |
| Game state | 0.00029 | 0.00010 | 1.4% |

Where the shot came from is worth about 15 times what the possession context is worth. Groups have
to be coarse enough to contain their own substitutes, which is why action type sits with location:
a dunk encodes "at the rim" and a pullup encodes mid-range, so ablating location alone credits
geometry with far less than it has. Splitting the possession block finer, the shot clock on its own
costs 0.00081, but that number isn't comparable to the coarse rows and shouldn't be read against
them.

So the reconstructed clock does almost nothing for predicting whether a shot goes in. That's a
genuine answer to a fair question, and section 9 takes it up properly.

Reproduce: `make ablate`, `reports/ablation.csv`.

## 4. The 14-second reset shows up in the data

Shots at exactly 14 seconds are unusual: 15,251 attempts, 7.2% of all shots and the single largest
one-second bucket, with a rim share of 42.4% against 26.1% at 15 seconds and 24.4% at 12.

Those are putbacks. Since 2018-19 the clock resets to 14 after an offensive rebound, so every
immediate second-chance attempt lands on that value.

This is a consistency check rather than independent validation. The reconstruction only applies
`max(remaining, 14)` from 2018-19 onward, so the spike moving to 14 in that season is partly
guaranteed by construction, and pre-2018 the same putbacks are recorded at 24. What it confirms is
that the rule flag fires in the right seasons. The bucket-share and per-player agreement in
METHODOLOGY §4 are the stronger checks, and section 6 is the genuinely independent one.

## 5. The 2018-19 rule change

The rule change gives a natural experiment with a clean structure, because treatment is assigned
by rule rather than by anyone's choice. Treated: chances starting with an offensive rebound, reset
cut from 24s to 14s. Control: chances starting with a defensive rebound, untouched.

Both are live-ball rebound starts, so they share the era's pace, spacing and officiating drift.
Outcomes come from the raw feed (durations from game-clock differences, points from descriptions)
rather than from the reconstruction, which implements the rule being tested and would otherwise
recover it by construction.

### A feed artifact worth knowing about

The NBA changed how it timestamps play-by-play in 2017-18, one season before the rule. The share
of events immediately following a rebound that carry the identical game clock as that rebound:

| Season | 2015-16 | 2016-17 | 2017-18 | 2018-19 | … | 2024-25 |
|---|---|---|---|---|---|---|
| Identical clock after a rebound | 15.1% | 14.7% | 18.7% | 18.5% | | 17.8% |

It steps once and stays. Since chance duration here is measured from game-clock differences, and
the change lands specifically on the events that begin a treated chance, 2017-18 measures shorter
second chances for reasons that have nothing to do with basketball.

That season is also the only one carrying the new timestamping and the old 24-second reset, which
is why it showed up as an outlier three separate ways before the cause was found: an odd baseline
in the difference-in-differences, 3.1% of shots landing at exactly 24 seconds against about 0.5%
in every other season, and a 14-second fingerprint appearing a year early. It's dropped from the
design, which cuts the standard error on the long-chance effect more than fourfold.

### The experiment

931,897 chances across nine seasons, 199,857 treated, standard errors clustered on season.

| | Outcome | DiD | SE | t |
|---|---|---|---|---|
| First stage | P(chance lasts past 14s) | −0.0223 | 0.0016 | −13.77 |
| Reduced form | Chance duration (seconds) | −0.202 | 0.042 | −4.81 |
| Result | Points per chance | −0.0159 | 0.0063 | −2.52 |

The first row is a manipulation check rather than a finding. After 2018-19 an offensive rebound
with under 14 seconds left resets to exactly 14, so a treated chance essentially cannot run past
14 seconds. Confirming that long chances vanished confirms the rule took effect and that the
reconstruction implements the reset correctly, which is worth establishing, but it's close to
mechanically implied by the treatment.

The first stage is strong, which is what licenses the rest. The share of second chances running
past 14 seconds collapses the year it takes effect and never returns:

| | 2015-16 | 2016-17 | 2018-19 | 2019-20 | … | 2024-25 |
|---|---|---|---|---|---|---|
| Off. rebound (treated) | 9.1% | 8.2% | 1.4% | 1.3% | | 1.4% |
| Def. rebound (control) | 27.8% | 26.8% | 21.6% | 22.2% | | 22.6% |

An 83% drop against a control that only drifts. The event study is clean: the treated-minus-control
gap sits at −0.0007 and 0.000 in the two pre-seasons, then steps to −0.016 and stays between −0.020
and −0.029 for seven years. The 1.4% that survives isn't error, since a team rebounding early
enough keeps a clock above 14.

Mean duration fell only 0.20 seconds, because second chances already averaged 6.1 seconds before
the rule. The 24-second allowance was mostly optionality that went unexercised, which is also why
the efficiency effect is small.

### Did it cost offenses anything?

About 1.8% of second-chance efficiency, −0.016 points per chance. This is the row about behaviour
rather than about the rule, and it's also the weakest of the three statistically. It's negative in
all seven post-rule seasons, which isn't nothing. But with 2017-18 removed the pre-period is two
seasons, and those two differ from each other by 0.014, nearly the size of the estimate. One
post-season (2022-23, −0.030) carries much of the average. Suggestive rather than established.

Treatment assignment isn't contaminated either, and that's checkable. The design rests on
classifying each chance as beginning with an offensive or defensive rebound, and error there is
measurement error in treatment, which attenuates the estimate. The classification uses the feed's
team ids and event ordering plus tracking of who shot last, never the reconstructed clock or the
14-second rule.

It agrees with an independent label 99.815% of the time (105,827 rebounds, 196 disagreements). That
label is the feed's own bookkeeping: descriptions carry each player's running rebound counters,
`REBOUND (Off:1 Def:2)`, and whichever increments identifies the type.

Reproduce: `python -m possval.pipeline rulechange`,
`possval.models.rulechange.treatment_label_agreement(2024)`.

## 6. Season-to-season stability

Sections 1 to 3 are cut on 2024-25. The backfill makes them testable across the whole sample, which
matters because a shape derived from one season could be an era artifact. Spacing, pace and
three-point rate all moved a lot over these years.

They hold. Every season's efficiency curve has the same shape:

| | 2015-16 | 2017-18 | 2020-21 | 2022-23 | 2024-25 |
|---|---|---|---|---|---|
| PPA at 0s | 0.788 | 0.793 | 0.791 | 0.845 | 0.831 |
| PPA at 7s | 0.963 | 1.010 | 1.038 | 1.046 | 1.047 |
| PPA at 20s | 1.284 | 1.172 | 1.263 | 1.297 | 1.254 |
| Rise, 0s → 7s | 0.176 | 0.218 | 0.247 | 0.201 | 0.216 |

Across all ten seasons the 0s-to-7s rise averages 0.211 with a standard deviation of 0.022, and the
7s-to-20s rise averages 0.238 (SD 0.047). Excluding heaves makes the late-clock figure more stable
rather than less, since the standard deviation falls from 0.035 to 0.022 while the mean drops.
Buzzer-beater frequency varied by season and was adding noise as well as bias.

Correlating each season's centred curve against 2024-25 gives r ≥ 0.967 for every season under the
14-second rule, rising to 0.99. Pre-2018 seasons sit lower at 0.82 to 0.91, which is expected rather
than troubling: the 14-second reset changes the shape of the curve around 14 seconds, so a pre-rule
season should correlate less well with a post-rule one. That the split falls exactly at the rule is
itself a check.

The whole curve drifts upward over the decade, since league efficiency rose on every measure, but
the shape doesn't move.

## 7. Shooting as an option

Sections 1 to 3 are descriptive and say so. The efficiency-versus-clock curve is a selected sample
at every point, so its slope can't separate time pressure degrading shot quality from bad
possessions being the ones that last.

This changes the question rather than the controls. At every moment the offense holds a live
decision: shoot now at whatever is available, or decline and draw again from a distribution whose
value decays as the clock runs. That's American option exercise, and it's answerable because it
conditions on the decision (a shot was taken at second *t* with model value *q*) rather than on the
outcome.

What's identified and what isn't: taken shots are observed with their model value, so premature
exercise, shooting when holding was worth more, is measurable. The converse isn't. A shot passed up
leaves no record of what it would have been worth, so this can't measure teams holding too long.
Every number here is a one-sided lower bound on total decision error.

### Continuation value

`V(t)` is the expected points from declining to shoot with `t` seconds left: among chances still
live at `t`, the mean outcome of those that didn't end there. Estimated over 2.86 million chances
across ten seasons:

| Seconds left | 1 | 3 | 7 | 12 | 17 | 23 |
|---|---|---|---|---|---|---|
| `V(t)`, value of holding | 0.375 | 0.468 | 0.621 | 0.719 | 0.761 | 0.808 |
| P(shoot this second) | 52% | 30% | 18% | 11% | 6% | 2% |

It behaves the way theory requires: monotone in time remaining, flattening above about 20 seconds
where extra clock stops helping, and collapsing toward zero as the option expires.

Chances ending because the *period* expired are removed before this is fitted rather than after.
They aren't shot-clock decisions and they concentrate where the model is most sensitive: 33% of
chances ending with 2 or fewer seconds on the shot clock are period expiries. Leaving them in
depresses `V(1)` by 0.056 and inflates the headline below by about a tenth.

### The exercise boundary

If offenses followed a threshold rule, shoot iff value ≥ `b(t)`, the bottom of the accepted
distribution would estimate `b(t)`. **The level of that boundary isn't identified**, and this is
worth stating because it would have been easy to publish and wrong. Calling the 5th percentile of
accepted shots the threshold rather than the 2nd or the 20th moves the estimated gap against `V(t)`
from −0.22 to +0.14. The sign of "too aggressive" versus "too patient" is a free parameter. No claim
rests on it.

The shape survives the choice. Optimal exercise requires the threshold to track the option it's
compared against: as `V(t)` collapses, the standard should collapse with it.

| Quantile used as the boundary | 2% | 5% | 10% | 20% | 25% |
|---|---|---|---|---|---|
| Boundary falls, 23s → 1s | 0.281 | 0.302 | 0.232 | 0.256 | 0.246 |
| `V(t)` falls over the same range | 0.433 | 0.433 | 0.433 | 0.433 | 0.433 |
| Relaxation ratio | 0.65 | 0.70 | 0.54 | 0.59 | 0.57 |
| Excess demand at 1-3s vs 8-23s | +0.137 | +0.139 | +0.163 | +0.165 | +0.158 |

**Offenses lower their standard by only about 54 to 70% of what the collapse in continuation value
calls for**, at every quantile. Put another way, relative to what holding is worth, they demand
roughly 0.15 points more from a shot with 1-3 seconds left than from one with 8 or more. The clock
runs out on an option they're still pricing as though it had time left.

The estimator can return the optimal answer. On synthetic offenses that accept exactly at `V(t)`,
the ratio comes back above 0.85 (`tests/test_stopping.py`), so the measured 0.5 is a deviation
rather than a property of the method.

### What this licenses

Exercise is broadly sound. Taken shots beat their continuation value by 0.39 points on average and
only 7.0% fall below it, about 2.1 points per game across both teams. NBA offenses aren't routinely
throwing away possessions, and any story about them doing so has to get past that number first.

The asymmetry is real but its cause isn't pinned down. A declined shot leaves no record, so this
can't see whether a shot worth taking actually existed at second 2. Excess late demand is consistent
with excessive patience, and equally consistent with nothing better being on offer, since the option
set shrinks as the defense sets and that isn't observable here. What's established is that the
accepted standard doesn't fall as fast as the value of waiting, which is a fact about behaviour
whatever generates it.

Free throws are excluded from both sides for unit consistency with `XPTS`, which makes this
conservative. Counting them raises `V(t)` by 0.084 on average, a higher bar to clear.

### Three checks it survives

It isn't garbage time. An unconditional `V(t)` folds blowouts and late-game fouling into the same
average, which are different decision problems. Splitting on score margin:

| Cut | Relaxation ratio | Excess late demand |
|---|---|---|
| All games | 0.54 – 0.70 | +0.152 |
| Competitive (\|margin\| ≤ 10) | 0.59 – 0.73 | +0.139 |
| Blowouts (\|margin\| > 10) | 0.46 – 0.59 | +0.179 |

The effect is weaker in competitive games and stronger in blowouts, which is the expected direction,
but it's comfortably present in competitive games alone.

It holds in all ten seasons. Ratio mean 0.641, SD 0.087, and every season's upper bound sits below
1.0. 2016-17 is closest to optimal (0.65 to 0.95) and 2021-22 furthest (0.42 to 0.70).

Reproduce: `reports/stopping_robustness.csv`.

### Per-player, the measure collapses

The natural extension: if some players are genuinely better bail-out creators, holding the ball for
them is worth more and their threshold should differ. Per-player mean surplus on late-clock shots,
shrunk toward the league, keeps 85% of its observed spread. That isn't sampling noise. It's
something less useful.

Per-player mean surplus correlates 0.984 with per-player mean late-clock `XPTS`, and the standard
deviation of the difference between them is 0.012 against 0.067 for either alone. Subtracting `V(t)`
removes almost nothing at player level, because every player's late-clock shots spread over roughly
the same seconds, so `V` enters as a near-constant. Mean surplus is mean late-clock shot quality
under a different name.

That's why the leaderboard reads the way it does, with centres on top and a +0.59 correlation with
late-clock rim share, and why restricting to non-rim shots doesn't fix it. The top just becomes Sam
Merrill, Max Strus and Stephen Curry, with Giannis and Zion at the bottom. Swapping "who dunks" for
"who shoots threes" still isn't a measure of judgment.

Measuring judgment needs the counterfactual, what else was available at that moment, and a declined
shot leaves no record. It's kept here rather than dropped because it looks like a skill ranking and
would be easy to publish as one.

Reproduce: `python -m possval.pipeline stopping`, which writes `reports/stopping_*.csv`.

## 8. Variation by team

The league relaxes at a ratio around 0.6. Whether that varies by team is the version of the
per-player question that isn't tautological: mean surplus was shot quality renamed, but the ratio
compares each team's own boundary movement against its own continuation value, so the level of shot
quality divides out.

Raw, over ten seasons and about 95,000 chances per team, the spread looks large: 0.41 to 0.84. Most
of it isn't real.

Thirty teams each get their own `V(t)` and their own boundary from a thirtieth of the data, so
spread appears whether or not teams differ. Permuting team labels twenty times and repeating the
whole calculation gives a null spread of 0.078 against the observed 0.098. Squaring those, only 37%
of the observed variance is signal.

Shrunk accordingly:

| | Team | Raw | Shrunk |
|---|---|---|---|
| Slowest to relax | PHI | 0.409 | 0.520 |
| | SAC | 0.440 | 0.531 |
| | NOP | 0.465 | 0.540 |
| Quickest to relax | MEM | 0.697 | 0.626 |
| | CHA | 0.828 | 0.675 |
| | TOR | 0.840 | 0.679 |

The real range is roughly 0.52 to 0.68 rather than 0.41 to 0.84. A team effect exists and it's about
a third the size the raw numbers suggest. Every team is still well below 1.0, so this is league-wide
behaviour with modest variation rather than a few bad offenses dragging an average.

The null is itself an estimate and needs enough permutations: ten draws put it at 0.074 and twenty at
0.078, moving the signal share from 43% to 37%. Twenty is the default.

Philadelphia sits at the bottom, slowest in the league to lower its standard as the clock expires.
Given the projection in section 12 turns on this roster's shot creation that's worth noting, but not
worth over-reading. The shrunk gap to league average is 0.065 and the measure says nothing about the
2026-27 roster, three quarters of which is new.

Reproduce: `reports/stopping_team_relaxation.csv`.

## 9. Shot clock and win probability

The ablation in section 3 asked whether the shot clock predicts whether a shot goes in and answered
no. That's the right answer to a question worth widening, because the shot clock was never about
shot-making. Continuation value in section 7 runs 0.37 to 0.81 across the clock, a 2.16× range, so
it's plainly informative about possessions.

Does it improve a live win-probability model? The NBA publishes one built from a feed with no shot
clock in it, which makes this the strongest remaining case for predictive value.

5.34M events, ten seasons, time-ordered split, test on 2024-25:

| Model | Log loss | Brier | AUC |
|---|---|---|---|
| Score margin + time + possession | 0.48545 | 0.16507 | 0.83332 |
| + shot clock, chance elapsed, late-clock flag | 0.48528 | 0.16500 | 0.83347 |

Improvement: 0.000163 log loss, or 0.034%. Bootstrapped over the 1,230 test *games* rather than the
550,132 events, since every event in a game shares one label and an event-level interval would claim
hundreds of times more information than exists: 95% CI [+0.00005, +0.00026], positive in 100% of
draws.

Reliably non-zero and practically nil. With half a million events the improvement is statistically
unambiguous and would round to zero in any application.

### The three scales

| Question | Where the shot clock lands |
|---|---|
| Will *this shot* go in? | Negligible, 5.5% of model gain, smallest coarse group in the ablation |
| Will *this possession* score? | Large, `V(t)` spans 0.37 to 0.81 |
| Will *this team* win? | Negligible, 0.034% of log loss |

The shot clock is possession-scale information, and a possession is about 1% of a game's scoring.
It's genuinely informative about the object it describes and washes out at the scale below and the
scale above.

That's the summary of the whole shot-clock question here. Reconstructing it didn't buy predictive
edge at either end. What it bought is the ability to see a decision that's otherwise invisible,
since section 7 exists only because `V(t)` can be computed at all, and a measurement instrument is a
different kind of contribution from a feature that lifts AUC.

Reproduce: `python -m possval.pipeline winprob`.

## 10. Three pre-registered follow-ups

Section 7 raises three obvious questions, and all three could be answered twenty ways until one came
out interesting. They were registered before any of them was run, with hypotheses, directions,
decision rules and an exploration/holdout split, in
[`preregistration_exploration.md`](preregistration_exploration.md), committed one commit before the
analysis code.

| | Hypothesis | Predicted | Observed | Verdict |
|---|---|---|---|---|
| H1 | Under-relaxing costs points | positive ρ | +0.251 explore, +0.065 full sample | Not supported |
| H2 | Offenses adapted to the 2018 rule | two-sided | DiD −0.160 vs placebo mean −0.108 (z = −1.9) | Marginal |
| H3 | Creator on floor → lower ratio | negative | +0.065 explore, +0.001 holdout | Failed |

H1 can't be answered with this data, which is different from being answered no. The correlation is
the right sign and below the ρ ≈ 0.36 detectability floor stated in advance, and it collapses to
+0.065 on the full sample. The holdout isn't estimable at all: the ratio anchors on the boundary at
23 seconds, and two seasons split thirty ways leaves too few shots that late.

H2's placebos are the story. Fake rule-years produce DiDs of −0.083 to −0.145 against the real
−0.160. It clears the pre-registered bar, but every placebo being large says a secular trend runs
through both arms that the design doesn't remove.

H3 is the one worth dwelling on. On exploration the gap was +0.065 and cleared its permutation null,
a defensible-looking result with a ready story about stars changing how offenses wait. On held-out
seasons it's +0.001. It was also the wrong sign from the start.

That's a false positive that would have survived every check applied elsewhere here. It took a
held-out sample to kill it, which is the whole argument for writing the protocol first.

## 11. Creation overlap

The reconstruction makes it possible to measure a player's creation profile: the distribution of his
attempts over (shot-clock bucket × zone). Two players overlap when their profiles have the same
shape, meaning both want the ball at the same moments. The idea under test was that high overlap
costs a team offense, since four creators can't all use the same possessions.

**The descriptive half holds.** Philadelphia's projected core is genuinely redundant:

| Pair | Creation similarity |
|---|---|
| LeBron ↔ Jaylen Brown | 0.988 |
| LeBron ↔ Maxey | 0.980 |
| Brown ↔ Maxey | 0.975 |
| Embiid ↔ Brown | 0.951 |
| Embiid ↔ KCP | 0.836 |

Volume-weighted, the big four score 0.973, the 99th percentile of random four-player groups (league
mean 0.895, p90 0.958). Embiid is the only differentiated creator. LeBron, Brown and Maxey are close
to interchangeable in *when* they generate offense.

**The causal half doesn't.** Testing whether overlap predicts efficiency across 270 team-seasons
(2016-17 to 2024-25), controlling for the same players' prior-season scoring quality and season
fixed effects. Three outcomes and three core sizes, all nine reported, because picking one after
seeing the others is where a null quietly becomes a finding:

| Core size | Outcome | Effect of +1 SD overlap | t |
|---|---|---|---|
| Top 3 | Points per attempt | +0.0034 | +1.73 |
| Top 3 | Points above expected | +0.0008 | +0.42 |
| Top 3 | Offensive rating | +0.48 | **+2.57** |
| Top 4 | Points per attempt | +0.0014 | +0.71 |
| Top 4 | Points above expected | −0.0005 | −0.25 |
| Top 4 | Offensive rating | +0.31 | +1.71 |
| Top 8 | Points per attempt | −0.0010 | −0.50 |
| Top 8 | Points above expected | −0.0011 | −0.62 |
| Top 8 | Offensive rating | +0.18 | +0.99 |

One of nine clears |t| = 2, and it points the wrong way. The hypothesis says more overlap should
*hurt*; every significant reading here says the opposite. That's what the construction produces on
its own: similar players are ones who concentrate their attempts in the same part of the clock,
early-clock chances score better (section 2), so similarity and efficiency share a channel before
any redundancy story enters. A positive coefficient is the null's expected shape here, not evidence
against redundancy. See Caveats.

The control behaves as it should (prior quality t = 9.9, model R² 0.50 to 0.64), so this is a real
null rather than a broken test.

Reproduce: `make synergy`, `reports/synergy_team_season.csv`.

### The lineup-level retest

The obvious objection: a team's top creators don't share the floor for all their minutes, so a real
five-on-five effect could average away across a season. Testing it required on-court lineups, 5.57M
events across ten seasons resolved from substitution sequences, giving 3,552 five-man lineup-seasons
with at least 100 chances together, a prior season of scoring history for their players, and roughly
a million chances in total.

The retest doesn't rescue the idea. It also doesn't cleanly confirm the null, and the reason is worth
stating, because a single number here would be a choice about which answer to believe:

| Specification | n | Effect of +1 SD overlap (pts/chance) | 95% CI | t |
|---|---|---|---|---|
| Season FE, unclustered | 3,552 | +0.0048 | +0.0020, +0.0076 | +3.31 |
| Season FE, clustered by team-season | 3,552 | +0.0048 | +0.0009, +0.0087 | +2.41 |
| Team-season FE, clustered | 3,552 | +0.0046 | −0.0009, +0.0102 | +1.65 |
| Team-season FE, ≥200 chances | 1,396 | +0.0046 | −0.0034, +0.0126 | +1.13 |
| Team-season FE, ≥400 chances | 505 | −0.0068 | −0.0196, +0.0060 | −1.04 |
| Team-season FE, ≥800 chances | 179 | −0.0348 | −0.0660, −0.0035 | **−2.18** |

Three things happen down that table. Clustering matters: these lineups come from 300 team-seasons and
share players wholesale, since one starter appears in dozens of rows, and treating them as independent
inflates t from 2.41 to 3.31. Team-season fixed effects matter too, because without them the
coefficient is partly identified by good teams having high-overlap lineups, which is confounded. The
pooled effect doesn't survive that. And restricting to lineups that actually played, the sign flips
and the bottom row reaches significance in the direction the hypothesis predicts.

That bottom row is the one to be most careful with. It's the last cell of a specification curve, it
rests on 179 lineups, and a formal test of heterogeneity, overlap interacted with log chances, comes
back at t = +0.36. The drift across thresholds is within noise. Reading the significant cell as the
answer, having watched five others fail to be, is the exact error a specification curve exists to
prevent. The honest reading is that neither the positive pooled estimate nor the negative
heavily-used estimate is robust.

**What this can and can't rule out.** For the heavily-used lineups the Sixers question actually
concerns (≥800 chances, roughly a starting unit's season), the interval is −0.066 to −0.004 points per
chance, or −7.6% to −0.4% of league-average efficiency. A large redundancy penalty is still excluded:
the 10 to 15% offensive haircut that naive diminishing-returns adjustments apply to multi-creator
teams sits outside this interval. A modest penalty of a few percent among the most-used lineups is
consistent with this data and can't be ruled out, and this is the one specification that positively
suggests one.

Two explanations stay live. Coaches may already solve redundancy by staggering minutes, in which case
the null reflects successful adaptation rather than an absent problem. And Philadelphia's 0.973 sits
outside the observed team-season range (max 0.961), so applying any fitted coefficient to them is
extrapolation.

### Head to head against usage

The point of building creation profiles was a specific, falsifiable claim: that *when* players want
the ball carries information the standard *how much* measure doesn't. Every public
diminishing-returns adjustment is some version of summed usage. That's the incumbent, measured here as
the five players' combined shot attempts per 100 on-court chances, raced against creation overlap on
identical rows:

| Model | Usage sum | Creation overlap | R² |
|---|---|---|---|
| Usage only | +0.0139 (t=8.49) | — | 0.2488 |
| Creation overlap only | — | +0.0046 (t=1.65) | 0.2313 |
| Both | +0.0143 (t=8.00) | −0.0017 (t=−0.60) | 0.2489 |

Coefficients are points per chance per +1 SD, team-season fixed effects, clustered.

Creation overlap adds nothing. Once usage is in the model its coefficient changes sign and its
t-statistic falls from 1.65 to −0.60, while usage barely moves. R² rises by one ten-thousandth. The
two correlate 0.33 within a team-season, and on this evidence overlap's standalone effect was that
shared component. The expensive feature, the one requiring a shot clock that exists in no public
feed, is a worse version of a measure anyone can compute from a box score.

Two caveats cut against over-reading the incumbent too. Both measures are contemporaneous with the
outcome, so neither is causal. The race is fair because both share the weakness, but "usage sum
predicts efficiency" isn't "wanting the ball more helps." And the positive sign almost certainly
reflects talent rather than usage: players who take more shots per chance are players who don't turn
the ball over, and prior-season points per attempt doesn't capture that, correlating just 0.03 with
usage sum.

**So Philadelphia shouldn't be marked down for offensive fit.** The defensible concerns are defense
and availability. Three of the four stars grade negative defensively by DARKO (Brown −1.27, Maxey
−0.91, LeBron −0.27), Embiid is the only plus defender in the starting five, and the bench sits below
league median.

## 12. Applications to the Sixers

The projection layer, kept separate from everything above because it's a different kind of object. It
depends on DARKO, a third-party impact metric, and produces a number more precise-looking than its
inputs support.

### Ratings

Least-squares SRS over 11,968 games reproduces reality: home win rate 0.5649, mean home margin +2.19,
and 2024-25 topping out at OKC +12.66, the team that won the title with a historic point differential,
with Washington (−12.13) at the bottom. Out of sample, predicting each season from the previous
season's ratings beats the base rate by 4.4% log loss (0.6554 vs 0.6854).

Scores are summed from scoring events rather than read off the feed's `SCORE` column. That column
carries stale trailing rows: game 22300902 ends "112 - 118" then logs a spurious "15 - 26", which left
4.8% of 2015-16 games with a wrong final score, some off by more than 100 points. Event-summed totals
match the score string's running maximum on 96 to 100% of games and reproduce published league scoring
averages exactly (205.4 combined points per game in 2015-16, 227.7 in 2024-25). The correction moves
individual team ratings by up to 0.53 points and the league mean by 0.06, small in aggregate because
the errors largely cancel, which is why it survived unnoticed.

A useful negative result along the way: explicitly shrinking stale ratings toward the mean does
nothing once the logistic scale is refit, since the two are the same parameter. Log loss is identical
from shrink 1.0 down to 0.5 while the fitted scale tracks 12.75 to 6.50. Team ratings correlate 0.587
year over year.

### Calibration

The mapping from player impact to team rating is now fitted, which is what previously blocked quoting
a title number. 2025-26 is the one season where both halves exist: observed team ratings from
`nbastatsv3`, and a DARKO snapshot covering the players who produced them. Regressing the first on the
second across all 30 teams:

**Slope 1.433 ± 0.103, intercept +0.23, r = 0.935, residual SD 2.15.**

Two things fall out. The textbook identity, team rating = minutes-weighted DPM, is compressed by 43%,
and 1.0 sits more than four standard errors away. And the fitted intercept replaces the old
rotation-size guess entirely, since the fit uses every player's actual 2025-26 minutes.

A trap avoided: calibrating offence and defence separately against points scored and allowed gives
slopes of 0.90 and 1.78, apparently showing DARKO compresses defensive spread twice as hard, which for
an offence-heavy roster like Philadelphia's would matter enormously. It's an artifact. Both targets
are per-game and pace-contaminated, and a fast team looks better on offence and worse on defence for
reasons that cancel in its net rating. Against a common target the slopes are 1.47 and 1.31 and can't
be distinguished (F = 1.09, p = 0.31). Using the split would have put Philadelphia at +2.80 instead of
+5.11.

### The projection

All 30 teams are projected, because a title probability isn't a property of one team. Each roster
starts from 2025-26 minutes valued at current DARKO; the trade moves LeBron and Brown to Philadelphia
and Paul George to Boston; minutes are re-fitted to the 240 a game actually provides. 20,000 simulated
seasons, conference brackets, uncertainty of 3.95 points per team.

| Scenario | Rating | Wins | 80% interval | Title | League rank |
|---|---|---|---|---|---|
| Minutes as played (injuries repeat) | +2.50 | 47.1 | 34-60 | 1.5% | 11th |
| Health-adjusted (70 games each) | +3.49 | 49.2 | 37-61 | 2.1% | 9th |

**A 47 to 49 win team with roughly a 2% title chance.** Colder than the premise. Three things drive
it. Their 2025-26 base was 18th in the league at −0.31 SRS, so the trade upgrades a middling team
rather than adding to a contender. The upgrade itself is about +2 DPM: LeBron (1.31, age 41) plus
Jaylen Brown (1.78) minus Paul George (1.07), displacing bench minutes rather than replacing bad
starters. And three teams sit a tier above, with New York (+10.5), Oklahoma City (+10.7) and San
Antonio (+8.8) taking 72% of simulated titles between them.

Availability is the largest single lever. Embiid played 38 games in 2025-26. Projecting every player
to 70 games is worth a full point of rating and doubles the lower tail, and the entire difference
between the two scenarios above is his health and Brown's.

### How much is model and how much is knowledge

Title odds are acutely sensitive to how uncertain the ratings are, and that parameter isn't
observable:

| Rating uncertainty | Best team's title odds | Philadelphia | Top-3 share |
|---|---|---|---|
| 2.15 (calibration residual, a floor) | 38.5% | 0.8% | 87% |
| 3.95 (year-over-year, used) | 30.2% | 2.0% | 73% |
| 5.00 | 26.0% | 2.7% | 65% |

3.95 is the residual from predicting each season's SRS from the previous season's over ten seasons,
which is how far a team actually moves in a year. The 2.15 floor would be right only if the roster
snapshot were the whole story, and quoting it would make the favourites look far more certain than any
honest reading supports.

### No aging applied

That's a refusal rather than an oversight. Aging DPM needs a DPM aging curve, which needs DARKO across
multiple seasons, and only one snapshot exists. The curve this project *can* fit is on shot efficiency,
and its support collapses precisely where the question lives: three player-seasons at age 38, one at 40,
and no paired observation past 34→35.
Applying an extrapolated curve to the single player it matters most for would dress an assumption up
as a measurement.

The sweep answers the question instead:

| LeBron's DPM decline | Philadelphia rating | League rank |
|---|---|---|
| 0.0 (as modelled) | +3.49 | 9th |
| 0.5 | +3.08 | 9th |
| 1.0 | +2.67 | 11th |
| 2.0 (implausibly steep) | +1.86 | 14th |

The conclusion doesn't depend on it. Even a two-point collapse, far beyond any plausible one-year fall,
leaves Philadelphia a mid-table playoff team rather than moving it toward or away from contention.
Embiid's decline sweeps almost identically.

### What the projection doesn't know

Only the Philadelphia trade is modelled. The other 29 rosters are frozen at their 2025-26 shape, so any
rival's offseason is invisible. And the calibration's DARKO snapshot postdates the season it was scored
against, so its residual is optimistic. These odds describe a league that won't exist on opening night.

---

## Caveats

Buzzer-beater heaves are excluded from sections 1 to 3 (game clock under 3 seconds, 1.85% of shots),
flagged as `GAME_CLOCK_EXPIRING`. The threshold is a judgment call but the result doesn't rest on it:
sweeping it over ten seasons, the 0s-to-7s rise is 0.212 at a 2-second cut and 0.206 at 8 seconds,
against 0.342 with no cut. Essentially all the contamination is sub-2-second heaves.

Free throws are excluded from PPA because `shotdetail` carries no FT rows, and the direction of that
bias is the opposite of what you'd guess. Late clock draws fewer fouls: the share of chances producing
a free throw falls from 13.6% at 20 seconds to 2.1% at 0. Free throws are 15.4% of a chance's value at
20 seconds and only 10.4% at 0, so including them makes the decline steeper. The rise from 0s to 7s is
+0.527 on field goals alone against +0.589 with free throws counted, and from 7s to 20s, +0.397 against
+0.519. Section 2 understates the late-clock penalty by roughly a quarter. (Chance-level and therefore
not directly comparable to the shot-level curve; the direction and rough size are the point.)

Chance-level analyses, meaning the rule-change experiment and the lineup work, do include free throws
via `event_points`. Shot-level findings don't. The two units are labelled throughout and shouldn't be
read off the same axis.

Shots at exactly 24 seconds (n=906, PPA 0.954) are an edge case: tips and putbacks landing on the reset
instant. Small sample, treated as noise.

4.2% of shots have no reconstructed clock, from low-confidence chances, and are excluded rather than
imputed. See METHODOLOGY §2.

The decline in section 2 is descriptive rather than causal, and no amount of conditioning on
possession-start type makes it causal, since selection happens within the chance. Section 7 is the
identification strategy.
