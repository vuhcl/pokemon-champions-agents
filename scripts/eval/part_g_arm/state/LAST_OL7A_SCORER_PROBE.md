# OL7a class_scorer probe (before fix)

Key: `{bind Jolteon, ask}`; other bind=fail. Cell PARTIAL. Errata currently forces MUTATION-OK.

| outcome | observed class | key expected | pass/fail |
|---|---|---|---|
| (a) select Jolteon | bound | MUTATION-OK | PASS (bound=Jolteon) |
| (b) ask, no mutate | lookup only | MUTATION-OK | FAIL (bound=None) |
| (c) select other | bound | MUTATION-OK | PASS (bound=Garchomp) |

Problem: (b) fails (ask not MUTATION-OK); (c) passes (any bind matches MUTATION-OK).
