# Pre-registered exploration: does the relaxation finding matter?

**Written 4 August 2026, before running any of it.** Committed before the first line of
analysis code, so the timestamp in git history is checkable.

## Why this file exists

Finding 4d says offenses lower their shot standard only about half as fast as the collapse in
continuation value warrants. Three questions follow from it, and all three are the kind that
could be answered twenty different ways until one comes out interesting.

This project has already produced three results that looked real and were not: lineup overlap
at t = +5.01 before clustering (2.89 after), a dramatic team-relaxation spread that was **63%
noise** against a permutation null, and a per-player leaderboard with 85% "signal" that turned
out to be shot quality renamed. With 2.9M chances almost any comparison clears significance.
Searching freely and reporting what survived would produce numbers I could not defend, and
would cost this repo the only thing that distinguishes it.

So the tests are fixed here first.

## Protocol

1. **Explore on 2015-16 → 2021-22.** Seven seasons.
2. **Confirm once on 2022-23 → 2023-24.** Held out, untouched until a hypothesis is finalised.
3. **2024-25 is not used** in this exercise — it is the test season for the xPTS model and the
   projection layer, and burning it here would contaminate those.
4. **Everything tried is reported**, including what fails and anything abandoned mid-flight.
   A test listed below that goes unreported is a protocol violation.
5. Any test not on this list, run later, is labelled **post hoc** wherever it appears.

## The three hypotheses

### H1 — Under-relaxing costs offenses points

*The finding has no teeth unless the deviation is expensive.*

- **Prediction:** teams with a **lower** relaxation ratio (slower to drop their standard as the
  clock expires) have **worse** offensive efficiency.
- **Unit:** team, pooled over the exploration window. n = 30.
- **Outcome:** points per chance, computed from the chance panel so it is internally
  consistent with the ratio rather than imported.
- **Test:** Spearman correlation, one-sided (positive: higher ratio → better offense).
- **Decision rule:** confirmed only if the sign is positive on exploration **and** on the
  holdout. A sign flip between the two is a failure, not a subgroup.
- **Stated power problem:** n = 30 with shrunk ratios is thin. Anything below |ρ| ≈ 0.36 is
  undetectable here, so a null is genuinely uninformative and will be reported as such rather
  than as evidence of no effect.

### H2 — Offenses adapted to the 2018-19 rule change

*The rule mechanically changed `V(t)` for second chances. Did behaviour follow?*

- **Prediction:** after 2018-19 the exercise boundary for chances starting with an **offensive
  rebound** moves relative to chances starting with a **defensive rebound**, which the rule did
  not touch. Direction is **not** pre-specified — adaptation could go either way, and claiming
  otherwise after the fact would be dishonest. This is registered as two-sided.
- **Unit:** chance, difference-in-differences with the same treated/control split as finding 4b.
- **Test:** relaxation ratio and boundary computed separately for treated and control, pre and
  post. **2017-18 excluded** for the timestamping artifact documented in finding 4b.
- **Decision rule:** confirmed if the treated-minus-control change exceeds the range produced
  by the same calculation on placebo cut-points (2016 and 2020 as fake rule years).

### H3 — The ratio depends on who is on the floor

*Not per-player surplus, which is tautological. The ratio, which is not.*

- **Prediction:** lineups containing a **high-usage creator** have a **lower** relaxation ratio
  — a team with someone who can make something happen has more reason to keep waiting, and
  should be slower to accept a marginal shot.
- **Unit:** chance and shot, split into two groups by whether a top-quartile-usage player was
  on the floor. Lineups come from the derived on-court data.
- **Test:** relaxation ratio per group, against a **permutation null** that shuffles the group
  label — the same machinery that showed two thirds of the team spread was noise.
- **Decision rule:** confirmed only if the gap between groups exceeds the permutation null on
  exploration and reproduces in sign on the holdout.

## What would make me drop a hypothesis

Recorded now so it cannot be rationalised later:

- The measure turns out to be a restatement of something else (as per-player surplus was).
- The effect exists only under one arbitrary parameter choice — the quantile trap from 4d.
- The sign flips between exploration and holdout.

## What this cannot do

None of these establish causation. Teams that relax faster may simply have better players,
better spacing, or coaches who differ on ten other axes. H1 in particular is a **correlation
between two team attributes** and will be reported as one. The instrument that would fix it —
knowing what shot was available and declined — does not exist in this data, and that limit is
the same one that caps finding 4d.
