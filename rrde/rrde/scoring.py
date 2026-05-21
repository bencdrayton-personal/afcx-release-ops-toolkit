"""Scoring engine for RRDE.

The composite score uses a hybrid of weighted-average and weighted-max so that
a single catastrophic dimension can never be averaged away by four safe ones.
Decision bands are deliberately step-wise, with single-dimension red-flag
escalation for intel-integrity or regulatory exposure.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import List

from .models import (
    ReleaseCandidate,
    VendorTelemetry,
    MemberSurfaceMap,
    AffectedMembers,
    RiskScores,
    Decision,
)
from .obligations import ObligationMatrix


# --- per-dimension scoring -------------------------------------------------

def _score_vendor_delivery(telemetry: VendorTelemetry) -> float:
    score = (
        telemetry.defect_leakage_rate_p90 * 40 +
        telemetry.env_drift_incidents_90d * 0.6 +
        telemetry.change_request_overrun_rate * 30 +
        (1 - telemetry.member_uat_participation_rate) * 4
    )
    return round(min(10.0, score), 2)


def _score_intel_integrity(rc: ReleaseCandidate) -> float:
    s = 0.0
    if rc.scope.intel_pipeline_changes > 0:
        s += 4
    if rc.scope.schema_changes > 0:
        s += 3
    if rc.scope.touches("dedup") or rc.scope.touches("matching"):
        s += 2
    if any(f.startswith("victim_pii") for f in rc.scope.touched_fields):
        s += 2
    if any("intel" in surface.lower() or "signal" in surface.lower()
           for surface in rc.scope.touched_surfaces):
        s += 1
    return round(min(10.0, s), 2)


def _score_member_impact(affected: AffectedMembers) -> float:
    s = len(affected) * 0.5
    if affected.includes_tier1:
        s += 3
    return round(min(10.0, s), 2)


def _score_rollback_difficulty(rc: ReleaseCandidate, affected: AffectedMembers) -> float:
    s = (
        rc.scope.schema_changes * 3 +
        rc.scope.auth_changes * 4 +
        (2 if affected.requires_member_redeploy else 0)
    )
    return round(min(10.0, float(s)), 2)


def _composite(dims: List[float], weights: List[float]) -> float:
    """Weighted-blend: protect against single-dimension catastrophes.

    composite = max(0.7 * max_dim, weighted_avg)
    So a single 8/10 score will produce composite >= 5.6 regardless of the others,
    while four 3s and one 8 will not average down to ~4.
    """
    weighted_avg = sum(d * w for d, w in zip(dims, weights))
    return round(max(0.7 * max(dims), weighted_avg), 2)


# --- decision band ---------------------------------------------------------

DECISION_BANDS = {
    "ESCALATE_TO_MD": "Single-dimension critical risk requires MD authorisation before promotion.",
    "HOLD_FOR_REVIEW": "Composite risk above ship threshold; CAB must re-review with mitigations.",
    "SHIP_WITH_GUARDRAILS": "Acceptable composite but specific gates must be satisfied before promotion.",
    "SHIP": "Standard promotion path applies.",
}


def _decide(scores: RiskScores) -> str:
    if scores.intel_integrity_risk >= 8 or scores.regulatory_exposure_risk >= 8:
        return "ESCALATE_TO_MD"
    if scores.composite_risk >= 7:
        return "HOLD_FOR_REVIEW"
    if scores.composite_risk >= 5 or scores.member_impact_risk >= 6:
        return "SHIP_WITH_GUARDRAILS"
    return "SHIP"


# --- gate computation ------------------------------------------------------

def _scope_driven_gates(rc: ReleaseCandidate, scores: RiskScores,
                        affected: AffectedMembers) -> List[str]:
    """Gates triggered by the shape of the release, beyond the obligation matrix."""
    gates: List[str] = []
    if rc.scope.intel_pipeline_changes > 0:
        gates.append("INTEL_QUALITY_SHADOW_RUN")
    if affected.includes_tier1 and scores.composite_risk >= 5:
        gates.append("MEMBER_UAT_TIER1_SIGNOFF")
    if rc.scope.schema_changes > 0:
        gates.append("BACKOUT_PLAN_REHEARSED")
    if rc.scope.auth_changes > 0:
        gates.append("MEMBER_NOTIFICATION_72H")
    return gates


# --- natural-language explanation -----------------------------------------

def _explain(rc: ReleaseCandidate, scores: RiskScores,
             affected: AffectedMembers, obligations: List[str],
             gates: List[str], decision: str) -> str:
    bits: List[str] = []
    if rc.scope.schema_changes > 0 and any(f.startswith("victim_pii")
                                           for f in rc.scope.touched_fields):
        bits.append(f"Schema change touches victim PII used by {len(affected)} members"
                    f"{' (incl. tier-1)' if affected.includes_tier1 else ''}.")
    elif rc.scope.schema_changes > 0:
        bits.append(f"Schema change affects {len(affected)} members.")
    if rc.scope.intel_pipeline_changes > 0:
        bits.append("Intel pipeline change requires shadow-run before promotion.")
    if rc.scope.auth_changes > 0:
        bits.append("Auth surface change triggers 72h member notification.")
    if obligations:
        bits.append(f"Triggered obligations: {', '.join(obligations)}.")
    bits.append(DECISION_BANDS[decision])
    return " ".join(bits)


# --- public entry point ----------------------------------------------------

def score_release(rc: ReleaseCandidate,
                  telemetry: VendorTelemetry,
                  members: MemberSurfaceMap,
                  obligations: ObligationMatrix,
                  weights: dict | None = None) -> Decision:
    weights = weights or {
        "vendor_delivery": 0.20,
        "intel_integrity": 0.30,
        "member_impact": 0.20,
        "regulatory_exposure": 0.20,
        "rollback_difficulty": 0.10,
    }

    affected = members.affected_by(rc.scope.touched_surfaces)
    vendor_delivery = _score_vendor_delivery(telemetry)
    intel_integrity = _score_intel_integrity(rc)
    member_impact = _score_member_impact(affected)
    rollback = _score_rollback_difficulty(rc, affected)
    regulatory_exposure, triggered_obligations, obligation_gates = obligations.evaluate(rc.scope)

    dims = [vendor_delivery, intel_integrity, member_impact, regulatory_exposure, rollback]
    w = [weights["vendor_delivery"], weights["intel_integrity"], weights["member_impact"],
         weights["regulatory_exposure"], weights["rollback_difficulty"]]

    composite = _composite(dims, w)
    scores = RiskScores(
        vendor_delivery_risk=vendor_delivery,
        intel_integrity_risk=intel_integrity,
        member_impact_risk=member_impact,
        regulatory_exposure_risk=regulatory_exposure,
        rollback_difficulty=rollback,
        composite_risk=composite,
    )
    decision = _decide(scores)

    # Merge obligation gates with scope-driven gates, preserving order, deduped
    gates: List[str] = []
    seen = set()
    for g in obligation_gates + _scope_driven_gates(rc, scores, affected):
        if g not in seen:
            gates.append(g)
            seen.add(g)

    return Decision(
        release_id=rc.release_id,
        product_line=rc.product_line,
        decision=decision,
        scores=scores,
        required_gates=gates,
        triggered_obligations=triggered_obligations,
        explanation=_explain(rc, scores, affected, triggered_obligations, gates, decision),
        obligation_matrix_version=obligations.version,
        scored_at=datetime.now(timezone.utc).isoformat(),
    )
