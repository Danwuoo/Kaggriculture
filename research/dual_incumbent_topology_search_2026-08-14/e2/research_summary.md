# E2 topology research summary

Date: 2026-08-15
Current decision: **READY_FOR_E2_S2_FRESH_CONFIRMATION**
Promotion status: not promoted
Kaggle technical submissions executed: true (user-authorized; not promotion)

This is the consolidated entry point for E2 development, formal S1/S2, the
Boatlee remediation, and the two user-authorized technical submission
artifacts. The individual decision files and machine-readable artifacts remain
authoritative for their respective gates.

## Outcome by stage

| Stage | Evidence | Decision |
| --- | --- | --- |
| Development | Technical seed `811407`; no E2 fresh seed | `READY_FOR_E2_S1` |
| S1 | Fresh seeds `42284410`, `73912654` | Advance Boatlee unchanged; stop v27 |
| S2 | Fresh seeds `95715007`, `41193493`, `61594307`, `58893729` | Reject the always-on Boatlee block; remediation required |
| Remediation | Diagnostics over the 48 consumed S1/S2 contexts; no new fresh seed | Freeze one public-state selector for fresh confirmation |
| Technical packaging and server smoke | Correctness seed `811407`, both seats; Kaggle validation replays | Both standalone files execute correctly through the required server entrypoint; no efficacy or promotion claim |

All six E2 formal seeds are now consumed. Do not rerun them as fresh evidence.
The older E1 seeds `81426017` and `81426029` also remain consumed. Seed
registries record their prelaunch state; the formal execution roots and S1/S2
decisions record the completed runs.

## Lane decisions

### v27 current meta

The exact E1c probe `ac_46448f767f398cc4ce8047d3` remained diagnostic-only.
The delayed public selector `e2v27_8b3ebcb128a4f4709ea94ce3` intervened in two
fresh S1 contexts and changed receipts/public state, but all 16 paired terminal
margins and own-bank deltas were zero. The v27 E2 lane stopped at S1 and has no
remediation candidate.

The retained representative `ac_bad79e4d71965c86b6b351a1` is the permanent
action-only no-op regression. An action digest difference cannot establish
efficacy without a receipt, public/economic state, terminal bank/reward, or
attributed economic-diagnostic difference from the lane control.

### Boatlee

The unchanged E1c finalist `ac_3aa759d7d7fc4a409c409326` was strong in S1,
but its always-on coupled step-240/241 market block failed S2 tail
characterization. Its S2 mean was positive only because one Roman context
contributed `+14235`; the other 31 contexts averaged `-243.26`. The failure
was a public-market externality rather than a runtime, crop-death, or
animal-escape failure.

Atomic diagnostics attributed the block as follows:

| Variant | Candidate | Consumed-context W/D/L | Median | Worst | Role |
| --- | --- | ---: | ---: | ---: | --- |
| Step 240 only | `ac_501500daa79fcb8068244d0e` | 8/4/36 | -51 | -639 | Rejected diagnostic |
| Step 241 only | `ac_a85701baf0cd39d61ab067d3` | 42/0/6 | 203 | -4229 | Useful but unsafe diagnostic branch |

One selector version is frozen:

- candidate: `e2boatlee_7f591d609cf14d89e6aa1599`;
- decision step: 240;
- intervention: exact step-241 fertilizer branch;
- public condition: fertilizer price at most `84` and public fertilizer
  inventory at least `10082`;
- fallback: unchanged Boatlee incumbent;
- rejoin: step 242;
- opponent identity/private opponent information: not used;
- strategy SHA-256 before the packaging-only server entrypoint:
  `b4ef9bff8cbba2dfaccacc320a32f707006158fcf905c02db02ad89fe0f6099a`.

On the 48 consumed contexts the selector produced 36 positive interventions,
12 incumbent fallbacks, and zero negative paired margins. This is diagnostic
fit, not fresh efficacy. The threshold perfectly separates Roman from the
other retained opponent families, so public-state proxy overfit remains the
main unresolved risk. Actual win delta was zero.

## Technical submission artifacts and server verification

The user separately authorized two independent, single-file technical
packages and later explicitly authorized Kaggle API submission. Each directory
contains only `main.py`, imports in isolation, stays below 5 MiB, and completed
the correctness seed from both seats on the audited official engine.

The first two public-selector smoke attempts (`55529498`, raw `main.py`, and
`55529549`, archive) exposed a packaging defect: the generated file exported
`agent` but omitted Kaggle's required `_kaggle_submission_entrypoint`. Kaggle
accepted both packages but their validation episodes returned only `PASS`.
The builder now separately freezes the strategy bytes and appends only this
server adapter:

```python
def _kaggle_submission_entrypoint(obs, configuration=None):
    return agent(obs, configuration)
```

The local verifier invokes the same entrypoint. This repair changed package
hashes but not either strategy hash or action digest.

| Artifact | Candidate | Strategy SHA-256 | Packaged `main.py` SHA-256 | Role |
| --- | --- | --- | --- | --- |
| `submission/e2_boatlee_public_selector/main.py` | `e2boatlee_7f591d609cf14d89e6aa1599` | `b4ef9bff8cbba2dfaccacc320a32f707006158fcf905c02db02ad89fe0f6099a` | `17b149a652b3c7ebb7d46482ecff3f81103f65287409d3281cd732bca86451f6` | Preferred fresh-confirmation candidate |
| `submission/e2_boatlee_step_241_only/main.py` | `ac_a85701baf0cd39d61ab067d3` | `13ac97f6f9c311b52e18ca42ffc1916e09ba12f2dd4aba7fd0f525ba63c5101c` | `3fdef34507528484cbad579e2d8c5e8bc831bf5493e95e720cd111a971b68634` | Diagnostic/risk comparator only |

Both repaired archives completed Kaggle's mirrored validation game:

| Variant | Submission | Validation episode | Result | Server actions |
| --- | ---: | ---: | --- | --- |
| Public selector | `55529631` | `93331533` | `DONE/DONE`, rewards `57528/57674` | 719 calls and 690 non-pass actions per seat; max 10 market orders |
| Step 241 only | `55529790` | `93333341` | `DONE/DONE`, rewards `57528/57674` | 719 calls and 690 non-pass actions per seat; max 10 market orders |

These are server-runtime smoke tests, not matched efficacy games. They do not
promote either artifact, supply fresh-confirmation evidence, or change the E2
decision. Step 241-only retains the known Roman tail and remains excluded from
all efficacy frontiers unless a new contract explicitly challenges that
decision. Machine-readable package, replay, submission, and archive hashes are
in `submission_variant_verification.json` and
`submission_server_verification.json`.

## Engine and controls

- audited engine commit: `bded87b0d7879078c726a93a4884d044f79c4eed`;
- Python SHA-256:
  `fb9215c5e21a25243e2d13e75b3d70a79cf7d78fff150a90f1bb5eacf9ba2bcf`;
- configuration SHA-256:
  `7f196f4aaf9b4e482fbd61ba4bf19f5cec4da0f81938ece756954035a65c0bb5`;
- Boatlee control SHA-256:
  `69ce4f657df5a168c676acfa4f9089a373bc291fe3486950de0bca16ad042213`;
- v27 control SHA-256:
  `ec7d384806d4717b91c8f7f8da20710b054fdcb729abd767328c7520fa01bec0`.

Controls, caches, scores, candidates, and decisions were lane-local throughout.

## Next authorized research step

No fresh confirmation seed has been selected or executed after remediation.
The next efficacy action is a separately authorized, smallest paired fresh
confirmation of the frozen Boatlee public selector. It must preserve the
existing selector bytes and thresholds, keep both seats and opponent-family
strata explicit, and stop on a renewed Roman/seat-sensitive tail. v27 remains
stopped and must not be pooled into the Boatlee decision.

## Evidence map

- development: `development_decision.md` and
  `artifacts/development/e2_development_20260815_v3/development_verification.json`;
- S1: `s1_decision.md`, `s1_decision.json`, and
  `artifacts/formal/e2_s1_20260815_fresh_v4/`;
- S2: `s2_decision.md`, `s2_decision.json`, and
  `artifacts/formal/e2_s2_20260815_boatlee_tail_v1/`;
- remediation: `remediation_decision.md`,
  `remediation_candidate_registry.json`, and `remediation_verification.json`;
- technical packages: `submission_variant_verification.json` and
  `build_submission_variants.py`;
- Kaggle server smoke: `submission_server_verification.json`.
