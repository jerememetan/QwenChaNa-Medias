# Phase 2 — Spec Flow Analysis: Core Agents

> **Scope:** Director, Research, Script, Storyboard agents + AlibabaCloudLLMService implementation.
> **Grounded in:** Phase 1 codebase (models, storage, pipeline, API all working; agent files empty).

---

## 1. Codebase Context

### What exists (Phase 1)

| Component        | Status  | Key Detail                                                                                              |
| ---------------- | ------- | ------------------------------------------------------------------------------------------------------- |
| `BaseAgent` ABC  | ✅ Done | `name: AgentName`, `run(context: WorkflowState) -> WorkflowState`                                       |
| `LLMService` ABC | ✅ Done | `generate(prompt: str, agent_name: AgentName) -> str`                                                   |
| `Pipeline`       | ✅ Done | Runs agents sequentially, persists context after each agent                                             |
| `WorkflowState`  | ✅ Done | `agent_results: dict[AgentName, AgentResult]`, `prompt`, `status`, etc.                                 |
| Models           | ✅ Done | `CreativeBrief`, `ResearchNotes`, `Script`, `Scene`, `Storyboard`, `Shot`, `AgentResult`, `ArtifactRef` |
| Storage          | ✅ Done | `LocalStorage` — `save(job_id, agent_name, filename, data)`                                             |
| API              | ✅ Done | `/generate` creates job but does NOT run pipeline (no background task)                                  |
| `Settings`       | ✅ Done | `LLMConfig` with `provider`, `api_key`, `base_url`, `model`, `timeout`                                  |

### What's missing (Phase 2 scope)

| Component                    | Status        | Key Detail                                                             |
| ---------------------------- | ------------- | ---------------------------------------------------------------------- |
| `agents/director.py`         | ❌ Empty file | Must implement `BaseAgent` with `name = AgentName.DIRECTOR`            |
| `agents/research.py`         | ❌ Empty file | Must implement `BaseAgent` with `name = AgentName.RESEARCH`            |
| `agents/script.py`           | ❌ Empty file | Must implement `BaseAgent` with `name = AgentName.SCRIPT`              |
| `agents/storyboard.py`       | ❌ Empty file | Must implement `BaseAgent` with `name = AgentName.STORYBOARD`          |
| `tools/llm.py` concrete impl | ❌ Only ABC   | `AlibabaCloudLLMService` not implemented yet                           |
| Pipeline → API wiring        | ❌ Gap        | `/generate` creates a `WorkflowState` but never calls `Pipeline.run()` |

### Existing patterns to follow

- **Agent pattern:** `name` class attribute + `run(context) -> context` + raise exception on failure (Pipeline catches it)
- **LLM pattern:** ABC + concrete subclass injected at runtime; agents never call raw APIs
- **Persistence pattern:** Agent writes output to `context.agent_results[self.name]` as `AgentResult`; Pipeline persists context.json
- **Config pattern:** `Settings` provides grouped `LLMConfig`; concrete service reads from it

---

## 2. User Flows

### Flow 1: Generate a video (happy path)

```
User sends POST /generate {"prompt": "Make a 30s explainer about climate change"}
  → API creates JobRecord + WorkflowState (status=PENDING)
  → Pipeline starts: status → RUNNING
  → Director.run(ctx): reads ctx.prompt → calls LLM → parses CreativeBrief → writes to ctx.agent_results[DIRECTOR]
  → Research.run(ctx): reads ctx.agent_results[DIRECTOR].output_data → calls LLM → parses ResearchNotes → writes to ctx.agent_results[RESEARCH]
  → Script.run(ctx): reads brief + research → calls LLM → parses Script → writes to ctx.agent_results[SCRIPT]
  → Storyboard.run(ctx): reads script → calls LLM → parses Storyboard → writes to ctx.agent_results[STORYBOARD]
  → Pipeline sets status → COMPLETED
  → User calls GET /result/{job_id} → gets output_path + artifacts
```

**Decision points:** None in Phase 2 (sequential, no branching).

**Terminal states:**

- ✅ COMPLETED — all 4 agents ran, context persisted
- ❌ FAILED — one agent raised; Pipeline catches, sets `failed_agent` + `error`

### Flow 2: Resume after failure

```
User sends POST /resume/{job_id}
  → resume_job loads context.json from storage
  → Skips agents with results already in agent_results
  → Runs remaining agents via Pipeline.run()
  → Returns final context
```

**Already works** — Phase 1 resume logic handles this. No new flow needed for Phase 2 agents.

### Flow 3: LLM failure mid-pipeline

```
Director.run(ctx) calls LLM → LLM returns invalid/unparseable JSON
  → Director raises ValueError or LLM timeout
  → Pipeline catches → sets status=FAILED, failed_agent=DIRECTOR, error=message
  → User sees GET /status/{job_id} → status=failed, failed_agent=director
  → User calls POST /resume/{job_id} → retry from Director
```

---

## 3. Gaps

### Critical

**G1: `/generate` never runs the pipeline.**
The `/generate` endpoint creates a `WorkflowState` and saves it, but never calls `Pipeline.run()`. The job stays at `PENDING` forever. This must be wired — either synchronously (blocks the request, bad for UX) or via a background task. The PROJECT_SPEC §5 says "job-based execution" but Phase 1 left this as a stub.

**Default:** Synchronous execution for Phase 2 (simplest, matches sequential pipeline). Background tasks deferred to a later phase.

**G2: No prompt template system.**
Each agent needs to construct an LLM prompt from upstream outputs. Where do these templates live? Hardcoded in each agent? A separate templates file? The PROJECT_SPEC doesn't specify prompt engineering structure — agents will need structured prompts that produce parseable JSON output.

**Default:** Each agent owns its own prompt template as a class method or module-level constant. No external template files — YAGNI for Phase 2.

**G3: LLM structured output parsing.**
`LLMService.generate()` returns a raw `str`. Agents need to parse that string into typed Pydantic models (`CreativeBrief`, `Script`, etc.). What happens when the LLM returns malformed JSON? No retry logic, no fallback.

**Default:** Each agent parses with `model_validate_json()` inside a try/except. If parsing fails, raise a descriptive error (Pipeline catches it). Retry logic deferred to Phase 3.

### Important

**G4: `AlibabaCloudLLMService` needs real API integration.**
The ABC exists but the concrete class doesn't. Need to call Alibaba Cloud's DashScope-compatible endpoint (OpenAI-compatible API per `.env.example`). The `Settings.llm` config has `base_url`, `api_key`, `model`, `timeout` — the service should use all of these.

**Default:** Use `openai` Python SDK against the DashScope-compatible endpoint (already OpenAI-format). Add `openai` to `requirements.txt`.

**G5: Agent output_data schema is untyped.**
`AgentResult.output_data` is `dict = Field(default_factory=dict)` — completely unstructured. Agents dump their model dicts into it, but there's no schema enforcement. Downstream agents reading `ctx.agent_results[DIRECTOR].output_data["brief"]` have no type safety.

**Default:** Agents serialize their output model with `model_dump(mode="json")` into `output_data`. Downstream agents extract and validate with `CreativeBrief.model_validate()`. No schema change to `AgentResult.output_data` — it stays a dict.

**G6: Job status updates not propagated to JobRecord.**
`Pipeline.run()` updates `WorkflowState.status`, but `routes.py` reads from the in-memory `job_store` (dict of `JobRecord`). The `JobRecord.status` stays at `PENDING` unless the route explicitly syncs it from the WorkflowState. Currently `/status` reads `WorkflowState` to get `current_agent`, but uses `JobRecord.status` — these can diverge.

**Default:** The `/generate` route or background task must sync `JobRecord.status` from the final `WorkflowState.status` after pipeline completes. For synchronous execution, the route can update `job_store[job_id].status` directly after `Pipeline.run()` returns.

### Minor

**G7: Agent naming convention in storage.**
`StorageBackend.save()` takes `agent_name: str` (not `AgentName`). Pipeline passes `"pipeline"` for context.json. Agents should pass `self.name.value` for their artifacts. Currently inconsistent — some places use enum, some use string.

**Default:** Agents pass `self.name.value` when calling `storage.save()`. Pipeline passes `"pipeline"` for context.json (existing pattern, keep it).

**G8: No logging in agents.**
PROJECT_SPEC §5 mentions logging but no `logger.py` exists. Agents will produce no log output during execution.

**Default:** Use Python's `logging` module directly in each agent. No custom logger utility — YAGNI.

---

## 4. Questions

| #   | Question                                                                                                                                                                    | Stakes                                                                                                                                    | Default if unanswered                                                                                  |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| Q1  | Should `/generate` run the pipeline synchronously (blocking the HTTP response until all agents finish) or spawn a background task?                                          | Synchronous = simple but slow (30s+ for 4 LLM calls). Background = better UX but needs asyncio/task tracking.                             | Synchronous for Phase 2. Background deferred.                                                          |
| Q2  | Should `AlibabaCloudLLMService` use the `openai` Python SDK or raw `httpx` calls against the DashScope endpoint?                                                            | `openai` SDK gives retries, streaming, error types for free. `httpx` = fewer deps, more control.                                          | `openai` SDK — DashScope is OpenAI-compatible, so it works out of the box.                             |
| Q3  | How should agents handle LLM output that doesn't parse into the expected model? Raise immediately, or retry with a simplified prompt?                                       | Retry = more resilient but complex. Raise = simpler, lets Pipeline/Resume handle recovery.                                                | Raise immediately. Retry logic deferred to Phase 3.                                                    |
| Q4  | Should agents also persist their individual output model as a separate JSON file (e.g., `outputs/{job_id}/director/creative_brief.json`), or rely solely on `context.json`? | Separate files = easier debugging, matches PROJECT_SPEC §6 layout. Only context.json = simpler, but harder to inspect individual outputs. | Persist both: agent saves its model JSON via `storage.save()` AND writes to `AgentResult.output_data`. |
| Q5  | Should the Director agent generate the `CreativeBrief` in one LLM call or two (enrichment → brief)?                                                                         | One call = simpler prompt but harder to control output format. Two calls = more reliable but doubles latency.                             | One call with a structured prompt that requests JSON output.                                           |

---

## 5. Recommended Next Steps

1. **Resolve Q1** — decide synchronous vs background for `/generate`. This determines the entire route wiring approach.
2. **Resolve Q2** — decide `openai` SDK vs `httpx`. This determines `AlibabaCloudLLMService` implementation and `requirements.txt` update.
3. **Implement `AlibabaCloudLLMService`** first — all 4 agents depend on it.
4. **Implement agents in dependency order:** Director → Research → Script → Storyboard (matches pipeline order and data flow).
5. **Wire `/generate` to call `Pipeline.run()`** — closes G1, the critical gap.
6. **Sync JobRecord status from WorkflowState** — closes G6.

---

## Resolved Decisions (for implementation plan)

Based on defaults and codebase patterns:

| Decision             | Resolution                                                                                              |
| -------------------- | ------------------------------------------------------------------------------------------------------- |
| Execution mode       | **Synchronous** — `/generate` calls `Pipeline.run()` inline. Simple, testable. Background deferred.     |
| LLM client           | **`openai` SDK** — DashScope is OpenAI-compatible. Add `openai>=1.0` to requirements.                   |
| LLM output parsing   | **Raise on parse failure** — `model_validate_json()` in try/except. No retry.                           |
| Artifact persistence | **Dual** — agent saves model JSON via `storage.save()` AND writes `AgentResult.output_data`.            |
| Prompt structure     | **One LLM call per agent** — structured prompt requesting JSON output matching the target model schema. |
