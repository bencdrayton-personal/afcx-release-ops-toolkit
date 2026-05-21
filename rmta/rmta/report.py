"""Markdown report renderer."""
from __future__ import annotations
from datetime import datetime
from typing import List
from collections import defaultdict

from .adapters import Milestone
from .projection import ScheduleProjection
from .triage import Flag


FLAG_ORDER = [
    "STALE_BLOCKED",
    "UNANSWERED_QUESTION",
    "AC_MISSING_NEAR_DEADLINE",
    "STALE_IN_PROGRESS",
    "SCOPE_AT_RISK",
]

STATUS_BADGE = {
    "ON_TRACK": "ON_TRACK — promote on schedule",
    "AT_RISK": "AT_RISK — recover via descope or accelerate",
    "AT_HIGH_RISK": "AT_HIGH_RISK — open communications with members now",
    "SLIPPED": "SLIPPED — re-baseline milestone with members",
}


def render(milestone: Milestone, projection: ScheduleProjection,
           flags: List[Flag], top3: List[str], as_of: datetime) -> str:
    grouped: dict[str, List[Flag]] = defaultdict(list)
    for f in flags:
        grouped[f.type].append(f)

    out: List[str] = []
    out.append(f"# RMTA Triage Report — {milestone.name}")
    out.append(f"*Generated {as_of:%Y-%m-%d %H:%M %Z} · milestone deadline {milestone.target_date:%Y-%m-%d}*\n")

    out.append("## Schedule projection")
    out.append("```")
    out.append(f"  progress              {projection.completed_pct}% complete  "
               f"({int(projection.completed_points)} of {int(projection.total_points)} story points)")
    out.append(f"  velocity 14d rolling  {projection.velocity_pts_per_day} pts/day")
    out.append(f"  projected end date    {projection.projected_end_date:%Y-%m-%d}  "
               f"({_pretty_delta(projection.days_vs_plan)})")
    out.append(f"  status                {STATUS_BADGE[projection.status]}")
    out.append("```\n")

    if top3:
        out.append("## Top 3 risks (auto-summarised)")
        for i, s in enumerate(top3, 1):
            out.append(f"  {i}. {s}")
        out.append("")

    out.append(f"## Flagged stories ({len(flags)})\n")
    for flag_type in FLAG_ORDER:
        items = grouped.get(flag_type, [])
        if not items:
            continue
        out.append(f"### {flag_type} ({len(items)})")
        for f in items:
            out.append(f"  - **{f.story_key}**  \"{f.story_summary}\"")
            out.append(f"    {f.detail} · suggested: {f.suggested_action}")
        out.append("")

    if projection.status in ("ON_TRACK",) and not flags:
        out.append("## ✓ No flags raised. Milestone tracking on schedule.\n")

    out.append("---")
    out.append("*Run by RMTA — Release Milestone Triage Agent.*")
    return "\n".join(out)


def _pretty_delta(days_vs_plan: int) -> str:
    if days_vs_plan == 0:
        return "on plan"
    if days_vs_plan > 0:
        return f"+{days_vs_plan} working days vs plan"
    return f"{days_vs_plan} working days vs plan"
