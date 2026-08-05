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

*Not yet run. This section is empty by design and will be filled in one pass against the
protocol above.*
