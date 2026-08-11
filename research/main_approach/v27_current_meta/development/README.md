# v27_current_meta development source

This directory is the editable, decompressed source of truth.  The sibling
`main.py` is a generated single-file Kaggle artifact.

- `route_actions.json`
- `constants.py`
- `runtime.py`
- `weed_repair.py`
- `market.py`
- `agent.py`

After editing code or the readable 719-turn route, rebuild and verify with:

```powershell
python research\main_approach\v27_current_meta\development\build_standalone.py
python research\main_approach\v27_current_meta\development\build_standalone.py --check
```

Do not share modules or route data with another approach.  Cross-approach
similarity is provenance, not a reason to couple their editable sources.

## Performance contract

- Route actions are read-only templates. Aligned static turns return the
  template directly; a dynamic turn uses the action-schema copier once.
- Route hand counts, weed-candidate turns, and multi-SELL turns are computed
  once by `route.py` for development and emitted as literals by the builder.
- Weed repair and SELL ranking mutate only a materialized action. The final
  schema/hand-alignment projection remains immediately before return.
- The generated standalone uses deterministic JSON + zlib + Base64 route
  storage. It does not read the development route at runtime.
