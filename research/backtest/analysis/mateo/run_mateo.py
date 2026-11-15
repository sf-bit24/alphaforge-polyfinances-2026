"""Run Mateo profiles through the engine (with the analysis/mateo patches). Usage:
    .venv/bin/python -I analysis/mateo/run_mateo.py <profile_id> [--mode rolling] [--horizon 8] [--no-oracle]
SIMULATION ONLY.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("profile")
    ap.add_argument("--mode", default=None)
    ap.add_argument("--horizon", type=float, default=None)
    ap.add_argument("--step", type=int, default=None)
    ap.add_argument("--start", default=None)
    ap.add_argument("--no-oracle", action="store_true")
    a = ap.parse_args(argv)
    t0 = time.time()
    prof = common.load_profile(a.profile)
    res = common.run_profile(prof, a.mode, a.horizon, a.start, None, a.step, False if a.no_oracle else None,
                             verbose=False)
    common.annotate_trace(res["trace_path"], {"runtime_s": round(time.time() - t0, 1)})
    print(res["trace_path"], f"{time.time()-t0:.0f}s", "robust:", res["summary"]["robust_choice"],
          "| warnings:", len(res["warnings"]))
    for w in res["warnings"]:
        print("  WARN", w[:200])


if __name__ == "__main__":
    main()
