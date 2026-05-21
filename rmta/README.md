# RMTA — Release Milestone Triage Agent

## What it is

A daily-running scan of the in-flight milestone that surfaces issues while they are still inexpensive to remediate. Intended to give the TPM and the member-bank tech leads as much advance notice of schedule risk as the data will support.

## What it does

RMTA reads the milestone each morning from Jira (or Azure DevOps Boards via the adapter pattern). It produces a one-page report:

- The projected end date and the working-days delta against plan.
- A short list of stories currently driving that projection — stale work, stale blockers, unanswered questions, missing acceptance criteria near the deadline, and scope unlikely to complete at the current velocity.
- A suggested next action for each.

## Outcome

I built a version of this at Orbus. It saved days of work each sprint by removing the need to triage the board manually, surfaced stories that had gone stale and needed attention, and brought forward remediation rather than absorbing it as end-of-milestone slip.

For AFCX the benefit compounds. Every working day of additional notice you give the Big 4 is a day their change-window teams can use inside their normal governance cadence, rather than emergency-rescheduling in week-of. The outcome is a quieter relationship with member banks, fewer "we need to move our window" conversations, and a more honest milestone signal at status reviews.

## Quick start

```bash
pip install -r requirements.txt

python -m rmta triage samples/jira_milestone.json --as-of 2026-06-10
```

The committed sample output is in [`samples/triage_report.md`](samples/triage_report.md).

## Why this matters at AFCX specifically

AFCX releases coordinate change windows at the Big 4 banks. A slipped AFCX release isn't a private problem; it's eight downstream change windows that need to move at ANZ, CBA, NAB and Westpac — each with their own Risk Day-1/Day-2 governance. The TPM's job is *not* to manage the slip when it lands; it's to **make the slip visible to members three weeks earlier than it would otherwise be**, so member-side change windows can be rescheduled inside their own governance cadence rather than emergency-rescheduled in week-of.

RMTA's job is to make in-flight schedule risk visible to the TPM (and to member-bank tech leads) *while the slip is still recoverable*.

## Sample output (real run)

```
# RMTA Triage Report — AFCX_IQ_v2.14.0
*Generated 2026-06-10 · milestone deadline 2026-06-21*

## Schedule projection
  progress              35% complete  (15 of 43 story points)
  velocity 14d rolling  1.7 pts/day
  projected end date    2026-06-26  (+5 working days vs plan)
  status                AT_HIGH_RISK — open communications with members now

## Top 3 risks
  1. AFCX-1142 has been blocked for 7 days; unblock requires ATO POC response.
     This single story holds 5 of the 28 remaining points.
  2. 2 stories (AFCX-1138, AFCX-1146) have unanswered questions from the
     vendor sitting in Jira comments. The oldest is 5 days old.
  3. AFCX-1151 is still missing acceptance criteria with 11 days to milestone
     close. At normal AC-clarification cycle time this is now critical-path.

## Flagged stories (12)
  STALE_BLOCKED (1) · UNANSWERED_QUESTION (2) · AC_MISSING_NEAR_DEADLINE (1)
  STALE_IN_PROGRESS (5) · SCOPE_AT_RISK (3)
```

Full committed report in [`samples/triage_report.md`](samples/triage_report.md).

## Design notes

**Why daily, not weekly?** Schedule risk compounds. A question unanswered for 24 hours costs one cycle of clarification. A question unanswered for 8 days costs the milestone. Daily detection lets the TPM act inside the cycle, not after it.

**Why an adapter pattern (Jira vs Azure DevOps)?** Most banks and Atlassian-shop vendors use Jira; Microsoft-shop vendors (like Alliance Software historically) often use Azure DevOps Boards. The agent shouldn't care. The adapter normalises both into a single `Story` shape, and the heuristic engine runs the same regardless.

**Why hand-rolled heuristics first, LLM second?** A heuristic with a clear rule (`blocked_days > 5 → STALE_BLOCKED`) is auditable, testable, and learnable. LLMs are excellent at summarising the *narrative* across the flags ("the milestone is at risk because of X, Y, Z") but should not be in the critical path of *detection*. Production RMTA uses an LLM only for the natural-language summary at the top of the report.

**Why projected slip days, not just a binary "on track / off track"?** Banks budget change windows in days. "+2 working days" tells a member-bank tech lead exactly what to ask their CAB for. "Off track" is a vibe.

## Limits of this concept implementation

- **Jira adapter is mocked.** The `JiraAdapter` class shows the call shape and parses a saved JSON dump rather than calling the real Jira API. Production version reads `JIRA_HOST`, `JIRA_USER`, `JIRA_TOKEN` from env and uses the Jira Cloud REST v3 endpoints (`/rest/api/3/search`, `/rest/api/3/issue/{id}/comment`, `/rest/api/3/issue/{id}/changelog`).
- **Azure DevOps adapter is a stub** with the method signatures matched to Jira. Implementing the Azure side is ~150 LOC.
- **LLM summarisation is hand-rolled** — the production version would call an LLM (Anthropic Claude / OpenAI) with the flag set as context to produce the top-3 narrative.
- **Velocity projection is linear.** Production version would use a Monte Carlo simulation over the last N sprints' velocity distribution to produce a probability cone (`P50 / P85 / P95` projected end dates) rather than a single point estimate.

All of these are 1–2 sprint upgrades.
