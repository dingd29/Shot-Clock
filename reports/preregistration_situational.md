# Pre-registered exploration: where situationally does an offense decide badly?

Written 4 August 2026, before the analysis module existed and committed before the first line
of it was written, so the timestamp is checkable against `git log`.

## Why this file exists

The headline result is that offenses lower their shot standard at only 37–54% of the rate the
collapse in continuation value calls for. That is a single number for the whole league over a
whole possession. Two obvious refinements follow — *when* in the possession does a team's
process actually break, and *who* does the offense route to when it breaks — and each of them
can be cut a hundred ways.

The cutting is the danger. `SHOT_CLOCK` × `START_TYPE` × `MARGIN` × team × season is several
hundred cells over 2.9M chances, and at that width something always clears p < 0.05. This
project has already produced three results that looked real and were not, one of which
(`H3` in [`preregistration_exploration.md`](preregistration_exploration.md)) cleared its own
permutation null on exploration and came back at +0.001 held out.

So the tests are fixed here first, with the same protocol as before.

## Protocol

Identical to the first exploration, deliberately, so the two are readable side by side.

1. **Explore on 2015-16 → 2021-22.** Seven seasons, 210 team-seasons.
2. **Confirm once on 2022-23 → 2023-24.** Held out, untouched until both hypotheses below are
   finalised and their code is frozen.
3. **2024-25 is not used.** It is the test season for the xPTS model and the projection layer.
4. **Everything tried is reported**, including failures and anything abandoned mid-flight. A
   test listed here that goes unreported is a protocol violation.
5. Any test not on this list, run later, is labelled **post hoc** wherever it appears.

One addition to the protocol, learned from H1 last time. H1 could not be evaluated on the
holdout at all, because the relaxation ratio was anchored on two individual seconds and two
seasons split thirty ways left some teams with no shots at all at 23 seconds. **Anything
registered here must be estimable on two seasons, and that constraint drives the estimator
choice in H4 rather than being discovered after the fact.**

## H4, the team spread in relaxation is concentrated in the late clock

*Where in the possession does the difference between offenses actually live?*

`team_relaxation` currently returns one ratio per team, computed by differencing the boundary
at second 23 against second 1. That single number averages over a whole possession and cannot
say whether a team is fine early and impatient late, or uniformly impatient. It is also the
fragile estimator described above.

- **Estimator change, registered in advance and applied at league level too.** Within a band
  of the clock, fit `BOUNDARY(t)` on `t` by weighted least squares (weights = shots at that
  second) and `V_CONT(t)` on `t` the same way (weights = chances continued at that second).
  The band relaxation is the ratio of the two slopes. This uses every second in the band
  rather than two endpoints, which is what makes a two-season holdout estimable. The estimator
  is validated by recovering a known ratio on synthetic data before it touches real shots.

- **Bands, fixed now:** `late` = 1–7, `middle` = 8–15, `early` = 16–23. Second 0 is excluded
  (violations and heaves) and second 24 is excluded (the reset instant, already excluded in
  `exercise_boundary` for documented reasons).

- **Prediction:** the **share of team-to-team variance that is signal rather than noise is
  higher in the `late` band than in the `early` band.** Early in a possession every offense has
  time and the decision does not bind, so teams should look alike. The decision only bites when
  the clock is dying, so genuine differences in process should surface there.

- **Unit:** chance and shot, grouped by team, pooled over the window.

- **Test:** for each band, observed variance of the team ratios against a **permutation null**
  that relabels whole team-games with one shared mapping across both frames — the same
  machinery that showed two thirds of the single-number team spread was noise. Signal share is
  `max(observed_var − null_var, 0) / observed_var`.

- **Decision rule:** confirmed only if `signal_share(late) > signal_share(early)` on
  exploration **and** the ordering reproduces on the holdout. A flip between the two is a
  failure, not a subgroup.

- **Stated power problem.** Each team-band ratio is a two-stage quantity fitted on a thirtieth
  of the data, and the pooled version was already two-thirds noise. Splitting three ways can
  only make each cell thinner. It is entirely possible that **all three** bands come back at
  near-zero signal share, in which case the honest report is that this question cannot be
  answered at this sample size — not that teams are identical.

- **What would make me drop it:** if the null variance exceeds the observed variance in every
  band, the comparison of signal shares is between two zeros and means nothing. That is
  reported as *not estimable*, the same verdict H1 got, rather than dressed up as a null result.

## H5, concentrating the late clock in one creator pays

*The Sixers question, asked of 300 team-seasons instead of one roster.*

When the clock is dying the offense has to route the ball somewhere. Two philosophies: funnel
it to the best creator, or keep it moving. This asks which one scores.

- **Treatment:** `HHI_LATE`, the Herfindahl index over players' shares of their team's
  late-clock (≤ 7s) field-goal attempts in a season. 1.0 is one player taking everything;
  0.1 is ten players sharing evenly.

- **Outcome:** points per chance on chances that **reached** the late clock — live at second 7,
  meaning `START_SC ≥ 7` and `END_SC ≤ 7`, the same liveness definition `continuation_value`
  uses.

- **Control:** points per chance on chances that **ended above** second 7. This is registered
  as the control specifically because it is a **disjoint sample** from the outcome. Using
  full-season efficiency would put the outcome's own chances on both sides of the regression
  and induce a mechanical correlation. Season fixed effects absorb league-wide scoring drift.

- **Unit:** team-season. n = 210 on exploration, 60 on holdout.

- **Test:** OLS with season dummies, standard errors clustered on **team** (30 clusters), and
  the coefficient's p-value from a **wild cluster bootstrap-t** rather than a normal reference.
  30 clusters is not obviously enough for the asymptotic clustered SE, and this project already
  had one headline result die when that assumption was checked properly.

- **Direction.** My prediction is **positive** — late-clock possessions are broken possessions,
  and a known creator with the ball beats five players improvising. But the counter-story is
  real (a predictable late-clock target is a guardable one), so the **test is two-sided** and
  the prediction is recorded only so it can be scored. A sign flip between exploration and
  holdout is a failure either way.

- **Secondary specification, registered now rather than added later:** `FUNNEL = HHI_LATE −
  HHI_ALL`, how much *more* concentrated a team gets when the clock dies, relative to its own
  baseline. This is the cleaner playstyle signature — it differences out simply having one
  dominant scorer — and it is reported whatever it shows.

- **Stated confounds, in advance:**
  - HHI is partly roster construction, not coaching. A team whose star misses 40 games has a
    lower HHI for reasons that have nothing to do with late-clock philosophy.
  - HHI correlates with having a good player, which correlates with scoring well. The disjoint
    control absorbs some of that and certainly not all of it.
  - This is a **correlation between two team attributes** and will be reported as one. Nothing
    here identifies a causal effect of concentrating the late clock.

## What would make me drop a hypothesis

Recorded now so it cannot be rationalised later. Same list as last time, because the failure
modes have not changed:

- The measure turns out to be a restatement of something else — the way per-player exercise
  surplus turned out to be late-clock shot quality renamed, at correlation 0.984.
- The effect exists only under one arbitrary parameter choice: one band cut, one late-clock
  threshold, one HHI minimum.
- The sign flips between exploration and holdout.

## What this cannot do

Neither hypothesis establishes causation. Both are correlations between team attributes,
measured on realised behaviour, and a team's realised behaviour reflects its coach, its roster,
its opponents and its injuries jointly. The instrument that would fix this — knowing which shot
was available and declined — does not exist in any public feed, and that is the same ceiling
that caps the headline relaxation result itself.

H4 additionally inherits every caveat on the boundary: it is estimated from accepted shots
only, the *level* of the boundary is not identified (the quantile choice flips the sign of "too
aggressive" versus "too patient"), and only the **shape** is claimed.

---

# Results

**Run 4 August 2026**, against the protocol above. Both registered tests were run on
exploration, the code was committed unchanged, and the holdout was then run once. One post hoc
addition is recorded and labelled below.

## Scoreboard

| | Hypothesis | Predicted | Explore | Holdout | Verdict |
|---|---|---|---|---|---|
| **H4** | Team spread is concentrated late | late > early | 0.46 > 0.23 ✓ | 0.00 < 0.42 ✗ | **Failed** |
| **H5a** | `HHI_LATE` → late efficiency | positive | +0.568, p < 0.001 | +0.841, p < 0.001 | **Passes the rule, fails the placebo** |
| **H5b** | `FUNNEL` → late efficiency | positive | +0.781, p = 0.032 | +1.702, p = 0.045 | **Marginal, and the only clean one** |

## H4, failed, and it failed in the direction that matters

The prediction was that team-to-team differences in relaxation live in the late clock, where
the decision actually binds, and not early, where every offense has time.

| Band | Explore signal share | Holdout signal share |
|---|---|---|
| `late` (1–7s) | **0.459** | **0.000** |
| `middle` (8–15s) | 0.577 | 0.165 |
| `early` (16–23s) | 0.229 | 0.418 |

On exploration the prediction held and the middle band, which was not predicted at all, was the
strongest. On the holdout the ordering **reversed completely**. The pre-registered rule was
that the ordering had to reproduce; it did not, so H4 fails.

The late band's holdout number is worth stating exactly rather than as a rounded zero: observed
team spread was 0.1033 against a null spread of 0.1305. **Teams differ less in their late-clock
relaxation than random relabelling of team-games produces.** That is what a signal share of
zero means here, and it is a stronger null than "we could not detect anything".

*This is the same failure mode as H3 in the first exploration, and it is the second time it has
been caught by the same mechanism.* On exploration alone, H4 would have been written up as a
finding — 0.46 against 0.23 clears its own permutation null, has a ready mechanism, and would
have survived every check applied elsewhere in this repo. It took a held-out sample to kill it.

### The by-product, which did reproduce

`H4a` — the league-level band ratios, registered as part of the estimator and computed
unconditionally — is descriptive rather than a hypothesis test, and it is stable across both
windows at every boundary quantile:

| Band | Value slope (pts/sec) | Relaxation ratio, explore | Relaxation ratio, holdout |
|---|---|---|---|
| `late` (1–7s) | 0.039–0.043 | 0.11–0.51 (0.35–0.51 excluding q = 0.02) | 0.29–0.41 |
| `middle` (8–15s) | 0.014–0.019 | 0.36–0.94 | 0.26–0.71 |
| `early` (16–23s) | 0.008–0.010 | 0.78–2.75 | 1.27–3.61 |

Two things follow, and neither is a claim about teams.

**The headline under-relaxation is a late- and middle-clock phenomenon.** The ratio sits in the
0.3–0.7 range in both bands and both windows, consistent with the pooled 0.37–0.54. The one
straggler is the `late` band at q = 0.02 on exploration, which comes in at 0.11 and does not
reproduce (0.31 at the same quantile on the holdout). The 2nd percentile of accepted shot values
is the thinnest tail available, so it is where a quantile-defined boundary is least stable. It is
reported rather than trimmed.

**The early band is not estimable and should not be reported as a ratio at all.** Continuation
value is nearly flat above 16 seconds — a slope of 0.008 points per second against 0.039 late,
roughly five times flatter — so the ratio is a quotient with a denominator near zero. It swings
from 0.78 to 2.75 across boundary quantiles *within the same window*. A ratio above 1 there is
arithmetic, not an offense relaxing faster than it should. This is exactly the instability the
pre-registration flagged in advance as the reason to compare signal shares rather than raw
variances, and it is very likely what the early band's 0.418 "signal share" on the holdout
actually is.

## H5, the registered test passes and the post hoc placebo is the interesting part

Team-season panel, n = 210 exploration and 60 holdout, 30 team clusters, season fixed effects,
p-values from a wild cluster bootstrap-t.

| Specification | Explore estimate | p | Holdout estimate | p |
|---|---|---|---|---|
| `HHI_LATE` → `PPC_LATE` (registered) | +0.568 | < 0.001 | +0.841 | < 0.001 |
| `FUNNEL` → `PPC_LATE` (registered) | +0.781 | 0.032 | +1.702 | 0.045 |
| `HHI_LATE` → `PPC_EARLY` (**post hoc placebo**) | +0.491 | < 0.001 | +0.274 | 0.326 |
| `FUNNEL` → `PPC_EARLY` (**post hoc placebo**) | −0.750 | 0.096 | −1.518 | 0.084 |

By the pre-registered decision rule — sign stable across windows, two-sided — **both registered
specifications confirm.** That is the first confirmation this project's exploration protocol has
produced across five registered hypotheses.

### The placebo, and why it was run

The placebo is **post hoc**. It was written after H5 confirmed, and it is reported here because
the protocol requires that anything run later be labelled, not because it helped.

It asks the only question a confirmation of this shape has to survive. If concentrating the late
clock is a *late-clock* effect, then concentration must not predict efficiency on the chances
that ended *before* the late clock. Those chances are a disjoint sample by construction, so the
test is available for free: swap the outcome and the control.

**`HHI_LATE` fails it.** On exploration, concentration predicts early-clock efficiency at
+0.0072 points per chance per standard deviation, against +0.0084 on late-clock efficiency —
essentially the same effect, in a part of the possession where the mechanism does not apply. It
does not replicate on the holdout (p = 0.33), which is inconsistent rather than reassuring. The
registered test passed; **the interpretation does not hold.** `HHI_LATE` is substantially a
proxy for something about the offense in general, and the disjoint control did not remove it.

**`FUNNEL` passes it, and passes it in the sharpest possible way.** How much *more* concentrated
a team gets when the clock dies, relative to its own baseline, is **positive on late-clock
efficiency and negative on early-clock efficiency**, with consistent signs in both windows. A
general quality proxy cannot do that. This is the specification with the weaker p-values
(0.032 and 0.045, either of which a sceptic can dismiss at 30 clusters) and it is the one worth
believing.

### The size of it

Both effects are small, and the honest unit is points per game rather than points per chance.

A team-season averages about 2,230 chances that reach the late clock. One standard deviation of
`FUNNEL` is worth +0.0059 to +0.0105 points per late chance, or **13 to 23 points across a
season — 0.16 to 0.29 points per game.** `HHI_LATE` runs a little larger at 0.23 to 0.37 points
per game, and the placebo says most of that is not about the late clock.

So the defensible statement is: **funnelling the late clock more than your own baseline is worth
something, it is worth well under half a point per game, and it is measured to about a factor of
two.** Anyone reading this as a lever to pull has read it wrong.

## Deviations from the protocol

1. **The placebo specifications are post hoc**, added after H5 confirmed on both windows. They
   are labelled as such in the output table, in the CSV's `spec` column, and everywhere the
   result is quoted. They weaken the finding rather than strengthen it, which is the direction
   post hoc analysis is least likely to be self-serving in, but the label stands regardless.
2. **`H4a` is descriptive, not a hypothesis test.** It was registered as part of the estimator
   ("applied at league level too") and is computed unconditionally, so it is not a result
   selected after the fact. It is reported as description and no significance is attached to it.

Nothing else was added, dropped, or re-specified. Both registered tests were run on both windows
and both are reported.

## What this bought

Five registered hypotheses across two exploration files now. Four failed or came back marginal,
one passed its registered test and then failed the first serious check applied to it.

The thing worth keeping is the pair of near-misses. H4 cleared its permutation null on
exploration at 0.46 against 0.23, with a clean mechanism, and reversed on held-out data. H5's
`HHI_LATE` cleared a wild cluster bootstrap at p < 0.001 in *both* windows and still does not
mean what it appears to mean. Neither would have been caught by significance testing, more
data, or better standard errors. One needed a holdout and the other needed a placebo, and both
of those had to be decided on before the number came back.
