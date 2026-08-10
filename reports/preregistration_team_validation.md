# Team-profile validation sprint

Registered 9 August 2026 after the 2015-24 team-profile results were known, after inspecting the
play-by-play schema for how shooting fouls are encoded, and **before** calculating foul-accounting
effects, inspecting 2024-25 team profiles, acquiring closest-defender data, or reviewing flagged
possessions on film.

This is a validation protocol for an existing exploratory result. It is not a claim that the
original team hypothesis was prospectively registered.

## Candidate headline

> NBA teams have persistent possession-decision profiles, and some offenses end actions before
> exhausting valuable continuation opportunities.

The first clause is already supported descriptively. This sprint tests whether the second clause
survives alternative accounting, omitted defensive pressure, a new season, and possession-level
review. If it does not, the team profile remains a descriptive film queue and is not the project's
headline.

## Existing result that must not be redefined

- Exploration: 2015-16 through 2021-22.
- Holdout: 2022-23 through 2023-24.
- A shot is below curve when its expected field-goal value plus rebound option is below its team's
  possession-level, field-goal-points continuation curve at the same reconstructed second.
- Observed held-out signal share: 0.795.
- Cross-window franchise persistence: Spearman +0.398, one-sided p = 0.015.
- Held-out review queue: Houston and Orlando, defined as bottom-third all-points offense plus
  top-third positive continuation gap per shot.
- Context result: 67.4% of positive exposure comes from non-restricted-area paint attempts;
  context-standardized Houston ranks second and Orlando eighth.

No threshold or estimator below will be changed after its corresponding result is inspected.

## Gate 1: foul and points accounting

### Audit

The current implementation uses `PTS_POSS`, chained from `PTS_FG`, for `V(t)`. Free throws are
therefore excluded from both the shot and continuation units. The initially proposed asymmetry—free
throws present only in `V(t)`—is not the current code. The remaining concern is missing exercise
events: a missed shot drawing a shooting foul has no official FGA, and an and-one's free throw is
not part of current shot value.

Build and report:

1. Counts and rates of shooting-foul exercises by team, clock phase, and season.
2. The field-goal-only baseline, reproduced unchanged.
3. An all-points continuation curve chained from `PTS_ALL`.
4. An event-level exercise table containing official FGA and shooting-foul exercises at their
   reconstructed clock time.
5. A leakage-safe expected exercise value using only features shared by FGA and foul-only events.
   Realized free-throw points may be the training target but may not be used as the scored value of
   the same event.
6. Explicit lower and upper bounds where foul-only shot location cannot be recovered.

### Pass conditions

All must hold:

- baseline versus all-points team exposure ranks: Spearman at least +0.60;
- all-points team spread exceeds its team-game permutation null with signal share at least 0.50;
- Houston remains in the top third of context-adjusted exposure;
- no single foul-accounting choice explains more than half the baseline Houston-versus-league
  exposure difference;
- the non-RA paint conclusion is either reproduced after foul pricing or narrowed explicitly to
  field-goal-only exposure.

Failure of any condition blocks the prescriptive team headline until a better exercise model exists.

## Gate 2: closest-defender distance

Use the 2015-16 public SportVU shot-log overlap. Join by game, shooter, period, game clock, and shot
result, reporting match rate and ambiguous matches. Do not silently keep only easy matches.

Fit defender-aware shot value with game-level cross-fitting. Compare original and defender-aware
exposure for the same matched shots. Report results overall, for non-RA paint, and by team.

Before fitting the defender-aware model, “materially improves” is operationalized as a held-out
log-loss reduction of at least 0.0005 per shot with a paired team-game bootstrap 95% interval above
zero. The baseline recalibrates the published xPTS using the same folds and features; the treatment
adds closest-defender distance, so fold construction cannot favor the treatment.

### Pass conditions

All must hold:

- at least 80% of eligible reconstructed FGA match uniquely to the defender file;
- adding defender distance materially improves held-out shot-value calibration or the test is
  labeled uninformative rather than favorable;
- at least 50% of baseline positive exposure remains after defender adjustment;
- team exposure ranks correlate at least +0.50 before and after adjustment;
- below-curve shots remain more common than matched controls among attempts classified as open or
  wide open under a threshold fixed from the provider's definitions.

If the data source cannot support a reliable join, this gate is unresolved, not passed.

## Gate 3: temporal and specification stability

The 2024-25 season is a new temporal evaluation for the team-profile estimator. Curves, rebound
lookup, and second-chance value must be frozen using 2022-23 and 2023-24 only. No 2024-25 outcomes
may enter the reference values.

Also rerun the 2022-24 result under:

- minimum team-curve sample thresholds of 3,000, 5,000, and 8,000 possessions;
- clock rounding by floor, nearest integer, and ceiling;
- leave-one-season-out curves;
- exclusion of heaves at 2, 3, 5, and 8 period seconds;
- team-game cluster bootstrap intervals;
- removal of each shot family in turn;
- a negative-control permutation preserving team, season, clock phase, and shot family.

### Pass conditions

- 2024-25 cross-sectional signal share at least 0.50;
- 2023-24 to 2024-25 team-rank Spearman at least +0.30;
- the sign of the team-level spread and the Houston/context conclusions do not depend on one clock
  rule, one season, or one shot family;
- no team promoted as a review candidate has an exposure interval overlapping the league median
  under every specification.

Individual franchise names may change with roster and coaching changes. The gate concerns whether
the construct and its mechanism replicate, not whether Orlando must remain flagged forever.

## Gate 4: blinded possession review

Generate a reproducible sample before watching film:

- 50 high-exposure early/middle-clock possessions from Houston;
- 50 from Orlando;
- 50 from a high-capability strong offense;
- 50 matched low-exposure controls;
- matching on season, clock phase, shot family, possession origin, and score state;
- random order with team, player, model gap, and case/control status hidden from the coder where
  the video permits it.

Code:

- whether a live advantage remained at the shot moment;
- whether an open teammate or credible next action was available;
- whether the shot was a bailout after a failed action;
- whether defensive pressure made continuation implausible;
- whether the primary issue was shot choice, play design, personnel, or model error.

Use at least two coders for a 40-possession overlap and report Cohen's kappa for the binary
“credible continuation available” label.

### Pass conditions

- kappa at least 0.60, or disagreements are adjudicated with the ambiguity reported;
- high-exposure cases show a credible continuation at least 15 percentage points more often than
  matched controls;
- the difference is not driven exclusively by one team or one shot family.

Until human coding is complete, this gate is unresolved and the word “should” is not licensed.

## Decision rule

The prescriptive team-profile headline requires all four gates. A failed gate triggers the fallback:

1. document the failed validation without removing the original result;
2. make the held-out 2-for-1/end-period result the public headline;
3. retain team profiles as a clearly exploratory secondary application or film-review tool;
4. stop adding analyses and package a short paper plus hosted dashboard.

An unresolved external-data or film gate leaves the headline unresolved; it does not count as a pass.

## Results log

### Gate 1 — passed (9 August 2026)

The first development run appeared to reverse the team ranking. That was a diagnostic bug: two
independently sorted team tables had been passed to `spearmanr` without first joining on team. The
comparison is now an explicit one-to-one team join with a regression test. This correction was
made before evaluating any later gate and is preserved here because the false negative materially
affected interpretation.

- Shooting fouls are not present on only one side of the published comparison. `V(t)` was chained
  from field-goal points, so free throws were excluded from both shot value and continuation. The
  actual omission was the exercise event: foul-only attempts are not official FGA, and and-one free
  throws are outside field-goal xPTS.
- Foul-only exercises are 8.3% of observed shooting actions across 2015–24, large enough that they
  required explicit treatment.
- Under all-points continuation, all-points rebound value, strictly historical player foul
  premiums, and foul-only exercise rows, the held-out exposure-rank correlation with the registered
  field-goal-only result is **+0.946** (threshold +0.60).
- The repriced cross-team signal share is **0.865** (threshold 0.50).
- Houston remains second in raw exposure and second after the registered context standardization
  (threshold: top third). Orlando moves from eighth to sixth in raw exposure.
- Full foul repricing changes Houston's excess over the league mean by **32.3%** (threshold: no more
  than 50%).
- Non-restricted-area paint attempts account for **67.3%** of repriced positive exposure. The
  lower and upper bounds coincide because location-missing foul-only actions have no positive gap
  under the registered, non-outcome imputation.
- Replacing field-goal points with all points does not explain the league calibration offset: raw
  held-out bias is nearly unchanged and a one-constant level shift remains necessary.

Authoritative outputs are `team_validation_gate1_summary.csv`,
`team_validation_accounting_comparisons.csv`, `team_validation_foul_counts.csv`, and
`team_validation_location_bounds.csv`. Gate 1 passing does **not** license the prescriptive
headline; Gates 2–4 remain unresolved.

### Gate 3 — passed (9 August 2026)

The 2024–25 temporal profile freezes all reference curves, rebound rates, second-chance value, and
foul premiums on earlier seasons. The temporal permutation null likewise refits curves only on the
historical side after jointly relabelling whole historical and future team-games. A preliminary
null that refit nuisance curves on 2024–25 was discarded before interpretation because it violated
the frozen-estimator rule; it produced a non-comparable signal share of 0.367.

- The estimator-matched 2024–25 signal share is **0.639** (threshold 0.50). Observed cross-team SD
  is 0.00734 against a permutation-null mean of 0.00441 and p95 of 0.00538.
- 2023–24 to 2024–25 exposure-rank persistence is **Spearman +0.574** (threshold +0.30).
- Houston ranks fourth in the new season. Its held-out rank remains in the top third under every
  registered clock rule, period-expiry cutoff, leave-one-season-out curve, and leave-one-shot-family-
  out specification. Removing non-RA paint is the largest perturbation and moves Houston from
  second to ninth rather than erasing the profile.
- Team-game cluster-bootstrap 95% intervals for both Houston and Orlando remain above the league
  median in the held-out window.
- The exact-value negative control within team × season × broad clock phase × shot family leaves
  the team ranking almost unchanged (rho +0.989). This is not treated as independent confirmation:
  it shows that broad shot-family/capability structure, rather than exact reconstructed seconds,
  carries most of the profile.

Authoritative outputs are `team_validation_gate3_temporal_summary.csv`,
`team_validation_temporal_profiles.csv`, `team_validation_specification_comparisons.csv`, and
`team_validation_team_game_bootstrap.csv`.

### Gate 2 — failed on coverage (10 August 2026)

The public SportVU source covers 523 games from 27 October 2015 through 23 January 2016. Its exact
game/event/shooter keys join uniquely to 96.33% of reconstructed FGA in covered games. The source's
precomputed `SHOT_TIME` could not be used: inspection of the published code found an indexing error
that frequently selects a frame near the ball's apex, and the ball was already more than 18 feet
from the shooter in one quarter of those frames. The initial apparent Gate-2 pass using that proxy
was rejected before being recorded as a result.

Release was redefined before rerunning the full archive as the final shooter-possession frame from
0.5 seconds after through five seconds before the PBP shot timestamp: ball within three horizontal
feet and at 3–13 feet height, followed 0.2 seconds later by both rising height and separation. A
close-frame fallback handles dunks and tracking noise and is flagged. This definition is tested
against the independently recorded shot distance and retains all missing attempts in the match-rate
denominator.

- **64,135 of 81,647 eligible reconstructed FGA match uniquely to a defensible release frame:
  78.55%, below the frozen 80% threshold.** Fifty reconstructed rows are explicitly ambiguous;
  none of the tracking keys are duplicated. No time window, possession radius, or denominator was
  changed after observing the full-archive rate.
- On the valid subset, defender distance is informative: game-cross-fitted log loss improves by
  **0.00355 per shot**, with a paired team-game bootstrap 95% interval of **[0.00279, 0.00436]**.
- The defender adjustment does not explain the exposure away. It retains **107.4%** of positive
  exposure overall and **102.0%** in non-RA paint; team exposure ranks correlate **+0.979** before
  and after adjustment.
- Among attempts at least four feet open, baseline-flagged cases remain defender-aware below curve
  much more often than exact-context controls. This is a sensitivity result, not a substitute for
  the failed coverage condition.

Because all Gate-2 conditions were required, the candidate prescriptive headline fails the frozen
decision rule even though every estimand on the valid subset points in the favorable direction.
The failure is coverage, not evidence that defender pressure explains the team profile.

Authoritative outputs are `team_validation_gate2_summary.csv`,
`team_validation_defender_match_summary.csv`, `team_validation_defender_release_quality.csv`,
`team_validation_defender_model_improvement.csv`, and `team_validation_defender_context.csv`.

### Gate 4 — sample frozen; human coding unresolved (10 August 2026)

The 200-possession sample, blinded worksheet, and closed key were generated before watching film.
They live in the gitignored `.review/` directory; the public coding instructions are in
`team_validation_review_protocol.md`. Two human coders and at least 40 overlapping decisions remain
required. This unresolved gate cannot rescue the failed Gate-2 decision rule and is retained as the
clearest path for a future prescriptive study.

### Decision

The prescriptive statement “these NBA teams should wait longer” is not the project headline. Gates
1 and 3 pass, the valid Gate-2 subset is supportive, but Gate 2 misses its preregistered coverage
threshold by 1.45 percentage points and Gate 4 lacks human labels. The registered fallback applies:

1. this failed validation remains beside the original team result;
2. the held-out 2-for-1/end-period result becomes the public headline;
3. team profiles remain a secondary, explicitly exploratory film-review application;
4. analysis stops here and the project moves to a short paper and hosted dashboard.
