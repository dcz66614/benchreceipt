# P027 factory run log

- 2026-11-17 ~07:04 GMT: construction dispatched by main chat; coordinator session started; work dir + git repo created.
- 2026-11-17 ~07:24 GMT: T001 PASS, merged to main (f6c2363). T002 dispatched.
- 2026-11-17 ~07:30 GMT: T002 PASS, merged to main (4e87756). T003 dispatched.
- 2026-11-17 ~07:40 GMT: T003 PASS, merged to main (7bd8061). T004 (S0 gate) dispatched.
- 2026-11-17 ~07:55 GMT: S0 PASS 10/10 (coordinator-verified re-run), merged to main (5bafd91). T005 dispatched.
- 2026-11-17 ~08:00 GMT: T005 PASS, merged to main (11b6154). T006 dispatched.
- 2026-11-17 ~08:10 GMT: T006 PASS, merged to main (3a6844f). T007 dispatched.
- 2026-11-17 ~08:20 GMT: T007 PASS, merged to main (166bd2f). T008 dispatched.
- 2026-11-17 ~08:25 GMT: T008 PASS, merged to main (7d479c3). T009 + T010 dispatched in parallel.
- 2026-11-17 ~08:30 GMT: T009 + T010 PASS, merged to main (ffba31a). P1 seam reproduced (capture lacks junit summary). FIX-capture-junit dispatched; T011 follows after the fix.
- 2026-11-17 ~08:35 GMT: FIX-capture-junit CLOSED (seam verified fixed E2E), merged to main (fd487a3). T011 dispatched.
- 2026-11-17 ~08:40 GMT: T011 STOPPED on P0-01 (false PASS, verified by coordinator). NOT merged. Awaiting spec decision for the fix.
