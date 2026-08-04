# Pre-registered exploration: does the relaxation finding matter?

Written 4 August 2026, before running any of it, and committed before the first line of
analysis code so the timestamp is checkable.

## Why this file exists

Findings §7 says offenses lower their shot standard only about half as fast as the collapse in
continuation value calls for. Three questions follow, and all three could be answered twenty
ways until one comes out interesting.

With 2.9M chances almost any comparison clears significance, and this project has already
produced three results that looked real and weren't: an overlap effect at t = +5.01 before
clustering, a team spread that was 63% noise against a permutation null, and a per-player
leaderboard with 85% "signal" that turned out to be shot quality renamed. Searching freely and
reporting what survived would produce numbers I couldn't defend.

So the tests are fixed here first.

## Protocol

1. **Explore on 2015-16 → 2021-22.** Seven seasons.
2. **Confirm once on 2022-23 → 2023-24.** Held out, untouched until a hypothesis is finalised.
3. **2024-25 is not used** in this exercise, it is the test season for the xPTS model and the
   projection layer, and burning it here would contaminate those.
4. **Everything tried is reported**, including what fails and anything abandoned mid-flight.
   A test listed below that goes unreported is a protocol violation.
5. Any test not on this list, run later, is labelled **post hoc** wherever it appears.

## The three hypotheses

### H1, Under-relaxing costs offenses points

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

### H2, Offenses adapted to the 2018-19 rule change

*The rule mechanically changed `V(t)` for second chances. Did behaviour follow?*

- **Prediction:** after 2018-19 the exercise boundary for chances starting with an **offensive
  rebound** moves relative to chances starting with a **defensive rebound**, which the rule did
  not touch. Direction is **not** pre-specified, adaptation could go either way, and claiming
  otherwise after the fact would be dishonest. This is registered as two-sided.
- **Unit:** chance, difference-in-differences with the same treated/control split as finding 4b.
- **Test:** relaxation ratio and boundary computed separately for treated and control, pre and
  post. **2017-18 excluded** for the timestamping artifact documented in finding 4b.
- **Decision rule:** confirmed if the treated-minus-control change exceeds the range produced
  by the same calculation on placebo cut-points (2016 and 2020 as fake rule years).

### H3, The ratio depends on who is on the floor

*Not per-player surplus, which is tautological. The ratio, which is not.*

- **Prediction:** lineups containing a **high-usage creator** have a **lower** relaxation ratio
  a team with someone who can make something happen has more reason to keep waiting, and
  should be slower to accept a marginal shot.
- **Unit:** chance and shot, split into two groups by whether a top-quartile-usage player was
  on the floor. Lineups come from the derived on-court data.
- **Test:** relaxation ratio per group, against a **permutation null** that shuffles the group
  label, the same machinery that showed two thirds of the team spread was noise.
- **Decision rule:** confirmed only if the gap between groups exceeds the permutation null on
  exploration and reproduces in sign on the holdout.

## What would make me drop a hypothesis

Recorded now so it cannot be rationalised later:

- The measure turns out to be a restatement of something else (as per-player surplus was).
- The effect exists only under one arbitrary parameter choice, the quantile trap from 4d.
- The sign flips between exploration and holdout.

## What this cannot do

None of these establish causation. Teams that relax faster may simply have better players,
better spacing, or coaches who differ on ten other axes. H1 in particular is a **correlation
between two team attributes** and will be reported as one. The instrument that would fix it,
knowing what shot was available and declined, does not exist in this data, and that limit is
the same one that caps findings §7.

---

# Results

**Run 4 August 2026**, against the protocol above. Every test listed was run; nothing was
added, dropped, or re-specified after seeing an outcome. Two deviations are recorded below and
labelled.

## Scoreboard

| | Hypothesis | Predicted | Observed | Verdict |
|---|---|---|---|---|
| **H1** | Under-relaxing costs points | positive ρ | +0.251 explore, +0.065 full sample | **Not supported** |
| **H2** | Offenses adapted to the 2018 rule | two-sided | DiD −0.160 vs placebo mean −0.108 | **Marginal** |
| **H3** | Creators on floor → lower ratio | **negative** | **+0.065** explore, +0.001 holdout | **Failed** |

Nothing cleanly confirmed, which is a normal yield from three honest tests and the reason the
protocol was written first.

## H1, not supported

| Window | n | Spearman ρ | One-sided p |
|---|---|---|---|
| Exploration, 2015-16 → 2021-22 | 30 | +0.251 | 0.091 |
| Full sample, 2015-16 → 2024-25 | 30 | +0.065 | 0.367 |
| Holdout, 2022-23 → 2023-24 | — | **not estimable** | — |

The sign is right and the magnitude is not. +0.251 sits below the |ρ| ≈ 0.36 detectability
floor stated in advance, and it **falls to +0.065 on the full sample**, a correlation that
moves that much with the window is not a finding.

*The holdout could not be run, and the reason is a real constraint rather than an excuse.* The
relaxation ratio is anchored on the boundary at 23 seconds, and two seasons split thirty ways
leaves each team with too few shots that late to estimate one. The code now raises
`InsufficientData` rather than returning a number, which is how this was discovered.

**So the honest statement is not "under-relaxing is costless", it is that this test cannot
tell.** A team-level correlation at n = 30 was underpowered from the start, and the
pre-registration said so before the number came back.

## H2, marginal, and the placebos are the story

Difference-in-differences on the boundary gap, treated = offensive-rebound chances, control =
defensive-rebound chances, 2017-18 excluded for the timestamping artifact:

| Cut point | DiD |
|---|---|
| 2016 (placebo) | −0.127 |
| **2018 (real rule)** | **−0.160** |
| 2019 (placebo) | −0.145 |
| 2020 (placebo) | −0.093 |
| 2021 (placebo) | −0.091 |
| 2022 (placebo) | −0.083 |

Placebo mean −0.108, SD 0.027, **z = −1.94**. The real cut is the largest in magnitude and
sits outside the placebo range, which satisfies the pre-registered decision rule, but only
just, and the rule was arguably too lenient.

**Every placebo is large and negative.** That is the finding worth taking from this: a strong
secular trend in the boundary gap runs through both arms, and the difference-in-differences
does not remove it. An effect only 1.9 SD from what fake rule-years produce is not something
to build on. The nearest placebo, 2019, is adjacent to the real change and plausibly
contaminated by it; dropping it lifts z to −3.1, but that exclusion is **post hoc** and is not
claimed.

**Verdict: suggestive, not established.** Teams may have adapted. This design cannot separate
adaptation from drift.

## H3, failed, and it's the most useful one here

| Window | Gap (with creator − without) | Permutation null max | Exceeds null? |
|---|---|---|---|
| Exploration | **+0.0646** | 0.0506 | **yes** |
| Holdout | +0.0011 | 0.0728 | no |

Two independent failures:

1. **The direction was wrong.** I predicted lineups with a high-usage creator would relax
   *more slowly*, more reason to keep waiting. Both windows came back positive.
2. **It did not replicate.** The exploration gap cleared its permutation null. On held-out
   data it is **+0.001**, indistinguishable from zero.

This is the false positive the protocol exists to catch. Without a holdout I'd have reported a
+0.065 gap that beat its own null, with a ready story about stars changing how offenses wait,
and it would have been wrong.

## Deviations from the protocol

Both recorded because concealing them would defeat the point.

1. **H3's group definition was changed before any outcome was computed.** The registered "top
   quartile of players with ≥200 FGA" put a creator on the floor for **99% of chances**, not a
   split. Replaced with the top 15 by FGA per season, which gives 44/56. The threshold was
   chosen from on-floor share alone, with no outcome inspected; the sweep is in the log.
2. **H2 has no holdout, and the protocol should not have implied one.** The rule change is a
   one-time event in 2018-19, inside the exploration window, so later seasons cannot confirm
   it. The placebo cut-points carry that load instead. This was a design error in the
   registration, not a result-driven change.

## What this bought

Three hypotheses, zero confirmations, one marginal. On raw output that's a thin day.

What it bought is knowing which of these numbers to trust, and the answer for all three is not
much, stated in advance rather than left for a reader to work out. The H3 exploration result
would have survived every check applied elsewhere here. It took a held-out sample to kill it.
