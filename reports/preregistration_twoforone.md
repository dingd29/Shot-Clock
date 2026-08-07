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

*Not yet run. Filled in one pass against the protocol above.*
