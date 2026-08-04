# Context for a reviewer

Written for someone landing cold with no history of the project. `README.md` sells it and
`METHODOLOGY.md` audits it; neither is organised for review. This maps claims to code, says
what can be checked without rebuilding anything, and hands over the weak points rather than
making you find them.

## If you cannot run code

Use [`reports/REVIEW_BRIEF.md`](reports/REVIEW_BRIEF.md) instead of this file. It is
self-contained — every number inline, no navigation — and aimed at direction-level review
rather than verification. The rest of this document assumes a terminal.

## Read in this order

1. **`README.md`** — what the project claims, ~15 minutes.
2. **`reports/findings.md`** — the numbers and their caveats. Sections 1-3 are descriptive,
   4b-4g are the tested claims, 5-6 are the fit and projection layers.
3. **`METHODOLOGY.md`** — how each number was produced and what went wrong on the way. Long,
   and the `>` blockquotes are where the bugs are documented.
4. **`reports/preregistration_exploration.md`** — three hypotheses registered before testing;
   none confirmed.

## Claim → code → artifact

| Claim | Code | Committed artifact |
|---|---|---|
| Shot-clock reconstruction | `clock/reconstruct.py`, `clock/rules.py` | — (validated below) |
| Validation vs NBA's published splits | `clock/validate.py` | `data/reference/official_shotclock_2024_25.csv` |
| Findings 1-3, efficiency curve | `features/shots.py` | — (from `shots_scored.parquet`) |
| Finding 4, ablation | `models/xpts.py` | `reports/ablation.csv` |
| Finding 4b, 2018 rule change | `models/rulechange.py` | `reports/rulechange_*.csv` |
| Finding 4d, optimal stopping | `models/stopping.py` | `reports/stopping_*.csv` |
| Finding 4e, team relaxation | `models/stopping.py::team_relaxation` | `reports/stopping_team_relaxation.csv` |
| Finding 4f, win probability | `models/winprob.py` | `reports/winprob_*.csv` |
| Finding 4g, pre-registered tests | scratch scripts, logs committed | `reports/exploration_h*.log` |
| Finding 5, creation overlap | `models/creation.py`, `synergy.py`, `lineup_synergy.py` | `reports/lineup_overlap_*.csv` |
| Finding 6, projection | `models/dpm_calibration.py`, `league.py`, `simulate.py` | `reports/league_projection_2026_27.csv` |
| Pre-registered projection | `models/scorecard.py` | `PREREGISTRATION.md` |

## What you can check without running anything

**All 24 report artifacts are committed.** Every published number can be traced to a CSV in
`reports/` without regenerating data. Arithmetic, internal consistency, and whether the prose
matches the tables are all checkable from a clone.

**No data is committed** — `data/processed/` is gitignored. To reproduce from scratch:

| Stage | Command | Rough cost |
|---|---|---|
| Download + reconstruct 10 seasons | `make backfill` | **hours**, mostly download |
| Train + score 2M shots | `make score` | ~1 min |
| On-court lineups | `make lineups` | ~10 min |
| Chance panel + stopping | `make stopping` | ~4 min |
| Win-probability test | `make winprob` | ~3 min |
| Ablation (9 refits) | `make ablate` | ~4 min |
| Tests | `make test` | 5 s, 79 tests |

If you only have an hour, `make test` and reading the CSVs gets you most of the way.

## Where I think the bodies are

Ranked by how much they'd change if you pushed. This is my own assessment, so treat it as a
starting point rather than a boundary.

1. **`XPTS` carries no defender proximity.** No public feed has it. Every shot-quality number
   is therefore selection, not contestedness, and the whole `stopping.py` layer inherits it —
   `V(t)` is "expected points given the shots this offense actually takes", not given what was
   available. Stated in the docs, but it is the deepest limitation and it is load-bearing.
2. **The stopping result's counterfactual is unobservable.** A declined shot leaves no record,
   so "teams under-relax" rests on the *accepted* distribution moving less than `V(t)`. An
   alternative reading — that the option set genuinely shrinks late so there is nothing worse
   to accept — is not excluded. I say this in 4d; I would push on whether I say it firmly
   enough.
3. **`V(t)` is estimated under observed policy**, so it is not a true continuation value under
   optimal play. I argue this is the right benchmark for a marginal question. That argument is
   worth attacking.
4. **The projection layer depends on DARKO**, calibrated at n = 30 on one season, against a
   snapshot that had already seen that season. Scoped in its own README section, but a
   reviewer may think even that is too generous.
5. **Finding 4b's efficiency effect is small and fragile** — t = −2.52 with two usable
   pre-period seasons that differ from each other by nearly the estimate's size.
6. **Chance-start-type classification comes from my own reconstruction**, not the feed. I
   validated it against the feed's Off/Def rebound counters at 99.8%, but only for rebounds.

## Deliberate — please don't "fix" these

Each looks wrong at a glance and is defended in `METHODOLOGY.md`:

- **NaN instead of a fabricated 24** for chances where a reset had to be invented. Imputing
  would corrupt the `24-22` bucket, where 84% of them sit.
- **Inbound delay calibrated on shot-clock violations**, not on the official bucket
  distribution. Fitting to the aggregates would destroy the validation.
- **Ablation instead of permutation importance** — `CLOCK_ELAPSED` is exactly `24 − SHOT_CLOCK`.
- **Clustering on team-season (lineups) and season (rule change)**, not on the row count.
  Un-clustered inflated one t-statistic from 2.9 to 5.0.
- **Field-goal points only** on both sides of the stopping comparison, for unit consistency
  with `XPTS`. Free throws are quantified separately and cut conservatively.
- **Specification curves** where the answer moves with defensible choices, rather than one
  number.

## What I would most like challenged

- Whether **finding 4d survives** the objection in weak point 2. It is the project's one strong
  positive result and it rests on an argument, not a measurement.
- Whether the **three-scale framing** in the README (shot / possession / game) is a real insight
  or a tidy story fitted to three unrelated nulls.
- Whether reporting so many **negative results** reads as rigour or as a project that did not
  work. I believe the former; I am not a neutral judge of it.

## Recent history worth knowing

Several published numbers changed after review, and the commit messages carry the reasoning:

- Finding 2's headline fell **36%** when buzzer-beater heaves were excluded.
- Finding 4's comparative claim was **withdrawn** when action type was grouped with location.
- Finding 4b flipped from "no effect" to a small real one after a **2017-18 feed artifact** was
  found — the NBA changed play-by-play timestamping one season before the rule.
- The per-player stopping measure was found to be **tautological** (r = 0.984 with shot
  quality) and is reported as a failure.
