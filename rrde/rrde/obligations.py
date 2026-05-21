"""Obligation matrix - the versioned regulatory lookup table.

The obligation matrix is the single most important asset RRDE consumes.
It is owned by the TPM + Privacy/Compliance lead and lives in git as YAML
so every change is diff-able, reviewable, and historically replayable.

The matrix encodes: for a given release scope, which legal/regulatory/contractual
obligations are triggered? Each obligation carries an exposure weight (0-10)
and a set of required gates that must be passed before the release ships.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Set, Dict, Tuple
import yaml
from pathlib import Path

from .models import ReleaseScope


@dataclass
class ObligationRule:
    id: str
    label: str
    triggered_when: Dict       # dict of conditions, see _matches
    exposure: float            # 0-10
    required_gates: List[str]

    def _matches(self, scope: ReleaseScope) -> bool:
        c = self.triggered_when
        if "scope_field_gt" in c:
            for field, threshold in c["scope_field_gt"].items():
                if getattr(scope, field, 0) <= threshold:
                    return False
        if "touches_field_any" in c:
            if not any(f in scope.touched_fields for f in c["touches_field_any"]):
                return False
        if "touches_keyword_any" in c:
            if not any(scope.touches(kw) for kw in c["touches_keyword_any"]):
                return False
        if "touches_surface_prefix_any" in c:
            if not any(s.startswith(prefix) for prefix in c["touches_surface_prefix_any"]
                                              for s in scope.touched_surfaces):
                return False
        return True


class ObligationMatrix:
    def __init__(self, version: str, rules: List[ObligationRule]):
        self.version = version
        self.rules = rules

    @classmethod
    def from_yaml(cls, path: str | Path) -> "ObligationMatrix":
        data = yaml.safe_load(Path(path).read_text())
        rules = [
            ObligationRule(
                id=r["id"],
                label=r["label"],
                triggered_when=r["triggered_when"],
                exposure=float(r["exposure"]),
                required_gates=r.get("required_gates", []),
            )
            for r in data["rules"]
        ]
        return cls(version=data["version"], rules=rules)

    def evaluate(self, scope: ReleaseScope) -> Tuple[float, List[str], List[str]]:
        """Returns (total_exposure_capped_at_10, triggered_obligation_ids, required_gates)."""
        triggered = [r for r in self.rules if r._matches(scope)]
        # Exposure stacks but caps at 10
        exposure = min(10.0, sum(r.exposure for r in triggered))
        obligations = [r.id for r in triggered]
        # Deduplicate gates while preserving order
        gates: List[str] = []
        seen: Set[str] = set()
        for r in triggered:
            for g in r.required_gates:
                if g not in seen:
                    gates.append(g)
                    seen.add(g)
        return exposure, obligations, gates
