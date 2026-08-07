# Pre-registered: does the 2-for-1 pay?

Written 6 August 2026, before `src/possval/models/twoforone.py` existed and committed before
the first line of it, so the ordering is checkable against `git log`.

## Why this one

Every previous hypothesis in this project compared team attributes and either failed or came
back too small to matter. The diagnosis in `preregistration_situational.md` was structural: a
question phrased as "which teams do X" collapses 2.9M chances into 30 numbers, and no amount of
clever splitting fixes a sample of 30.

This question is different in the one way that matters. **The unit is a possession, there are
101,130 of them, and the treatment is not chosen by the team.** When an offense gains the ball
at the end of a period is decided by when the *opponent's* previous possession ended. Whether a
2-for-1 is even available is therefore close to exogenous, which is the identification every
earlier hypothesis here lacked.

It is also the question this repo is uniquely equipped for. The benefit side of a 2-for-1 — an
extra possession — is public folklore. The **cost** side is forgone continuation value: shooting
at second 17 of the shot clock instead of second 8 gives up `V(17) − V(8)`. Nobody outside the
league can price that, because pricing it needs a per-shot clock.

## Protocol

Same as the two previous exploration files.

1. **Explore on 2015-16 → 2021-22.**
2. **Confirm once on 2022-23 → 2023-24**, untouched until the code is frozen.
3. **2024-25 is not used.** It is the xPTS test season.
4. **Everything tried is reported**, including failures.
5. Any test not listed here, run later, is labelled **post hoc** wherever it appears.

## Definitions, all fixed now

- **Window.** A chance where the offense gains the ball with `PREV_GC` between 24 and 45
  seconds left in a period, periods 1–4 only. Overtime is 5 minutes and its end-of-period
  dynamics differ; it is excluded rather than pooled.
- **Feasibility threshold.** A 2-for-1 requires shooting early enough that the opponent cannot
  run out the clock. The opponent can use 24 seconds, and running any deliberate play takes
  roughly 8, so the threshold is fixed at **`PREV_GC` ≥ 32** on mechanics, not on the data.
  Registered sensitivity: the whole sweep from 28 to 36 is reported, not the best cell.
- **Clock used.** `PREV_GC − LAST_GC`, game seconds from gaining the ball to the chance ending.
- **Outcome.** **Net points to the end of the period**: points scored by the team in possession,
  minus points scored by the opponent, over every chance from this one to the buzzer. This is
  the right outcome because a 2-for-1 trades shot quality for possession count, and only a net
  measure prices both.

## H6a, teams do shoot faster when a 2-for-1 is available

*The behavioural precondition. If this fails, H6b is not worth interpreting.*

- **Prediction:** mean clock used is **lower** just above the feasibility threshold than just
  below it.
- **Test:** difference in mean clock used across the threshold, standard errors clustered on
  game, plus the full curve of clock used against `PREV_GC` in one-second bins.
- **Decision rule:** confirmed if the sign holds on exploration **and** the holdout.

## H6b, and it is worth net points

- **Prediction:** net points to end of period is **higher** just above the threshold. This is
  the reduced form — treatment is *feasibility*, set by the opponent, not the team's choice to
  take it. That is deliberate: conditioning on teams that actually went fast would put the
  choice back into the estimate.
- **Test:** difference in mean net points across the threshold, clustered on game.
- **Direction:** predicted positive, but registered **two-sided**. A negative result — teams
  capture the extra possession and lose more in shot quality than they gain — is a real and
  publishable answer, and pretending otherwise after the fact would be dishonest.
- **Decision rule:** sign stable across exploration and holdout. A flip is a failure.

- **Stated confound, in advance.** Net points to end of period is mechanically increasing in
  `PREV_GC` — more time left means more scoring by *someone*, and possession parity makes it
  sawtooth rather than smooth. The threshold comparison is only meaningful against that trend,
  so a **local linear fit on each side** is registered alongside the raw difference, and both
  are reported whatever they show.

## H6c, the cost side, descriptive

Not a hypothesis test. For window chances that shot early, the forgone continuation value
`V(t_shot) − V(t_typical)` is priced from the existing curve and reported as a magnitude. It is
registered here so that it cannot later be presented as a test it was never set up to be.

## What would make me drop this

- The behavioural precondition (H6a) fails, in which case there is no 2-for-1 to price.
- The result exists only at one threshold in the 28–36 sweep.
- The sign flips between exploration and holdout.

## What this cannot do

`PREV_GC` is quasi-random, not random. A team that just forced a quick turnover gets the ball
earlier *and* has momentum, better defence, or a worse opponent. The threshold comparison
narrows that but does not eliminate it, and this is a reduced-form discontinuity rather than a
controlled experiment.

Net points to end of period also ignores everything after the buzzer. A possession surrendered
at the end of the first quarter has consequences in the second that this outcome cannot see.

---

# Results

**Run 6 August 2026.** Exploration first, code committed unchanged, then the holdout once.

## Scoreboard

| | Hypothesis | Predicted | Explore | Holdout | Verdict |
|---|---|---|---|---|---|
| **H6a** | Teams shoot faster when a 2-for-1 is available | lower clock used | −3.70s | −3.60s | **Confirmed, emphatically** |
| **H6b** | And it is worth net points | two-sided | +0.009 (t = 0.24) | +0.044 (t = 0.68) | **Precise null** |
| **H6c** | Cost of the early shot | descriptive | 0.062 pts | 0.073 pts | measured |

**Teams run the 2-for-1, unmistakably. It is worth approximately nothing.**

## H6a, confirmed, and it is not subtle

Mean clock used, against when the offense gained the ball (exploration window):

| Ball gained at | 26s | 30s | 34s | 38s | 42s | 45s |
|---|---|---|---|---|---|---|
| Clock used | 14.6 | 13.3 | 10.7 | **9.2** | 10.0 | 10.7 |

That is the 2-for-1 in one row. Offenses burn 14.6 seconds when there is no second trip to be
had, speed up to 9.2 as the window opens, and **slow down again past 40 seconds** when they no
longer need to hurry to get the ball back. The raw difference across the registered threshold is
**−3.70 seconds** on exploration and **−3.60** on the holdout, on ~8,300 and ~2,500 games.

### The registered estimator was the wrong one, and the profile says so

The local linear fit at the threshold gives −0.59s (t = −3.9) on exploration and −0.52s
(t = −1.8) on the holdout — same sign, so H6a passes as registered, but far weaker than the raw
comparison. The threshold sweep explains why. On the holdout the local estimates run −0.28,
+0.27, +0.20, −0.33, −0.52, −1.28, −1.28, −0.82, −0.47 across thresholds 28 to 36, flipping sign
twice.

**The behaviour is smooth, not a discontinuity.** Teams treat the end of a period as a
continuum and start hurrying gradually from about 34 seconds, so there is no sharp jump at 32
for a regression discontinuity to find. The design was registered on the assumption of a knife
edge and the assumption was wrong. The evidence for H6a is the profile and the raw difference,
both overwhelming; the local estimate is noisy because it is looking for a corner that is not
there. That is recorded here rather than quietly swapped for the estimator that worked.

## H6b, a precise null, and my decision rule was not good enough

Net points to the end of the period, jump at the registered threshold, trend-adjusted:

| | Estimate | Std error | t |
|---|---|---|---|
| Exploration | +0.0088 | 0.0362 | 0.24 |
| Holdout | +0.0439 | 0.0646 | 0.68 |

**The registered decision rule was sign stability, two-sided. The sign held. That does not make
this a confirmation, and reporting it as one would be exploiting a hole in my own protocol.**

A sign-stability rule cannot distinguish "no effect" from "an effect too small to see", and with
a true value near zero the sign holds or flips at random. The rule should have required
significance as well. It did not, so the loophole is named here and not used.

What the numbers do support is stronger than a shrug: this is a **precise** null, not an
indeterminate one. Pooling the two windows the effect is bounded to roughly **−0.06 to +0.17
points per opportunity**. About five such possessions occur per game across both teams, so even
the top of that interval is well under a point of scoring per game.

## H6c, where the points went

The mechanism, and the part that needs a shot clock:

| | Explore | Holdout |
|---|---|---|
| Shot-clock second the chance ended, above threshold | 14.24 | 13.87 |
| Below threshold | 10.96 | 10.40 |
| **Forgone continuation value** | **0.062** | **0.073** |

Teams running a 2-for-1 stop about 3.5 seconds earlier on the shot clock and hand back **0.06 to
0.07 points** of continuation value to do it. Since the all-in net effect is +0.01 to +0.04, the
extra possession must be worth roughly 0.07 to 0.11 — **almost exactly what the degraded shot
costs.**

That is the answer, and it is a satisfying one: the 2-for-1 is close to a fair trade. Offenses
are not being fooled, and they are not finding free points either. Both sides of the ledger are
now measured, and the cost side has not been measurable before because it needs a per-shot clock.

## Deviations from the protocol

1. **None in what was run.** Both hypotheses, both estimators, the full 28–36 sweep and the
   descriptive cost were run on both windows and all are reported.
2. **One design error is recorded rather than corrected**: the regression discontinuity assumes
   a sharp threshold and the behaviour is gradual. The registered estimator is still reported at
   the registered threshold; the profile is presented as the better evidence, and it was
   registered too ("the full curve of clock used against `PREV_GC` in one-second bins").
3. **The H6b decision rule was too weak** and is described above rather than reinterpreted.

## What this cannot do

`PREV_GC` is quasi-random, not random, and the reduced form compares feasibility rather than the
decision. Net points to the buzzer also ignores everything after it: a possession given up at
the end of the first quarter has second-quarter consequences this outcome cannot see.
