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
