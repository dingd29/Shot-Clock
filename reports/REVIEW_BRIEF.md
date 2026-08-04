# Review brief — self-contained

For a reviewer who cannot run code. Every number needed is inline; no file needs to be opened
to answer the questions at the end. Repo: https://github.com/dingd29/possession-value

**You cannot verify these figures.** They come from ~2M shots and ~2.9M possessions that are
not in the repo (regenerating them takes hours of downloads). Please do not describe any
number below as checked, replicated, or confirmed. Judge the *reasoning and direction*, which
is what is actually being asked.

## What it is

The NBA publishes shot-clock data only as six coarse per-game bucket averages. This
reconstructs the **per-shot shot clock** from play-by-play — a field in no public feed — for
2.01M shots across ten seasons, then validates it against NBA's own published aggregates
(1.20pp mean bucket-share error; per-player FGA agreement R² = 0.973).

Author is an undergraduate maths student; the goal is a portfolio piece for quant and AI
interviews.

## What it found

**The headline is a negative one.** The shot clock turned out to be useful at exactly one scale:

| Question | Shot clock's contribution |
|---|---|
| Will *this shot* go in? | Negligible — smallest group in an ablation |
| Will *this possession* score? | **Large** — continuation value spans 0.36 → 0.81 points |
| Will *this team* win? | Negligible — 0.034% of log loss over 5.34M events |

A possession is ~1% of a game's scoring, so possession-scale information washes out at the
scale below and above. The conclusion drawn is that the reconstruction's value is **as a
measurement instrument, not a predictive feature**.

**The one strong positive result** uses it as exactly that. Shooting is reframed as American
option exercise — take the shot in hand, or hold an option whose value decays — which
identifies something a raw efficiency curve cannot, because it conditions on the *decision*
rather than the outcome. Offenses lower their accepted shot standard by only **55-65%** of what
the collapse in continuation value warrants. Holds in all ten seasons and in competitive games
alone. The *level* of the threshold is explicitly reported as unidentified (the choice of
quantile flips its sign), so only the shape is claimed.

**Results reported as failures**, in the repo's own words:

- The project's original headline hypothesis — that players wanting the ball at the same
  moments hurts offenses — failed at team level, at lineup level, and lost a head-to-head
  against a plain box-score usage measure (t falls 2.89 → 0.49).
- A per-player version of the stopping result was found to correlate **0.984** with mean shot
  quality — it was that quantity renamed — and is published as a failure.
- An earlier claim that possession context was worth as much as shot location was **withdrawn**
  after grouping features more honestly.
- Three follow-up hypotheses were **pre-registered before testing** with an exploration/holdout
  split. None confirmed. One cleared its significance test on exploration (+0.065) and came
  back at +0.001 on held-out data — a false positive caught only by the protocol.

**Also live:** a projection for the 2026-27 season, committed with a timestamped git tag before
opening night, with a scoring harness already built and running. It projects Philadelphia — who
added LeBron James and Jaylen Brown — at 49.2 wins and a 2.1% title chance, 9th of 30.

## The questions

1. **Is the negative framing a strength or a problem?** Roughly half the reported results are
   nulls, withdrawals, or self-identified failures. The author believes this is the project's
   main credibility asset for a quant audience. Is that right, or does it read as a project
   that did not work?

2. **Is the three-scale framing (shot / possession / game) a real insight, or a tidy story
   fitted after the fact to three unrelated null results?** The author is not neutral on this.

3. **Is the optimal-stopping result strong enough to lead with?** Its limitation is that a
   declined shot leaves no record, so "teams under-relax" rests on the accepted distribution
   moving less than continuation value. An alternative reading — that late options genuinely
   shrink, so there is nothing worse to accept — is not excluded.

4. **Should the projection layer stay?** It depends on a third-party impact metric (DARKO),
   is calibrated at n = 30 on a single season, and emits a headline percentage far more precise
   than its inputs support. It is already scoped into its own section with those caveats. Keep,
   cut, or shrink further?

5. **Is it time to stop building?** Three pre-registered tests just returned nothing. The
   author reads that as the vein being worked out and wants to stop adding and let the live
   prediction score itself through the season. Agree?

## What would be unhelpful

Line-by-line code critique (you cannot see it run), praise, or invented verification. The
useful output is a view on direction: what to lead with, what to cut, and whether the honesty
strategy is the right bet for the audience.
