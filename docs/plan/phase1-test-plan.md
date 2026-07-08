# Phase 1 — TDD Test Plan

> **Methodology:** Red → Green → Refactor. Every test is written FIRST, watched failing, then minimal code is written to pass.
> **Scope:** Foundation — config, models, storage, BaseAgent, JobContext, pipeline, resume, API routes.
> **Prerequisites:** Resolve critical questions in `docs/spec/phase1-spec-flow-analysis.md` before starting.
> **Model alignment:** All tests reference the actual Pydantic v2 models in `models/`.

---

## Implementation Order

Components are ordered by dependency — each layer is tested and built before the layers that depend on it.

```
1. Config          (no deps)
2. Models          (no deps — already implemented)
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

Service-oriented design: flat `LLM_`, `VOICE_`, `VIDEO_`, `STORAGE_`, `SERVER_` env vars on `Settings` (BaseSettings), grouped via read-only `@property` access returning Pydantic `BaseModel` sub-models. No nested BaseSettings — avoids env_prefix propagation bug with pre-evaluated defaults.

**File:** `tests/test_backend/test_config.py`

| #   | Test Name                                      | What It Proves                                                                                                                               |
| --- | ---------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| 1.1 | `test_settings_loads_defaults`                 | `Settings` instantiates with all service defaults (`LLM_PROVIDER`, `LLM_API_KEY=""`, `LLM_MODEL`, `VOICE_PROVIDER`, `VIDEO_PROVIDER`, etc.). |
| 1.2 | `test_settings_llm_reads_env_vars`             | `Settings` picks up LLM overrides from env vars (monkeypatch `LLM_API_KEY`, `LLM_MODEL`).                                                    |
| 1.3 | `test_settings_llm_property_groups_fields`     | `settings.llm` returns an `LLMConfig` with all five fields populated from flat env vars.                                                     |
| 1.4 | `test_settings_llm_property_reflects_env_vars` | `settings.llm` reflects env var overrides (monkeypatch `LLM_API_KEY`, `LLM_MODEL` → property picks them up).                                 |
| 1.5 | `test_settings_storage_defaults`               | `settings.storage` returns `StorageConfig` with `backend="local"`, `output_dir="./outputs"`.                                                 |
| 1.6 | `test_settings_server_defaults`                | `settings.server` returns `ServerConfig` with `host="0.0.0.0"`, `port=8000`.                                                                 |
| 1.7 | `test_llm_config_standalone`                   | `LLMConfig()` can be constructed standalone with defaults (pure BaseModel, not BaseSettings).                                                |

**RED → GREEN checklist:**

- [x] All 7 tests fail (ImportError — `Settings`, `LLMConfig`, etc. don't exist yet)
- [x] Write `Settings` class (flat BaseSettings fields + @property grouped access)
- [x] Write `LLMConfig`, `VoiceConfig`, `VideoConfig`, `StorageConfig`, `ServerConfig` (BaseModel sub-models)
- [x] All 7 tests pass
- [x] Refactor: none needed

### Layer 1b: LLM Service Abstraction (`tools/llm.py`)

Provider-agnostic `LLMService` ABC. Agents call `llm_service.generate(prompt, agent_name)` — concrete implementation (`AlibabaCloudLLMService`) deferred to Phase 2.

**File:** `tests/test_tools/test_llm.py`

| #    | Test Name                                           | What It Proves                                                       |
| ---- | --------------------------------------------------- | -------------------------------------------------------------------- |
| 1b.1 | `test_llm_service_is_abstract`                      | `LLMService()` raises `TypeError` — cannot instantiate ABC directly. |
| 1b.2 | `test_llm_service_requires_generate`                | Subclass without `generate()` raises `TypeError` on instantiation.   |
| 1b.3 | `test_concrete_llm_service_can_be_instantiated`     | `StubLLMService` (with `generate()`) can be instantiated.            |
| 1b.4 | `test_concrete_llm_service_generate_returns_string` | `StubLLMService.generate()` returns a `str` — contract verified.     |

**RED → GREEN checklist:**

- [x] All 4 tests fail (ImportError — `LLMService` doesn't exist yet)
- [x] Write `LLMService` ABC with abstract `generate(prompt, agent_name) -> str`
- [x] All 4 tests pass
- [x] Refactor: none needed

---

## Layer 2: Models (`models/`)

> All models are **already implemented** in `models/`. These tests verify they work correctly and serve as regression tests.

### 2a: Enums (`models/enums.py`)

**File:** `tests/test_models/test_job.py`

| #    | Test Name                              | What It Proves                                                                                                    |
| ---- | -------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| 2a.1 | `test_job_status_enum_values`          | `JobStatus` has exactly four values: `pending`, `running`, `completed`, `failed`.                                 |
| 2a.2 | `test_agent_name_enum_values`          | `AgentName` has exactly seven values: `director`, `research`, `script`, `storyboard`, `video`, `voice`, `editor`. |
| 2a.3 | `test_agent_name_serializes_as_string` | `AgentName.DIRECTOR` serializes to `"director"` via `model_dump(mode="json")`.                                    |
| 2a.4 | `test_job_status_serializes_as_string` | `JobStatus.PENDING` serializes to `"pending"`.                                                                    |

### 2b: JobRecord (`models/job.py`)

| #    | Test Name                            | What It Proves                                                                  |
| ---- | ------------------------------------ | ------------------------------------------------------------------------------- |
| 2b.1 | `test_job_record_creation`           | `JobRecord(job_id="abc", prompt="test")` creates with `status=pending`.         |
| 2b.2 | `test_job_record_default_timestamps` | `created_at` and `updated_at` are auto-set to UTC now on creation.              |
| 2b.3 | `test_job_record_serialization`      | Round-trip: `model_dump_json()` → `model_validate_json()` preserves all fields. |
| 2b.4 | `test_job_record_tracks_failure`     | `failed_agent` and `error` fields default to `None`, can be set.                |
| 2b.5 | `test_job_record_status_transition`  | `status` can be mutated: `pending → running → completed`.                       |

### 2c: Agent Output Schemas (`models/brief.py`, `models/scene.py`, `models/script.py`, `models/storyboard.py`, `models/research.py`)

**File:** `tests/test_models/test_schemas.py`

| #     | Test Name                                       | What It Proves                                                                                     |
| ----- | ----------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| 2c.1  | `test_creative_brief_required_fields`           | `CreativeBrief` requires `title`, `prompt`, `tone`, `audience`, `duration_seconds`, `summary`.     |
| 2c.2  | `test_creative_brief_rejects_negative_duration` | `duration_seconds=-1` raises `ValidationError`.                                                    |
| 2c.3  | `test_creative_brief_defaults`                  | `aspect_ratio` defaults to `"16:9"`, `style_keywords` defaults to `[]`.                            |
| 2c.4  | `test_scene_required_fields`                    | `Scene` requires `scene_number`, `narration`, `duration_hint`, `visual_direction`.                 |
| 2c.5  | `test_scene_rejects_scene_number_zero`          | `scene_number=0` raises `ValidationError` (must be `>=1`).                                         |
| 2c.6  | `test_script_requires_at_least_one_scene`       | `Script(scenes=[])` raises `ValidationError` (`min_length=1`).                                     |
| 2c.7  | `test_script_scene_ordering`                    | Scenes are stored in insertion order and `scene_number` is explicit.                               |
| 2c.8  | `test_shot_required_fields`                     | `Shot` requires `shot_number`, `scene_number`, `visual_prompt`, `camera`, `motion`, `duration`.    |
| 2c.9  | `test_storyboard_requires_at_least_one_shot`    | `Storyboard(shots=[])` raises `ValidationError`.                                                   |
| 2c.10 | `test_research_note_required_fields`            | `ResearchNote` requires `topic` and `content`; `source` and `verified` are optional with defaults. |
| 2c.11 | `test_research_notes_confidence_range`          | `overall_confidence=1.5` raises `ValidationError` (must be `0.0–1.0`).                             |

### 2d: AgentResult and WorkflowState (`models/agent_result.py`, `models/workflow_state.py`)

**File:** `tests/test_models/test_schemas.py` (continued)

| #    | Test Name                                   | What It Proves                                                                                                       |
| ---- | ------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| 2d.1 | `test_agent_result_success`                 | `AgentResult(agent_name=AgentName.DIRECTOR, success=True)` creates with empty `output_data` and `artifacts`.         |
| 2d.2 | `test_agent_result_failure`                 | `AgentResult(agent_name=AgentName.SCRIPT, success=False, error="LLM timeout")` stores the error.                     |
| 2d.3 | `test_artifact_ref_required_fields`         | `ArtifactRef` requires `agent_name`, `filename`, `content_type`. `size_bytes` is optional.                           |
| 2d.4 | `test_workflow_state_creation`              | `WorkflowState(job_id="abc", prompt="test")` defaults to `status=pending`, `agent_results={}`, `current_agent=None`. |
| 2d.5 | `test_workflow_state_agent_results_by_enum` | `agent_results` is keyed by `AgentName` enum values.                                                                 |
| 2d.6 | `test_workflow_state_json_roundtrip`        | `model_dump_json()` → `model_validate_json()` preserves `agent_results` dict with `AgentResult` values.              |
| 2d.7 | `test_workflow_state_tracks_current_agent`  | `current_agent` can be set to any `AgentName` value.                                                                 |

**RED → GREEN checklist:**

- [ ] All tests pass immediately (models already exist)
- [ ] If any test fails, models have a bug — fix the model, not the test

---

## Layer 3: Storage (`storage/`)

### 3a: Storage Backend ABC (`storage/base.py`)

**File:** `tests/test_storage/test_base.py`

| #    | Test Name                                            | What It Proves                                                      |
| ---- | ---------------------------------------------------- | ------------------------------------------------------------------- |
| 3a.1 | `test_storage_backend_cannot_be_instantiated`        | `StorageBackend` is abstract — instantiating it raises `TypeError`. |
| 3a.2 | `test_storage_backend_requires_save`                 | Subclass without `save()` raises `TypeError`.                       |
| 3a.3 | `test_storage_backend_requires_load`                 | Subclass without `load()` raises `TypeError`.                       |
| 3a.4 | `test_storage_backend_requires_exists`               | Subclass without `exists()` raises `TypeError`.                     |
| 3a.5 | `test_storage_backend_requires_list_artifacts`       | Subclass without `list_artifacts()` raises `TypeError`.             |
| 3a.6 | `test_storage_backend_concrete_implementation_works` | A subclass implementing all abstract methods can be instantiated.   |

**Abstract method signatures:**

```python
class StorageBackend(ABC):
    @abstractmethod
    def save(self, job_id: str, agent_name: str, filename: str, data: dict) -> None: ...
    @abstractmethod
    def load(self, job_id: str, agent_name: str, filename: str) -> dict | None: ...
    @abstractmethod
    def exists(self, job_id: str, agent_name: str, filename: str) -> bool: ...
    @abstractmethod
    def list_artifacts(self, job_id: str, agent_name: str) -> list[str]: ...
```

### 3b: Local Storage (`storage/local.py`)

**File:** `tests/test_storage/test_local.py` — all tests use `tmp_path` fixture, never touch real `outputs/`.

| #    | Test Name                                     | What It Proves                                                                                                    |
| ---- | --------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| 3b.1 | `test_local_save_creates_file`                | `save(job_id, agent_name, filename, data)` writes a JSON file to `{output_dir}/{job_id}/{agent_name}/{filename}`. |
| 3b.2 | `test_local_save_creates_directories`         | Nested directories are created automatically if they don't exist.                                                 |
| 3b.3 | `test_local_load_reads_file`                  | `load(job_id, agent_name, filename)` reads and returns the JSON content as a dict.                                |
| 3b.4 | `test_local_load_returns_none_for_missing`    | `load()` returns `None` when the file doesn't exist (not an exception).                                           |
| 3b.5 | `test_local_exists_returns_true_for_existing` | `exists(job_id, agent_name, filename)` returns `True` when file is present.                                       |
| 3b.6 | `test_local_exists_returns_false_for_missing` | `exists()` returns `False` when file is absent.                                                                   |
| 3b.7 | `test_local_save_and_load_roundtrip`          | Data saved as dict is loaded back as identical dict.                                                              |
| 3b.8 | `test_local_list_artifacts_returns_filenames` | `list_artifacts(job_id, agent_name)` returns a list of filenames in that agent's output directory.                |
| 3b.9 | `test_local_list_artifacts_empty_directory`   | `list_artifacts()` returns an empty list for a directory with no files.                                           |

**RED → GREEN checklist:**

- [ ] All tests fail (storage classes don't exist)
- [ ] Write `StorageBackend` ABC with `@abstractmethod` decorators
- [ ] Write `LocalStorage` implementing all methods using `pathlib`
- [ ] All tests pass
- [ ] Refactor: ensure path construction is consistent

---

## Layer 4: BaseAgent (`agents/base.py`)

**File:** `tests/test_agents/test_base.py`

| #   | Test Name                                  | What It Proves                                                                                                          |
| --- | ------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------- |
| 4.1 | `test_base_agent_is_abstract`              | `BaseAgent` is abstract — instantiating it raises `TypeError`.                                                          |
| 4.2 | `test_base_agent_requires_name`            | Subclass without `name` class attribute raises `TypeError` on instantiation (or `name` is an `__init_subclass__` hook). |
| 4.3 | `test_base_agent_requires_run_method`      | Subclass without `run()` raises `TypeError`.                                                                            |
| 4.4 | `test_concrete_agent_run_receives_context` | A concrete agent's `run(ctx)` receives the `WorkflowState` context as its argument.                                     |
| 4.5 | `test_concrete_agent_run_returns_context`  | A concrete agent's `run(ctx)` returns the (possibly modified) `WorkflowState`.                                          |
| 4.6 | `test_agent_name_matches_enum`             | The agent's `name` attribute is a valid `AgentName` enum value.                                                         |

**Expected BaseAgent interface:**

```python
from abc import ABC, abstractmethod
from models.workflow_state import WorkflowState
from models.enums import AgentName

class BaseAgent(ABC):
    name: AgentName

    @abstractmethod
    def run(self, context: WorkflowState) -> WorkflowState:
        ...
```

**RED → GREEN checklist:**

- [ ] Tests 4.1–4.3 fail with `TypeError` (abstract)
- [ ] Tests 4.4–4.6 fail (no concrete agent to test — create a `StubAgent` in the test file)
- [ ] Write `BaseAgent` ABC with abstract `run(context) -> context` and `name` attribute
- [ ] All tests pass

---

## Layer 5: JobContext (`workflow/context.py`)

> `JobContext` is a re-export of `WorkflowState` from `models/workflow_state.py`. Tests verify the Pydantic model operations used by the pipeline — `model_dump()`, `model_validate_json()`, `agent_results` dict, and status transitions.

**File:** `tests/test_workflow/test_context.py`

| #   | Test Name                                           | What It Proves                                                                                                                               |
| --- | --------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| 5.1 | `test_job_context_is_workflow_state`                | `JobContext` is the same class as `WorkflowState`.                                                                                           |
| 5.2 | `test_context_creation_defaults`                    | `JobContext(job_id="abc", prompt="test")` has `status=pending`, `agent_results={}`, `current_agent=None`, `failed_agent=None`, `error=None`. |
| 5.3 | `test_context_serializes_to_json`                   | `model_dump_json()` produces a valid JSON string that can be written to disk.                                                                |
| 5.4 | `test_context_deserializes_from_json`               | `model_validate_json(json_string)` reconstructs an identical `JobContext`.                                                                   |
| 5.5 | `test_context_agent_results_preserved_in_roundtrip` | After adding an `AgentResult` to `agent_results`, the round-trip through JSON preserves it.                                                  |
| 5.6 | `test_context_agent_completion_by_key`              | An agent is "complete" if its `AgentName` key exists in `agent_results`.                                                                     |
| 5.7 | `test_context_status_transitions`                   | `status` can be set to `JobStatus.RUNNING`, `JobStatus.COMPLETED`, `JobStatus.FAILED`.                                                       |
| 5.8 | `test_context_updated_at_tracks_changes`            | Modifying any field updates `updated_at` (caller's responsibility — the model doesn't auto-update).                                          |

**RED → GREEN checklist:**

- [ ] All tests should pass immediately (`JobContext` is already implemented as `WorkflowState`)
- [ ] If any test fails, fix the re-export in `workflow/context.py`

---

## Layer 6: Pipeline (`workflow/pipeline.py`)

> Uses **stub agents** — concrete `BaseAgent` subclasses that either succeed (write to `ctx.agent_results` and return ctx) or fail (raise exception). No real LLM/TTS/video calls.

**File:** `tests/test_workflow/test_pipeline.py`

| #    | Test Name                                         | What It Proves                                                                                                   |
| ---- | ------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| 6.1  | `test_pipeline_runs_agents_in_order`              | Given agents `[A, B, C]`, they execute in that exact order. Tracked by a call-order list.                        |
| 6.2  | `test_pipeline_passes_context_between_agents`     | Agent B's `run()` receives the `WorkflowState` that Agent A returned, including A's outputs in `agent_results`.  |
| 6.3  | `test_pipeline_persists_context_after_each_agent` | After each agent completes, `ctx.model_dump_json()` is serialized and saved via `storage.save()`.                |
| 6.4  | `test_pipeline_records_agent_completion`          | After agent A completes, `AgentName.DIRECTOR in ctx.agent_results` is `True`.                                    |
| 6.5  | `test_pipeline_stops_on_agent_failure`            | When agent B raises an exception, agent C is never called.                                                       |
| 6.6  | `test_pipeline_sets_job_status_running`           | Pipeline sets `ctx.status = JobStatus.RUNNING` before executing the first agent.                                 |
| 6.7  | `test_pipeline_sets_job_status_completed`         | Pipeline sets `ctx.status = JobStatus.COMPLETED` after the last agent succeeds.                                  |
| 6.8  | `test_pipeline_sets_job_status_failed_on_error`   | Pipeline sets `ctx.status = JobStatus.FAILED` when an agent raises.                                              |
| 6.9  | `test_pipeline_records_failed_agent`              | On failure, `ctx.failed_agent` is set to the agent's `AgentName` and `ctx.error` contains the exception message. |
| 6.10 | `test_pipeline_with_empty_agent_list`             | Pipeline with no agents completes immediately without error (edge case).                                         |
| 6.11 | `test_pipeline_saves_context_json`                | The pipeline saves `context.json` (the serialized `WorkflowState`) to storage after each agent.                  |

**Test helpers needed:**

- `StubAgent(name: AgentName, should_fail: bool = False)` — concrete `BaseAgent` that either writes to `ctx.agent_results` or raises `RuntimeError`.
- `tmp_storage` fixture — `LocalStorage` pointed at `tmp_path`.

**Expected Pipeline signature:**

```python
class Pipeline:
    def __init__(self, storage: StorageBackend): ...

    def run(self, job_id: str, agents: list[BaseAgent], context: WorkflowState) -> WorkflowState:
        """Runs agents sequentially. Persists context after each. Returns final context."""
        ...
```

**RED → GREEN checklist:**

- [ ] All tests fail (Pipeline doesn't exist)
- [ ] Write `Pipeline` class with `run(job_id, agents, context)` method
- [ ] All tests pass
- [ ] Refactor: extract context persistence into a helper if repeated

---

## Layer 7: Resume (`workflow/resume.py`)

**File:** `tests/test_workflow/test_resume.py`

| #   | Test Name                                     | What It Proves                                                                                                                                |
| --- | --------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| 7.1 | `test_resume_loads_context_from_storage`      | Resume loads the persisted JSON, deserializes with `WorkflowState.model_validate_json()`.                                                     |
| 7.2 | `test_resume_skips_completed_agents`          | Given context where `agent_results` has entries for `DIRECTOR` and `RESEARCH`, resume only runs `[SCRIPT, STORYBOARD, VIDEO, VOICE, EDITOR]`. |
| 7.3 | `test_resume_runs_from_failed_agent`          | If `SCRIPT` failed (not in `agent_results`), resume starts from `SCRIPT`, not `STORYBOARD`.                                                   |
| 7.4 | `test_resume_raises_for_missing_context`      | Resume raises a clear error when `context.json` doesn't exist in storage for the given `job_id`.                                              |
| 7.5 | `test_resume_updates_job_status`              | Resume sets `ctx.status = JobStatus.RUNNING` before executing, then to `COMPLETED` or `FAILED`.                                               |
| 7.6 | `test_resume_clears_previous_failure`         | After successful resume, `ctx.failed_agent` and `ctx.error` are cleared.                                                                      |
| 7.7 | `test_resume_persists_context_for_new_agents` | Each newly-run agent's output is persisted via `storage.save()` during resume.                                                                |

**Expected Resume signature:**

```python
def resume_job(job_id: str, agents: list[BaseAgent], storage: StorageBackend) -> WorkflowState:
    """Loads persisted context, skips completed agents, runs remaining, returns final context."""
    ...
```

**RED → GREEN checklist:**

- [ ] All tests fail (resume module doesn't exist)
- [ ] Write `resume_job(job_id, agents, storage)` function
- [ ] All tests pass
- [ ] Refactor: share persistence logic with Pipeline if duplicated

---

## Layer 8: API Schemas (`backend/api/schemas.py`)

> These are Pydantic models for the HTTP request/response layer. They are separate from the internal models in `models/`.

**File:** `tests/test_api/test_schemas.py`

| #    | Test Name                                        | What It Proves                                                                                                                     |
| ---- | ------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------- |
| 8.1  | `test_generate_request_requires_prompt`          | `GenerateRequest` rejects missing `prompt` field.                                                                                  |
| 8.2  | `test_generate_request_rejects_empty_prompt`     | `GenerateRequest` rejects `prompt=""` and `prompt="   "` (whitespace-only).                                                        |
| 8.3  | `test_generate_request_rejects_oversized_prompt` | `GenerateRequest` rejects prompt `> 5000` characters.                                                                              |
| 8.4  | `test_generate_request_strips_whitespace`        | Leading/trailing whitespace is stripped from prompt before validation.                                                             |
| 8.5  | `test_generate_response_schema`                  | `GenerateResponse` has `job_id` field, serializes to `{"job_id": "..."}`.                                                          |
| 8.6  | `test_status_response_schema`                    | `StatusResponse` has `job_id`, `prompt`, `status`, `current_agent`, `created_at`, `updated_at`. Optional: `failed_agent`, `error`. |
| 8.7  | `test_status_response_current_agent_nullable`    | `current_agent` is `None` when no agent is executing (e.g., job is `pending` or `completed`).                                      |
| 8.8  | `test_result_response_schema`                    | `ResultResponse` has `job_id`, `status`, `output_path`, `artifacts` (list of `ArtifactRef`).                                       |
| 8.9  | `test_resume_response_schema`                    | `ResumeResponse` has `job_id` field.                                                                                               |
| 8.10 | `test_error_response_schema`                     | Error response has `detail` field (FastAPI standard).                                                                              |

**Note on `StatusResponse` vs `JobRecord`:** `StatusResponse` includes `current_agent` from `WorkflowState`, but `JobRecord` does not have this field. The routes layer is responsible for building `StatusResponse` from both `JobRecord` (in-memory job store) and `WorkflowState` (from disk). This keeps `JobRecord` lean and API-only.

**RED → GREEN checklist:**

- [ ] All tests fail (schemas don't exist)
- [ ] Write Pydantic request/response models with `Field` validators
- [ ] All tests pass

---

## Layer 9: API Routes (`backend/api/routes.py`)

> Uses FastAPI `TestClient`. No real pipeline execution — stub the pipeline.

**File:** `tests/test_api/test_routes.py`

| #    | Test Name                                        | What It Proves                                                                                                     |
| ---- | ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------ |
| 9.1  | `test_generate_returns_202_with_job_id`          | `POST /generate` with valid prompt returns `202` and a `job_id` in the response body.                              |
| 9.2  | `test_generate_returns_422_for_empty_prompt`     | `POST /generate` with `prompt=""` returns `422`.                                                                   |
| 9.3  | `test_generate_returns_422_for_missing_prompt`   | `POST /generate` with no body returns `422`.                                                                       |
| 9.4  | `test_generate_returns_422_for_oversized_prompt` | `POST /generate` with `>5000` char prompt returns `422`.                                                           |
| 9.5  | `test_generate_creates_job_record`               | After `/generate`, the job exists in the job store with `status` set to `pending` (before background task starts). |
| 9.6  | `test_status_returns_job_info`                   | `GET /status/{job_id}` returns `job_id`, `prompt`, `status`, `current_agent`, `created_at`, `updated_at`.          |
| 9.7  | `test_status_returns_404_for_unknown_job`        | `GET /status/nonexistent` returns `404`.                                                                           |
| 9.8  | `test_result_returns_output_for_completed_job`   | `GET /result/{job_id}` returns `output_path` and `artifacts` when job is `completed`.                              |
| 9.9  | `test_result_returns_404_for_unknown_job`        | `GET /result/nonexistent` returns `404`.                                                                           |
| 9.10 | `test_result_returns_409_for_non_completed_job`  | `GET /result/{job_id}` returns `409` when job is `running` or `pending`.                                           |
| 9.11 | `test_resume_returns_202`                        | `POST /resume/{job_id}` returns `202` for a `failed` job.                                                          |
| 9.12 | `test_resume_returns_404_for_unknown_job`        | `POST /resume/nonexistent` returns `404`.                                                                          |
| 9.13 | `test_resume_returns_409_for_running_job`        | `POST /resume/{job_id}` returns `409` when job is `running`.                                                       |
| 9.14 | `test_resume_returns_409_for_completed_job`      | `POST /resume/{job_id}` returns `409` when job is `completed`.                                                     |

**Test helpers needed:**

- `test_client` fixture — FastAPI `TestClient` with a test app that has stub pipeline injected
- `job_store` fixture — in-memory `dict[str, JobRecord]` for tracking active jobs
- Stub pipeline that returns a pre-configured `WorkflowState`

**RED → GREEN checklist:**

- [ ] All tests fail (routes don't exist)
- [ ] Write route handlers with proper status codes and validation
- [ ] All tests pass
- [ ] Refactor: extract job store access into FastAPI dependency

---

## Layer 10: FastAPI App (`backend/main.py`)

**File:** `tests/test_api/test_app.py`

| #    | Test Name                     | What It Proves                                                       |
| ---- | ----------------------------- | -------------------------------------------------------------------- |
| 10.1 | `test_app_creates`            | FastAPI app can be instantiated without errors.                      |
| 10.2 | `test_app_has_generate_route` | App has a route registered for `POST /generate`.                     |
| 10.3 | `test_app_has_status_route`   | App has a route registered for `GET /status/{job_id}`.               |
| 10.4 | `test_app_has_result_route`   | App has a route registered for `GET /result/{job_id}`.               |
| 10.5 | `test_app_has_resume_route`   | App has a route registered for `POST /resume/{job_id}`.              |
| 10.6 | `test_app_health_check`       | `GET /health` returns `200 {"status": "ok"}` (convenience endpoint). |

---

## Test Execution Summary

| Layer                           | File                                   | Test Count |
| ------------------------------- | -------------------------------------- | ---------- |
| 1. Config                       | `tests/test_backend/test_config.py`    | 4          |
| 2a. Enums                       | `tests/test_models/test_job.py`        | 4          |
| 2b. JobRecord                   | `tests/test_models/test_job.py`        | 5          |
| 2c. Agent Schemas               | `tests/test_models/test_schemas.py`    | 11         |
| 2d. AgentResult + WorkflowState | `tests/test_models/test_schemas.py`    | 7          |
| 3a. Storage ABC                 | `tests/test_storage/test_base.py`      | 6          |
| 3b. Local Storage               | `tests/test_storage/test_local.py`     | 9          |
| 4. BaseAgent                    | `tests/test_agents/test_base.py`       | 6          |
| 5. JobContext                   | `tests/test_workflow/test_context.py`  | 8          |
| 6. Pipeline                     | `tests/test_workflow/test_pipeline.py` | 11         |
| 7. Resume                       | `tests/test_workflow/test_resume.py`   | 7          |
| 8. API Schemas                  | `tests/test_api/test_schemas.py`       | 10         |
| 9. API Routes                   | `tests/test_api/test_routes.py`        | 14         |
| 10. App                         | `tests/test_api/test_app.py`           | 6          |
| **Total**                       |                                        | **108**    |

---

## TDD Discipline Checklist

Before marking Phase 1 complete, verify:

- [ ] Every test was written BEFORE the implementation
- [ ] Every test was watched failing (RED) before writing code
- [ ] Every failure was the expected one (missing feature, not typo)
- [ ] Minimal code was written to pass each test (no over-engineering)
- [ ] All 108 tests pass (GREEN)
- [ ] `pytest` output is clean — no warnings, no errors, no skipped
- [ ] No mocks used unless unavoidable (stub agents are real code, not mocks)
- [ ] Test file structure mirrors source structure

---

## Fixtures & Helpers to Build

| Helper           | Where                                                                    | Purpose                                                                                |
| ---------------- | ------------------------------------------------------------------------ | -------------------------------------------------------------------------------------- |
| `StubAgent`      | `tests/test_agents/test_base.py`, `tests/test_workflow/test_pipeline.py` | Concrete `BaseAgent` that writes to `ctx.agent_results` and passes or raises on demand |
| `tmp_storage`    | `tests/conftest.py`                                                      | `LocalStorage` pointed at `tmp_path`                                                   |
| `sample_context` | `tests/conftest.py`                                                      | `WorkflowState` with pre-populated `agent_results` for pipeline/resume tests           |
| `sample_job`     | `tests/conftest.py`                                                      | `JobRecord` with known state                                                           |
| `test_app`       | `tests/conftest.py`                                                      | FastAPI `TestClient` with stub pipeline injected                                       |
| `job_store`      | `tests/conftest.py`                                                      | `dict[str, JobRecord]` for tracking active jobs in route tests                         |

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

---

## Changes From Previous Version

| Area      | Old                                                                                              | New                                                                                                                  | Reason                                                                            |
| --------- | ------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| Layer 2a  | 5 tests for `JobStatus` only                                                                     | 4 tests for `JobStatus` + `AgentName` enums                                                                          | `AgentName` enum was untested                                                     |
| Layer 2b  | 5 tests for `JobRecord`                                                                          | Split into 2b (enums, 4 tests) + 2b (JobRecord, 5 tests)                                                             | Cleaner separation                                                                |
| Layer 2c  | 5 tests for schemas                                                                              | 11 tests covering all agent output models                                                                            | Was missing `ResearchNote`, `ResearchNotes`, `AgentResult`, `WorkflowState` tests |
| Layer 2d  | —                                                                                                | 7 new tests for `AgentResult`, `ArtifactRef`, `WorkflowState`                                                        | These models are central to the pipeline                                          |
| Layer 3a  | 5 tests, no `list_artifacts`                                                                     | 6 tests, `list_artifacts` added to ABC                                                                               | Pipeline needs to enumerate artifacts                                             |
| Layer 3b  | 8 tests                                                                                          | 9 tests, added empty-dir edge case                                                                                   | Coverage gap                                                                      |
| Layer 5   | Dict-like API (`set`, `get`, `mark_agent_complete`, `is_agent_complete`, `to_dict`, `from_dict`) | Pydantic model operations (`model_dump_json`, `model_validate_json`, `agent_results` dict check, `status` attribute) | `JobContext` is `WorkflowState` — a Pydantic `BaseModel`                          |
| Layer 6   | Tests reference `ctx.is_agent_complete("A")`                                                     | Tests reference `AgentName.DIRECTOR in ctx.agent_results`                                                            | Matches actual `WorkflowState` model                                              |
| Layer 6   | Test 6.11 "creates output directory"                                                             | Test 6.11 "saves context.json to storage"                                                                            | Pipeline delegates to `StorageBackend`, not filesystem                            |
| Layer 7   | Tests reference `ctx.is_agent_complete()`                                                        | Tests reference `agent_name in ctx.agent_results`                                                                    | Matches actual model                                                              |
| Layer 8   | 7 tests, no `current_agent` clarity                                                              | 10 tests, `StatusResponse` explicitly includes `current_agent` from `WorkflowState`                                  | Matches spec-flow analysis Q5                                                     |
| Layer 10  | 5 tests                                                                                          | 6 tests, added health check endpoint                                                                                 | Standard practice                                                                 |
| **Total** | 85 tests                                                                                         | **108 tests**                                                                                                        | +23 tests for coverage and alignment                                              |
