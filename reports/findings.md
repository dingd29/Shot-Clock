# Findings

2024-25 regular season unless noted. 210,805 shots with a reconstructed shot clock, 96.0% of
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

**The same missingness sits under section 2's curve, so it gets the same test.** Testing only the
finding that prompted the objection is how a check turns into decoration.

| Basis | n | PPA 0-3s | PPA 4-7s | Late decline | PPA 20s+ |
|---|---|---|---|---|---|
| Dropped (default) | 207,097 | 0.934 | 1.041 | 0.107 | 1.269 |
| Imputed at chance start | 215,616 | 0.934 | 1.041 | 0.107 | 1.153 |

The late-clock decline is unchanged to three decimals, and it has to be: **99.6% of the restored
shots impute to 20 seconds or higher**, because a fabricated reset is a fabricated 24. The drop is
non-random and it is non-random at the *other end* of the clock from where section 2's claim lives.

The high-clock level is a different matter. Restoring those shots pulls PPA above 20 seconds from
1.269 to 1.153, so the missing shots are considerably worse than the ones we kept. That doesn't
touch section 2, which is about the late decline, and it doesn't touch the transition argument
above, which is about *shares* rather than levels. It does mean the `24-22` bucket level in section
1 is quoted on a favourable subset, and shouldn't be read as the true efficiency of a shot taken
immediately after a reset.

Reproduce: `possval.clock.validate.low_confidence_sensitivity(2024)` and
`low_confidence_curve_sensitivity(2024)`.

### What the shot model leans on

The shot model behind the expected-points figures used here reaches log loss 0.6349 and AUC 0.663
on 2024-25, trained through 2022-23, an 8.2% improvement on predicting the league mean for every
shot. Every downstream number depends on it, so it's worth being explicit about which features
carry it. Each group is valued by refitting without it, averaged over five seeds:

| Removed | Log-loss cost | SD over seeds | Share of gain |
|---|---|---|---|
| Geometry (location + action type) | 0.01657 | 0.00008 | 82.9% |
| Shooter prior | 0.00193 | 0.00010 | 9.7% |
| Possession (shot clock + chance start) | 0.00120 | 0.00010 | 6.0% |
| Game state | 0.00029 | 0.00006 | 1.5% |

Where the shot came from is worth about 15 times what the possession context is worth. Groups have
to be coarse enough to contain their own substitutes, which is why action type sits with location:
a dunk encodes "at the rim" and a pullup encodes mid-range, so ablating location alone credits
geometry with far less than it has. Splitting the possession block finer, the shot clock on its own
costs 0.00095, but that number isn't comparable to the coarse rows and shouldn't be read against
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

**Dropping it isn't enough, and this is the problem with the whole section.** With 2017-18 gone,
the feed regime lines up almost exactly with treatment: two pre-seasons on the old timestamping,
seven post-seasons on the new. That's only survivable if the shift hit both arms equally. Split by
rebound type, it didn't:

| Identical clock after… | 2015-16 | 2016-17 | 2017-18 | 2018-19 | … | 2024-25 |
|---|---|---|---|---|---|---|
| an **offensive** rebound (treated) | 26.7% | 27.4% | 41.6% | 40.9% | | 37.5% |
| a **defensive** rebound (control) | 7.3% | 6.9% | 7.6% | 7.2% | | 6.7% |
| gap | 19.4pp | 20.5pp | 34.0pp | 33.6pp | | 30.8pp |

The treated arm jumps 14 points and the control arm moves by less than one, in the season
immediately before treatment, and the new gap persists for the rest of the sample. So a change in
how the feed timestamps offensive rebounds is nearly collinear with the rule whose effect on
offensive-rebound chances is being estimated. A difference-in-differences cannot separate them.

### The experiment

931,897 chances across nine seasons, 199,857 treated, standard errors clustered on season.

| | Outcome | DiD | SE | t | p (wild cluster) |
|---|---|---|---|---|---|
| First stage | P(chance lasts past 14s) | −0.0227 | 0.0016 | −14.30 | 0.008 |
| Reduced form | Chance duration (seconds) | −0.207 | 0.040 | −5.23 | 0.066 |
| Result | Points per chance | −0.0154 | 0.0065 | −2.38 | **0.119** |

**The last column is the one to read.** There are nine season clusters, and a clustered standard
error read against a normal is badly optimistic at that count. The wild cluster bootstrap is the
standard fix, and with nine clusters there are only 2⁹ = 512 distinct sign vectors, so the whole
reference distribution is enumerated rather than sampled and the p-value is exact.

Against that reference the efficiency result does not clear conventional significance, and the
duration result only just does. An earlier version of this section reported t = −2.52 against 1.96
and called the efficiency effect established. That was wrong, and the fix is not a matter of
degree: p = 0.12 on nine clusters is not a marginal result, it is an absent one.

The first row is a manipulation check rather than a finding. After 2018-19 an offensive rebound
with under 14 seconds left resets to exactly 14, so a treated chance essentially cannot run past
14 seconds. Confirming that long chances vanished confirms the rule took effect and that the
reconstruction implements the reset correctly, which is worth establishing, but it's close to
mechanically implied by the treatment.

The first stage is strong, which is what licenses the rest. The share of second chances running
past 14 seconds collapses the year it takes effect and never returns:

| | 2015-16 | 2016-17 | 2018-19 | 2019-20 | … | 2024-25 |
|---|---|---|---|---|---|---|
| Off. rebound (treated) | 9.1% | 8.2% | 1.3% | 1.2% | | 1.4% |
| Def. rebound (control) | 27.9% | 27.0% | 21.7% | 22.3% | | 22.7% |

An 85% drop against a control that only drifts. The event study is clean: the treated-minus-control
gap sits at −0.0009 and 0.000 in the two pre-seasons, then steps to −0.017 and stays between −0.021
and −0.030 for seven years. The 1.3% that survives isn't error, since a team rebounding early
enough keeps a clock above 14.

This row is the one that survives the wild bootstrap, and it is also the one that is close to
mechanically guaranteed. That combination is worth stating plainly: the design detects the thing it
cannot fail to detect, and does not detect the thing it was built to measure.

Mean duration fell only 0.20 seconds, because second chances already averaged 6.1 seconds before
the rule. The 24-second allowance was mostly optionality that went unexercised, which is also why
the efficiency effect is small.

### Did it cost offenses anything?

The point estimate is −0.0154 points per chance, about 1.7% of second-chance efficiency, and it
does not survive inference. Three things stack against it, and any one would be enough to withhold
the claim:

- **p = 0.119** against an exact wild cluster bootstrap over the nine season clusters.
- **The pre-period is two seasons**, and those two differ from each other by 0.014, nearly the size
  of the estimate itself.
- **The feed shift above lands on the treated arm**, so even the sign is not cleanly attributable
  to the rule.

It is negative in all seven post-rule seasons, and one of them (2022-23, −0.030) carries much of
the average. That pattern is consistent with a small real effect and equally consistent with the
timestamping change. **The honest summary is that this design cannot tell whether the 2018-19 rule
cost offenses anything.** The rule's mechanical effect on chance length is established; its effect
on scoring is not.

Something else would be needed to settle it: a source of variation in the reset that isn't
confounded with the feed change, or timestamps for the pre-2017-18 era on the post-2017-18
convention. Neither exists in this data.

Treatment assignment isn't contaminated either, and that's checkable. The design rests on
classifying each chance as beginning with an offensive or defensive rebound, and error there is
measurement error in treatment, which attenuates the estimate. The classification uses the feed's
team ids and event ordering plus tracking of who shot last, never the reconstructed clock or the
14-second rule.

It agrees with an independent label 99.8% of the time (105,827 rebounds, 196 disagreements). That
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
| `V(t)`, value of holding | 0.362 | 0.466 | 0.622 | 0.720 | 0.763 | 0.810 |
| P(shoot this second) | 53% | 30% | 18% | 11% | 6% | 2% |

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
| Boundary falls, 23s → 1s | 0.164 | 0.183 | 0.174 | 0.216 | 0.243 |
| `V(t)` falls over the same range | 0.448 | 0.448 | 0.448 | 0.448 | 0.448 |
| Relaxation ratio | 0.37 | 0.41 | 0.39 | 0.48 | 0.54 |
| Excess demand at 1-3s vs 8-23s | +0.216 | +0.208 | +0.199 | +0.186 | +0.152 |

**Offenses lower their standard by only about 37 to 54% of what the collapse in continuation value
calls for**, at every quantile. Put another way, relative to what holding is worth, they demand
roughly 0.19 points more from a shot with 1-3 seconds left than from one with 8 or more. The clock
runs out on an option they're still pricing as though it had time left.

The estimator can return the optimal answer: on synthetic offenses that accept exactly at `V(t)`,
the ratio comes back above 0.85 (`tests/test_stopping.py`). That check is narrower than it looks,
though. It hands the estimator a correct value function rather than computing one, so it establishes
that the ratio arithmetic is sound and says nothing about bias in `V(t)` itself. There is a reason to
expect such a bias, and it pushes the ratio down. See Caveats.

### What this licenses

Exercise is broadly sound. Taken shots beat their continuation value by 0.39 points on average and
only 5.8% fall below it, about 1.8 points per game across both teams. NBA offenses aren't routinely
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
| All games | 0.37 – 0.54 | +0.192 |
| Competitive (\|margin\| ≤ 10) | 0.32 – 0.53 | +0.194 |
| Blowouts (\|margin\| > 10) | 0.42 – 0.58 | +0.185 |

It's present in competitive games alone, which is what this check is for, so it isn't a garbage-time
artifact. The ordering runs slightly against intuition: competitive games show the *lower* ratio, not
the higher one. The two intervals overlap heavily and I wouldn't read a story into the gap.

It holds in all ten seasons. Ratio mean 0.549, SD 0.074, and every season's upper bound sits below
1.0. 2024-25 is closest to optimal (0.49 to 0.79) and 2015-16 furthest (0.16 to 0.59).

Reproduce: `reports/stopping_robustness.csv`.

### Per-player, the measure collapses

The natural extension: if some players are genuinely better bail-out creators, holding the ball for
them is worth more and their threshold should differ. Per-player mean surplus on late-clock shots,
shrunk toward the league, keeps 85% of its observed spread. That isn't sampling noise. It's
something less useful.

Per-player mean surplus correlates 0.984 with per-player mean late-clock `XPTS`, and the standard
deviation of the difference between them is 0.012 against 0.066 for either alone. Subtracting `V(t)`
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

The league relaxes at a ratio around 0.47. Whether that varies by team is the version of the
per-player question that isn't tautological: mean surplus was shot quality renamed, but the ratio
compares each team's own boundary movement against its own continuation value, so the level of shot
quality divides out.

Raw, over ten seasons and about 95,000 chances per team, the spread looks large: 0.33 to 0.67. Most
of it isn't real.

Thirty teams each get their own `V(t)` and their own boundary from a thirtieth of the data, so
spread appears whether or not teams differ. The null comes from permuting team labels and repeating
the whole calculation. The permutation unit is the **team-game**, not the row: whole games move
together, so a fake team's chances stay clustered the way a real team's are, and its shots come from
the same games as its chances. Fifty draws give a null spread of 0.052 (SD 0.007 across draws, 5th
to 95th percentile 0.042 to 0.062) against the observed 0.068. Squaring those, **42% of the observed
variance is signal.**

Shrunk accordingly:

| | Team | Raw | Shrunk |
|---|---|---|---|
| Slowest to relax | SAC | 0.328 | 0.409 |
| | BKN | 0.359 | 0.421 |
| | MIA | 0.372 | 0.427 |
| Quickest to relax | TOR | 0.549 | 0.501 |
| | MIL | 0.583 | 0.515 |
| | CHA | 0.666 | 0.549 |

The real range is roughly 0.41 to 0.55 rather than 0.33 to 0.67. A team effect exists and it's about
half the size the raw numbers suggest. Every team is still well below 1.0, so this is league-wide
behaviour with modest variation rather than a few bad offenses dragging an average.

The null is itself an estimate and needs enough permutations. An earlier version drew ten and then
twenty, and the signal share moved from 43% to 37% between them, which is a sign the null hadn't
settled. Fifty is now the default and the spread across draws is reported alongside it.

Philadelphia is fourth-slowest in the league to lower its standard as the clock expires. Given the
projection in section 12 turns on this roster's shot creation that's worth noting, but not worth
over-reading. The shrunk gap to league average is 0.033 and the measure says nothing about the
2026-27 roster, three quarters of which is new.

One caution on all of the above, from section 13. Resolving this same ratio by band of the clock and
re-running the same permutation null on held-out seasons returns a signal share of **zero** in the
late clock — teams differ less there than random relabelling produces. The 42% here is measured over
ten seasons and a whole possession and stands as reported, but a reader who takes it as licence to
rank teams on late-clock decision-making should read section 13 first.

Reproduce: `reports/stopping_team_relaxation.csv`.

## 9. Shot clock and win probability

The ablation in section 3 asked whether the shot clock predicts whether a shot goes in and answered
no. That's the right answer to a question worth widening, because the shot clock was never about
shot-making. Continuation value in section 7 runs 0.36 to 0.81 across the clock, a 2.24× range, so
it's plainly informative about possessions.

Does it improve a live win-probability model? The NBA publishes one built from a feed with no shot
clock in it, which makes this the strongest remaining case for predictive value.

5.35M events, ten seasons, time-ordered split, test on 2024-25:

| Model | Log loss | Brier | AUC |
|---|---|---|---|
| Score margin + time + possession | 0.48536 | 0.16506 | 0.83335 |
| + shot clock, chance elapsed, late-clock flag | 0.48512 | 0.16496 | 0.83356 |

Improvement: 0.000241 log loss, or 0.050%. Bootstrapped over the 1,230 test *games* rather than the
550,651 events, since every event in a game shares one label and an event-level interval would claim
hundreds of times more information than exists: 95% CI [+0.00014, +0.00035], positive in 100% of
draws.

That bootstrap holds both fitted models fixed and resamples the test games, which answers whether the
difference is stable on unseen games but not whether it's stable at all. Both fits carve their
early-stopping split at random, and the quantity is 2e-4, so refitting is the other half of the
question. Over five seeds the gain is +0.000233 ± 0.000016 and positive every time.

Reliably non-zero and practically nil. With half a million events the improvement is statistically
unambiguous and would round to zero in any application.

### The three scales

| Question | Where the shot clock lands |
|---|---|
| Will *this shot* go in? | Negligible, 6.0% of model gain, third of four coarse groups |
| Will *this possession* score? | Large, `V(t)` spans 0.36 to 0.81 |
| Will *this team* win? | Negligible, 0.050% of log loss |

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
| Top 3 | Points per attempt | +0.0033 | +1.68 |
| Top 3 | Points above expected | +0.0007 | +0.36 |
| Top 3 | Offensive rating | +0.47 | **+2.52** |
| Top 4 | Points per attempt | +0.0013 | +0.68 |
| Top 4 | Points above expected | −0.0004 | −0.20 |
| Top 4 | Offensive rating | +0.30 | +1.63 |
| Top 8 | Points per attempt | −0.0010 | −0.51 |
| Top 8 | Points above expected | −0.0011 | −0.59 |
| Top 8 | Offensive rating | +0.18 | +0.95 |

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
events across ten seasons resolved from substitution sequences, giving 3,512 five-man lineup-seasons
with at least 100 chances together, a prior season of scoring history for their players, and 925,466
chances in total.

The retest doesn't rescue the idea. It also doesn't cleanly confirm the null, and the reason is worth
stating, because a single number here would be a choice about which answer to believe:

| Specification | n | Effect of +1 SD overlap (pts/chance) | 95% CI | t |
|---|---|---|---|---|
| Season FE, unclustered | 3,512 | +0.0048 | +0.0020, +0.0077 | +3.30 |
| Season FE, clustered by team-season | 3,512 | +0.0048 | +0.0008, +0.0088 | +2.35 |
| Team-season FE, clustered | 3,512 | +0.0056 | +0.0001, +0.0111 | +1.98 |
| Team-season FE, ≥200 chances | 1,395 | +0.0058 | −0.0021, +0.0138 | +1.44 |
| Team-season FE, ≥400 chances | 504 | −0.0043 | −0.0175, +0.0089 | −0.64 |
| Team-season FE, ≥800 chances | 177 | −0.0338 | −0.0615, −0.0060 | **−2.39** |

Three things happen down that table. Clustering matters: these lineups come from 300 team-seasons and
share players wholesale, since one starter appears in dozens of rows, and treating them as independent
inflates t from 2.35 to 3.30. Team-season fixed effects matter too, because without them the
coefficient is partly identified by good teams having high-overlap lineups, which is confounded. The
pooled effect barely survives that, sitting right on the 1.96 line. And restricting to lineups that
actually played, the sign flips and the bottom row reaches significance in the direction the
hypothesis predicts.

That bottom row is the one to be most careful with. It's the last cell of a specification curve, it
rests on 177 lineups, and a formal test of heterogeneity, overlap interacted with log chances, comes
back at t = +0.35. The drift across thresholds is within noise. Reading the significant cell as the
answer, having watched five others fail to be, is the exact error a specification curve exists to
prevent. The honest reading is that neither the positive pooled estimate nor the negative
heavily-used estimate is robust.

**What this can and can't rule out.** For the heavily-used lineups the Sixers question actually
concerns (≥800 chances, roughly a starting unit's season), the interval is −0.062 to −0.006 points per
chance, or −7.1% to −0.7% of league-average efficiency. A large redundancy penalty is still excluded:
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
| Usage only | +0.0138 (t=8.60) | — | 0.2523 |
| Creation overlap only | — | +0.0056 (t=1.98) | 0.2349 |
| Both | +0.0140 (t=8.05) | −0.0010 (t=−0.35) | 0.2524 |

Coefficients are points per chance per +1 SD, team-season fixed effects, clustered.

Creation overlap adds nothing. Once usage is in the model its coefficient changes sign and its
t-statistic falls from 1.98 to −0.35, while usage barely moves. R² rises by one ten-thousandth. The
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

**That slope cannot be applied forward as it stands, and this is the subtlest thing in the section.**
The DARKO snapshot is from July 2026, after the season it's regressed on. What 1.433 measures is how
much DARKO shrinks its own within-season estimates, so un-shrinking by it is the right correction for
*reproducing* 2025-26 and the wrong one for *projecting* 2026-27, where a team's rating is only about
59% persistent year to year. Composing the two gives a forward slope near 0.84, and that is what the
projection uses. The composition is an approximation and its error runs in the safe direction, since
DARKO's snapshot is already partly forward-looking. The clean version regresses on a snapshot taken
*before* the season, which needs a back-dated DARKO pull that doesn't exist here.

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
| Minutes as played (injuries repeat) | +1.47 | 44.8 | 32-58 | 2.9% | 11th |
| Health-adjusted (70 games each) | +2.05 | 46.1 | 33-59 | 3.5% | 9th |

**A 45 to 46 win team with roughly a 3% title chance.** Colder than the premise. Three things drive
it. Their 2025-26 base was 18th in the league at −0.31 SRS, so the trade upgrades a middling team
rather than adding to a contender. The upgrade itself is about +2 DPM: LeBron (1.31, age 41) plus
Jaylen Brown (1.78) minus Paul George (1.07), displacing bench minutes rather than replacing bad
starters. And three teams sit a tier above, with New York (+6.2), Oklahoma City (+6.3) and San
Antonio (+5.2) taking half of simulated titles between them.

Availability is the largest single lever. Embiid played 38 games in 2025-26. Projecting every player
to 70 games is worth about half a point of rating and 1.3 wins, and the entire difference between the
two scenarios above is his health and Brown's.

The playoff field is rebuilt inside every one of the 20,000 simulations rather than seeded once from
mean wins. That sounds like a detail and isn't: seeding once makes reaching the playoffs an assumption
instead of an outcome, and in the first version of this projection it left **14 of 30 teams at exactly
0.000** title probability, including a +0.27 team whose 80% interval reached 55 wins. Two teams sit at
zero now.

### How much is model and how much is knowledge

Title odds are acutely sensitive to how uncertain the ratings are, and that parameter isn't
observable:

| Rating uncertainty | Best team's title odds | Philadelphia | Top-3 share |
|---|---|---|---|
| 2.15 (calibration residual, a floor) | 25.3% | 2.9% | 63% |
| 3.95 (year-over-year, used) | 18.9% | 3.7% | 50% |
| 5.00 | 17.0% | 3.8% | 44% |

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
| 0.0 (as modelled) | +2.05 | 9th |
| 0.5 | +1.81 | 9th |
| 1.0 | +1.57 | 11th |
| 2.0 (implausibly steep) | +1.09 | 14th |

The conclusion doesn't depend on it. Even a two-point collapse, far beyond any plausible one-year fall,
leaves Philadelphia a mid-table playoff team rather than moving it toward or away from contention.
Embiid's decline sweeps almost identically.

### What the projection doesn't know

Only the Philadelphia trade is modelled. The other 29 rosters are frozen at their 2025-26 shape, so any
rival's offseason is invisible. And the calibration's DARKO snapshot postdates the season it was scored
against, so its residual is optimistic and its slope needs the forward shrink described above. These
odds describe a league that won't exist on opening night.

The margin scale converting a rating edge into a win probability is 7.5, from fitting SRS on each
season's odd-numbered games and scoring it on the even ones, then correcting for the noise half-season
ratings add. The obvious alternative, fitting on a whole season and scoring on the same season, is
circular: the ratings have already absorbed those outcomes and the scale comes out too small. That
route gave 7.0 here, defended by an argument that turned out to be circular too.

## 13. Two more pre-registered follow-ups: where and to whom

Section 8 says teams differ in how they relax. Section 7 says the league under-relaxes. Both are
single numbers spanning a whole possession, and two obvious refinements follow — *where* in the
possession the difference lives, and *who* the offense routes to when the clock dies.

Registered first, in [`preregistration_situational.md`](preregistration_situational.md), committed
one commit before the analysis module existed. Same protocol as section 10: explore on 2015-16 to
2021-22, confirm once on 2022-23 to 2023-24, leave 2024-25 alone.

| | Hypothesis | Predicted | Explore | Holdout | Verdict |
|---|---|---|---|---|---|
| H4 | Team spread is concentrated late | late > early | 0.46 > 0.23 ✓ | 0.00 < 0.42 ✗ | Failed |
| H5a | Late-clock concentration → efficiency | positive | +0.568, p < 0.001 | +0.841, p < 0.001 | Passes, fails its placebo |
| H5b | Funnelling above own baseline → efficiency | positive | +0.781, p = 0.032 | +1.702, p = 0.045 | Marginal, and the clean one |

### The estimator changed, and that was registered in advance

Section 8's ratio differences the boundary at second 23 against second 1 — two numbers out of
twenty-three. That is why H1 in section 10 could not be evaluated on a holdout at all. H4 instead
fits `BOUNDARY(t)` and `V(t)` by weighted least squares within each band and takes the ratio of
slopes, which uses every second in the band and degrades gracefully when one is thin. The choice
was made for holdout estimability *before* running anything, rather than after discovering the
failure, and the estimator is validated by recovering a known ratio on noiseless synthetic data.

### H4 failed, and the late band failed hard

| Band | Explore signal share | Holdout signal share |
|---|---|---|
| `late` (1–7s) | 0.459 | **0.000** |
| `middle` (8–15s) | 0.577 | 0.165 |
| `early` (16–23s) | 0.229 | 0.418 |

The ordering reversed. On the holdout the late band's observed team spread is 0.1033 against a null
spread of 0.1305 — **teams differ less in late-clock relaxation than random relabelling of
team-games produces.** That is a stronger null than "undetectable".

This is the second time the same mechanism has caught the same failure. On exploration alone H4
clears its permutation null, has a clean mechanism, and would have survived every other check in
this repo. Like H3, it took held-out seasons.

### What did reproduce, as description rather than a test

The league-level band ratios, across five boundary quantiles in each window:

| Band | `V(t)` slope, pts/sec | Ratio, explore | Ratio, holdout |
|---|---|---|---|
| `late` (1–7s) | 0.039–0.043 | 0.11–0.51 (0.35–0.51 excluding q = 0.02) | 0.29–0.41 |
| `middle` (8–15s) | 0.014–0.019 | 0.36–0.94 | 0.26–0.71 |
| `early` (16–23s) | 0.008–0.010 | 0.78–2.75 | 1.27–3.61 |

The `late` band's 0.11 is the q = 0.02 fit on exploration and is the one estimate in the table that
doesn't sit with its neighbours. The 2nd percentile of accepted shot values is the thinnest tail on
offer, so it is where a quantile boundary is least stable; the holdout does not reproduce it (0.31 at
the same quantile). It is left in rather than trimmed.

**Section 7's under-relaxation is a late- and middle-clock phenomenon**, and the early band is not
estimable as a ratio at all. Continuation value above 16 seconds is nearly flat — 0.008 points per
second against 0.039 late — so the ratio there divides by something close to zero and swings from
0.78 to 2.75 across quantiles within one window. An early-band ratio above 1 is arithmetic, not an
offense relaxing quickly. The instability was predicted in the registration, which is why the test
compares signal shares (where it cancels) rather than raw variances; the early band's 0.418 on the
holdout is most likely that same arithmetic.

### H5 passes its registered test and then fails the first real check

Team-season panel, n = 210 exploration and 60 holdout, season fixed effects, standard errors
clustered on team, p-values from a wild cluster bootstrap-t rather than a normal — the general form
of the correction that put section 5's rule-change result at p = 0.119.

The outcome and the control are **disjoint sets of chances by construction**: chances live at second
7 supply the outcome, chances that ended above it supply the control. Controlling on full-season
efficiency instead would put the outcome's own chances on both sides of the regression.

| Specification | Explore | p | Holdout | p |
|---|---|---|---|---|
| `HHI_LATE` → late efficiency (registered) | +0.568 | < 0.001 | +0.841 | < 0.001 |
| `FUNNEL` → late efficiency (registered) | +0.781 | 0.032 | +1.702 | 0.045 |
| `HHI_LATE` → **early** efficiency (post hoc placebo) | +0.491 | < 0.001 | +0.274 | 0.326 |
| `FUNNEL` → **early** efficiency (post hoc placebo) | −0.750 | 0.096 | −1.518 | 0.084 |

Both registered specifications confirm under the pre-registered rule. That is the first confirmation
across five registered hypotheses in this project.

The placebo is **post hoc** and is labelled as such everywhere it appears, including the `spec`
column of the CSV. It asks the question a confirmation of this shape has to survive: if this is a
*late-clock* effect, concentration must not predict efficiency on the chances that ended before the
late clock. Because those chances are already a disjoint sample, the test costs nothing — swap the
outcome and the control.

**`HHI_LATE` fails it.** On exploration it predicts early-clock efficiency at +0.0072 points per
chance per SD against +0.0084 late: essentially the same effect where the mechanism does not apply.
The registered test passed and the interpretation did not. Raw late-clock concentration is
substantially a proxy for something general about the offense, and the disjoint control did not
remove it.

**`FUNNEL` — how much more concentrated a team gets when the clock dies, relative to its own
baseline — passes it in the sharpest way available.** Positive on late-clock efficiency, negative on
early-clock efficiency, consistent signs in both windows. A general quality proxy cannot produce
that pattern. It is also the specification with the weaker p-values, and those two facts belong in
the same sentence.

### The size of it

A team-season averages about 2,230 chances reaching the late clock. One SD of `FUNNEL` is worth
+0.0059 to +0.0105 points per late chance, or **13 to 23 points across a season — 0.16 to 0.29
points per game.** `HHI_LATE` runs 0.23 to 0.37 points per game and the placebo says most of that
isn't about the late clock.

So: funnelling the late clock beyond your own baseline is worth something, it is worth well under
half a point per game, and it is measured to about a factor of two. It is a real effect and not a
lever.

Reproduce: `make situational` (and `WINDOW=holdout` for the confirmation);
`reports/situational_band_signal_*.csv`, `reports/situational_concentration_*.csv`.

## 14. What a miss is worth, and what finding 7 was missing

Everything in section 7 compares a shot's `XPTS` against `V(t)`. Both sides omit the same thing:
an offensive rebound ends a *chance* but not a *possession*, so the points a team goes on to
score after rebounding its own miss were credited to a different row and counted on neither side.

That would be harmless if the rebound probability were constant. It is not.

| | Conditional on a miss | Unconditional retention |
|---|---|---|
| Restricted Area | **40.1%** | 14.0% |
| In The Paint (non-RA) | 32.6% | **18.6%** |
| Right Corner 3 | 24.8% | 15.1% |
| Above the Break 3 | 23.3% | 15.0% |
| Mid-Range | **22.1%** | **13.0%** |

The two columns rank shots differently and both are needed. Rim misses come back most often, but
rim shots mostly go in, so a rim attempt is the *least* likely to leave you holding the ball. The
second column is what valuation needs.

**The correction concentrates exactly where finding 7 is anchored.** Retention runs **23.2% at
0–3 seconds** on the shot clock against about 14% mid-clock, because late shots miss more *and*
come back more when they do.

Pricing the option on both sides — a shot is worth `XPTS + P(retain) × V(second chance)`, and
`V(t)` is rebuilt on points to the end of the *possession* rather than the chance:

| | Published | Re-priced |
|---|---|---|
| Value drop, 23s → 1s | 0.448 | 0.386 |
| Relaxation ratio | 0.366 – 0.543 | **0.258 – 0.443** |

**Finding 7 was understated.** Offenses relax their standard even less, relative to the value
they are giving up, than the published number says.

Two validation notes. The rebound side is read from which description column an event was logged
in rather than from a team-id join, which keeps the 15.6% of rebounds credited to a team rather
than a player — a ball knocked out off the defence is a retained possession, and a team-id join
drops exactly those. And the player-rebound rate off missed field goals comes to 25.5% against a
published league figure near 24%; **a 1.6pp gap remains and is not explained here.** It is small
next to the 17pp spread across zones the valuation rests on, but it is a level disagreement.

Reproduce: `make rebound`; `reports/rebound_*.csv`.

### What a second chance is worth

The raw numbers say an offensive-rebound chance (0.845) beats a fresh possession (0.771). That
gap is composition: second chances start at 15.4 seconds and fresh ones at 23.9.

Held at the same start clock it vanishes. **Before 2018-19 an offensive rebound reset to 24
exactly as a defensive one did**, so that era needs no adjustment and is the clean test:
**+0.0011 points**, on 80,086 against 246,187 chances. The scrambled-defence premium is zero.

Within the post-rule era the value of a second chance is flat from 14 to 18 seconds (1.006,
1.003, 1.013, 1.007, 1.001) and falls only above 19, where the sample becomes rebounds off very
early shots. Neither slope is causal — start clock is set by when the rebound arrived, which is
set by what shot preceded it — so this says what second chances with `s` seconds are worth, not
what one more second would be worth to a given one. Nothing here is claimed from a pre/post
comparison, for the reason section 5 was withdrawn.

## 15. The 2-for-1: teams do it, and it is close to free

Registered in [`preregistration_twoforone.md`](preregistration_twoforone.md) before the module
existed. Unit is a possession, n = 101,130, and treatment is not chosen by the team: when you
gain the ball at the end of a period is set by the opponent's previous possession.

**They do it, and it is obvious.** Mean game seconds used, by when the ball was gained:

| Ball gained at | 26s | 30s | 34s | 38s | 42s | 45s |
|---|---|---|---|---|---|---|
| Clock used | 14.6 | 13.3 | 10.7 | **9.2** | 10.0 | 10.7 |

Offenses burn 14.6 seconds with no second trip available, speed up to 9.2 as the window opens,
and slow down again past 40 seconds when they no longer need to hurry. The difference across the
registered threshold is −3.70 seconds on exploration and −3.60 on the holdout.

The held-out seasons trace the same curve almost exactly — 14.1, 13.8, 10.9, **9.1**, 10.0, 10.8
against the 14.6, 13.3, 10.7, **9.2**, 10.0, 10.7 above. Two disjoint sets of seasons, no fitting
between them.

**It is worth nothing measurable.** Net points to the end of the period, trend-adjusted, jumps
+0.009 (t = 0.24) on exploration and +0.044 (t = 0.68) held out. Pooled, the effect is bounded to
about **−0.06 to +0.17 points** per opportunity, on roughly five opportunities a game across both
teams.

**And the ledger balances.** Teams running a 2-for-1 stop about 3.5 seconds earlier on the shot
clock and give up **0.06 to 0.07 points** of continuation value. With an all-in net near zero,
the extra possession must be worth about that same 0.07 to 0.11. The 2-for-1 is a fair trade —
offenses are neither being fooled nor finding free points. The cost side of that ledger has not
been measurable before, because it needs a per-shot clock.

Two honest notes on the design. The registered estimator was a regression discontinuity, and
**the behaviour turns out to be smooth rather than sharp** — teams start hurrying gradually from
about 34 seconds, so there is no corner at 32 for an RD to find, and the local estimates wander
across the threshold sweep while the raw comparison and the profile are overwhelming. And the
registered decision rule for the value test was sign stability alone; the sign did hold, but two
insignificant estimates are not a confirmation, and that hole in the protocol is named in the
registration rather than used.

Reproduce: `make twoforone` (and `WINDOW=holdout`); `reports/twoforone_*.csv`.

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

### Four limitations that don't have a fix here

These are design problems rather than defects, and none of them has a patch. They're the sharpest
objections I know of to the results above, and where they cut is stated rather than hedged.

**`V(t)` is adversely selected, and the bias lands on the shape.** `V(t)` averages the outcomes of
chances that *declined* to shoot at `t`, and that group gets worse as the clock falls: 94% of live
chances continue past 17 seconds, only 48% past 1. So `V(t)` is biased down, increasingly so late,
which makes it fall faster than the true option value and pushes the relaxation ratio below 1 on its
own. This is the selection argument from section 2 applied to section 7's own estimator, and it lands
on the shape, which is the only thing section 7 claims is identified. Fixing it means changing what
`V(t)` is, not correcting a calculation. Until that's done, read 0.54-0.70 as an upper bound on how
far offenses actually fall short rather than a point estimate.

Relatedly, the synthetic check in `tests/test_stopping.py` hands the estimator a hand-written value
function and never calls `continuation_value`. It shows the ratio arithmetic returns 1 when given a
correct `V(t)`; it can't detect bias in `V(t)` itself. Section 7 says the measured 0.5 is a deviation
rather than a property of the method, and that claim is broader than the tests support.

**`V(t)` omits offensive-rebound continuation.** A chance ending in a missed shot the offense rebounds
scores 0 on field-goal points, but the *possession* continues and has real value. Off-rebound chances
are 10.2% of the panel. The free-throw omission above is quantified and signed at +0.084; this larger
one isn't, and folding it in would change what a chance's value means rather than correct a number.

**Creation overlap is entangled with its own outcome.** Overlap is a similarity between two players'
distributions over (shot-clock bucket × zone), measured in the same season as the efficiency it
predicts. Players who both concentrate early in the clock score high similarity, and early-clock
chances are more efficient by section 2, so a positive coefficient is what the construction produces
before any redundancy story. Team-season fixed effects don't break that channel. Separately, the
Jensen-Shannon divergence is biased upward on finite samples by roughly (cells−1)/(2n ln 2), which
with 18 cells and a 150-attempt floor varies across the sample and correlates with usage; the Laplace
smoothing pushes the same way. Neither is corrected. This is why the one significant team-season
specification in section 11 having a *positive* sign is evidence about the construction, not about
basketball.

**The uncorrected off-rebound timing residual sits on the treated arm.** METHODOLOGY §3 records a
+2.0s residual on `off_rebound` chances and attributes it to airballs, which get no 14-second reset in
reality because the rule requires rim contact and the feed doesn't record it. `off_rebound` is the
treated group in the rule-change experiment, whose outcome is a game-clock difference and whose
estimate is 0.202s. The residual and the estimate are the same order of magnitude. Bounding it needs a
model of rim contact, which isn't available here.
