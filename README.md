# Release Ops Toolkit
*Two small tools for the AFCX Technical Product Manager role. Ben Drayton, 2026-05-21.*

*Repository: **github.com/bencdrayton/afcx-release-ops-toolkit***

Two Python programs that address the two recurring failure modes in vendor-managed release delivery: the risk label on a release is assigned inconsistently or in tribal knowledge, and milestone slippage becomes visible too late to renegotiate with downstream stakeholders.

| Tool | What it does | Run it |
|---|---|---|
| **RRDE** | Scores each release candidate against five risk dimensions and the regulatory obligations that apply, producing a risk label and the reasoning behind it. Intended to run ahead of CAB. | `python -m rrde score samples/release_candidates.json` |
| **RMTA** | Reads the milestone each morning. Produces a one-page report: schedule projection in working days against plan, the stories currently driving that projection, and a suggested next action for each. | `python -m rmta triage samples/jira_milestone.json --as-of 2026-06-10` |

## Why this exists

AFCX delivers releases through a vendor into an environment chain that touches the Big 4 banks, smaller members, telcos, and government partners. Each release has a different blend of regulatory exposure, intel-data sensitivity, and member impact. Today this is reasoned through in CAB by experienced humans. The reasoning is good, but it isn't documented in a form the organisation can replay, audit, or learn from — and it isn't pre-computed in a form that respects the CAB's time.

Milestone slippage has a parallel problem. By the time it surfaces at a status review, the working days available to renegotiate with member-bank change-window teams are already gone, and downstream rework lands as an unplanned cost.

Both tools are intended to be implementable in 2-3 sprints each, against data and systems AFCX already has. The point is the operating model, not the code.

## Run locally

```bash
# RRDE
cd rrde
pip install -r requirements.txt
python -m rrde score samples/release_candidates.json --obligations rrde/data/obligation_matrix.yaml

# RMTA
cd ../rmta
pip install -r requirements.txt
python -m rmta triage samples/jira_milestone.json --as-of 2026-06-10
```

## Portfolio framing

This toolkit is concept code (~600 lines of Python) deliberately kept lean. The point is **the design decisions, the scoring/heuristic logic, and the operational workflow** — not the line count. Both artefacts are designed to be re-implementable inside the AFCX vendor-managed model in 2–3 sprints each, using data that already exists in the vendor's pipeline and the member-coordination workflow.

If extended into production, RRDE would gain (1) post-incident weight recalibration via supervised learning, (2) a member-facing UAT scheduling integration, and (3) an obligation-matrix UI for the Privacy Officer. RMTA would gain (1) anomaly detection on team velocity, (2) LLM-powered summarisation of the daily digest with confidence-rated risk calls, and (3) automated nudges into Jira/Slack on flagged tickets.

## Repo layout

```
afcx-release-ops-toolkit/
├── README.md                          (this file)
├── rrde/
│   ├── README.md                      (RRDE detail + design notes)
│   ├── requirements.txt
│   ├── rrde/
│   │   ├── __init__.py
│   │   ├── __main__.py
│   │   ├── models.py                  (dataclasses)
│   │   ├── scoring.py                 (the scoring engine)
│   │   ├── obligations.py             (obligation-matrix lookup)
│   │   └── data/
│   │       └── obligation_matrix.yaml (versioned regulatory matrix)
│   └── samples/
│       ├── release_candidates.json    (3 sample RCs)
│       ├── vendor_telemetry.json      (90d rolling vendor stats)
│       ├── members.json               (member surface map)
│       └── expected_output.json       (committed sample output)
└── rmta/
    ├── README.md                      (RMTA detail + design notes)
    ├── requirements.txt
    ├── rmta/
    │   ├── __init__.py
    │   ├── __main__.py
    │   ├── adapters.py                (Jira + Azure DevOps adapters)
    │   ├── triage.py                  (heuristics + scoring)
    │   ├── projection.py              (burn-up + slip projection)
    │   └── report.py                  (markdown digest writer)
    ├── samples/
    │   ├── jira_milestone.json        (mock milestone with 18 stories)
    │   └── triage_report.md           (committed sample output)
    └── .github/workflows/
        └── daily-triage.yml           (runs RMTA daily, opens an issue if risks)
```
