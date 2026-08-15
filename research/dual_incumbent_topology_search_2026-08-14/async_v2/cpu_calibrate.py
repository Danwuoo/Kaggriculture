"""Measure the launched process tree while running a technical-only async smoke.

This is an offline launcher.  It intentionally delegates to ``cli.py search``,
whose evaluator is hard-bound to the consumed technical seed 811407.
"""

from __future__ import annotations

import argparse
import ctypes
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
from typing import Any

from library import atomic_json
from model import payload_hash


HERE = Path(__file__).resolve().parent


class _FileTime(ctypes.Structure):
    _fields_ = (("low", ctypes.c_uint32), ("high", ctypes.c_uint32))

    @property
    def ticks(self) -> int:
        return (int(self.high) << 32) | int(self.low)


class _ProcessEntry(ctypes.Structure):
    _fields_ = (
        ("size", ctypes.c_uint32),
        ("usage", ctypes.c_uint32),
        ("process_id", ctypes.c_uint32),
        ("default_heap_id", ctypes.c_size_t),
        ("module_id", ctypes.c_uint32),
        ("threads", ctypes.c_uint32),
        ("parent_process_id", ctypes.c_uint32),
        ("priority_class_base", ctypes.c_long),
        ("flags", ctypes.c_uint32),
        ("executable", ctypes.c_wchar * 260),
    )


def _system_times() -> tuple[int, int]:
    idle = _FileTime()
    kernel = _FileTime()
    user = _FileTime()
    if not ctypes.windll.kernel32.GetSystemTimes(  # type: ignore[attr-defined]
        ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
    ):
        raise ctypes.WinError()
    return idle.ticks, kernel.ticks + user.ticks


def _cpu_between(before: tuple[int, int], after: tuple[int, int]) -> float:
    idle = after[0] - before[0]
    total = after[1] - before[1]
    if total <= 0:
        return 0.0
    return max(0.0, min(100.0, 100.0 * (total - idle) / total))


def _process_parents() -> dict[int, int]:
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    invalid_handle = ctypes.c_void_p(-1).value
    if snapshot == invalid_handle:
        raise ctypes.WinError()
    result: dict[int, int] = {}
    entry = _ProcessEntry()
    entry.size = ctypes.sizeof(entry)
    try:
        present = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while present:
            result[int(entry.process_id)] = int(entry.parent_process_id)
            present = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return result


def _descendants(root_pid: int, root_created: int) -> set[int]:
    parents = _process_parents()
    result = {int(root_pid)}
    changed = True
    while changed:
        changed = False
        for process_id, parent_id in parents.items():
            if parent_id in result and process_id not in result:
                process_times = _process_times(process_id)
                # Windows retains only a parent PID, so PID reuse can make an
                # older unrelated process look like a child of this launcher.
                if process_times is None or process_times[0] < root_created:
                    continue
                result.add(process_id)
                changed = True
    return result


def _process_times(process_id: int) -> tuple[int, int] | None:
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    handle = kernel32.OpenProcess(0x1000, False, int(process_id))
    if not handle:
        return None
    created = _FileTime()
    exited = _FileTime()
    kernel = _FileTime()
    user = _FileTime()
    try:
        if not kernel32.GetProcessTimes(
            handle,
            ctypes.byref(created),
            ctypes.byref(exited),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            return None
        return created.ticks, kernel.ticks + user.ticks
    finally:
        kernel32.CloseHandle(handle)


def _tree_cpu_sample(
    root_pid: int,
    root_created: int,
    previous: dict[int, tuple[int, int]],
    elapsed_seconds: float,
    logical_processors: int,
) -> tuple[float, dict[int, tuple[int, int]], int]:
    current = {
        process_id: process_times
        for process_id in _descendants(root_pid, root_created)
        if (process_times := _process_times(process_id)) is not None
    }
    interval_ticks = max(elapsed_seconds, 1e-9) * 10_000_000.0
    delta_ticks = 0.0
    for process_id, (created, ticks) in current.items():
        old = previous.get(process_id)
        if old is not None and old[0] == created:
            delta_ticks += max(0, ticks - old[1])
        else:
            # The process was born between samples (or became observable one
            # sample late).  It cannot have used more than one core during the
            # interval; cap its initial contribution accordingly.
            delta_ticks += min(float(ticks), interval_ticks)
    percent = 100.0 * (delta_ticks / 10_000_000.0) / max(elapsed_seconds, 1e-9) / logical_processors
    percent = max(0.0, min(100.0, percent))
    return percent, current, len(current)


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1))
    return float(ordered[index])


def _summary(values: list[float]) -> dict[str, float | int]:
    return {
        "samples": len(values),
        "mean": statistics.fmean(values) if values else 0.0,
        "median": statistics.median(values) if values else 0.0,
        "p95": _percentile(values, 0.95),
        "maximum": max(values, default=0.0),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    if os.name != "nt":
        raise RuntimeError("cpu_calibrate.py requires Windows GetSystemTimes")
    if args.output.exists():
        raise FileExistsError(f"refusing to replace calibration evidence: {args.output}")
    args.run_root.mkdir(parents=True, exist_ok=False)
    stdout_path = args.run_root / "smoke.stdout.log"
    stderr_path = args.run_root / "smoke.stderr.log"
    command = [
        sys.executable,
        str(HERE / "cli.py"),
        "search",
        "--library",
        str(args.library),
        "--run-root",
        str(args.run_root / "search"),
        "--population",
        str(args.population),
        "--generations",
        str(args.generations),
        "--workers",
        str(args.workers),
    ]

    baseline_before = _system_times()
    time.sleep(float(args.sample_seconds))
    baseline = _cpu_between(baseline_before, _system_times())
    samples: list[float] = []
    tree_samples: list[float] = []
    tree_process_counts: list[int] = []
    throughput_samples: list[float] = []
    started = time.perf_counter()
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        process = subprocess.Popen(
            command,
            cwd=str(HERE.parents[2]),
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            creationflags=creationflags,
        )
        previous = _system_times()
        root_times = _process_times(process.pid)
        if root_times is None:
            raise RuntimeError("launched calibration process is not queryable")
        root_created = root_times[0]
        previous_tree = {
            process_id: process_times
            for process_id in _descendants(process.pid, root_created)
            if (process_times := _process_times(process_id)) is not None
        }
        previous_clock = time.perf_counter()
        previous_completed = 0
        while process.poll() is None:
            time.sleep(float(args.sample_seconds))
            current = _system_times()
            samples.append(_cpu_between(previous, current))
            previous = current
            current_clock = time.perf_counter()
            tree_percent, previous_tree, process_count = _tree_cpu_sample(
                process.pid,
                root_created,
                previous_tree,
                current_clock - previous_clock,
                int(os.cpu_count() or 1),
            )
            tree_samples.append(tree_percent)
            tree_process_counts.append(process_count)
            completed = len(list((args.run_root / "search" / "shards").glob("job_*.json")))
            throughput_samples.append(
                max(0, completed - previous_completed) / max(current_clock - previous_clock, 1e-9)
            )
            previous_completed = completed
            previous_clock = current_clock
        returncode = int(process.returncode or 0)
    wall_seconds = time.perf_counter() - started

    # The search has short serial control/parity phases.  Values clearly above
    # the pre-launch baseline are the representative parallel-search samples.
    active_threshold = max(10.0, baseline + 5.0)
    active = [value for value in samples if value >= active_threshold]
    if len(active) < max(3, len(samples) // 10):
        active = list(samples)
    # At least one full core indicates that the spawn pool is doing useful
    # evaluation work.  Serial trace/control/parity samples remain separately
    # visible in the all-phase summary.
    tree_active_threshold = 100.0 / int(os.cpu_count() or 1)
    tree_active = [value for value in tree_samples if value >= tree_active_threshold]
    if len(tree_active) < max(3, len(tree_samples) // 10):
        tree_active = list(tree_samples)
    pool_process_threshold = max(2, int(args.workers) + 1)
    tree_pool = [
        value
        for value, process_count in zip(tree_samples, tree_process_counts)
        if process_count >= pool_process_threshold
    ]
    if len(tree_pool) < 3:
        tree_pool = list(tree_active)
    result: dict[str, Any] = {
        "schema_version": 2,
        "purpose": "technical CPU calibration; no fresh formal seeds",
        "technical_seed": 811407,
        "formal_fresh_seeds_executed": False,
        "command": command,
        "workers": int(args.workers),
        "logical_processors": int(os.cpu_count() or 1),
        "population_per_lane": int(args.population),
        "generations": int(args.generations),
        "candidate_context_jobs": 2 * int(args.population) * int(args.generations) * 2 * 2,
        "sample_seconds": float(args.sample_seconds),
        "baseline_cpu_percent": baseline,
        "active_threshold_percent": active_threshold,
        "wall_seconds": wall_seconds,
        "throughput_candidate_context_jobs_per_second": (
            2 * int(args.population) * int(args.generations) * 2 * 2 / wall_seconds
        ),
        "throughput_completed_jobs_per_second": _summary(throughput_samples),
        "whole_machine_cpu_percent_diagnostic_all_phases": _summary(samples),
        "whole_machine_cpu_percent_diagnostic_parallel_active": _summary(active),
        "program_tree_cpu_percent_all_phases": _summary(tree_samples),
        "program_tree_cpu_percent_parallel_active": _summary(tree_active),
        "program_tree_cpu_percent_parallel_pool": _summary(tree_pool),
        "program_tree_active_threshold_percent": tree_active_threshold,
        "program_tree_pool_process_threshold": pool_process_threshold,
        "program_tree_process_count": {
            "median": statistics.median(tree_process_counts) if tree_process_counts else 0,
            "maximum": max(tree_process_counts, default=0),
        },
        "program_tree_samples_percent": tree_samples,
        "throughput_samples_completed_jobs_per_second": throughput_samples,
        "program_tree_process_count_samples": tree_process_counts,
        "target_cpu_percent": {"minimum": 30.0, "maximum": 40.0},
        "returncode": returncode,
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
        "search_root": str(args.run_root / "search"),
    }
    active_mean = float(result["program_tree_cpu_percent_parallel_pool"]["mean"])
    result["target_mean_met"] = 30.0 <= active_mean <= 40.0
    result = {**result, "cpu_calibration_sha256": payload_hash(result)}
    atomic_json(args.output, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--population", type=int, default=3)
    parser.add_argument("--generations", type=int, default=1)
    parser.add_argument("--sample-seconds", type=float, default=0.5)
    args = parser.parse_args()
    result = run(args)
    print(
        f"workers={result['workers']} returncode={result['returncode']} "
        f"program_tree_pool_mean={result['program_tree_cpu_percent_parallel_pool']['mean']:.2f}% "
        f"wall={result['wall_seconds']:.2f}s target={result['target_mean_met']}"
    )
    if result["returncode"]:
        raise SystemExit(result["returncode"])


if __name__ == "__main__":
    main()
