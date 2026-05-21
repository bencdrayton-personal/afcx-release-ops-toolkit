"""RRDE - Release Risk Decision Engine for the AFCX vendor-managed platform stack."""
__version__ = "0.1.0"

from .models import ReleaseCandidate, VendorTelemetry, MemberSurfaceMap, Decision
from .scoring import score_release
from .obligations import ObligationMatrix

__all__ = [
    "ReleaseCandidate",
    "VendorTelemetry",
    "MemberSurfaceMap",
    "Decision",
    "ObligationMatrix",
    "score_release",
]
