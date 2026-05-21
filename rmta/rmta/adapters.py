"""Adapters that normalise different release-tracking tools into a Milestone+Story shape.

The agent doesn't care whether the underlying system is Jira, Azure DevOps Boards, or
a hand-rolled CSV — adapters expose a uniform interface. In this concept implementation
the JiraAdapter reads a saved JSON dump; the real version would call the Jira Cloud
REST API.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
import json
from pathlib import Path


# --- normalised shape ------------------------------------------------------

@dataclass
class Comment:
    author: str
    body: str
    created_at: datetime
    is_question: bool = False
    answered_by_later_comment: bool = False


@dataclass
class StatusChange:
    from_status: str
    to_status: str
    changed_at: datetime
    changed_by: str


@dataclass
class Story:
    key: str
    summary: str
    status: str                                # "To Do" | "In Progress" | "Blocked" | "Done" etc
    story_points: float
    assignee: Optional[str]
    has_acceptance_criteria: bool
    in_scope_milestone: str
    is_critical_path: bool
    created_at: datetime
    last_status_change: Optional[StatusChange] = None
    blocked_since: Optional[datetime] = None
    comments: List[Comment] = field(default_factory=list)


@dataclass
class Milestone:
    id: str
    name: str
    target_date: datetime
    scope: List[Story]
    sprint_velocity_14d: float    # rolling points/day
    plan_start_date: datetime


# --- adapter base ----------------------------------------------------------

class TrackerAdapter:
    name = "abstract"

    def fetch_milestone(self, milestone_id: str) -> Milestone:
        raise NotImplementedError


# --- Jira adapter ----------------------------------------------------------

class JiraAdapter(TrackerAdapter):
    """Concept implementation: reads a saved JSON dump.

    Real version: instantiate with host/user/token, calls Jira Cloud REST v3.
    """
    name = "jira"

    def __init__(self, source: str | Path):
        self.source = Path(source)

    def fetch_milestone(self, milestone_id: str) -> Milestone:
        data = json.loads(self.source.read_text())
        if data.get("id") != milestone_id and milestone_id != "":
            # In a mock, allow either an ID match or pass-through
            pass

        plan_start = _iso(data["plan_start_date"])
        target = _iso(data["target_date"])

        stories: List[Story] = []
        for s in data["scope"]:
            comments = [
                Comment(
                    author=c["author"],
                    body=c["body"],
                    created_at=_iso(c["created_at"]),
                    is_question=c["body"].rstrip().endswith("?"),
                )
                for c in s.get("comments", [])
            ]
            # mark questions as answered if a later non-question comment exists
            for i, c in enumerate(comments):
                if c.is_question:
                    later = comments[i+1:]
                    if any((not l.is_question) and (l.author != c.author) for l in later):
                        c.answered_by_later_comment = True

            last_status_change = None
            if s.get("last_status_change"):
                lsc = s["last_status_change"]
                last_status_change = StatusChange(
                    from_status=lsc["from_status"],
                    to_status=lsc["to_status"],
                    changed_at=_iso(lsc["changed_at"]),
                    changed_by=lsc.get("changed_by", "?"),
                )

            stories.append(Story(
                key=s["key"],
                summary=s["summary"],
                status=s["status"],
                story_points=float(s["story_points"]),
                assignee=s.get("assignee"),
                has_acceptance_criteria=bool(s.get("has_acceptance_criteria", False)),
                in_scope_milestone=s.get("in_scope_milestone", data["id"]),
                is_critical_path=bool(s.get("is_critical_path", False)),
                created_at=_iso(s["created_at"]),
                last_status_change=last_status_change,
                blocked_since=_iso(s["blocked_since"]) if s.get("blocked_since") else None,
                comments=comments,
            ))

        return Milestone(
            id=data["id"],
            name=data["name"],
            target_date=target,
            scope=stories,
            sprint_velocity_14d=float(data["sprint_velocity_14d"]),
            plan_start_date=plan_start,
        )


# --- Azure DevOps adapter (stub) ------------------------------------------

class AzureDevOpsAdapter(TrackerAdapter):
    """Stub for Azure DevOps Boards. Same interface as JiraAdapter.

    Production implementation:
      - List work items in an iteration via Azure DevOps Work Item Tracking API
      - Read state-transition history via the Work Item Updates endpoint
      - Read comments via the Comments endpoint
      - Normalise into the Story / Milestone shape above
    """
    name = "azure_devops"

    def fetch_milestone(self, milestone_id: str) -> Milestone:
        raise NotImplementedError("Azure DevOps adapter not implemented in concept code.")


# --- helpers ---------------------------------------------------------------

def _iso(s: str) -> datetime:
    # normalise common ISO variants
    return datetime.fromisoformat(s.replace("Z", "+00:00"))
