"""CLI entry point for RRDE.

Usage:
    python -m rrde score [path_to_rcs.json] [--telemetry path] [--members path] [--obligations path]
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

from .models import (
    ReleaseCandidate, ReleaseScope, VendorTelemetry,
    MemberSurfaceMap, MemberSurface,
)
from .obligations import ObligationMatrix
from .scoring import score_release


PKG_DIR = Path(__file__).parent
DEFAULTS = {
    "rcs": PKG_DIR.parent / "samples" / "release_candidates.json",
    "telemetry": PKG_DIR.parent / "samples" / "vendor_telemetry.json",
    "members": PKG_DIR.parent / "samples" / "members.json",
    "obligations": PKG_DIR / "data" / "obligation_matrix.yaml",
}


def _load_rc(d: dict) -> ReleaseCandidate:
    scope = ReleaseScope(**d.pop("scope"))
    return ReleaseCandidate(scope=scope, **d)


def _load_members(path: Path) -> MemberSurfaceMap:
    data = json.loads(Path(path).read_text())
    return MemberSurfaceMap(members=[MemberSurface(**m) for m in data["members"]])


def _print_human(decision) -> None:
    s = decision.scores
    print(f"\n{decision.release_id}  →  {decision.decision}  (composite {s.composite_risk})")
    print(f"  product_line              {decision.product_line}")
    print(f"  vendor_delivery_risk      {s.vendor_delivery_risk}")
    print(f"  intel_integrity_risk      {s.intel_integrity_risk}")
    print(f"  member_impact_risk        {s.member_impact_risk}")
    print(f"  regulatory_exposure_risk  {s.regulatory_exposure_risk}")
    print(f"  rollback_difficulty       {s.rollback_difficulty}")
    if decision.triggered_obligations:
        print(f"  Triggered obligations:")
        for o in decision.triggered_obligations:
            print(f"    - {o}")
    if decision.required_gates:
        print(f"  Required gates:")
        for g in decision.required_gates:
            print(f"    - {g}")
    print(f"  Explanation:")
    print(f"    {decision.explanation}")
    print(f"  (obligation matrix v{decision.obligation_matrix_version}, scored at {decision.scored_at})")


def main():
    parser = argparse.ArgumentParser(prog="rrde")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_score = sub.add_parser("score", help="Score one or more release candidates")
    p_score.add_argument("rcs", nargs="?", default=str(DEFAULTS["rcs"]))
    p_score.add_argument("--telemetry", default=str(DEFAULTS["telemetry"]))
    p_score.add_argument("--members", default=str(DEFAULTS["members"]))
    p_score.add_argument("--obligations", default=str(DEFAULTS["obligations"]))
    p_score.add_argument("--json", action="store_true", help="emit JSON instead of human-readable")

    args = parser.parse_args()
    if args.cmd != "score":
        parser.error(f"Unknown command {args.cmd}")

    rcs_data = json.loads(Path(args.rcs).read_text())
    if isinstance(rcs_data, dict):
        rcs_data = [rcs_data]

    telemetry_data = json.loads(Path(args.telemetry).read_text())
    telemetry = VendorTelemetry(**telemetry_data)
    members = _load_members(Path(args.members))
    obligations = ObligationMatrix.from_yaml(Path(args.obligations))

    decisions = []
    for rc_data in rcs_data:
        rc = _load_rc(rc_data)
        d = score_release(rc, telemetry, members, obligations)
        decisions.append(d)

    if args.json:
        print(json.dumps([d.to_dict() for d in decisions], indent=2, default=str))
    else:
        for d in decisions:
            _print_human(d)
        print()


if __name__ == "__main__":
    main()
