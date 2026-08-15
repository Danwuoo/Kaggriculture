# Runbook

Run from the repository root.

```powershell
python research\dual_incumbent_topology_search_2026-08-14\async_v2\cli.py build-library --output research\dual_incumbent_topology_search_2026-08-14\async_v2\artifacts\motif_library.json
python research\dual_incumbent_topology_search_2026-08-14\async_v2\cli.py compile-smoke --library research\dual_incumbent_topology_search_2026-08-14\async_v2\artifacts\motif_library.json --output research\dual_incumbent_topology_search_2026-08-14\async_v2\artifacts\compile_smoke.json
python research\dual_incumbent_topology_search_2026-08-14\async_v2\cli.py search --library research\dual_incumbent_topology_search_2026-08-14\async_v2\artifacts\motif_library.json --run-root research\dual_incumbent_topology_search_2026-08-14\async_v2\artifacts\technical_search --population 6 --generations 2 --workers 15
python research\dual_incumbent_topology_search_2026-08-14\async_v2\cli.py status --run-root research\dual_incumbent_topology_search_2026-08-14\async_v2\artifacts\technical_search
python -m unittest discover -s research\dual_incumbent_topology_search_2026-08-14\async_v2 -p "test_*.py" -v
```

`search` refuses every seed other than `811407`.  Formal search is deliberately
absent from this CLI until a separate frozen protocol is reviewed.

`--workers` defaults to 15 and rejects values above 15.  The retained E1 seeds
`81426017` and `81426029` must be read only from their existing artifacts; do
not pass either seed to a search or verification command.  The progressive E1b
protocol is documentation only and has `execute_in_this_development=false`.

`topology_space.py` reports compile-distinct nonempty semantic capacity.  Do
not label that number behavior-changing.  Exact observed change is reported
separately from lane-control action digests in the technical search summary.
Seed accounting in every new manifest keeps technical, retained/consumed E1,
fresh, and formal authorization fields independent.
Formal launcher validation additionally requires an explicit schema-v2 seed
partition matching the frozen registry and its hash.  Never populate
`fresh_evaluation_seeds` from the complete evaluation set.
Pass the protocol-selected registry path to both `_manifest_body` and
`run_search`; resume must compare the resulting registry run-id and file hash.
Treat `*_configured` as intent only.  Do not report retained/fresh execution
until `execution_started` is true.
