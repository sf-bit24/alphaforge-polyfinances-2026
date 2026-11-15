"""Run one cross-check job: <profile_id>:<mode>:<horizon>:<oracle 0/1>. Traces in results/croisement_runs/<id>/.
Mateo profiles (x_mateo_*) go through analysis/mateo/common.py (US_MKT_XEN data + delayed_glidepath), exactly
like the original Mateo runs; all others through engine.run. engine/ and data/ are not modified.
    .venv/bin/python -I analysis/croisement/run_job.py x_robert_cad_w05:rolling:4:1
SIMULATION ONLY."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BT = HERE.parents[1]
OUT = BT / "results" / "croisement_runs"


def main(job: str):
    pid, mode, h, orc = job.split(":")
    if pid.startswith("x_mateo"):
        sys.path.insert(0, str(BT / "analysis" / "mateo"))
        import common as runner  # noqa: E402
        load = runner.load_profile
    else:
        from engine import run as runner  # noqa: E402
        from engine.profile import load_profile as load  # noqa: E402
    t0 = time.time()
    res = runner.run_profile(load(pid), mode, float(h), None, None, 12, orc == "1", out_dir=OUT / pid, verbose=False)
    p = Path(res["trace_path"])
    t = json.loads(p.read_text())
    t["croisement"] = {"job": job, "runtime_s": round(time.time() - t0, 1),
                       "runner": "analysis/mateo/common.py" if pid.startswith("x_mateo") else "engine.run"}
    p.write_text(json.dumps(t, indent=1, default=str))
    print(job, "->", p.relative_to(BT), f"{time.time()-t0:.0f}s", res["summary"]["robust_choice"], flush=True)


if __name__ == "__main__":
    for j in sys.argv[1:]:
        main(j)
