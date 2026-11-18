# R4 current partial response — installed browser focal

Source/package cut `92529cf4d4d3660ac98e1c415fb60151aefaa9a7`, wheel `9204183fcb00628b311f417d9cc601bbc6060f2c1347d200cf433cb8e32773a8`. The app imported only the frozen installed prefix with `-I -B` and own helper files. The concurrently changing R5 checkout was not the product under test; no claim of a clean current-checkout source audit is made.

Nine checks passed in `cuts/r4-current-partial-ui/freshness-result.json`. Real Core sessions/turn results supply current Idle proof; the optional external source is disabled and overall coverage remains visibly partial. The card now says **Idle**, and the operational summary says **1 connected · 0 working · 1 Idle**, without “Last known” or “Previous snapshot.” Two actual successful 15-second fallback reads retained the same semantic revision while paused, without a false update notice. A single controlled browser transport abort made the retained Idle label stale and rendered an alert. A subsequent successful read restored the current label while still paused. This transport fault is not an actual Server or authorization failure.

Screenshots are copied with hashes under `screenshots-r4/`: `r4-current-idle.png` and `r4-failed-refresh.png`. The first was visually inspected. The own fixture and CLI browser closed normally, exit 0; no own-root process or listener remained. No provider, real harness, human trial or browser POST occurred. The intentional abort produced one expected console network error. No performance or percentile conclusion is drawn under concurrent host activity.

This focal does not qualify Working or erase the preserved R3 canonical parallel-work failure. R5 requires a separate frozen package and fresh fixture.
