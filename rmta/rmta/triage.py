"""Heuristic triage engine.

For each story in scope, classify it into zero-or-more flag types and produce
a suggested action. Heuristics are deliberately simple, explainable, and
unit-testable.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

from .adapters import Milestone, Story, Comment
from .projection import ScheduleProjection, DONE_STATUSES, IN_PROGRESS_STATUSES, BLOCKED_STATUSES


# Thresholds — these are knobs the TPM tunes for their cadence.
STALE_IN_PROGRESS_DAYS = 5
STALE_BLOCKED_DAYS = 3
UNANSWERED_QUESTION_HOURS = 48
AC_MISSING_BUFFER_DAYS = 14   # AC missing this close to milestone end is risky


@dataclass
class Flag:
    type: str                       # STALE_IN_PROGRESS | STALE_BLOCKED | ...
    story_key: str
    story_summary: str
    detail: str
    suggested_action: str
    severity: str                   # critical | high | medium | low


def triage(milestone: Milestone, projection: ScheduleProjection, as_of: datetime) -> List[Flag]:
    flags: List[Flag] = []
    for s in milestone.scope:
        if s.status in DONE_STATUSES:
            continue
        flags.extend(_flags_for_story(s, milestone, projection, as_of))
    flags.extend(_scope_at_risk_flags(milestone, projection, as_of))
    return flags


def _flags_for_story(s: Story, m: Milestone,
                     proj: ScheduleProjection, as_of: datetime) -> List[Flag]:
    out: List[Flag] = []

    # STALE_IN_PROGRESS
    if s.status in IN_PROGRESS_STATUSES and s.last_status_change:
        days = (as_of - s.last_status_change.changed_at).days
        if days >= STALE_IN_PROGRESS_DAYS:
            out.append(Flag(
                type="STALE_IN_PROGRESS",
                story_key=s.key,
                story_summary=s.summary,
                detail=f"in progress {days}d no movement",
                suggested_action="vendor to provide status",
                severity="high" if s.is_critical_path else "medium",
            ))

    # STALE_BLOCKED
    if s.status in BLOCKED_STATUSES and s.blocked_since:
        days = (as_of - s.blocked_since).days
        if days >= STALE_BLOCKED_DAYS:
            severity = "critical" if s.is_critical_path else "high"
            out.append(Flag(
                type="STALE_BLOCKED",
                story_key=s.key,
                story_summary=s.summary,
                detail=f"blocked {days} days · {s.story_points} pts"
                       f"{' · scope critical' if s.is_critical_path else ''}",
                suggested_action=_suggest_unblock_action(s),
                severity=severity,
            ))

    # UNANSWERED_QUESTION
    for c in s.comments:
        if c.is_question and not c.answered_by_later_comment:
            hours = (as_of - c.created_at).total_seconds() / 3600
            if hours >= UNANSWERED_QUESTION_HOURS:
                days = round(hours / 24)
                out.append(Flag(
                    type="UNANSWERED_QUESTION",
                    story_key=s.key,
                    story_summary=s.summary,
                    detail=f"question {days}d unanswered (from {c.author})",
                    suggested_action=_suggest_question_action(s, c),
                    severity="high" if s.is_critical_path else "medium",
                ))
                break   # only flag once per story

    # AC_MISSING_NEAR_DEADLINE
    if not s.has_acceptance_criteria and s.status not in DONE_STATUSES:
        days_to_close = (m.target_date - as_of).days
        if days_to_close <= AC_MISSING_BUFFER_DAYS:
            out.append(Flag(
                type="AC_MISSING_NEAR_DEADLINE",
                story_key=s.key,
                story_summary=s.summary,
                detail=f"no AC · {days_to_close}d to milestone close",
                suggested_action="PM to draft AC by EOD",
                severity="high",
            ))

    return out


def _scope_at_risk_flags(m: Milestone, proj: ScheduleProjection,
                         as_of: datetime) -> List[Flag]:
    """At current velocity, which started-but-incomplete stories won't finish?"""
    if proj.status == "ON_TRACK":
        return []

    # Capacity in points between now and milestone target
    days_to_close = max(0, (m.target_date - as_of).days)
    capacity = proj.velocity_pts_per_day * days_to_close

    # We need: completed_during_remaining_period >= remaining_points
    overshoot = proj.remaining_points - capacity
    if overshoot <= 0:
        return []

    # Pick from open work, lowest critical-path first to descope
    open_stories = [s for s in m.scope if s.status not in DONE_STATUSES]
    descope_candidates = sorted(
        open_stories,
        key=lambda s: (s.is_critical_path, -s.story_points),
    )
    flags: List[Flag] = []
    saved = 0.0
    for s in descope_candidates:
        if saved >= overshoot:
            break
        flags.append(Flag(
            type="SCOPE_AT_RISK",
            story_key=s.key,
            story_summary=s.summary,
            detail="will not complete at current velocity",
            suggested_action="descope to next milestone" if not s.is_critical_path
                              else "split or descope",
            severity="medium",
        ))
        saved += s.story_points
    return flags


def _suggest_unblock_action(s: Story) -> str:
    if "AGD" in s.summary or "Home Affairs" in s.summary or "ATO" in s.summary:
        return "TPM to escalate to gov POC"
    if "Privacy" in s.summary:
        return "TPM to escalate to Privacy Officer"
    if "Member" in s.summary or "ANZ" in s.summary or "CBA" in s.summary or "NAB" in s.summary or "Westpac" in s.summary:
        return "TPM to escalate to member tech lead"
    return "TPM to identify unblock owner"


def _suggest_question_action(s: Story, c: Comment) -> str:
    body_lower = c.body.lower()
    if "privacy" in body_lower or "pii" in body_lower:
        return "re-ping Privacy Officer"
    if "ac" in body_lower or "acceptance" in body_lower:
        return "TPM to clarify AC"
    if "anz" in body_lower:
        return "re-ping ANZ tech lead"
    if "cba" in body_lower:
        return "re-ping CBA tech lead"
    if "nab" in body_lower:
        return "re-ping NAB tech lead"
    if "westpac" in body_lower:
        return "re-ping Westpac tech lead"
    return f"re-ping {c.author}"


def summarise_top3(flags: List[Flag], milestone: Milestone,
                   projection: ScheduleProjection) -> List[str]:
    """Hand-rolled top-3 narrative.

    Production version: pass `flags` and `projection` to an LLM with a
    `system` prompt that constrains output to 3 concise risk narratives
    with confidence ratings. The structure below approximates what that
    summary would look like.
    """
    summaries: List[str] = []

    # 1. Blocked critical-path
    blocked = [f for f in flags if f.type == "STALE_BLOCKED"]
    if blocked:
        f = sorted(blocked,
                   key=lambda x: (x.severity != "critical", x.story_summary))[0]
        days = f.detail.split()[1]
        # Find the points on this story
        story = next(s for s in milestone.scope if s.key == f.story_key)
        summaries.append(
            f"{f.story_key} has been blocked for {days} days; "
            f"unblock requires {_unblock_who(f.story_summary)} response. "
            f"No owner has been assigned for the chase. This single story holds "
            f"{int(story.story_points)} of the {int(projection.remaining_points)} remaining points."
        )

    # 2. Unanswered questions
    qs = [f for f in flags if f.type == "UNANSWERED_QUESTION"]
    if qs:
        oldest = sorted(qs, key=lambda f: -int(f.detail.split('d')[0].split()[1]))[0]
        days = oldest.detail.split('d')[0].split()[1]
        summaries.append(
            f"{len(qs)} stories ({', '.join(f.story_key for f in qs[:3])}) "
            f"have unanswered questions from the vendor sitting in Jira comments. "
            f"The oldest is {days} days old."
        )

    # 3. AC missing
    acs = [f for f in flags if f.type == "AC_MISSING_NEAR_DEADLINE"]
    if acs:
        f = acs[0]
        days = f.detail.split('·')[1].strip().split('d')[0].strip()
        summaries.append(
            f"{f.story_key} is still missing acceptance criteria and the "
            f"milestone closes in {days} days. At normal AC-clarification "
            f"cycle time this is now critical-path."
        )

    return summaries[:3]


def _unblock_who(summary: str) -> str:
    if "AGD" in summary or "Home Affairs" in summary:
        return "AGD/Home Affairs"
    if "ATO" in summary:
        return "ATO POC"
    if "Privacy" in summary:
        return "Privacy Officer"
    return "external"
