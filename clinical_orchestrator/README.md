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

A **publish / subscribe event bus** (`core/event_bus.py`) lets every
agent emit and consume `ClinicalEvent`s (e.g. `diagnostic.finding`,
`vitals.deviation`, `documentation.update`). The orchestrator registers
default subscriptions so that, for example, a new imaging finding
automatically updates the current SOAP note and the chronic care risk
dashboard — exactly as required by the master prompt.

The transport is **pluggable** via `CLINICAL_BUS_URL`:

| URL | Backend | Notes |
| --- | --- | --- |
| `memory://` *(default)* | In-process | Single-host; zero deps |
| `redis://host:6379/0?stream=clinical` | Redis Streams | `pip install -e ".[redis]"` |
| `kafka://broker:9092?topic=clinical&group=orchestrator` | Confluent Kafka | `pip install -e ".[kafka]"` |

If a configured broker is unreachable or its client library is missing,
the bus **degrades to in-process** rather than crashing — consistent with
the orchestrator's "self-debug & graceful fallback" stance.

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
rule-based agents so it can be tested end-to-end in CI.

### LLM providers

Three OpenAI-compatible providers are supported behind one router; pick via
`CLINICAL_LLM_PROVIDER` (`auto` is the default and tries them in order):

| Provider | Env keys | Install extra |
| --- | --- | --- |
| OpenAI | `OPENAI_API_KEY` (+ `OPENAI_MODEL`) | `pip install -e ".[openai]"` |
| Anthropic | `ANTHROPIC_API_KEY` (+ `ANTHROPIC_MODEL`) | `pip install -e ".[anthropic]"` |
| Gemini | `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) (+ `GEMINI_MODEL`) | `pip install -e ".[gemini]"` |
| All three | — | `pip install -e ".[llm]"` |

If no key is present, the router reports `provider="none"` and every
`complete*()` call returns `None` so agents transparently fall back to their
rule-based path. JSON-mode is supported via `complete_json(...)`.

### Persistent storage

`CLINICAL_STORAGE_URL` selects where patients, HITL actions, and the audit
log are mirrored:

| URL | Backend |
| --- | --- |
| `memory://` *(default)* | In-process only |
| `sqlite:///path/to/co.sqlite` | File-backed sqlite (stdlib, no deps) |

In-memory copies are still maintained for fast reads; durable storage is
written-through. Pending HITL actions and patient state are replayed on
process restart so a crash does not lose work.

### ICD-10 / CPT data

* **ICD-10-CM:** ~190 curated codes from the **CMS FY2025** public-domain
  release. For the full ~70k-code set, hand the CMS XML to
  `data.icd10_cpt.load_icd10_cm_xml(path)` at startup.
* **CPT®:** intentionally **empty by default** (AMA-licensed; not
  redistributable). Plug in your licensed JSONL via
  `data.icd10_cpt.load_cpt_jsonl(path)`.
* **Protocol thresholds:** pinned to specific cited guideline versions
  (JNC-8 / ACC-AHA 2017, ADA 2024, AHA/ACC/HFSA 2022, GOLD 2024, KDIGO 2024).
  Inspect at runtime via `data.protocols.protocol_versions()`.

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
