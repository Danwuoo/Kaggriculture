"""Build the two independently packaged Boatlee E2 submission variants."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ASYNC_V3 = HERE.parent / "async_v3"
sys.path[:0] = [str(HERE), str(ASYNC_V3)]

from boatlee_remediation import remediation_candidates  # noqa: E402
from boatlee_selector import SELECTORS, render_selector  # noqa: E402
from materialize import render_standalone  # noqa: E402


BASE = (
    ROOT
    / "research"
    / "main_approach"
    / "boatlee_v16_rc2_market_relay"
    / "main.py"
)
VARIANTS = {
    "public_selector": {
        "candidate_id": "e2boatlee_7f591d609cf14d89e6aa1599",
        "directory": ROOT / "submission" / "e2_boatlee_public_selector",
        "strategy_sha256": "b4ef9bff8cbba2dfaccacc320a32f707006158fcf905c02db02ad89fe0f6099a",
        "sha256": "17b149a652b3c7ebb7d46482ecff3f81103f65287409d3281cd732bca86451f6",
    },
    "step_241_only": {
        "candidate_id": "ac_a85701baf0cd39d61ab067d3",
        "directory": ROOT / "submission" / "e2_boatlee_step_241_only",
        "strategy_sha256": "13ac97f6f9c311b52e18ca42ffc1916e09ba12f2dd4aba7fd0f525ba63c5101c",
        "sha256": "3fdef34507528484cbad579e2d8c5e8bc831bf5493e95e720cd111a971b68634",
    },
}
SERVER_ENTRYPOINT = """
def _kaggle_submission_entrypoint(obs, configuration=None):
    return agent(obs, configuration)
"""


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def render_variants() -> dict[str, bytes]:
    selector = SELECTORS[0]
    if selector.candidate_id != VARIANTS["public_selector"]["candidate_id"]:
        raise RuntimeError("public-selector identity drifted")

    ablation = remediation_candidates()["step_241_only"]
    if ablation.candidate_id != VARIANTS["step_241_only"]["candidate_id"]:
        raise RuntimeError("step-241-only identity drifted")

    strategy = {
        "public_selector": render_selector(
            BASE.read_text(encoding="utf-8"), selector
        ).encode("utf-8"),
        "step_241_only": render_standalone(ablation).encode("utf-8"),
    }
    for name, content in strategy.items():
        observed = _sha256(content)
        expected = str(VARIANTS[name]["strategy_sha256"])
        if observed != expected:
            raise RuntimeError(
                f"{name} strategy artifact drifted: expected {expected}, observed {observed}"
            )
    rendered = {
        name: (
            content.decode("utf-8").rstrip()
            + "\n\n"
            + SERVER_ENTRYPOINT.strip()
            + "\n"
        ).encode("utf-8")
        for name, content in strategy.items()
    }
    for name, content in rendered.items():
        observed = _sha256(content)
        expected = str(VARIANTS[name]["sha256"])
        if observed != expected:
            raise RuntimeError(
                f"{name} package artifact drifted: expected {expected}, observed {observed}"
            )
    return rendered


def build(*, check: bool) -> dict[str, Any]:
    rendered = render_variants()
    results: dict[str, Any] = {}
    for name, metadata in VARIANTS.items():
        directory = Path(metadata["directory"])
        target = directory / "main.py"
        if directory.exists():
            unexpected = sorted(
                path.name for path in directory.iterdir() if path.name != "main.py"
            )
            if unexpected:
                raise RuntimeError(
                    f"refusing to alter non-main.py entries in {directory}: {unexpected}"
                )
        content = rendered[name]
        if check:
            if not target.is_file() or target.read_bytes() != content:
                raise RuntimeError(f"stale or missing submission artifact: {target}")
        else:
            directory.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        results[name] = {
            "candidate_id": metadata["candidate_id"],
            "strategy_sha256": metadata["strategy_sha256"],
            "path": str(target),
            "bytes": len(content),
            "sha256": _sha256(content),
            "server_entrypoint": "_kaggle_submission_entrypoint",
            "directory_entries": sorted(path.name for path in directory.iterdir()),
            "check": check,
        }
    return {
        "schema_version": 1,
        "kind": "e2_boatlee_submission_variants_build",
        "base_path": str(BASE),
        "base_sha256": _sha256(BASE.read_bytes()),
        "variants": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    print(json.dumps(build(check=args.check), sort_keys=True))


if __name__ == "__main__":
    main()
