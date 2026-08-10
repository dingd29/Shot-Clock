# Blinded possession-review protocol

This is Gate 4 of `preregistration_team_validation.md`. It is deliberately a human basketball
review, not another model. Gates 1–3 can establish that the statistical profile survives accounting,
defender distance, a new season, and specification changes; only film can establish whether a
credible continuation was actually available.

## Frozen sample

`python -m possval.pipeline team-review-sample` produces 200 possessions in a random order:

- 50 upper-quartile positive-exposure, early/middle-clock Houston possessions;
- 50 equivalent Orlando possessions;
- 50 equivalent Boston possessions. Boston was fixed before viewing film because it ranked first
  in held-out offense and provides a high-capability comparison;
- 50 zero-exposure controls matched exactly on season, broad clock phase, shot family, possession
  origin, and score state.

The private `.review/` directory is gitignored. `team_review_worksheet.csv` contains only a random
review ID, event video link, and blank labels. `team_review_key.csv` contains team, player, model
gap, sample group, and matching context and must remain closed until coding is complete. Broadcast
video may reveal identities; coders should not research the team profile or model score.

## Labels

Code each item independently:

1. `LIVE_ADVANTAGE_REMAINED`: did the offense still have a live advantage at release?
2. `CREDIBLE_CONTINUATION_AVAILABLE`: could a reasonable pass, drive, re-screen, swing, or reset
   plausibly improve the possession without assuming perfect execution?
3. `OPEN_TEAMMATE_OR_NEXT_ACTION`: was such an option visible?
4. `BAILOUT_AFTER_FAILED_ACTION`: was the attempt a necessary end to an already failed action?
5. `DEFENSIVE_PRESSURE_BLOCKED_CONTINUATION`: did pressure make continuing implausible?
6. `PRIMARY_ISSUE`: one of `shot choice`, `play design`, `personnel`, `model error`, `none/unclear`.
7. Confidence from 1 (guess) to 5 (clear), plus a short note.

Binary fields use `1`, `0`, or blank if the clip cannot adjudicate the question. A credible
continuation does not mean a guaranteed better result; it means a normal NBA action was visibly
available and plausibly preserved or improved the advantage.

## Reliability and decision rule

Two coders independently review at least the same 40 possessions. Run the scoring command only
after closing the key. Report Cohen's kappa for `CREDIBLE_CONTINUATION_AVAILABLE`; kappa must be at
least 0.60 or disagreements must be adjudicated and ambiguity reported. High-exposure cases must
exceed matched controls by at least 15 percentage points, and the difference cannot come only from
one team or shot family. Until those conditions are met, “teams should wait longer” remains
unlicensed.
