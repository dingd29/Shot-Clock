# Possession Value — 45-second brief

I rebuilt the shot clock for 2.0 million NBA shots from public play-by-play and validated it against
independent NBA splits (96% usable; player-by-bucket FGA R² 0.973). That lets me price the option to
continue a possession, not just the shot a team took.

The cleanest finding is that the NBA's 2-for-1 is a fair trade, not free points: teams hurry by 3.6
seconds and surrender about 0.073 points of continuation value, while the held-out net gain is near
zero. Variable possession lengths explain why the textbook end-of-quarter advantage almost
disappears.

I also built team continuation profiles. They are persistent and survive foul, time-split,
specification, and valid-subset defender checks, but I deliberately stopped short of saying a team
“should wait longer”: public tracking coverage missed my preregistered threshold and a blinded
200-possession film review still needs human coders. The project is as much about honest research
discipline as it is about basketball modeling.
