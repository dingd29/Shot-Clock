# Pre-registered: do teams really differ in how far they deviate from the curve?

Written 6 August 2026, **after** the exploration window had been examined and before the holdout
was touched. That asymmetry is stated up front because it changes what this file can claim: it is
a registration of the **confirmation**, not of the exploration.

## What has already been seen

On 2015-16 → 2021-22, scoring every shot against its own team's possession curve:

- Premature share — the fraction of a team's shots taken below what continuing was worth to
  *that team* — runs from **0.058 (ATL) to 0.105 (DEN)**.
- Observed spread SD **0.0126** against a team-game permutation null of **0.0054**, a signal
  share of **0.816**.
- It correlates **+0.71** with the gap between a team's curve level and its mean shot value.

That last number is the reason this needs a registration rather than a write-up. The measure is
*built* from that gap, so the correlation is arithmetic, not a discovered mechanism — and this
project has already published one leaderboard (`stopping.player_exercise`) that turned out to be
mean late-clock shot quality renamed at correlation 0.984.

## Why the estimator changed, and why that is not cherry-picking

Two previous attempts at team differences used the **relaxation ratio**, a quotient of two fitted
slopes. `preregistration_situational.md` H4 resolved it by clock band and returned a signal share
of **zero** on held-out seasons — teams differed *less* than random relabelling produced.

The diagnosis was the estimator, not the question. A ratio of slopes fitted on a thirtieth of the
data is badly conditioned; a **proportion** over ~44,000 shots per team has a standard error near
0.0013. That is a ten-to-one improvement in signal against sampling noise, and it was predicted
from the arithmetic before the number came back — see the session record and the docstring on
`value.premature_share`.

## Protocol

1. The code is **frozen** at the commit carrying this file.
2. **Confirm once on 2022-23 → 2023-24.** Untouched until now.
3. **2024-25 is not used.** It is the xPTS test season.
4. Everything run is reported, including failures.

## H7a, the spread is real out of sample

- **Prediction:** signal share on the holdout is **greater than zero** — observed team spread
  exceeds the team-game permutation null.
- **Test:** same estimator, same null construction, 50 draws.
- **Decision rule:** confirmed if signal share > 0.2. A bar of "greater than zero" is too weak,
  since the estimate is bounded below at zero by construction.

## H7b, the differences are a property of teams, not of seasons

*The harder test, and the one that matters.*

- **Prediction:** the rank correlation between a franchise's exploration premature share and its
  holdout premature share is **positive**.
- **Test:** Spearman across the 30 franchises, one-sided.
- **Decision rule:** confirmed if ρ > 0.3.
- **Stated problem, in advance.** Seven seasons separate the two windows and a franchise is not a
  constant — rosters, coaches and the league's whole shot profile turn over. A null here is
  therefore **ambiguous** between "teams do not differ" and "the differences belong to rosters
  rather than franchises", and will be reported as ambiguous rather than as evidence of no
  effect. A *positive* result is the informative one, because persistence across that much
  turnover is hard to produce by chance.

## H7c, is it decision quality or unrealised capability?

Descriptive, not a test, registered so it cannot later be presented as one.

Premature share says a team took shots worse than what waiting was worth **to it**. Denver with
Jokić has a high continuation value because Jokić generates good late looks, so a shot that would
be fine for another team is premature for Denver. Two readings, and this data does not separate
them:

- **Decision quality.** A team with a high ceiling that settles is genuinely leaving value.
- **Unrealised capability.** The continuation value is estimated on chances that *declined* to
  shoot, a selected group, and that selection is worse for teams whose late offence is good.

Both readings are reported. Neither is claimed over the other.

## What would make me drop this

- Signal share on the holdout below 0.2.
- Rank correlation negative.
- The measure turning out to track something already available from a box score — checked
  against mean shot value and curve level, both reported whatever they show.

---

# Results

**Run 6 August 2026.** Holdout run once, against the frozen code.

## Scoreboard

| | Hypothesis | Bar | Result | Verdict |
|---|---|---|---|---|
| **H7a** | The spread is real out of sample | signal share > 0.2 | **0.795** | **Confirmed** |
| **H7b** | The ranking persists across windows | ρ > 0.3 | **+0.398**, p = 0.015 | **Confirmed** |
| **H7c** | Decision quality or capability? | descriptive | unresolved, both reported | — |

**This is the first team-level result in this project to survive a holdout.**

## H7a, confirmed

| | Explore | Holdout |
|---|---|---|
| Premature share, range | 0.058 – 0.105 | 0.026 – 0.089 |
| Observed SD | 0.01263 | 0.01514 |
| Permutation null SD | 0.00542 | 0.00686 |
| Null 95th percentile | 0.00683 | 0.00838 |
| **Signal share** | **0.816** | **0.795** |

Both windows land in the same place, and both sit far above the null's own draw-to-draw range.
Compare with what the same question returned under the old estimator: 42% over ten seasons for
the pooled relaxation ratio, and **zero** for the band-resolved version on held-out seasons.

The improvement is the estimator, and it was predictable from the arithmetic. A proportion over
~44,000 shots has a standard error near 0.0013 against an observed spread of 0.0126 — ten to one.
A quotient of two fitted slopes on a thirtieth of the data has no such margin.

## H7b, confirmed, and it is the one that matters

Spearman ρ = **+0.398** across 30 franchises, one-sided p = **0.015**, Pearson r = +0.416.

Seven seasons separate the windows. Rosters, coaches and the league's whole shot profile turn
over in that time, so persistence at this level is not trivially explained. The stable ends are
Golden State and Denver high, Atlanta, Dallas, Orlando and the Lakers low.

The **levels** move a lot between windows — the whole distribution shifts down on the holdout,
0.058–0.105 to 0.026–0.089. That is the same era effect the curve's calibration found: the league
scores more now, so shots clear their own continuation value more often. Only the ordering was
registered, and only the ordering is claimed.

## The selection check, which the measure passes

`V(t)` is estimated on chances that **declined** to shoot. A team that shoots early leaves a
worse residual behind, so its curve should be biased down and its premature share with it. If
that drove the measure, premature share would track shot timing.

It does not:

| | Correlation with premature share |
|---|---|
| Mean shot-clock second (higher = shoots earlier) | **−0.048** |
| Late-shot share | +0.026 |

Essentially zero on both. **The measure is orthogonal to style**, which is what a decision-quality
measure should be and what rules out the obvious selection story. It also means this is not pace
or tempo under another name — the two are separately identified here, which is the whole reason
for measuring them separately.

## H7c, unresolved, as registered

Premature share correlates **+0.709** with the gap between a team's curve level and its mean shot
value. That is arithmetic — the measure is built from that gap — not a discovered mechanism, and
it is reported so that nobody mistakes it for one.

The two readings remain:

- **Decision quality.** Denver's continuation value is high because Jokić generates good late
  looks. A shot that is fine for another team is genuinely a waste for Denver, and settling for
  it leaves value on the floor.
- **Unrealised capability.** `V(t)` is estimated on chances that declined to shoot, and that
  selection is more favourable for teams whose late offence is good, inflating their bar.

Nothing here separates them, and the selection check above constrains the second reading without
eliminating it.

## What it is worth

The mean shortfall on a premature shot is **0.104 points**. Multiplying through:

| | |
|---|---|
| Cost per shot attempt | 0.0061 to 0.0117 points |
| Spread between the extreme franchises | 0.0057 points per attempt |
| At ~85 attempts per team-game | **0.48 points per game** |

Real, replicated, orthogonal to style — and worth about half a point per game between the most
and least premature franchises, which is roughly a point and a half of margin over a season.
Nobody should reorganise an offence around it.
