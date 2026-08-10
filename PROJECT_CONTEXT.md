# Project context for contributors and review agents

This file is the compact, shareable map of the repository. It contains project state and research
guardrails, not private review notes or a task work order.

## Objective

Reconstruct a per-shot NBA shot clock from public play-by-play, validate it independently, and use
it to understand possession value and offensive decision context. The project is explanatory: it
aims to make quantitative patterns line up with recognizable basketball mechanisms, not to claim a
betting edge or issue decontextualized coaching grades.

## Current research thesis

The shot clock matters most at possession scale. It contributes little to shot-make prediction and
almost nothing to live win probability, but it makes continuation value measurable.

The current team work distinguishes:

1. **Outcome:** points scored per possession.
2. **Style:** when the team shoots.
3. **Capability:** what the team historically creates by continuing.
4. **Deviation:** how often a taken shot falls below the team's continuation curve.

Deviation is one-sided and descriptive. Taken shots are recorded; passed-up shots are not. A high
value can identify possessions for film review, while a low value cannot establish that a team
should shoot sooner.

## Most important current results

- Reconstruction validation: 96.0% usable clocks and player/bucket FGA R² = 0.973.
- Possession-value curve: held-out shape calibrates to 0.0093 mean absolute error after one
  league-level shift.
- Team below-curve share: 79.5% signal beyond a team-game permutation null; cross-window
  persistence ρ = +0.398.
- The team measure is not a waste ranking. Strong offenses often have higher exposure because
  their continuation option is better.
- Non-restricted-area paint attempts produce 67.4% of exposure league-wide.
- Orlando's review-queue profile is mostly explained by shot/context mix. Houston remains
  second-highest after coarse context matching.
- Houston's close-fourth exposure is 0.0162 per shot versus 0.0055 league-wide with normal timing,
  supporting a creation-under-pressure interpretation.
- The prospective next-20-game test is null after current-offense controls (p = 0.378).
- Player-relative tendencies partly travel across teams (+0.462), but the new team environment
  moves the raw measure more strongly (+0.785).
- Previous possession outcome changes next first-shot timing by only 0.30 seconds.

See [RESULTS.md](RESULTS.md) before repeating or extending an analysis.

## Data conventions

- `SEASON` is the starting year: `2023` means 2023-24.
- A **chance** is one shot-clock interval.
- A **possession** continues through offensive rebounds and ends when the offense changes.
- `SHOT_CLOCK` is seconds remaining, so a larger value means an earlier shot.
- `GAME_CLOCK_EXPIRING == 1` marks attempts with fewer than three period seconds; these are removed
  from shot-clock decision analyses.
- `SHOT_VALUE = XPTS + P(retain) × second_chance_value`.
- Exploration window: 2015-16 through 2021-22.
- Holdout window: 2022-23 through 2023-24.
- 2024-25 is the external xPTS/reconstruction test season where applicable.

Processed parquet files live in `data/processed/` and are intentionally ignored. Generated CSV
results in `reports/` are the committed inspection layer.

## Pipeline map

```text
raw play-by-play + shot detail
        │
        ├── clock reconstruction ── validation against NBA bucket splits
        │
        ├── shot features ── xPTS ── player grades / ablation
        │
        └── chance panel ── possession chaining
                              │
                              ├── continuation value / stopping boundary
                              ├── rebound option and second-chance value
                              ├── 2-for-1 and end-period handover value
                              └── team curves / player context / mechanisms
```

Primary implementation files:

- `src/possval/clock/reconstruct.py`: event-state machine.
- `src/possval/clock/validate.py`: independent validation.
- `src/possval/models/value.py`: possession curve, team curves, shot valuation.
- `src/possval/models/stopping.py`: shoot-or-hold framework.
- `src/possval/models/rebound.py`: possession chaining and rebound option.
- `src/possval/models/twoforone.py`, `endgame.py`: end-period decisions.
- `src/possval/models/team_profiles.py`: team/player diagnostics and context standardization.
- `src/possval/models/prospective.py`: next-block prediction test.
- `src/possval/models/mechanisms.py`: season, mover, game-state, and sequence analysis.
- `src/possval/pipeline.py`: CLI orchestration.
- `app/dashboard.py`: interactive presentation.

## Reproduction commands

```bash
make test
make lint
make validate
make stopping
make rebound
make value
make value WINDOW=holdout
make prospective
make mechanisms
make twoforone
make twoforone WINDOW=holdout
make endgame
make endgame WINDOW=holdout
make app
```

Do not run `make backfill` unless the processed data genuinely need rebuilding; it downloads and
processes ten seasons. Do not overwrite `reports/league_projection_2026_27_original.csv`; it is a
frozen pre-amendment artifact retained for auditability.

## Research guardrails

- Inspect existing reports and registrations before choosing a hypothesis.
- Preserve chronological splits; never substitute a random train/test split.
- Label post-hoc work exploratory.
- Keep style, capability, outcome, and deviation separate.
- Do not convert continuation gaps into “points left on the table.” The possession-specific
  counterfactual is unobserved.
- A player row identifies who ended the possession, not who caused the shot decision.
- Treat the 2018-19 scoring effect as withdrawn; only the shortening of chances is established.
- Report null results and failed holdouts rather than pruning them from the narrative.
- Add a generated artifact, a pipeline entry point, and estimator-recovery tests for any result
  promoted into the public findings.

## Good next questions

- Validate high-exposure early/middle-clock possessions against film or tracking data.
- Separate lineup creation capability from shot-family composition with sufficient sample sizes.
- Test whether the close-fourth Houston pattern holds in newer seasons and different roster eras.
- Develop a design for passed-up shots; without one, “shoot sooner” remains unidentified.

## Verification baseline

At the time this context file was written, the full suite passed **152 tests**, lint was clean, both
`make value` windows and `make mechanisms` completed, and the Streamlit app loaded without
exceptions. Re-run the checks after modifying code or public numerical claims.
