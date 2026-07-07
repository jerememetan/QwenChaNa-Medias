# Phase 1 — TDD Test Plan

> **Methodology:** Red → Green → Refactor. Every test is written FIRST, watched failing, then minimal code is written to pass.
> **Scope:** Foundation — config, models, storage, BaseAgent, JobContext, pipeline, resume, API routes.
> **Prerequisites:** Resolve critical questions in `docs/phase1-spec-flow-analysis.md` before starting.

---

## Implementation Order

Components are ordered by dependency — each layer is tested and built before the layers that depend on it.

```
1. Config          (no deps)
2. Models          (no deps)
3. Storage         (depends on models)
4. BaseAgent       (depends on models)
5. JobContext      (depends on models, storage)
6. Pipeline        (depends on agents, context, storage)
7. Resume          (depends on pipeline, storage)
8. API Schemas     (depends on models)
9. API Routes      (depends on pipeline, schemas, config)
10. FastAPI App    (depends on routes, config)
```

---

## Layer 1: Config (`backend/config.py`)

**File:** `tests/test_backend/test_config.py`

| # | Test Name | What It Proves |
|---|-----------|---------------|
| 1.1 | `test_settings_loads_defaults` | Settings instantiates with sensible defaults when no env vars are set (OUTPUT_DIR="./outputs", HOST="0.0.0.0", PORT=8000). |
| 1.2 | `test_settings_reads_env_vars` | Settings picks up values from environment variables (monkeypatch `OPENAI_API_KEY`, verify it's loaded). |
| 1.3 | `test_settings_output_dir_default` | Default OUTPUT_DIR is `"./outputs"`. |
| 1.4 | `test_settings_storage_backend_default` | Default STORAGE_BACKEND is `"local"`. |

**RED → GREEN checklist:**
- [ ] All 4 tests fail (ImportError or AttributeError — Settings doesn't exist yet)
- [ ] Write `Settings` class using `pydantic-settings.BaseSettings`
- [ ] All 4 tests pass
- [ ] Refactor: none needed at this scale

---

## Layer 2: Models (`models/`)

### 2a: Job Status (`models/job.py`)

**File:** `tests/test_models/test_job.py`

| # | Test Name | What It Proves |
|---|-----------|---------------|
| 2a.1 | `test_job_status_enum_values` | JobStatus has exactly: `pending`, `running`, `completed`, `failed`. |
| 2a.2 | `test_job_record_creation` | JobRecord can be created with job_id, prompt, status=pending. |
| 2a.3 | `test_job_record_default_timestamps` | JobRecord auto-sets `created_at` and `updated_at` on creation. |
| 2a.4 | `test_job_record_serialization` | JobRecord round-trips through `model_dump()` / `model_validate_json()`. |
| 2a.5 | `test_job_record_tracks_failed_agent` | JobRecord stores `failed_agent` and `error` fields (both optional, default None). |

### 2b: Agent Schemas (`models/brief.py`, `models/script.py`, etc.)

**File:** `tests/test_models/test_schemas.py`

> Phase 1 only needs the schemas that the pipeline orchestrator touches directly. Full agent output schemas can be stubs.

| # | Test Name | What It Proves |
|---|-----------|---------------|
| 2b.1 | `test_creative_brief_schema` | CreativeBrief validates with required fields: `title`, `tone`, `audience`, `duration_seconds`, `style_keywords`. |
| 2b.2 | `test_creative_brief_rejects_missing_fields` | CreativeBrief raises ValidationError when required fields are missing. |
| 2b.3 | `test_script_scene_schema` | Scene has `narration` (str), `duration_hint` (float), `visual_direction` (str). |
| 2b.4 | `test_script_schema` | Script is a list of Scenes, validates as a collection. |
| 2b.5 | `test_storyboard_shot_schema` | Shot has `visual_prompt` (str), `camera` (str), `motion` (str), `duration` (float). |

**RED → GREEN checklist:**
- [ ] All tests fail (models don't exist yet)
- [ ] Write Pydantic models with minimum fields to pass
- [ ] All tests pass
- [ ] Refactor: extract shared patterns if any

---

## Layer 3: Storage (`storage/`)

### 3a: Storage Backend ABC (`storage/base.py`)

**File:** `tests/test_storage/test_base.py`

| # | Test Name | What It Proves |
|---|-----------|---------------|
| 3a.1 | `test_storage_backend_cannot_be_instantiated` | StorageBackend is abstract — instantiating it raises TypeError. |
| 3a.2 | `test_storage_backend_requires_save` | Subclass without `save()` raises TypeError. |
| 3a.3 | `test_storage_backend_requires_load` | Subclass without `load()` raises TypeError. |
| 3a.4 | `test_storage_backend_requires_exists` | Subclass without `exists()` raises TypeError. |
| 3a.5 | `test_storage_backend_concrete_implmentation_works` | A subclass implementing all abstract methods can be instantiated. |

### 3b: Local Storage (`storage/local.py`)

**File:** `tests/test_storage/test_local.py`

| # | Test Name | What It Proves |
|---|-----------|---------------|
| 3b.1 | `test_local_save_creates_file` | `save(job_id, agent_name, filename, data)` writes a JSON file to `outputs/{job_id}/{agent_name}/{filename}`. |
| 3b.2 | `test_local_save_creates_directories` | Nested directories are created automatically if they don't exist. |
| 3b.3 | `test_local_load_reads_file` | `load(job_id, agent_name, filename)` reads and returns the JSON content. |
| 3b.4 | `test_local_load_returns_none_for_missing` | `load()` returns `None` when the file doesn't exist (not an exception). |
| 3b.5 | `test_local_exists_returns_true_for_existing` | `exists(job_id, agent_name, filename)` returns True when file is present. |
| 3b.6 | `test_local_exists_returns_false_for_missing` | `exists()` returns False when file is absent. |
| 3b.7 | `test_local_save_and_load_roundtrip` | Data saved as dict is loaded back as identical dict. |
| 3b.8 | `test_local_list_artifacts` | `list_artifacts(job_id, agent_name)` returns list of filenames for that agent's output directory. |

**Setup:** All tests use `tmp_path` fixture — never touch real `outputs/` directory.

**RED → GREEN checklist:**
- [ ] All tests fail (storage classes don't exist)
- [ ] Write `StorageBackend` ABC with `@abstractmethod` decorators
- [ ] Write `LocalStorage` implementing all methods using `pathlib`
- [ ] All tests pass
- [ ] Refactor: ensure path construction is consistent

---

## Layer 4: BaseAgent (`agents/base.py`)

**File:** `tests/test_agents/test_base.py`

| # | Test Name | What It Proves |
|---|-----------|---------------|
| 4.1 | `test_base_agent_cannot_be_instantiated` | BaseAgent is abstract — raises TypeError. |
| 4.2 | `test_base_agent_requires_name` | Subclass without `name` class attribute raises an error (or name is part of `__init__`). |
| 4.3 | `test_base_agent_requires_run_method` | Subclass without `run()` raises TypeError on instantiation. |
| 4.4 | `test_concrete_agent_run_receives_context` | A concrete agent's `run()` receives the context object as its argument. |
| 4.5 | `test_concrete_agent_run_returns_context` | A concrete agent's `run()` returns the (possibly modified) context. |
| 4.6 | `test_agent_has_name_attribute` | Every agent instance has a `.name` property/string identifying it (e.g., "director", "research"). |

**RED → GREEN checklist:**
- [ ] Tests 4.1–4.3 fail with TypeError (abstract)
- [ ] Tests 4.4–4.6 fail (no concrete agent to test with — create a `StubAgent` in the test file)
- [ ] Write `BaseAgent` ABC with abstract `run(context) -> context` and `name` attribute
- [ ] All tests pass

---

## Layer 5: JobContext (`workflow/context.py`)

**File:** `tests/test_workflow/test_context.py`

| # | Test Name | What It Proves |
|---|-----------|---------------|
| 5.1 | `test_context_creation` | JobContext created with `job_id` and `prompt`. |
| 5.2 | `test_context_set_and_get` | `set(key, value)` stores a value; `get(key)` retrieves it. |
| 5.3 | `test_context_get_missing_returns_none` | `get("nonexistent")` returns `None`. |
| 5.4 | `test_context_get_missing_with_default` | `get("nonexistent", default="fallback")` returns the default. |
| 5.5 | `test_context_tracks_completed_agents` | `mark_agent_complete(agent_name)` adds to completed set; `is_agent_complete(name)` returns True/False. |
| 5.6 | `test_context_serialization` | `to_dict()` produces a JSON-serializable dict; `from_dict()` reconstructs an identical context. |
| 5.7 | `test_context_preserves_agent_outputs` | Agent outputs stored via `set()` survive serialization round-trip. |
| 5.8 | `test_context_completed_agents_survive_serialization` | The completed-agents set is preserved through `to_dict()` / `from_dict()`. |

**RED → GREEN checklist:**
- [ ] All tests fail (JobContext doesn't exist)
- [ ] Write `JobContext` as a dataclass or Pydantic model
- [ ] All tests pass
- [ ] Refactor: consider if dataclass or Pydantic is more appropriate (Pydantic for validation, dataclass for simplicity — Phase 1 can use either)

---

## Layer 6: Pipeline (`workflow/pipeline.py`)

**File:** `tests/test_workflow/test_pipeline.py`

> Uses **stub agents** — no real LLM/TTS/video calls. Stub agents either succeed (copy input to output) or fail (raise exception).

| # | Test Name | What It Proves |
|---|-----------|---------------|
| 6.1 | `test_pipeline_runs_agents_in_order` | Given agents [A, B, C], they execute in that exact order. |
| 6.2 | `test_pipeline_passes_context_between_agents` | Agent B receives the context that Agent A returned (including A's outputs). |
| 6.3 | `test_pipeline_persists_context_after_each_agent` | After each agent completes, context is saved to storage. Verified by checking storage has the file. |
| 6.4 | `test_pipeline_marks_agent_complete` | After agent A completes, `context.is_agent_complete("A")` is True. |
| 6.5 | `test_pipeline_stops_on_agent_failure` | When agent B raises an exception, agent C is never called. |
| 6.6 | `test_pipeline_sets_job_status_running` | Pipeline sets job status to `running` before executing first agent. |
| 6.7 | `test_pipeline_sets_job_status_completed` | Pipeline sets job status to `completed` after last agent succeeds. |
| 6.8 | `test_pipeline_sets_job_status_failed_on_error` | Pipeline sets job status to `failed` when an agent raises. |
| 6.9 | `test_pipeline_records_failed_agent` | On failure, job record stores `failed_agent` name and `error` message. |
| 6.10 | `test_pipeline_with_empty_agent_list` | Pipeline with no agents completes immediately (edge case — shouldn't happen but must not crash). |
| 6.11 | `test_pipeline_creates_output_directory` | Pipeline creates `outputs/{job_id}/` directory structure before running. |

**Test helpers to create:**
- `StubAgent(name, should_fail=False)` — a concrete BaseAgent that either passes or raises.
- `MockStorage` — or use `LocalStorage` with `tmp_path`.

**RED → GREEN checklist:**
- [ ] All tests fail (Pipeline doesn't exist)
- [ ] Write `Pipeline` class with `run(job_id, agents, context, storage)` method
- [ ] All tests pass
- [ ] Refactor: extract context persistence into a helper if repeated

---

## Layer 7: Resume (`workflow/resume.py`)

**File:** `tests/test_workflow/test_resume.py`

| # | Test Name | What It Proves |
|---|-----------|---------------|
| 7.1 | `test_resume_loads_context_from_storage` | Resume loads the persisted context for a given job_id from storage. |
| 7.2 | `test_resume_skips_completed_agents` | Given context where agents A and B are complete, resume only runs [C, D, E]. |
| 7.3 | `test_resume_runs_from_failed_agent` | If agent C failed, resume starts from C (not D). |
| 7.4 | `test_resume_raises_for_missing_context` | Resume raises a clear error when no context exists for the job_id. |
| 7.5 | `test_resume_updates_job_status` | Resume sets job status back to `running`, then to `completed` or `failed`. |
| 7.6 | `test_resume_clears_previous_failure` | After successful resume, `failed_agent` and `error` are cleared on the job record. |
| 7.7 | `test_resume_persists_context_for_new_agents` | Each newly-run agent's output is persisted during resume (same as initial run). |

**RED → GREEN checklist:**
- [ ] All tests fail (resume module doesn't exist)
- [ ] Write `resume_job(job_id, agents, storage, job_store)` function
- [ ] All tests pass
- [ ] Refactor: share persistence logic with pipeline if duplicated

---

## Layer 8: API Schemas (`backend/api/schemas.py`)

**File:** `tests/test_api/test_schemas.py`

| # | Test Name | What It Proves |
|---|-----------|---------------|
| 8.1 | `test_generate_request_requires_prompt` | GenerateRequest rejects missing `prompt` field. |
| 8.2 | `test_generate_request_rejects_empty_prompt` | GenerateRequest rejects `prompt=""` and `prompt="   "`. |
| 8.3 | `test_generate_request_rejects_oversized_prompt` | GenerateRequest rejects prompt > 5000 characters. |
| 8.4 | `test_generate_request_strips_whitespace` | Leading/trailing whitespace is stripped from prompt. |
| 8.5 | `test_generate_response_schema` | GenerateResponse has `job_id` field, serializes correctly. |
| 8.6 | `test_status_response_schema` | StatusResponse has `job_id`, `status`, `current_agent`, `created_at`, `updated_at`. Optional: `failed_agent`, `error`. |
| 8.7 | `test_result_response_schema` | ResultResponse has `job_id`, `status`, `output_path`, `artifacts`. |

**RED → GREEN checklist:**
- [ ] All tests fail (schemas don't exist)
- [ ] Write Pydantic request/response models
- [ ] All tests pass

---

## Layer 9: API Routes (`backend/api/routes.py`)

**File:** `tests/test_api/test_routes.py`

> Uses FastAPI `TestClient` (from `httpx`). No real pipeline execution — mock or stub the pipeline.

| # | Test Name | What It Proves |
|---|-----------|---------------|
| 9.1 | `test_generate_returns_202_with_job_id` | `POST /generate` with valid prompt returns 202 and a `job_id`. |
| 9.2 | `test_generate_returns_422_for_empty_prompt` | `POST /generate` with empty prompt returns 422. |
| 9.3 | `test_generate_returns_422_for_missing_prompt` | `POST /generate` with no body returns 422. |
| 9.4 | `test_generate_returns_422_for_oversized_prompt` | `POST /generate` with >5000 char prompt returns 422. |
| 9.5 | `test_generate_creates_job_record` | After `/generate`, the job exists in the job store with status `pending` or `running`. |
| 9.6 | `test_status_returns_job_info` | `GET /status/{job_id}` returns job_id, status, timestamps. |
| 9.7 | `test_status_returns_404_for_unknown_job` | `GET /status/nonexistent` returns 404. |
| 9.8 | `test_result_returns_output_for_completed_job` | `GET /result/{job_id}` returns output_path when job is completed. |
| 9.9 | `test_result_returns_404_for_unknown_job` | `GET /result/nonexistent` returns 404. |
| 9.10 | `test_result_returns_409_for_non_completed_job` | `GET /result/{job_id}` returns 409 when job is still running or pending. |
| 9.11 | `test_resume_returns_202` | `POST /resume/{job_id}` returns 202 for a failed job. |
| 9.12 | `test_resume_returns_404_for_unknown_job` | `POST /resume/nonexistent` returns 404. |
| 9.13 | `test_resume_returns_409_for_running_job` | `POST /resume/{job_id}` returns 409 when job is still running. |
| 9.14 | `test_resume_returns_409_for_completed_job` | `POST /resume/{job_id}` returns 409 when job already completed. |

**RED → GREEN checklist:**
- [ ] All tests fail (routes don't exist)
- [ ] Write route handlers with proper status codes and validation
- [ ] All tests pass
- [ ] Refactor: extract job store access into dependency if repeated

---

## Layer 10: FastAPI App (`backend/main.py`)

**File:** `tests/test_api/test_app.py`

| # | Test Name | What It Proves |
|---|-----------|---------------|
| 10.1 | `test_app_starts` | FastAPI app can be instantiated without errors. |
| 10.2 | `test_app_has_generate_route` | App has a route registered for `POST /generate`. |
| 10.3 | `test_app_has_status_route` | App has a route registered for `GET /status/{job_id}`. |
| 10.4 | `test_app_has_result_route` | App has a route registered for `GET /result/{job_id}`. |
| 10.5 | `test_app_has_resume_route` | App has a route registered for `POST /resume/{job_id}`. |

---

## Test Execution Summary

| Layer | File | Test Count |
|-------|------|-----------|
| 1. Config | `tests/test_backend/test_config.py` | 4 |
| 2a. Job Model | `tests/test_models/test_job.py` | 5 |
| 2b. Schemas | `tests/test_models/test_schemas.py` | 5 |
| 3a. Storage ABC | `tests/test_storage/test_base.py` | 5 |
| 3b. Local Storage | `tests/test_storage/test_local.py` | 8 |
| 4. BaseAgent | `tests/test_agents/test_base.py` | 6 |
| 5. JobContext | `tests/test_workflow/test_context.py` | 8 |
| 6. Pipeline | `tests/test_workflow/test_pipeline.py` | 11 |
| 7. Resume | `tests/test_workflow/test_resume.py` | 7 |
| 8. API Schemas | `tests/test_api/test_schemas.py` | 7 |
| 9. API Routes | `tests/test_api/test_routes.py` | 14 |
| 10. App | `tests/test_api/test_app.py` | 5 |
| **Total** | | **85** |

---

## TDD Discipline Checklist

Before marking Phase 1 complete, verify:

- [ ] Every test was written BEFORE the implementation
- [ ] Every test was watched failing (RED) before writing code
- [ ] Every failure was the expected one (missing feature, not typo)
- [ ] Minimal code was written to pass each test (no over-engineering)
- [ ] All 85 tests pass (GREEN)
- [ ] `pytest` output is clean — no warnings, no errors, no skipped
- [ ] No mocks used unless unavoidable (stub agents are real code, not mocks)
- [ ] Test file structure mirrors source structure

---

## Fixtures & Helpers to Build

These are test infrastructure — build them as needed, not upfront.

| Helper | Where | Purpose |
|--------|-------|---------|
| `StubAgent` | `tests/test_agents/test_base.py`, `tests/test_workflow/test_pipeline.py` | Concrete BaseAgent that succeeds or fails on demand |
| `tmp_storage` | `tests/conftest.py` | `LocalStorage` pointed at `tmp_path` |
| `sample_context` | `tests/conftest.py` | Pre-populated JobContext for pipeline/resume tests |
| `sample_job` | `tests/conftest.py` | JobRecord with known state |
| `test_client` | `tests/conftest.py` | FastAPI `TestClient` with test app |
| `mock_pipeline` | `tests/test_api/test_routes.py` | Stub pipeline that doesn't actually run agents |

---

## Running Tests

```bash
# All tests
pytest

# Single layer
pytest tests/test_storage/

# Single file
pytest tests/test_workflow/test_pipeline.py -v

# Single test
pytest tests/test_workflow/test_pipeline.py::test_pipeline_runs_agents_in_order -v

# With coverage
pytest --cov=backend --cov=agents --cov=workflow --cov=models --cov=storage --cov-report=term-missing
```
