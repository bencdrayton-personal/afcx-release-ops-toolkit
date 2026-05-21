"""Data models for RRDE."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Set, Optional


@dataclass
class ReleaseScope:
    feature_changes: int = 0
    schema_changes: int = 0
    auth_changes: int = 0
    intel_pipeline_changes: int = 0
    touched_surfaces: List[str] = field(default_factory=list)   # e.g. ["IQ.search", "Exchange.signals.scam"]
    touched_fields: List[str] = field(default_factory=list)     # e.g. ["victim_pii.account_holder_name"]
    keywords: List[str] = field(default_factory=list)           # e.g. ["dedup", "matching"]

    def touches(self, kw: str) -> bool:
        return kw in self.keywords or any(kw in s for s in self.touched_surfaces + self.touched_fields)


@dataclass
class ReleaseCandidate:
    release_id: str
    product_line: str               # "AFCX_IQ" | "AFCX_Exchange" | "FRX"
    vendor: str
    submitted_by: str
    submitted_at: str               # ISO datetime
    scope: ReleaseScope


@dataclass
class VendorTelemetry:
    """Rolling 90-day vendor delivery stats — calibrates vendor_delivery_risk."""
    defect_leakage_rate_p90: float = 0.0     # e.g. 0.07 = 7% of releases leaked a defect to prod
    env_drift_incidents_90d: int = 0
    change_request_overrun_rate: float = 0.0
    member_uat_participation_rate: float = 1.0   # 1.0 = every tier-1 attended UAT


@dataclass
class MemberSurface:
    member_id: str
    name: str
    tier: int                        # 1 = ANZ/CBA/NAB/Westpac, 2 = larger ADIs/telcos, 3 = smaller
    surfaces_consumed: List[str]
    requires_member_redeploy_on_schema: bool = False


@dataclass
class MemberSurfaceMap:
    members: List[MemberSurface]

    def affected_by(self, touched_surfaces: List[str]) -> "AffectedMembers":
        hit = [m for m in self.members
               if any(s in touched_surfaces for s in m.surfaces_consumed)]
        return AffectedMembers(hit)


@dataclass
class AffectedMembers:
    members: List[MemberSurface]

    def __len__(self) -> int:
        return len(self.members)

    @property
    def includes_tier1(self) -> bool:
        return any(m.tier == 1 for m in self.members)

    @property
    def requires_member_redeploy(self) -> bool:
        return any(m.requires_member_redeploy_on_schema for m in self.members)

    def names(self) -> List[str]:
        return [m.name for m in self.members]


@dataclass
class RiskScores:
    vendor_delivery_risk: float
    intel_integrity_risk: float
    member_impact_risk: float
    regulatory_exposure_risk: float
    rollback_difficulty: float
    composite_risk: float


@dataclass
class Decision:
    release_id: str
    product_line: str
    decision: str                    # SHIP | SHIP_WITH_GUARDRAILS | HOLD_FOR_REVIEW | ESCALATE_TO_MD
    scores: RiskScores
    required_gates: List[str]
    triggered_obligations: List[str]
    explanation: str
    obligation_matrix_version: str
    scored_at: str

    def to_dict(self) -> Dict:
        d = asdict(self)
        return d
