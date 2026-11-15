"""Run several persona-14 jobs in one process. Job = profile_id:mode:horizon:oracle(0/1)[:start]
Writes the list of trace paths to analysis/p14/runs_<tag>.json (results go to results/<profile id>/). SIMULATION ONLY."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402


def main():
    tag, jobs = sys.argv[1], sys.argv[2:]
    out_f = common.HERE / f"runs_{tag}.json"
    done = json.loads(out_f.read_text()) if out_f.exists() else {}
    for j in jobs:
        parts = j.split(":")
        pid, mode, h, orc = parts[:4]
        start = parts[4] if len(parts) > 4 else None
        t0 = time.time()
        res = common.run_profile(common.load_profile(pid), mode, float(h), start, None, 12, orc == "1", verbose=False)
        common.annotate_trace(res["trace_path"], {"runtime_s": round(time.time() - t0, 1), "job": j})
        done[j] = str(Path(res["trace_path"]).relative_to(common.BT))
        out_f.write_text(json.dumps(done, indent=1))
        print(j, "->", done[j], f"{time.time()-t0:.0f}s", res["summary"]["robust_choice"], flush=True)


if __name__ == "__main__":
    main()
