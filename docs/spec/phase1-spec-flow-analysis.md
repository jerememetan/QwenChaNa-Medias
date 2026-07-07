# Phase 1 — Spec Flow Analysis

> **Scope:** Foundation — FastAPI skeleton, BaseAgent, JobContext, sequential pipeline orchestrator, API endpoints, config, logging.
> **Source:** PROJECT_SPEC.md §3–§7

---

## User Flows

### Flow 1: Generate Video (Happy Path)

```
Client                          API                         Pipeline
  │                              │                             │
  │── POST /generate ───────────▶│                             │
  │   { prompt: "..." }          │── validate prompt           │
  │                              │── create job (pending)      │
  │                              │── start pipeline (bg) ─────▶│
  │◀── 202 { job_id } ──────────│                             │
  │                              │                             │── Director.run(ctx)
  │                              │                             │── persist context
  │── GET /status(job_id) ──────▶│                             │── Research.run(ctx)
  │◀── { status: "running" } ───│                             │── persist context
  │          ...                 │                             │── Script.run(ctx)
  │          ...                 │                             │── Storyboard.run(ctx)
  │          ...                 │                             │── Video.run(ctx)
  │          ...                 │                             │── Voice.run(ctx)
  │          ...                 │                             │── Editor.run(ctx)
  │── GET /status(job_id) ──────▶│◀── pipeline done ──────────│
  │◀── { status: "completed" } ─│                             │
  │                              │                             │
  │── GET /result(job_id) ──────▶│                             │
  │◀── { output_path, ... } ────│                             │
```

**Entry point:** `POST /generate` with a text prompt.
**Terminal state:** `completed` — final MP4 available via `/result`.
**Key decisions:**
- Pipeline runs as a FastAPI BackgroundTask (async execution).
- Context is persisted to disk after EACH agent completes (enables resume).
- Job status transitions: `pending → running → completed`.

---

### Flow 2: Agent Failure

```
Pipeline
  │
  ├── Director.run(ctx)     ✅ → persist context
  ├── Research.run(ctx)     ✅ → persist context
  ├── Script.run(ctx)       ❌ → raises AgentError
  │
  ▼
  Orchestrator catches exception
  ├── job.status = "failed"
  ├── job.failed_agent = "script"
  ├── job.error = "..."
  └── context already persisted after Research (last success)
```

**Terminal state:** `failed` — client sees which agent failed via `/status`.
**Key invariant:** Context on disk reflects the last *successfully completed* agent. No partial agent output is trusted.

---

### Flow 3: Resume After Failure

```
Client                          API                         Pipeline
  │                              │                             │
  │── GET /status(job_id) ──────▶│                             │
  │◀── { status: "failed",      │                             │
  │     failed_agent: "script" }│                             │
  │                              │                             │
  │── POST /resume(job_id) ─────▶│                             │
  │                              │── load context from disk ──▶│
  │                              │── detect completed agents   │
  │                              │     (Director ✅, Research ✅)│
  │                              │── skip completed ──────────▶│
  │                              │     Script.run(ctx)         │
  │                              │     Storyboard.run(ctx)     │
  │                              │     ...                     │
  │◀── 202 { job_id } ──────────│                             │
```

**Entry point:** `POST /resume/{job_id}` — only valid when status is `failed`.
**Key invariant:** Agents are skipped based on persisted artifacts, not in-memory state. If `director/creative_brief.json` exists on disk, Director is skipped.

---

### Flow 4: Invalid Input

```
Client                          API
  │                              │
  │── POST /generate ───────────▶│
  │   { prompt: "" }             │── validate: empty prompt
  │◀── 422 { detail: [...] } ──│
  │                              │
  │── POST /generate ───────────▶│
  │   { }                        │── validate: missing prompt
  │◀── 422 { detail: [...] } ──│
  │                              │
  │── GET /status(fake-id) ─────▶│
  │                              │── job not found
  │◀── 404 { detail: "..." } ──│
```

**Terminal state:** Immediate error response. No job created.

---

## Gaps

### Critical

| # | Gap | Why It Matters |
|---|-----|---------------|
| G1 | **No `POST /resume` endpoint defined.** Spec §3.1 only lists `/generate`, `/status`, `/result`. But §5 describes resume-from-failure as a core feature. Without an API trigger, resume is unreachable. | Implementation has no way to invoke resume. Must decide endpoint shape now. |
| G2 | **Sync vs async execution unspecified.** Video generation takes minutes. If `/generate` blocks, the HTTP request will timeout. Spec mentions "job-based execution" and polling, implying async — but it's not explicit. | Determines entire execution model. BackgroundTask vs subprocess vs task queue. |
| G3 | **Server crash recovery undefined.** If the process dies mid-pipeline, in-memory job state is lost. Context.json exists on disk but nothing reloads it on startup. | Jobs become permanently orphaned after a crash. Need at minimum a startup scan or a "retry failed" mechanism. |

### Important

| # | Gap | Why It Matters |
|---|-----|---------------|
| G4 | **Prompt validation rules absent.** Spec only says "text prompt." No max length, no character restrictions, no language constraints. | Without bounds, a 100KB prompt hits the LLM and wastes money or crashes the agent. |
| G5 | **`/result` response format unspecified.** Does it return the MP4 as a `FileResponse` download? Or JSON metadata with a file path? | Client integration depends on this. FileResponse is simpler for MVP but less flexible. |
| G6 | **Job status granularity unclear.** Does `/status` report just `pending/running/completed/failed`? Or also which agent is currently executing and how many are done? | Affects debuggability. Per-agent progress is high-value for a pipeline this long. |
| G7 | **Concurrent job handling undefined.** Can multiple `/generate` calls run simultaneously? Is there a limit? | Without a concurrency model, two simultaneous jobs could conflict on resources (FFmpeg, API rate limits). |

### Minor

| # | Gap | Why It Matters |
|---|-----|---------------|
| G8 | **No job listing endpoint.** Client can't discover existing jobs. | Low priority for MVP — client always knows its own job_ids. |
| G9 | **No job cleanup/TTL.** Output files accumulate on disk indefinitely. | Not urgent for MVP but will matter in testing. |
| G10 | **No optional parameters on `/generate`.** Future spec mentions duration, style, aspect ratio. | Phase 1 can hardcode defaults, but the request schema should leave room for expansion. |

---

## Questions

Ordered by priority. Each includes the stakes and a default assumption for Phase 1.

### Q1: Should `/generate` execute the pipeline asynchronously via BackgroundTask?
- **Stakes:** Determines the entire execution model. Sync = simple but broken for long pipelines. Async = correct but needs job state management.
- **Default assumption:** **Async via FastAPI BackgroundTask.** Return `202 Accepted` with `job_id` immediately. Pipeline runs in background. This matches the spec's polling model.

### Q2: What endpoint triggers resume, and what is its contract?
- **Stakes:** Without this, the resume feature described in §5 is dead code.
- **Default assumption:** **`POST /resume/{job_id}`**. Loads persisted context, skips completed agents, re-runs from the failure point. Returns `202 Accepted`. Only valid when job status is `failed`. Returns `409 Conflict` if job is `running` or `completed`.

### Q3: What does `/result/{job_id}` return?
- **Stakes:** Client integration pattern depends on this.
- **Default assumption:** **JSON response** with `output_path`, `job_id`, `status`, and `artifacts` (list of generated file paths). Not a raw file download — that's a Phase 2 concern. The path points to `outputs/{job_id}/editor/final/final_video.mp4`.

### Q4: What are the prompt validation rules?
- **Stakes:** Prevents waste and crashes from malformed input.
- **Default assumption:** **Non-empty string, 1–5000 characters.** Stripped of leading/trailing whitespace. Reject empty or whitespace-only prompts with 422.

### Q5: What does `/status` report?
- **Stakes:** Determines client polling experience and debuggability.
- **Default assumption:** **Rich status object:** `job_id`, `status` (pending/running/completed/failed), `current_agent` (name of agent currently executing or last completed), `failed_agent` (if failed), `error` (if failed), `created_at`, `updated_at`.

### Q6: How are concurrent jobs handled in Phase 1?
- **Stakes:** Resource contention (API rate limits, FFmpeg, disk I/O).
- **Default assumption:** **No limit in Phase 1.** Each job runs independently via BackgroundTask. Track all jobs in an in-memory dict keyed by `job_id`. Document this as a known limitation — Phase 5 should add a job queue.

### Q7: What happens on server crash? How are orphaned jobs recovered?
- **Stakes:** Jobs stuck in "running" state forever after a crash.
- **Default assumption:** **On startup, scan `outputs/` for `context.json` files.** Any job with a context but no "completed" marker is marked `failed` with `error: "server restart"`. Client can then call `/resume`. This is a best-effort recovery — good enough for MVP.

---

## Recommended Next Steps

1. **Resolve Q1–Q3 before writing any code.** These define the API contract and execution model. The defaults above are recommended — confirm or override.
2. **Resolve Q4–Q5 before implementing routes.** These define validation and response schemas.
3. **Q6–Q7 can be deferred to implementation** with the defaults above, but should be documented as known limitations.
4. **After questions are resolved, proceed to TDD test plan** (see `docs/phase1-test-plan.md`).
