# PROJECT SPEC — AI-Native Video Generation Platform

## 1. Project Overview

An AI-native short-form video generation platform that transforms a user's text prompt into a fully produced MP4 video. The system uses a **multi-agent architecture** where each agent owns a single responsibility in the production pipeline — mirroring how a real video production team works.

The pipeline flows from creative planning (research, script, storyboard) through asset generation (video clips, voiceover) to final assembly (editing, stitching).

---

## 2. Goals

| #   | Goal                                                                              |
| --- | --------------------------------------------------------------------------------- |
| G1  | Accept a text prompt and produce a watchable short-form MP4 video                 |
| G2  | Modular agent-based design — each agent is independently testable and replaceable |
| G3  | Sequential execution first; migrate to LangGraph orchestration later              |
| G4  | Intermediate outputs are persisted so the pipeline can resume after failures      |
| G5  | Clean separation between agent logic, orchestration, and I/O                      |

### Non-Goals (MVP)

- Real-time / live video generation
- User authentication or multi-tenant isolation
- GPU-level model training or fine-tuning
- Mobile app or browser-based UI (API-only for now)

---

## 3. Architecture

### 3.1 High-Level

```
┌─────────────────────────────────────────────────────────┐
│                     FastAPI Service                      │
│  POST /generate   GET /status   GET /result/{job_id}    │
└──────────────┬──────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────┐
│              Pipeline Orchestrator (sequential)          │
│                                                         │
│  Director ──▶ Research ──▶ Script ──▶ Storyboard        │
│                                         │               │
│                                         ▼               │
│                            ┌────────────────────┐       │
│                            │   Video Agent      │       │
│                            │   Voice Agent      │  ◀── parallel (future)
│                            └────────┬───────────┘       │
│                                     ▼                   │
│                               Editor Agent              │
│                                     │                   │
│                                     ▼                   │
│                              Final MP4 Output           │
└─────────────────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────┐
│              Shared Artifact Store (disk)                │
│         /outputs/{job_id}/{agent_name}/...               │
└─────────────────────────────────────────────────────────┘
```

### 3.2 Key Design Decisions

| Decision                              | Rationale                                                                                                 |
| ------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| **One agent = one responsibility**    | Easy to test, swap models, and reason about failures                                                      |
| **Artifact-per-step persistence**     | Enables resume-from-failure without re-running prior agents                                               |
| **Sequential first, LangGraph later** | LangGraph adds complexity; validate the pipeline logic first                                              |
| **Job-based execution**               | Each `/generate` call creates a `job_id`; all artifacts are namespaced under it                           |
| **Agent interface contract**          | Every agent implements a common `run(context) -> context` interface so the orchestrator is agent-agnostic |

### 3.3 Agent Interface Contract

Every agent must:

1. Accept a **shared context dict** (or typed object) containing upstream outputs.
2. Read its required inputs from that context.
3. Write its outputs back into the context AND persist them to disk under `outputs/{job_id}/{agent_name}/`.
4. Return the updated context.
5. Raise a typed exception on failure (the orchestrator logs and halts).

```
AgentInput (context)  ──▶  Agent.run()  ──▶  AgentOutput (context + files on disk)
```

---

## 4. Agent Responsibilities

### 4.1 Director Agent

- **Role:** Project manager / showrunner.
- **Input:** Raw user prompt.
- **Responsibilities:**
  - Parse and enrich the prompt (tone, audience, duration, style).
  - Produce a **creative brief** — the single source of truth for all downstream agents.
  - Decide the video format (aspect ratio, target length, style keywords).
- **Output:** `creative_brief.json`

### 4.2 Research Agent

- **Role:** Fact-checker and topic researcher.
- **Input:** Creative brief.
- **Responsibilities:**
  - Gather relevant facts, statistics, references, and talking points.
  - Validate claims that will appear in the script.
  - Return structured research notes.
- **Output:** `research_notes.json`
- **Tools:** Web search API, knowledge base, or LLM with retrieval.

### 4.3 Script Agent

- **Role:** Screenwriter.
- **Input:** Creative brief + research notes.
- **Responsibilities:**
  - Write a scene-by-scene script with narration text per scene.
  - Include timing estimates per scene.
  - Tag each scene with visual direction hints.
- **Output:** `script.json` (list of scenes with `narration`, `duration_hint`, `visual_direction`)

### 4.4 Storyboard Agent

- **Role:** Visual planner.
- **Input:** Script.
- **Responsibilities:**
  - Convert each scene into a detailed image/video generation prompt.
  - Specify camera angle, composition, motion, and mood per shot.
  - Produce a shot list.
- **Output:** `storyboard.json` (list of shots with `visual_prompt`, `camera`, `motion`, `duration`)

### 4.5 Video Agent

- **Role:** Visual asset generator.
- **Input:** Storyboard shot list.
- **Responsibilities:**
  - Generate a video clip (or image sequence) for each shot.
  - Save each clip with a deterministic filename (`shot_001.mp4`, etc.).
- **Output:** `clips/shot_XXX.mp4` (one per storyboard shot)
- **Tools:** Video generation model API (e.g., Runway, Kling, Pika, or local model).

### 4.6 Voice Agent

- **Role:** Narration producer.
- **Input:** Script (narration text per scene).
- **Responsibilities:**
  - Generate TTS audio for each scene's narration.
  - Match pacing and tone to the creative brief.
  - Optionally produce background music or sound effects.
- **Output:** `audio/scene_XXX.mp3`, optional `audio/bgm.mp3`
- **Tools:** TTS API (e.g., ElevenLabs, OpenAI TTS, Coqui).

### 4.7 Editor Agent

- **Role:** Final assembler.
- **Input:** Video clips + audio tracks + storyboard timing.
- **Responsibilities:**
  - Stitch clips in storyboard order.
  - Overlay narration audio, synced per scene.
  - Add transitions, background music, and titles if specified.
  - Export final MP4 at target resolution and framerate.
- **Output:** `final/final_video.mp4`
- **Tools:** FFmpeg (via `ffmpeg-python` or subprocess).

---

## 5. Data Flow

```
User Prompt
    │
    ▼
[Director] ──▶ creative_brief.json
    │
    ▼
[Research] ──▶ research_notes.json
    │
    ▼
[Script]   ──▶ script.json
    │
    ▼
[Storyboard]──▶ storyboard.json
    │
    ├──▶ [Video]  ──▶ clips/shot_001.mp4, shot_002.mp4, ...
    │
    └──▶ [Voice]  ──▶ audio/scene_001.mp3, scene_002.mp3, ...
              │
              ▼
         [Editor]   ──▶ final/final_video.mp4
```

### State Management

- A **JobContext** object is passed through the pipeline.
- Each agent reads its inputs from the context and writes outputs back.
- The orchestrator serializes the context to `outputs/{job_id}/context.json` after each agent completes.
- On resume, the orchestrator loads the last saved context and skips completed agents.

---

## 6. Folder Structure

```
qwenchana-medias/
├── PROJECT_SPEC.md
├── README.md
├── requirements.txt
├── .env.example
│
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app entry point
│   ├── config.py                # Settings (env vars, paths, model keys)
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py            # POST /generate, GET /status, GET /result
│   │   └── schemas.py           # Pydantic request/response models
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base.py              # BaseAgent abstract class
│   │   ├── director.py
│   │   ├── research.py
│   │   ├── script.py
│   │   ├── storyboard.py
│   │   ├── video.py
│   │   ├── voice.py
│   │   └── editor.py
│   │
│   ├── orchestrator/
│   │   ├── __init__.py
│   │   ├── pipeline.py          # Sequential pipeline runner
│   │   ├── context.py           # JobContext dataclass
│   │   └── resume.py            # Resume logic (load context, skip done)
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── llm.py               # LLM client wrapper (OpenAI, etc.)
│   │   ├── tts.py               # TTS client wrapper
│   │   ├── video_gen.py         # Video generation client wrapper
│   │   └── ffmpeg.py            # FFmpeg wrapper utilities
│   │
│   └── utils/
│       ├── __init__.py
│       ├── logger.py
│       └── file.py              # Path helpers, artifact I/O
│
├── outputs/                     # Runtime artifact storage (git-ignored)
│   └── {job_id}/
│       ├── context.json
│       ├── director/
│       │   └── creative_brief.json
│       ├── research/
│       │   └── research_notes.json
│       ├── script/
│       │   └── script.json
│       ├── storyboard/
│       │   └── storyboard.json
│       ├── video/
│       │   └── clips/
│       ├── voice/
│       │   └── audio/
│       └── editor/
│           └── final/
│
├── tests/
│   ├── test_agents/
│   ├── test_orchestrator/
│   └── test_services/
│
└── scripts/
    └── run_pipeline.py          # CLI entry for local testing
```

---

## 7. Development Roadmap

### Phase 1 — Foundation (Week 1)

- [x] Set up FastAPI project skeleton with folder structure.
- [x] Implement `BaseAgent` abstract class and `JobContext`.
- [x] Build sequential pipeline orchestrator with artifact persistence.
- [x] Implement `/generate`, `/status`, `/result` API endpoints.
- [x] Add `.env` config loading and logging.

### Phase 2 — Core Agents (Week 2)

- [x] Implement **Director Agent** (LLM-based prompt enrichment).
- [x] Implement **Script Agent** (LLM-based scene breakdown).
- [x] Implement **Storyboard Agent** (LLM-based visual prompt generation).
- [x] Wire LLM service wrapper (OpenAI or compatible API).

### Phase 3 — Asset Generation (Week 3)

- [ ] Implement **Research Agent** (LLM + optional web search).
- [ ] Implement **Video Agent** (integrate video generation API).
- [ ] Implement **Voice Agent** (integrate TTS API).
- [ ] Handle rate limits, retries, and fallback stubs.

### Phase 4 — Assembly (Week 4)

- [x] Implement **Editor Agent** (FFmpeg-based stitching).
- [x] End-to-end pipeline test: prompt → MP4.
- [x] Resume-from-failure testing.
- [x] Basic error handling and job status tracking.

### Phase 5 — LangGraph Migration (Week 5+)

- [ ] Model the pipeline as a LangGraph state graph.
- [ ] Migrate sequential orchestrator to LangGraph nodes.
- [ ] Add conditional edges (e.g., retry on failure, approval gates).
- [ ] Enable parallel execution of Video + Voice agents.

---

## 8. MVP Scope

The MVP delivers a **working end-to-end pipeline** that:

1. Accepts a text prompt via API.
2. Runs all 7 agents sequentially.
3. Produces a stitched MP4 with narration.
4. Persists intermediate artifacts for debugging and resume.
5. Returns the final video via a download endpoint.

### MVP In Scope

- Sequential execution only
- Single video style (e.g., explainer / narration-over-visuals)
- One LLM provider, one TTS provider, one video generation provider
- Local file-based artifact storage
- Basic job status tracking (pending, running, completed, failed)

### MVP Out of Scope

- Parallel agent execution
- LangGraph orchestration
- User auth / multi-tenancy
- Web UI / frontend
- Video style customization beyond the prompt
- Cost tracking or usage metering

---

## 9. Future Improvements

| Area                | Improvement                                                                                     |
| ------------------- | ----------------------------------------------------------------------------------------------- |
| **Orchestration**   | Migrate to LangGraph for parallelism, conditional routing, and human-in-the-loop approval gates |
| **Quality**         | Add a Reviewer Agent that scores output quality and triggers re-generation                      |
| **Personalization** | Support brand kits, custom voices, and style presets                                            |
| **Formats**         | Support multiple aspect ratios (9:16, 16:9, 1:1) and platforms (TikTok, Reels, Shorts)          |
| **Interactivity**   | Allow users to edit the script or storyboard before generation proceeds                         |
| **Streaming**       | Stream progress updates via WebSocket or SSE                                                    |
| **Storage**         | Move artifact storage to S3/GCS for cloud deployment                                            |
| **Observability**   | Add tracing (OpenTelemetry), per-agent latency metrics, and cost tracking                       |
| **Testing**         | Add integration tests with mocked external APIs; snapshot testing for output quality            |
| **Caching**         | Cache LLM responses and generated assets to reduce redundant API calls                          |

---

## 10. Key Risks & Mitigations

| Risk                                             | Mitigation                                                           |
| ------------------------------------------------ | -------------------------------------------------------------------- |
| Video generation API latency (30s–2min per clip) | Parallel execution (Phase 5), async job processing, timeout handling |
| LLM output inconsistency                         | Structured output schemas (Pydantic), retry with validation          |
| FFmpeg complexity                                | Wrap in a dedicated service with tested recipes                      |
| Pipeline failure mid-run                         | Context persistence + resume logic                                   |
| Cost of external APIs                            | Stub/mock mode for development; cache aggressively                   |

---

_This spec is a living document. Update it as architecture decisions are made during implementation._
