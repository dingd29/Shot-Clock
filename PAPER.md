# The NBA's 2-for-1 is a fair trade, not free points

## Abstract

NBA teams routinely hurry late in quarters to manufacture an extra possession. The extra trip is
easy to see; the shot quality sacrificed to create it is not. I reconstruct a continuous shot
clock for 2,018,360 NBA shots from 2015-16 through 2024-25, validate it against independent NBA
shot-clock splits, and estimate the possession value an offense gives up when it shoots early.
Teams use 3.60 fewer seconds when a 2-for-1 is feasible in a held-out 2022-24 sample and surrender
0.0726 points of continuation value. The estimated net effect is +0.030 points per opportunity
(SE 0.064), indistinguishable from zero. A separate end-period analysis finds a value sawtooth of
only 0.035–0.041 points, roughly one-twelfth of a rigid alternating-possession benchmark. The
mechanism is duration variance: actual possessions do not arrive at a fixed cadence, so the
theoretical handover advantage blurs. A secondary application builds persistent team continuation
profiles, but a preregistered validation sprint does not license prescriptive coaching claims.

## 1. The missing cost of an extra possession

The standard 2-for-1 argument treats the second possession as a free benefit. It is not. To get the
ball back, the first offense usually ends its current chance earlier than it otherwise would. The
decision trades the expected value of a more developed action for the probability of another trip.
Public shot data cannot price that cost because it does not report a continuous shot clock.

This project supplies the missing measurement. Play-by-play records the game clock and each event
that resets possession or the shot clock. A deterministic state machine walks every period,
applies the 24- and 14-second rules, handles offensive rebounds and dead-ball bookkeeping, and
marks cases where a reset would have to be invented as missing rather than silently assigning 24.
The resulting clock is usable for 96.0% of shots. Against NBA's independent 2024-25 player-by-clock-
bucket splits, reconstructed FGA per game has R² 0.973.

## 2. Valuing the option to continue

At each remaining second, `V(t)` estimates the value of keeping the possession alive. It is a
possession-level quantity: points after an offensive rebound remain attached to the original
possession. Taken-shot value combines expected field-goal points with the option value of an
offensive rebound. The difference between `V(t)` and the value of the accepted shot is informative,
but not automatically causal, because the model sees taken shots and never observes passed-up
looks.

The 2-for-1 design avoids making that individual counterfactual the headline. It examines chances
that begin with 24–45 seconds left in regulation periods and fixes 32 seconds as the mechanical
feasibility threshold: 24 seconds for the opponent plus roughly eight seconds to run another play.
The design was developed on 2015-22 and run once on a 2022-24 holdout. Its outcome is net points to
the buzzer, which prices both the degraded first attempt and any additional possession.

## 3. Teams unmistakably hurry

When the extra trip becomes available, teams finish the first chance 3.70 seconds faster in the
development window and 3.60 seconds faster in holdout. The response is smooth rather than a sharp
regression discontinuity: offenses begin hurrying around 34 seconds and relax again beyond 40,
when there is enough time to get the ball back without rushing as aggressively.

That shape matters methodologically. The registered local-linear threshold estimate keeps the same
sign but is much smaller and noisier because it searches for a corner the behavioral profile does
not contain. Both estimators are reported. The compelling evidence for behavior is the preregistered
full profile and the raw, game-clustered difference—not a selectively chosen threshold.

## 4. The payoff is approximately zero

The holdout local estimate is +0.030 net points per opportunity with standard error 0.064. The
development estimate is +0.008 with standard error 0.036. Pooling what the two windows can rule out
places the plausible range at roughly −0.09 to +0.16 points. The evidence does not say that every
2-for-1 decision is identical or that teams should stop attempting them. It says that the observed
league strategy does not create detectable free value.

The clock reconstruction shows where the benefit goes. In holdout, teams give up 0.0726 expected
points of continuation value by ending the first action early. That is almost exactly the magnitude
needed to reconcile an extra possession with the near-zero reduced-form payoff. NBA teams appear to
be exchanging shot quality for possession count at close to a fair price.

## 5. Why the textbook sawtooth collapses

A rigid model alternates possessions of fixed length. Near a period boundary, one extra second can
then switch which team gets the final trip, creating a large sawtooth in the value of possessing
the ball. With actual data, the empirical handover sawtooth is only 0.035–0.041 points, versus about
0.49 in that rigid benchmark.

The reason is not mysterious basketball behavior. It is variance. Possessions are distributed
broadly around their average duration. Across two future trips, fast and slow endings overlap; the
identity of the last team with the ball is not mechanically determined by a single fixed cadence.
Duration variance turns a sharp theoretical edge into a shallow probabilistic one.

## 6. The ambitious second application: team profiles

The same framework separates four ideas often collapsed into one number: offensive outcome, shot-
timing style, continuation capability, and deviation below a team's own curve. The held-out team
profile has 0.795 signal share beyond a team-game permutation null and cross-window franchise-rank
persistence of Spearman +0.398. Houston and Orlando surfaced as weak-offense, high-exposure review
candidates. Orlando was largely explained by shot-context mix; Houston remained unusual within
coarse context, especially in close fourth quarters.

Those findings are genuinely interesting, but “Houston should wait longer” is a stronger claim than
the data initially supported. A registered validation sprint therefore tried to break it. Foul and
all-points accounting passed: repriced ranks correlated +0.946 with baseline, Houston stayed second,
and foul repricing explained only 32.3% of its excess. Temporal validation passed: 2024-25 signal
share was 0.639 and 2023-24 to 2024-25 rank persistence was +0.574. Results were stable across clock
rules, heave exclusions, training seasons, and leave-one-shot-family-out specifications.

Public SportVU tracking supplied the critical pressure test. On 64,135 shots with defensible
release frames, defender distance materially improved game-cross-fitted shot valuation, retained
107.4% of positive exposure, and preserved team ranks at +0.979. But defensible frame coverage was
78.55%, missing the frozen 80% requirement by 1.45 percentage points. A blinded 200-possession film
sample has been generated, but two human coders have not yet completed it. Under the registered
rule, the prescriptive headline fails even though the observed tracking subset is supportive.

## 7. What the project establishes

The strongest conclusion is narrow and counterintuitive: NBA teams successfully create the extra
2-for-1 possession, but pay for it with roughly equal continuation value. The shot-clock rebuild is
what makes both sides of that ledger visible.

The team work should not be discarded. It establishes persistent possession-decision profiles and
a defensible method for surfacing possessions for film. What remains unearned is the final causal
step from “this action ended below the team's historical continuation curve” to “continuing this
specific possession would have improved the offense.” Completing blinded film coding—or acquiring
tracking with reliable full-season release coverage—is the shortest path back to that claim.

## Reproducibility

All registrations, corrections, null results, estimator outputs, and generated tables are retained
in the repository. Start with [RESULTS.md](RESULTS.md), then consult [METHODOLOGY.md](METHODOLOGY.md),
[reports/preregistration_twoforone.md](reports/preregistration_twoforone.md), and
[reports/preregistration_team_validation.md](reports/preregistration_team_validation.md).
