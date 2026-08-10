# The NBA's 2-for-1 is a fair trade, not free points

NBA teams hurry by **3.6 seconds** when a 2-for-1 is available. The extra trip is real—but in a
held-out test its net value is statistically indistinguishable from zero. Teams surrender about
**0.073 points of continuation value** by shooting early, almost exactly what the extra possession
returns. Real possession durations blur the textbook alternating-possession advantage: the
measured end-period sawtooth is only **0.035–0.041 points**, not roughly 0.49.

That result comes from reconstructing the shot clock for **2,018,360 NBA shots from 2015-16
through 2024-25**, validating it against independent NBA splits, and valuing the option to keep a
possession alive. The same machinery produces a second, more ambitious application: team
continuation profiles that identify possessions for film review. Those profiles are persistent
and robust, but they are not causal coaching grades.

Read the [short paper](PAPER.md), browse the [shareable dashboard](docs/index.html), or inspect the
complete [results registry](RESULTS.md).

## The project in one minute

| Result | What the data says |
|---|---|
| Reconstruction | 96.0% of shots receive a usable clock; reconstructed player/bucket FGA agrees with the NBA at R² = 0.973. |
| Raw efficiency | Efficiency declines late, but possessions surviving that long are selected on earlier actions failing. The raw curve is descriptive, not causal. |
| Shoot or continue | Offenses lower their accepted-shot standard more slowly than continuation value decays. Because the continuation sample is adversely selected, this is an upper-bound diagnosis rather than recovered points. |
| Miss value | Offensive-rebound value matters most late: retention is 23.2% at 0-3 seconds versus roughly 14% mid-clock. Pricing it strengthens the stopping result. |
| 2-for-1 | Teams hurry by 3.6 seconds, surrender 0.073 points of continuation value, and gain no detectable net advantage. Duration variance explains why. |
| Team profiles | The construct survives foul repricing, a new-season test, specification changes, and defender adjustment on a valid tracking subset. It remains a film-review queue, not a coaching grade. |
| Prescriptive validation | Accounting and temporal gates passed. The public tracking gate missed its frozen coverage threshold (78.55% versus 80%), and the 200-possession blinded film sample still needs two human coders. |
| Forecasting | Current below-curve share does not robustly predict the next 20 games after current offense, shot value, and timing are controlled (p = 0.378). |
| Useful nulls | Creation-profile overlap adds essentially nothing beyond usage; player stopping scores mostly identify who finishes possessions; short-run possession “momentum” changes next-shot timing by only 0.30 seconds. |

The complete result registry is in [RESULTS.md](RESULTS.md). The long-form research record is in
[reports/findings.md](reports/findings.md), and the implementation and validation details are in
[METHODOLOGY.md](METHODOLOGY.md).

## Why reconstruct the clock?

Public shot data supplies only six broad clock buckets. Play-by-play supplies the game clock at
every event and identifies the events that reset the shot clock. Walking each period in order
makes it possible to recover the clock continuously while respecting:

- 24-second resets after changes of possession;
- `max(remaining, 14)` after frontcourt resets;
- the pre-2018 rule that returned offensive rebounds to 24 seconds;
- dead-ball free throws, phantom rebound bookkeeping, and non-monotone feed timestamps;
- an empirically calibrated two-second inbound delay after made field goals.

Rows requiring an invented reset are marked low confidence and left missing. They are not silently
placed at 24 seconds.

### Independent validation

The calibration target is shot-clock violations, where the true clock is exactly zero. The NBA's
published 2024-25 player/bucket splits are never used to fit the reconstruction and remain a clean
validation set.

| Validation check | Result |
|---|---:|
| Mean absolute bucket-share error | 1.19 percentage points |
| Mean absolute bucket eFG error | 1.05 percentage points |
| Player × bucket FGA/game R² | 0.973 |
| Player × bucket FG% R² | 0.646 |
| Shots with usable reconstructed clock | 96.0% |

## The central analytical object

`V(t)` is expected possession value when the offense continues with `t` seconds remaining. It is
priced at possession level, so points scored after an offensive rebound stay attached to the
original possession.

For a taken shot, the project compares:

```text
shot value = expected points from the attempt
           + P(offensive rebound | shot context) × second-chance value

continuation gap = V_team(t) - shot value
```

This comparison supports three questions that must remain separate:

1. **Style:** When does the team shoot?
2. **Capability:** What does the team historically create if it continues?
3. **Deviation:** How often are taken shots below that team's own continuation curve?

Only the third is even a candidate decision-quality measure, and it still is not causal. A taken
shot is observable; a look that was passed up is not. The analysis can surface “possibly continue”
possessions for film review, but low exposure cannot prove that a team should shoot sooner.

## Team and player interpretation

Raw below-curve exposure is positively associated with offense. Strong offenses preserve a more
valuable continuation option, which raises the opportunity cost of otherwise reasonable shots.
The dashboard therefore combines outcome and exposure rather than presenting a waste ranking.

The most informative mechanism results are:

- **67.4%** of league exposure comes from non-restricted-area paint shots; threes contribute less
  than 1%.
- Houston receives **77.3%** of its exposure from non-RA paint shots and remains second-highest
  after matching shot family, clock phase, and possession origin.
- Orlando receives **75.3%** from non-RA paint shots, but most of its aggregate profile is explained
  by the coarse context mix itself.
- In close fourth quarters, Houston records **0.0162 exposure per shot** versus 0.0055 league-wide,
  while its shot timing is almost identical to league timing. That is more consistent with
  creation difficulty under pressure than simple impatience.
- Players carry a moderate team-relative fingerprint when changing teams (+0.462), while their
  raw change tracks the new team environment more strongly (+0.785).

Player tables identify the possession ender. They do not identify who called the play, passed up
an earlier look, delivered the ball late, or was assigned the bailout role.

## Interactive dashboard

```bash
make app
```

The Streamlit dashboard includes:

- continuous efficiency and possession-value curves;
- the two-chapter Decision Atlas: shoot-or-hold and end-of-period handover value;
- team outcome, style, capability, and deviation profiles;
- clock-phase and shot-family decomposition;
- close-fourth creation pressure and player possession-ender context;
- reconstruction validation, the rule-change study, player grades, and projection outputs.

## Reproduce the project

Python 3.11+ is recommended.

```bash
make install
make backfill       # download and reconstruct 2015-16 through 2024-25
make validate       # compare reconstruction with independent NBA aggregates
make score          # fit xPTS and score every shot
make stopping       # continuation curve and exercise boundary
make rebound        # rebound option and possession repricing
make value          # exploration-window team profiles
make value WINDOW=holdout
make prospective    # next-block test
make mechanisms     # context, roster, game-state, and sequence checks
make twoforone
make endgame
make test
make app
```

Raw and processed data are intentionally not committed. Generated result tables are committed in
`reports/`, so the claims can be inspected without downloading the full event archive.

## Repository map

```text
README.md                 concise public overview
RESULTS.md                index of every major result and its status
METHODOLOGY.md            reconstruction, models, validation, and limitations
PROJECT_CONTEXT.md        compact context for contributors and review agents
PREREGISTRATION.md        frozen 2026-27 projection and amendment history

src/possval/
  ingest/                 archive download and verification
  clock/                  reconstruction state machine, calibration, validation
  features/               shot features and on-court lineups
  models/                 valuation, stopping, rebound, team, endgame, projection
  pipeline.py             command-line entry points

app/dashboard.py          Streamlit research interface
reports/findings.md       complete chronological research record
reports/*.csv             generated result tables
tests/                    golden sequences, invariants, and estimator recovery
```

## Research discipline

- Splits are chronological by season, never random.
- Exploration and holdout windows are labeled explicitly.
- Pre-registered hypotheses remain reported when they fail.
- Feature value is measured by ablation rather than permutation importance when features have
  deterministic substitutes.
- Standard errors are clustered at the level where identifying variation occurs.
- The 2018-19 scoring effect is withdrawn because nine season clusters and a feed change do not
  support the original inference.
- The 2026-27 projection is separate from the possession research and retains both its original
  frozen artifact and documented corrected version.

The largest unresolved limitation is selection into continuation: possessions still alive late
are the ones where earlier actions failed. Public feeds also lack defender proximity and play-call
labels. Those are identification limits, not missing error bars, and the project treats them that
way.
