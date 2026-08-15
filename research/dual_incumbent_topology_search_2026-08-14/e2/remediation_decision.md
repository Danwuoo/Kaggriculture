# E2 S2 remediation decision

**READY_FOR_E2_S2_FRESH_CONFIRMATION**

The failed always-on Boatlee candidate remains byte-for-byte unchanged. Two
new attributable atomic ablations show that step 240 is broadly adverse
(`8/4/36`, median `-51`), while step 241 contains the useful fertilizer branch
(`42/0/6`, mean `+253.23`) and the Roman tail (worst `-4229`). The exact
full-block replay matched all 48 retained formal contexts.

One selector version is frozen: `e2boatlee_7f591d609cf14d89e6aa1599` with
standalone SHA-256
`b4ef9bff8cbba2dfaccacc320a32f707006158fcf905c02db02ad89fe0f6099a`.
At step 240 it uses only public fertilizer price and inventory. It schedules
the exact step-241 branch only when price is at most `84` and inventory is at
least `10082`; otherwise it preserves the incumbent. Preconditions are checked
at both steps, missing or changed state falls back, seat state is isolated, and
control rejoins at step 242.

On the 48 consumed S1/S2 contexts, exact selector execution is 36 positive,
12 incumbent draws, and zero negative paired margins, with mean `+273.90`,
median `+155.5`, mean own-bank delta `+1681.15`, and worst `0`. Observed
behavior and captured features match the predeclared branch prediction in
48/48 contexts. Worker 1-versus-4 matches in 8/8 contexts; technical seed
fast-versus-standalone matches in both seats; failure injection passes 2/2;
maximum p95 and call latency are `0.444 ms` and `13.473 ms`.

This is development and diagnostic evidence only. No new fresh seed was
selected or executed, and no efficacy claim is assigned. The threshold also
perfectly separates Roman from the other retained opponent families, so it may
still be a public-state proxy overfit even though the features are causal and
legal. A new formal-fresh S2 confirmation is mandatory before promotion or
submission packaging and requires separate authorization. v27 remains stopped,
lanes remain unpooled, and no later tier has been launched.
