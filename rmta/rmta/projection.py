"""Schedule slip projection.

In this concept implementation we use a linear projection over the rolling
14-day velocity. The production version would replace this with a Monte
Carlo over the last N sprints' velocity distribution, producing a P50/P85/P95
cone of projected milestone end dates.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List

from .adapters import Milestone, Story


DONE_STATUSES = {"Done", "Closed", "Released", "Resolved"}
IN_PROGRESS_STATUSES = {"In Progress", "In Review", "QA"}
BLOCKED_STATUSES = {"Blocked", "Impediment"}


@dataclass
class ScheduleProjection:
    total_points: float
    completed_points: float
    remaining_points: float
    velocity_pts_per_day: float
    projected_end_date: datetime
    days_vs_plan: int                 # +2 = 2 working days behind, -1 = 1 day ahead
    status: str                       # ON_TRACK | AT_RISK | AT_HIGH_RISK | SLIPPED

    @property
    def completed_pct(self) -> int:
        if self.total_points == 0:
            return 0
        return round(self.completed_points / self.total_points * 100)


def project(m: Milestone, as_of: datetime) -> ScheduleProjection:
    total = sum(s.story_points for s in m.scope)
    completed = sum(s.story_points for s in m.scope if s.status in DONE_STATUSES)
    remaining = max(0.0, total - completed)

    v = m.sprint_velocity_14d
    if v <= 0:
        # No data; assume infinite days remaining → slip
        projected_end = m.target_date + timedelta(days=999)
    else:
        days_remaining = remaining / v
        projected_end = as_of + timedelta(days=days_remaining)

    days_vs_plan = _working_days_between(m.target_date, projected_end)

    if projected_end <= m.target_date:
        status = "ON_TRACK"
    elif days_vs_plan <= 2:
        status = "AT_RISK"
    elif days_vs_plan <= 5:
        status = "AT_HIGH_RISK"
    else:
        status = "SLIPPED"

    return ScheduleProjection(
        total_points=total,
        completed_points=completed,
        remaining_points=remaining,
        velocity_pts_per_day=round(v, 2),
        projected_end_date=projected_end,
        days_vs_plan=days_vs_plan,
        status=status,
    )


def _working_days_between(start: datetime, end: datetime) -> int:
    """Inclusive working-day delta. Negative if end < start."""
    if end == start:
        return 0
    sign = 1 if end > start else -1
    a, b = (start, end) if sign == 1 else (end, start)
    days = 0
    cur = a
    while cur < b:
        cur = cur + timedelta(days=1)
        if cur.weekday() < 5:  # Mon-Fri
            days += 1
    return sign * days
