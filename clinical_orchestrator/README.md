# Clinical Orchestrator

An **agentic, multi-module AI system** that assists clinicians by automating
documentation, monitoring chronic care, and providing diagnostic decision
support. It is designed around the **Master System Prompt** for the
*Intelligent Clinical Orchestrator* and operates with strict
**human-in-the-loop (HITL)** safety, **PII masking**, and a built-in
**cross-collaboration event bus** that lets agents share findings in real
time.

> **Status:** suggestions only. The system *never* makes binding clinical
> decisions. Every care-plan or report change requires `Confirm` / `Modify`
> from a licensed clinician.

## Modules

| Agent | Purpose |
| --- | --- |
| **Documentation Agent** | Parses dialogue / encounter text into structured **SOAP** notes and maps findings to **ICD-10 / CPT** codes. |
| **Chronic Care Agent** | Watches incoming vitals & labs against **clinical protocols** (HTN, DM, CHF, COPD, CKD) and proposes care-plan adjustments + KPI deltas (ALOS, bed-occupancy). |
| **Diagnostic Agent** | Coordinates **Imaging**, **Pathology**, and **History** sub-agents to synthesize multimodal findings, with spatial coordinates / heatmap references. |
| **Orchestrator (Supervisor)** | Routes tasks, enforces HITL gates, and propagates findings across modules via the event bus. |

## Cross-collaboration framework

A lightweight in-process **publish / subscribe event bus**
(`core/event_bus.py`) lets every agent emit and consume `ClinicalEvent`s
(e.g. `diagnostic.finding`, `vitals.deviation`, `documentation.update`).
The orchestrator registers default subscriptions so that, for example, a new
imaging finding automatically updates the current SOAP note and the chronic
care risk dashboard — exactly as required by the master prompt.

## Self-debug & auto-recovery

`core/self_debug.py` wraps every agent call with:

* exponential-backoff **retries** on transient errors
* a **circuit breaker** that opens after repeated failures
* a periodic **health probe** that re-runs known-good fixtures and
  auto-resets the breaker once an agent recovers
* a structured **audit trail** of every retry, recovery, and HITL escalation

Combined with the always-on `/health` endpoint, this gives the system the
"self-correcting / auto-debug" property requested in the brief.

## Running

```bash
cd clinical_orchestrator
pip install -e ".[dev]"

# CLI demo (runs an end-to-end scenario, no external services required)
python -m clinical_orchestrator.cli demo

# REST API
uvicorn clinical_orchestrator.api.server:app --reload --port 8000
# then visit http://localhost:8000/docs
```

The system runs **fully offline by default** using deterministic
rule-based agents so it can be tested end-to-end in CI. To plug in a
real LLM, set `OPENAI_API_KEY` and install the `llm` extra
(`pip install -e ".[llm]"`); the LLM provider in `core/llm.py` will
use it automatically and fall back to the rule-based path on any error.

## Safety & compliance

* **HIPAA / GDPR-friendly:** PII (names, MRNs, DOBs, phone, email, addresses)
  is masked before any text leaves an agent unless the consumer explicitly
  declares a clinical need.
* **HITL gates:** every care-plan change, diagnostic conclusion, or coded
  encounter is emitted as a `pending_review` action that requires a
  clinician `confirm` or `modify` call before it is committed.
* **Audit log:** append-only JSONL audit (`core/audit.py`) records every
  agent action, escalation, retry, and clinician decision.

## Layout

```
clinical_orchestrator/
  core/        # event bus, shared patient context, safety, PII, audit, self-debug, LLM provider
  agents/      # documentation, chronic_care, diagnostic + sub-agents (imaging/pathology/history)
  data/        # ICD-10/CPT lookup, care protocols
  api/         # FastAPI server + Pydantic schemas
  cli.py       # demo CLI
tests/         # pytest suite (offline, deterministic)
examples/      # runnable demo scripts
```

See `examples/demo.py` for a complete walkthrough.
