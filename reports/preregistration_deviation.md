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

*Not yet run.*
