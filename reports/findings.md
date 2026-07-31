# Findings: shot clock and shot efficiency

2024-25 regular season. 210,394 shots with a reconstructed shot clock (95.8% of all FGA).
Points per attempt (PPA) counts field-goal points only — free throws are excluded, since
`shotdetail` contains no FT rows. Method and validation: [METHODOLOGY.md](../METHODOLOGY.md).

---

## 1. NBA's published buckets hide the steepest part of the curve

NBA publishes six shot-clock ranges. Their widths are wildly mismatched to where efficiency
actually changes, so the reported bucket average conceals very different amounts of variation.

| Bucket | Bucket PPA | Within-bucket range | Spread |
|---|---|---|---|
| 24-22 | 1.243 | 0.954 – 1.365 | **0.411** |
| 22-18 | 1.216 | 1.149 – 1.313 | 0.164 |
| 18-15 | 1.122 | 1.111 – 1.131 | 0.020 |
| 15-7 | 1.096 | 1.047 – 1.132 | 0.085 |
| 7-4 | 1.037 | 1.009 – 1.049 | 0.040 |
| **4-0** | 0.879 | **0.708 – 0.989** | **0.281** |

The `4-0` bucket reports a single number, 0.879, for a region where true efficiency falls
from 0.989 to 0.708 — a **28% swing collapsed into one figure**. Meanwhile `18-15` spans a
range of just 0.020 and is genuinely well summarised by its average.

A team studying its own late-clock offense from the published splits cannot distinguish a
possession that dies with 4 seconds left from one that dies with 1. Those are very different
outcomes.

## 2. The late-clock collapse is real, and it is not a selection artifact

PPA falls from **1.047 at 7 seconds to 0.708 at 0 seconds** — a drop of 0.339 (SE ≈ 0.020,
so roughly 17 standard errors). It holds across every possession-start type:

| Start type | PPA at 0s | PPA at 7s |
|---|---|---|
| After made FG | 0.742 | 1.043 |
| After defensive rebound | 0.599 | 1.020 |
| After turnover | 0.629 | 1.016 |
| After offensive rebound | 0.679 | 1.091 |

Because the collapse appears identically no matter how the possession began, it reflects
genuine deterioration in shot quality under time pressure rather than a difference in which
possessions survive that long.

**The mechanism is visible in the shot mix.** As the clock runs out, teams are forced off the
rim and into contested mid-range jumpers:

| Clock | Rim share | Mid share | 3PT share |
|---|---|---|---|
| 23s | 65.3% | 11.3% | 23.4% |
| 15s | 26.1% | 29.3% | 44.6% |
| 5s | 20.6% | 38.3% | 41.1% |
| 0s | 16.3% | 33.6% | 50.1% |

Rim attempts fall by three quarters. The 3PT share spike at 0s is desperation heaves, not
good looks — which is why PPA keeps falling even as three-point rate rises.

## 3. Early-clock efficiency is mostly transition, not "shooting early"

This is where the naive reading of the curve goes wrong. Raw PPA rises steeply above ~18
seconds, which looks like an argument for shooting earlier. It is not.

**Controlling for how the possession started removes most of the effect.** For possessions
beginning after a made basket — a dead-ball, half-court start — PPA is essentially flat from
12 seconds to 21 seconds (1.097 → 1.107). The apparent early-clock advantage is driven by
*which possessions are able to produce a shot that early*:

| Clock | After made FG | After turnover | After def. rebound |
|---|---|---|---|
| 5s | 57.7% of shots | 9.9% | 22.0% |
| 20s | **7.5%** | **34.3%** | **54.5%** |

At 20 seconds remaining, only 7.5% of shots come from a half-court inbound start, while 34%
come off live-ball turnovers. Those are fast breaks against a broken defense. The clock is a
*proxy* for transition, not a cause of efficiency.

**Practical implication:** "shoot earlier in the clock" is not supported by this data. What is
supported is "generate live-ball turnovers and defensive rebounds," because those create the
transition opportunities that produce early-clock shots in the first place.

## 4. The 14-second reset leaves a visible fingerprint

Shots at exactly 14 seconds are anomalous: 15,251 attempts (7.2% of all shots, the single
largest one-second bucket) with a rim share of **42.4%**, against 26.1% at 15 seconds and
24.4% at 12 seconds.

These are putbacks. The 2018-19 rule resets the clock to 14 after an offensive rebound, so
every immediate second-chance attempt lands on that exact value. The discontinuity is a
useful validation signal in its own right — it appears only because the reconstruction models
the 14-second rule correctly.

---

## 5. Creation overlap does not predict offensive underperformance — a null result

This was the project's headline hypothesis, and **it failed.**

The reconstruction makes it possible to measure a player's *creation profile*: the
distribution of his attempts over (shot-clock bucket × zone). Two players "overlap" when
their profiles have the same shape — both want the ball at the same moments. The hypothesis
was that high overlap costs a team offense, because four creators cannot all use the same
possessions.

**The descriptive half holds up.** Philadelphia's projected core is genuinely redundant:

| Pair | Creation similarity |
|---|---|
| LeBron ↔ Jaylen Brown | **0.988** |
| LeBron ↔ Maxey | 0.980 |
| Brown ↔ Maxey | 0.975 |
| Embiid ↔ Brown | 0.951 |
| Embiid ↔ KCP | 0.836 |

Volume-weighted, the big four score **0.973 — the 99th percentile** of random four-player
groups (league mean 0.895, p90 0.958). Embiid is the only differentiated creator; LeBron,
Brown and Maxey are close to interchangeable in *when* they generate offense.

**The causal half does not.** Testing whether overlap predicts efficiency across 270
team-seasons (2016-17 → 2024-25), controlling for the same players' prior-season scoring
quality and season fixed effects:

| Core size | Effect of +1 SD overlap on team xPTS/attempt | t |
|---|---|---|
| Top 3 creators | **+0.0029** | +1.62 |
| Top 4 creators | +0.0020 | +1.23 |
| Top 8 creators | −0.0001 | −0.03 |

No specification reaches significance, and at the star level **the sign is positive** — the
opposite of the hypothesis. The control behaves exactly as it should (prior quality t = 9.9,
model R² = 0.53-0.61), so this is a real null rather than a broken test.

**What this rules out, and what survives.** On this evidence there is no basis for projecting
Philadelphia to underperform because its stars want the ball at the same time. Three
explanations remain live and are not distinguished by this test:

1. Redundancy may bite at five-man lineup level and wash out over a whole team-season,
   since a team's top creators do not share the floor for all their minutes.
2. Coaches may already solve it by staggering minutes — in which case the null reflects
   successful adaptation rather than an absent problem.
3. The Sixers' overlap (0.973) sits **outside the observed team-season range** (max 0.961),
   so applying the fitted null to them is extrapolation either way.

**The implication for the projection is a change of subject.** The evidence for a
Philadelphia risk is not offensive fit — it is defense and availability. Three of the four
stars are negative defenders by DARKO (Brown −1.27, Maxey −0.91, LeBron −0.27), Embiid is
the only plus defender in the starting five, and the bench sits below league median. That
concern is untouched by this null result, and it is where the projection should focus.

---

## Caveats

- Free throws are excluded, so PPA understates the value of possessions that draw fouls. Late
  clock plausibly draws more fouls, which means finding 2 may *overstate* the late-clock
  penalty somewhat. Quantifying this requires joining FT events to chances — planned.
- Shots at exactly 24 seconds (n=906, PPA 0.954) are an edge case: tips and putbacks landing
  on the reset instant. Small sample, treated as noise.
- 4.2% of shots have no reconstructed clock (low-confidence chances) and are excluded rather
  than imputed. See METHODOLOGY.md §2.
- Single season. Ten-season backfill will establish whether these curves are stable and
  whether the 2018-19 rule change moved them.
