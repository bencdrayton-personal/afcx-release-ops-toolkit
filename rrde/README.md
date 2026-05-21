# RRDE — Release Risk Decision Engine

## What it is

A small Python tool that assigns each release candidate the correct risk label, with the reasoning recorded. Intended to be run ahead of the Change Advisory Board, so the CAB reviews and challenges a pre-computed call rather than constructing one from scratch.

## What it does

For each release candidate, RRDE produces:

- A score across five dimensions: vendor delivery, intel integrity, member impact, regulatory exposure, rollback difficulty.
- A risk label: `SHIP`, `SHIP_WITH_GUARDRAILS`, `HOLD_FOR_REVIEW`, or `ESCALATE_TO_MD`.
- The governance gates this release must pass (member UAT sign-off, Privacy Officer review, backout rehearsal, AUSTRAC liaison, and so on).
- A plain-English explanation of the call.

Each decision is timestamped and carries the version of the obligation matrix that produced it. A later inquiry — from AUSTRAC, the Privacy Officer, a member-bank Risk function, or a post-incident review — can replay it.

## The obligation matrix

The substantive content of the tool is the obligation matrix (`rrde/data/obligation_matrix.yaml`). It encodes the regulatory and contractual obligations AFCX is subject to — Privacy Act, AML/CTF, CDR, ePayments Code, Member Service Agreement clauses, government data-matching surfaces — as a set of rules that trigger on release-scope conditions. The matrix is the artefact that gets diffed, reviewed in pull requests, signed off by the Privacy and Compliance leads, and replayed against historical decisions. The scoring engine is a thin layer over it.

## Outcome

The intent is threefold:

- Shorten the CAB by pre-computing the risk label and the gates.
- Make the reasoning behind each release decision durable and recoverable.
- Move regulatory obligation tracking from tribal knowledge into a versioned file.

## Quick start

```bash
pip install -r requirements.txt

python -m rrde score \
    --rcs samples/release_candidates.json \
    --telemetry samples/vendor_telemetry.json \
    --members samples/members.json \
    --obligations rrde/data/obligation_matrix.yaml
```

You can also run `python -m rrde score samples/release_candidates.json` and it will use the bundled sample telemetry/members/obligations as defaults.

Expected output is committed in `samples/expected_output.json`.

## Sample output (excerpt, real run)

```
RC_2026_06_AFCX_IQ_v2.14.0  →  ESCALATE_TO_MD  (composite 8.76)
  vendor_delivery_risk      7.8    <-- vendor 90d: 6% defect leakage + 2 env-drift events
  intel_integrity_risk      10.0   <-- intel pipeline + schema + dedup + victim PII all touched
  member_impact_risk        9.5    <-- 13 members touched, including all 4 tier-1
  regulatory_exposure_risk  9.0    <-- Privacy Act + MSA 4.3 + MSA 4.7
  rollback_difficulty       5.0
  Triggered obligations:
    - privacy_act_notifiable_pii_change
    - msa_clause_4_3_data_handling
    - msa_clause_4_7_intel_dedup
  Required gates:
    - PRIVACY_OFFICER_REVIEW
    - PRIVACY_IMPACT_ASSESSMENT
    - MEMBER_NOTIFICATION_72H
    - INTEL_QUALITY_SHADOW_RUN
    - MEMBER_UAT_TIER1_SIGNOFF
    - BACKOUT_PLAN_REHEARSED

RC_2026_06_FRX_v1.8.2  →  SHIP_WITH_GUARDRAILS  (composite 5.46)
  Tier-1 members consume FRX.member.dashboard, so member_impact_risk hits
  the SHIP_WITH_GUARDRAILS threshold despite low intel/regulatory exposure.

RC_2026_06_Exchange_v3.2.0  →  ESCALATE_TO_MD  (composite 8.86)
  Multi-obligation stack (Privacy Act + AML/CTF + CDR + GovMatch + Auth)
  pushes regulatory_exposure_risk to 10.0, forcing MD authorisation.
```

Full JSON output is committed in [`samples/expected_output.json`](samples/expected_output.json).

## Design notes

**Why weighted-max, not weighted-average?** A release that's safe on four dimensions and catastrophic on the fifth is *not* a 5/10 release — it's the catastrophic one. The composite uses a weighted blend that respects single-dimension red flags. Specifically, `composite = max(α·max_dim, weighted_avg)` so a single 8/10 can never average itself away.

**Why an obligation matrix as YAML?** Regulatory obligations change. AML/CTF rule revisions, CDR endpoint changes, MSA renegotiations with member banks. A versioned YAML file owned by the TPM and Privacy/Compliance lead means the obligation lookup is auditable, diff-able, and historically replayable. Every score includes the obligation-matrix version that produced it.

**Why required-gates are computed, not assumed?** Releases differ. A no-schema, no-auth, intel-pipeline-only change needs `INTEL_QUALITY_SHADOW_RUN` but doesn't need `MEMBER_NOTIFICATION_72H`. The gates rules are first-class in code so they can be unit-tested and versioned alongside the scoring weights.

**Why a Decision Store?** Every decision (scores, gates, explanation, who authorised it) is timestamped and persisted. After 6 months, post-incident analysis can train weights against actual outcomes — *which scores best predicted which incidents?* The engine becomes learnable rather than static.

## Limits of this concept implementation

This is concept code. To run in production at AFCX you would add:

- **Authentication & RBAC** — currently anyone can submit an RC.
- **A real Decision Store** — currently writes to JSON; should be Postgres with audit log.
- **Member-impact data integration** — the sample `members.json` is hand-rolled; production would pull from the AFCX member-surface map.
- **A submission UI** — currently CLI-only; production needs a thin web form (or Jira intake template) for the vendor PM.
- **Notifications** — Slack/Teams/email on `HOLD_FOR_REVIEW` and `ESCALATE_TO_MD`.

All of these are ~1 sprint additions.
