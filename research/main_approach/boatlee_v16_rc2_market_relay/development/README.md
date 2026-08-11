# boatlee_v16_rc2_market_relay development source

This directory is the editable, decompressed source of truth.  The sibling
`main.py` is a generated single-file Kaggle artifact.

- `route_actions.json`
- `constants.py`
- `runtime.py`
- `weed_repair.py`
- `market.py`
- `livestock.py`
- `wool.py`
- `base_agent.py`
- `relay.py`
- `agent.py`

After editing code or the readable 719-turn route, rebuild and verify with:

```powershell
python research\main_approach\boatlee_v16_rc2_market_relay\development\build_standalone.py
python research\main_approach\boatlee_v16_rc2_market_relay\development\build_standalone.py --check
```

Do not share modules or route data with another approach.  Cross-approach
similarity is provenance, not a reason to couple their editable sources.

## Performance contract

- Route actions are read-only templates. Aligned static turns return the
  template directly; a dynamic turn uses the action-schema copier once.
- Route hand counts, weed/multi-SELL turns, livestock/wool turns, relay
  checkpoints, and relay target quantities are computed once by `route.py`
  for development and emitted as literals by this approach's builder.
- Weed, livestock, wool, market, and relay overlays share one dynamic action
  pipeline. The final schema/hand-alignment projection remains immediately
  before return.
- The generated standalone uses deterministic JSON + zlib + Base64 route
  storage. It does not read the development route at runtime.
