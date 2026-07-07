# Data Model Design

> All shared data models for the video generation pipeline. Pydantic v2. No business logic — pure data contracts.

---

## Model Inventory

```
models/
├── __init__.py          # Re-exports all public models
├── enums.py             # JobStatus, AgentName
├── brief.py             # CreativeBrief
├── research.py          # ResearchNote, ResearchNotes
├── scene.py             # Scene
├── script.py            # Script
├── storyboard.py        # Shot, Storyboard
├── agent_result.py      # ArtifactRef, AgentResult
├── workflow_state.py    # WorkflowState
├── job.py               # JobRecord (API-facing job metadata)
└── artifacts.py         # Artifact path conventions & helpers
```

---

## Model-by-Model Rationale

### 1. `JobStatus` (enum) — `enums.py`

```
pending → running → completed
                  → failed
```

**Why:** The pipeline has exactly four states. An enum prevents string typos (`"runnng"`) and makes invalid states unrepresentable. Every component that touches job lifecycle — API routes, orchestrator, resume logic — references this enum.

---

### 2. `AgentName` (enum) — `enums.py`

```
director | research | script | storyboard | video | voice | editor
```

**Why:** Agents are identified by name throughout the system — in WorkflowState per-agent results, in artifact paths (`outputs/{job_id}/{agent_name}/`), in error reporting (`failed_agent`), and in resume logic (skip completed agents by name). A string works but an enum catches typos at validation time and makes the set of agents exhaustive and discoverable.

---

### 3. `CreativeBrief` — `brief.py`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | str | yes | Working title for the video |
| `prompt` | str | yes | Original user prompt (preserved for reference) |
| `tone` | str | yes | e.g., "educational", "humorous", "dramatic" |
| `audience` | str | yes | Target audience description |
| `duration_seconds` | float | yes | Target video length |
| `aspect_ratio` | str | no | Default "16:9". Future: "9:16", "1:1" |
| `style_keywords` | list[str] | no | Visual/style tags for downstream agents |
| `summary` | str | yes | Enriched prompt — the single source of truth for all downstream agents |

**Why:** The Director Agent produces this as its sole output. It's the "single source of truth" that every subsequent agent reads. Without a typed schema, the Director's LLM output is an unstructured blob that every downstream agent must parse defensively. This model enforces the contract: Director writes it, everyone else reads it.

---

### 4. `ResearchNote` — `research.py`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `topic` | str | yes | What this note covers |
| `content` | str | yes | The factual content / talking point |
| `source` | str | no | Where the info came from (URL, knowledge base, etc.) |
| `verified` | bool | no | Whether the claim has been fact-checked |

### 5. `ResearchNotes` — `research.py`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `brief_summary` | str | yes | Link back to the brief this research supports |
| `notes` | list[ResearchNote] | yes | Ordered collection of research findings |
| `overall_confidence` | float | no | 0.0–1.0 — how confident the research agent is in the collected facts |

**Why:** The Research Agent's output is consumed by the Script Agent. A list of unstructured strings would force the Script Agent to guess what's a fact vs. a source vs. an opinion. Typed `ResearchNote` objects let the Script Agent selectively use verified facts, cite sources, and weight confidence. The wrapper `ResearchNotes` model adds context (which brief this is for) and an overall quality signal.

---

### 6. `Scene` — `scene.py`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `scene_number` | int | yes | 1-indexed position in the script |
| `narration` | str | yes | Voiceover text for this scene |
| `duration_hint` | float | yes | Estimated seconds for this scene |
| `visual_direction` | str | yes | Description of what should be visually shown |
| `mood` | str | no | Emotional tone for this specific scene |

**Why:** The Scene is the fundamental unit of the Script. Each Scene maps 1:1 to a narration segment (Voice Agent input) and eventually to a Shot (Storyboard Agent output). The `narration` field feeds TTS, `visual_direction` feeds the storyboard, and `duration_hint` constrains timing. Without `scene_number`, ordering depends on list position which is fragile during serialization/deserialization.

---

### 7. `Script` — `script.py`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | str | yes | From the creative brief |
| `scenes` | list[Scene] | yes | Ordered scene list |
| `total_estimated_duration` | float | no | Sum of scene durations (convenience, computed) |

**Why:** The Script is the Script Agent's output and the most-consumed model in the pipeline — Storyboard, Voice, and Editor agents all read it. Wrapping the scene list in a `Script` model (rather than passing a bare `list[Scene]`) provides a stable top-level object that can carry metadata, be serialized as a single JSON document, and evolve without breaking consumers.

---

### 8. `Shot` — `storyboard.py`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `shot_number` | int | yes | 1-indexed, matches scene_number |
| `scene_number` | int | yes | Links back to the source Scene |
| `visual_prompt` | str | yes | Detailed prompt for the video generation model |
| `camera` | str | yes | Angle/movement: "wide static", "close-up pan left", etc. |
| `motion` | str | yes | Describes subject/action motion in the shot |
| `duration` | float | yes | Seconds — drives clip generation and final assembly |
| `mood` | str | no | Visual mood for this shot |

**Why:** The Shot is the Video Agent's unit of work — one Shot = one clip generation call. The `visual_prompt` is the actual input to the video generation API, so it must be rich and detailed (unlike Scene's `visual_direction` which is more of a creative hint). `scene_number` maintains the traceability link back to the Script, which the Editor Agent needs for audio-video sync. `shot_number` allows multiple shots per scene (future) without losing ordering.

---

### 9. `Storyboard` — `storyboard.py`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `shots` | list[Shot] | yes | Ordered shot list |
| `total_duration` | float | no | Sum of shot durations |

**Why:** The Storyboard is the Storyboard Agent's output and the Video Agent's input. It's the bridge between the creative/narrative world (Script) and the visual/technical world (video generation). Like Script, wrapping the list provides a stable serialization target and room for metadata.

---

### 10. `ArtifactRef` — `agent_result.py`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `agent_name` | AgentName | yes | Which agent produced this |
| `filename` | str | yes | Relative path within the agent's output dir |
| `content_type` | str | yes | MIME type: "video/mp4", "audio/mp3", "application/json" |
| `size_bytes` | int | no | File size for status reporting |

**Why:** Agents produce files on disk. Rather than passing raw file paths (which are fragile and untyped), `ArtifactRef` is a typed reference that knows its producer, its type, and its location. The Editor Agent iterates over video artifacts to stitch clips and audio artifacts to overlay narration. Without `content_type`, the Editor would have to guess from file extensions.

---

### 11. `AgentResult` — `agent_result.py`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `agent_name` | AgentName | yes | Which agent produced this result |
| `success` | bool | yes | Whether the agent completed successfully |
| `output_data` | dict | no | The agent's structured output (brief, notes, script, etc.) — stored as raw dict for flexibility |
| `artifacts` | list[ArtifactRef] | no | Files produced on disk |
| `error` | str | no | Error message if `success` is False |
| `duration_seconds` | float | no | How long the agent took (observability) |

**Why:** The AgentResult is the universal return type for every agent. The orchestrator collects these into WorkflowState. Having a uniform result type means the orchestrator doesn't need to know what each agent produces — it just stores the result, checks `success`, and moves on. The `output_data` dict is intentionally loose: each agent writes its own typed model (CreativeBrief, Script, etc.) into this field via `model_dump()`, and consumers load it back with the appropriate model. This keeps the agent interface generic while preserving typed data.

---

### 12. `WorkflowState` — `workflow_state.py`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `job_id` | str | yes | Unique job identifier (UUID) |
| `prompt` | str | yes | Original user prompt |
| `status` | JobStatus | yes | Current pipeline status |
| `current_agent` | AgentName | no | Agent currently executing (None if between agents) |
| `agent_results` | dict[AgentName, AgentResult] | no | Completed agent results, keyed by name |
| `failed_agent` | AgentName | no | Which agent failed (if status is `failed`) |
| `error` | str | no | Error message from the failed agent |
| `created_at` | datetime | yes | When the job was created |
| `updated_at` | datetime | yes | Last state change |

**Why:** This is the serialized state of the entire pipeline — what gets written to `outputs/{job_id}/context.json` after each agent completes. It's the resume-from-failure mechanism: on restart, the orchestrator loads this file, checks which agents have results, and skips them. Every field serves a specific purpose:

- `agent_results` — determines which agents are done (key exists = completed)
- `current_agent` — enables `/status` to report "currently running: storyboard"
- `failed_agent` + `error` — enables `/status` to report what went wrong
- `created_at` / `updated_at` — enables job age tracking and cleanup

This replaces the untyped "shared context dict" from the spec with a typed, validated model. The dict approach works but loses all type safety and makes serialization/deserialization fragile.

---

### 13. `JobRecord` — `job.py`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `job_id` | str | yes | UUID |
| `prompt` | str | yes | Original prompt |
| `status` | JobStatus | yes | Current status |
| `created_at` | datetime | yes | Creation timestamp |
| `updated_at` | datetime | yes | Last update |
| `failed_agent` | AgentName | no | Which agent failed |
| `error` | str | no | Error message |

**Why:** Separate from WorkflowState. JobRecord is the **API-facing** model — it's what `/status` and `/generate` return to the client. WorkflowState is the **internal** model — it's what the orchestrator persists to disk. The separation matters because:

- The API doesn't need to expose `agent_results` (internal detail)
- The API doesn't need to expose `current_agent` (could add later, but not in MVP)
- WorkflowState can evolve independently of the API contract
- JobRecord is stored in-memory (dict of active jobs); WorkflowState is stored on disk

---

## Data Flow Through Models

```
User Prompt (str)
      │
      ▼
┌─────────────────────────────────────────────────┐
│ CreativeBrief                                    │
│   title, tone, audience, duration, summary       │
└─────────────────────┬───────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────┐
│ ResearchNotes                                    │
│   notes: [ResearchNote, ...]                     │
│   overall_confidence                             │
└─────────────────────┬───────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────┐
│ Script                                           │
│   scenes: [Scene, ...]                           │
│     each: narration, duration_hint,              │
│            visual_direction                       │
└─────────────────────┬───────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────┐
│ Storyboard                                       │
│   shots: [Shot, ...]                             │
│     each: visual_prompt, camera, motion,          │
│            duration, scene_number →               │
└──────┬──────────────────────────────┬────────────┘
       │                              │
       ▼                              ▼
┌──────────────────┐     ┌──────────────────────┐
│ Video Agent      │     │ Voice Agent           │
│ ArtifactRef[]    │     │ ArtifactRef[]          │
│ clips/shot_*.mp4 │     │ audio/scene_*.mp3      │
└────────┬─────────┘     └──────────┬─────────────┘
         │                          │
         └──────────┬───────────────┘
                    ▼
┌─────────────────────────────────────────────────┐
│ Editor Agent                                     │
│   reads: Storyboard.shots + ArtifactRefs         │
│   produces: final/final_video.mp4                │
└─────────────────────────────────────────────────┘

Throughout: WorkflowState tracks progress, AgentResult per agent.
```

---

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Pydantic v2 BaseModel everywhere** | Validation on construction, serialization for free, JSON schema generation for API docs. |
| **`output_data: dict` in AgentResult, not generic** | Keeps the agent interface uniform. Each agent writes its typed model into the dict via `model_dump()`. Consumers cast back with the specific model. A generic type would complicate serialization. |
| **WorkflowState separate from JobRecord** | Internal state (disk) vs. API contract (HTTP). Different audiences, different evolution. |
| **`scene_number` on Scene, not just list position** | List position is fragile through serialization. Explicit index is self-documenting and survives reordering. |
| **`shot_number` + `scene_number` on Shot** | `scene_number` links back to Script for audio sync. `shot_number` allows future multi-shot-per-scene without breaking ordering. |
| **ArtifactRef as typed reference, not raw path** | Carries producer identity, content type, and size. Editor Agent can filter by `content_type` without parsing paths. |
| **Enums for JobStatus and AgentName** | Exhaustive, typo-proof, discoverable. String enums serialize cleanly to JSON. |
| **No business logic in models** | Models validate shape, not behavior. Pipeline logic lives in `workflow/`. Agent logic lives in `agents/`. |
