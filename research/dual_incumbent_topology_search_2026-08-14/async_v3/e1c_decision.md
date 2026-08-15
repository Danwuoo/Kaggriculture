# Async V3 E1c decision

Decision: `E1C_COMPLETE_PROCEED_TO_E2_DEVELOPMENT`

The E1c retained-seed run completed all 5,792 declared jobs: 5,776 candidate
contexts and 16 frozen controls. All retained games ended `DONE`/`DONE`; the
finalist fast-versus-standalone parity checks passed. The run used 15 Windows
spawn workers and only already-consumed seeds `81426017` and `81426029`.
`formal_fresh_seeds_executed=false`.

E1 expansion stops here. The best useful Boatlee result was already present in
generation 0, the best v27 high-upside result in generation 1, and generations
22--23 did not improve either direction. More generations over the same surface
are not justified.

## Lane decisions

### Boatlee V16-RC2 market relay

Carry `ac_3aa759d7d7fc4a409c409326` into E2 as the fixed lane-local finalist.
It is a one-block market-route patch over steps 237--245 with effective orders
at steps 240 and 241. On the retained E1 screen it produced:

- mean paired margin `+307.125`;
- worst paired margin `+6`;
- mean own-bank delta `+1059`;
- non-negative evidence in both tested opponent families;
- actual win delta `0`.

The complexity-two variant improved the mean by only `0.5` coin with the same
worst result. Prefer the one-block representative. Do not mutate it during E2
S1; any repaired or extended version receives a new candidate ID and remains a
separate candidate.

### v27 current meta

Carry `ac_46448f767f398cc4ce8047d3` only as a high-upside diagnostic probe and
public-selector source. Its step-0 ordered market topology and step-494 removal
produced:

- mean paired margin `+11251.125`;
- actual win delta `+4`;
- mean own-bank delta `+19247`;
- worst paired margin `-6131`;
- only one opponent-family stratum satisfying the run's non-negative-family
  criterion.

It is not an always-on finalist. E2 may develop a bounded public-state selector
that chooses between this topology and the v27 incumbent, but may not use
opponent identity or private-opponent information.

The selected v27 "robust" representative
`ac_bad79e4d71965c86b6b351a1` had zero paired-margin, own-bank, and win effect
in all eight contexts. Its action digest changed while the effective economic
outcome did not. Retain it as a negative regression fixture and exclude it from
all efficacy and promotion frontiers.

## Ranking repair required before E2

An action-digest difference alone is not an observed topology effect. E2 must
count a context as effectively changed only when candidate-versus-control
evidence changes at least one of:

- executed market receipt digest;
- public/economic state digest;
- own or opponent terminal bank/reward;
- attributed economic diagnostics.

A candidate with only syntactic action changes is a no-op counterexample. It
may be retained for compiler analysis but cannot be robust, high-upside, an E2
finalist, or an efficacy-scored selector label.

## Frozen evidence

- Search summary file SHA-256:
  `fa0b2ee3ea9105b236352e17757ddb36d226fd81cef18d4acf53008fc7fa837b`
- Embedded canonical summary SHA-256:
  `5f70c83f1b94fa2d9eafcdd0811ee751f4d824dcdea9a39085439ed08a73a5b1`
- Manifest file SHA-256:
  `68e561b2ea18c92c5954c8878efea0aa877e20a4c8e1693cf15913294f7e2f86`
- Embedded manifest SHA-256:
  `eabc538ce8962fc073036d5443e058db3593fdb64cb538b827bad57b2cd2f1ea`
- Protocol file SHA-256:
  `e264a120385e3916757df6de52b94c49b508ee32264367f17c8f03e04f4e81fa`
- Launch file SHA-256:
  `3979442dafaa2d8216390c59da0e19ae09f0d14cc19dee3a7d62c59a07b91b85`
- Boatlee finalist standalone SHA-256:
  `54ce17ad14ef49aaa6c985ccd4245e06c82a450b39de65b9f14c412b3c7930c6`
- Retained v27 no-op standalone SHA-256:
  `b8b2aa6894ff75c9dac8d36d37609e5591d3a5f0c167afde8002fc9fe5b9bc69`

The compact summary, protocol, launch evidence, and finalist standalones are
committed. Raw shards, caches, generation files, manifest, checkpoint, and logs
remain preserved in the original local workspace and are ignored because they
occupy roughly 436 MiB. They must not be deleted, normalized, or overwritten.

## Boundary

E2 development is authorized only after its contract is read. This decision
does not select or execute a fresh seed, launch E2 S1, package a submission, or
promote either incumbent.
