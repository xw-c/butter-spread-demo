"""Check that the solver produced a stable, measurable butter spread."""
import argparse
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--state", type=Path, default=ROOT / "outputs" / "mpm-state.npz")
parser.add_argument("--output", type=Path, default=ROOT / "outputs" / "physics-audit.json")
parser.add_argument("--preview", action="store_true", help="check stability only for a partial run")
args = parser.parse_args()
state = np.load(args.state)
p = state["particles"]
knife = state["knife_positions"]
initial = np.ptp(p[0, :, :2], axis=0)
final = np.ptp(p[-1, :, :2], axis=0)
centroid_shift = float(np.linalg.norm(p[-1].mean(axis=0) - p[0].mean(axis=0)))
checks = {
    "expected_duration": (len(p) >= 2 if args.preview else len(p) == 73)
                         and int(state["fps"]) == 24,
    "particle_count_constant": p.ndim == 3 and p.shape[1] > 100,
    "finite_positions": bool(np.isfinite(p).all()),
    "inside_bread_region": bool((np.abs(p[:, :, 0]) < 0.071).all()
                                and (np.abs(p[:, :, 1]) < 0.051).all()
                                and (p[:, :, 2] > 0.025).all()
                                and (p[:, :, 2] < 0.07).all()),
}
if not args.preview:
    checks.update({
        "knife_travel_gt_10cm": float(np.ptp(knife[:, 0])) > 0.10,
        "spread_x_gt_40_percent": float(final[0] / initial[0]) > 1.40,
        "butter_centroid_shift_gt_5mm": centroid_shift > 0.005,
    })
report = {
    "pass": all(checks.values()), "checks": checks,
    "initial_span_m": initial.tolist(), "final_span_m": final.tolist(),
    "spread_area_ratio": float(np.prod(final / initial)),
    "centroid_shift_m": centroid_shift,
    "particle_count": int(p.shape[1]), "frames": int(len(p)),
}
args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
if not report["pass"]:
    raise SystemExit(1)
