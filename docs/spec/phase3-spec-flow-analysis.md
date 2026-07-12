# Phase 3 — Spec Flow Analysis: Asset Generation

> **Scope:** Research Agent (LLM + optional web search), Video Agent, Voice Agent, and rate-limit/retry/fallback-stub handling.
> **Grounded in:** Phase 1 (foundation) and Phase 2 (Director, Research, Script, Storyboard agents + LLM service) codebases.

---

## 1. Codebase Context

### What exists (after Phase 2)

| Component                                      | Status      | Key Detail                                                                      |
| ---------------------------------------------- | ----------- | ------------------------------------------------------------------------------- |
| `BaseAgent` ABC                                | ✅ Done     | `name: AgentName`, `run(context: WorkflowState) -> WorkflowState`               |
| `Pipeline`                                     | ✅ Done     | Runs agents sequentially, persists context after each agent                     |
| `WorkflowState` / `JobRecord`                  | ✅ Done     | Typed pipeline + API-facing state                                               |
| `LLMService` + `AlibabaCloudLLMService`        | ✅ Done     | OpenAI-compatible DashScope client, used by Director/Research/Script/Storyboard |
| `TTSService` + `DashScopeTTSService`           | ✅ Skeleton | `tools/tts.py` has ABC + concrete DashScope impl, no agent calls it             |
| `VideoGenService` + `DashScopeVideoGenService` | ✅ Skeleton | `tools/video_gen.py` has ABC + concrete DashScope impl, no agent calls it       |
| `WebSearchService`                             | ❌ Missing  | `tools/web_search.py` is empty; no abstraction exists                           |
| `ResearchAgent`                                | ✅ Partial  | LLM-only; no web search augmentation                                            |
| `VideoAgent` / `agents/video.py`               | ❌ Empty    | File exists but no implementation                                               |
| `VoiceAgent` / `agents/voice.py`               | ❌ Empty    | File exists but no implementation                                               |
| `Storyboard` / `Shot` models                   | ✅ Done     | Input schema for Video Agent                                                    |
| `Script` / `Scene` models                      | ✅ Done     | Input schema for Voice Agent                                                    |
| Video/Voice output models                      | ❌ Missing  | No `models/video.py` or `models/voice.py`                                       |
| `StorageBackend` / `LocalStorage`              | ✅ Done     | Saves JSON; binary files are written directly by service tools                  |
| API endpoints                                  | ✅ Done     | `/generate` runs pipeline synchronously; `/status`, `/result`, `/resume` exist  |
| `Settings`                                     | ✅ Done     | `LLMConfig`, `VoiceConfig`, `VideoConfig`, `StorageConfig`, `ServerConfig`      |

### What's missing (Phase 3 scope)

| Component                       | Status     | Key Detail                                                                  |
| ------------------------------- | ---------- | --------------------------------------------------------------------------- |
| `tools/web_search.py`           | ❌ Missing | Abstract + concrete web search service (optional)                           |
| `agents/research.py` web search | ❌ Missing | Inject optional web search service; include results in LLM prompt           |
| `models/video.py`               | ❌ Missing | Typed output model for Video Agent (clips, paths)                           |
| `models/voice.py`               | ❌ Missing | Typed output model for Voice Agent (tracks, paths)                          |
| `agents/video.py`               | ❌ Missing | Read Storyboard, generate clips, persist artifacts, write AgentResult       |
| `agents/voice.py`               | ❌ Missing | Read Script, generate narration audio, persist artifacts, write AgentResult |
| Retry / rate-limit handling     | ❌ Missing | Tenacity (or equivalent) for LLM, TTS, video generation                     |
| Fallback / stub mode            | ❌ Missing | Generate stub MP4/MP3 when APIs are unavailable or rate-limited             |

### Existing patterns to follow

- **Agent pattern:** `name` class attribute + `run(context) -> context` + raise on failure + persist via `storage.save()` + write `AgentResult.output_data` and `artifacts`.
- **Tool/service pattern:** ABC injected into agents; concrete classes hide provider details.
- **Model pattern:** Each agent's output is a typed Pydantic model dumped into `AgentResult.output_data`.
- **Persistence pattern:** Agents persist JSON metadata via `storage.save()`; binary media files are written directly by the tool/service that produces them, with `ArtifactRef` entries recording relative filenames and MIME types.
- **Pipeline execution:** Synchronous sequential execution for Phase 3; parallel execution is a future phase.

---

## 2. User Flows

### Flow 1: Generate a video (happy path)

```
User sends POST /generate {"prompt": "Make a 30s explainer about climate change"}
  → API creates JobRecord + WorkflowState (status=PENDING)
  → Pipeline starts: status → RUNNING
  → Director.run(ctx)   → CreativeBrief
  → Research.run(ctx)   → ResearchNotes (LLM + optional web search)
  → Script.run(ctx)     → Script
  → Storyboard.run(ctx) → Storyboard
  → Video.run(ctx)      → reads Storyboard.shots
                          calls VideoGenService for each shot
                          saves clips/shot_001.mp4, shot_002.mp4, ...
                          writes VideoOutput + ArtifactRefs to ctx
  → Voice.run(ctx)      → reads Script.scenes
                          calls TTSService for each scene narration
                          saves audio/scene_001.mp3, scene_002.mp3, ...
                          writes VoiceOutput + ArtifactRefs to ctx
  → Pipeline sets status → COMPLETED
  → User calls GET /result/{job_id} → gets artifacts
```

**Decision points:** None in Phase 3 (sequential, no branching).

**Terminal states:**

- ✅ COMPLETED — all agents ran, context persisted
- ❌ FAILED — one agent raised; Pipeline catches, sets `failed_agent` + `error`

### Flow 2: Research with web search

```
Research.run(ctx) receives CreativeBrief
  → If WEB_SEARCH_API_KEY or enable flag is set:
       WebSearchService.search(brief.summary / topics) → list[SearchResult]
       results are injected into the LLM prompt as additional context
  → LLM generates ResearchNotes
  → Persist research_notes.json + AgentResult
```

**Decision points:**

- Is web search enabled? If not, fall back to LLM-only (current behavior).
- Do search results improve the ResearchNotes, or just add context? MVP: add context.

### Flow 3: Retry on external service failure

```
VideoAgent calls VideoGenService.generate(shot.visual_prompt, ".../shot_001.mp4")
  → DashScope API returns 429 (rate limit) or times out
  → Service-level retry with exponential backoff (e.g., 3 attempts)
  → Success → continue
  → Max retries exceeded → raise (Pipeline fails job)
     OR
     → Fallback stub mode enabled → write stub clip and continue
```

**Decision points:**

- Is retry enabled? Default yes.
- Is fallback/stub mode enabled? Default no in production, yes in dev when API key missing.

### Flow 4: Resume after failure during asset generation

```
User sends POST /resume/{job_id}
  → resume_job loads context.json
  → Skips Director, Research, Script, Storyboard if results exist
  → If Video result exists but Voice does not, runs only Voice
  → If Video failed, re-runs Video
```

**Already works** — Phase 1 resume logic handles this. No new flow needed for Phase 3 agents.

### Flow 5: Development / no API key path

```
VIDEO_API_KEY or VOICE_API_KEY is missing
  → DashScope service raises RuntimeError on first call
  → If FALLBACK_STUBS=true:
       VideoAgent writes a tiny valid (or empty) MP4 to the expected path
       VoiceAgent writes a tiny valid (or empty) MP3 to the expected path
       AgentResult.success remains True
       Pipeline completes (with placeholder media)
  → Else:
       Pipeline fails with failed_agent=video or voice
```

---

## 3. Gaps

### Critical

**G1: No typed output models for Video and Voice agents.**
Video and Voice agents need structured output models to write into `AgentResult.output_data`. Without them, downstream consumers (Editor, API) must parse raw paths or invent schemas. We need `models/video.py` and `models/voice.py` that mirror `Storyboard` / `Script`.

**Default:** Define `VideoOutput` with a list of `VideoClip` objects (shot_number, file_path, duration) and `VoiceOutput` with a list of `AudioTrack` objects (scene_number, file_path, duration).

**G2: Web search integration is undefined.**
`tools/web_search.py` is empty, and `ResearchAgent` has no hook for a search service. The PROJECT_SPEC says "optional web search" but doesn't specify provider, API key, or how results feed into the prompt.

**Default:** Create a `WebSearchService` ABC and a stub/no-op implementation. If `WEB_SEARCH_API_KEY` is configured, optionally use a real provider (SerpAPI). Results are formatted and appended to the Research prompt. If no key, the agent behaves exactly as it does now (LLM-only).

**G3: Retry / rate-limit strategy is unspecified.**
Video generation APIs can return 429s, TTS can time out, and LLM calls can fail transiently. The spec says "handle rate limits, retries, and fallback stubs" but gives no policy.

**Default:** Add `tenacity` to `requirements.txt`. Wrap `AlibabaCloudLLMService.generate`, `DashScopeTTSService.synthesize`, and `DashScopeVideoGenService.generate` with a retry decorator: 3 attempts, exponential backoff starting at 1s, only on transient errors (HTTP 429, 5xx, timeouts, connection errors). Non-transient errors (4xx except 429, invalid prompt) fail immediately.

**G4: Fallback stub mode is unspecified.**
When an external API is unavailable, should the pipeline fail or produce a stub? What does a stub look like? The Editor agent in Phase 4 needs valid media files.

**Default:** Add a `FALLBACK_STUBS=true/false` env flag. When enabled and an API is unconfigured or rate-limited, the agent writes a minimal valid file (silent MP3, blank/solid-color MP4) to the expected path and records `success=True`. When disabled, the agent raises and the pipeline fails. Default: `false` so failures are obvious in production; developers can set `true` to test the rest of the pipeline without API costs.

### Important

**G5: Synchronous pipeline blocks for long-running asset generation.**
Video generation can take 30s–2min per clip. The current `/generate` runs synchronously, so a 5-shot video could block the HTTP response for several minutes.

**Default:** Keep synchronous execution for Phase 3 (matches Phase 2 decision). The spec explicitly defers async/background execution to a later phase. Document the limitation and recommend short prompts or stub mode for testing.

**G6: File naming and path conventions for generated assets.**
The PROJECT_SPEC §6 proposes `video/clips/shot_XXX.mp4` and `voice/audio/scene_XXX.mp3`. The exact zero-padding, extension, and directory layout need to be fixed.

**Default:** Use zero-padded 3-digit numbers: `video/clips/shot_001.mp4`, `voice/audio/scene_001.mp3`. This matches the spec and keeps filenames sortable.

**G7: Error handling for partial asset generation.**
If the Video Agent generates 3 of 5 clips and the 4th fails, what happens? The current agent raises and the pipeline fails, but partially-written files may remain on disk.

**Default:** Treat per-clip/per-track failure as an agent-level failure. The agent cleans up partial outputs (or leaves them for debugging). Resume logic will re-run the entire agent on `/resume`. A more granular per-file retry belongs in the service layer.

**G8: Artifact `content_type` and `size_bytes` for binary files.**
`ArtifactRef` supports `content_type` and optional `size_bytes`, but Phase 2 agents only set `content_type="application/json"`. Video/audio artifacts need `video/mp4` and `audio/mpeg` (or `audio/mp3`).

**Default:** Video Agent sets `content_type="video/mp4"`. Voice Agent sets `content_type="audio/mpeg"` (standard MIME for MP3). `size_bytes` is optional for Phase 3.

### Minor

**G9: Measuring actual duration of generated clips/tracks.**
We could use `ffmpeg-python` or `ffprobe` to fill `VideoClip.duration` and `AudioTrack.duration`, but this is not required for the MVP and adds a dependency.

**Default:** Leave `duration` as `float | None = None` in output models. Fill with expected duration from Storyboard/Script if known; ffprobe integration deferred.

**G10: Web search result caching.**
Repeated research queries could be cached, but the MVP does not need it.

**Default:** No caching in Phase 3.

---

## 4. Questions

| #   | Question                                                                                                             | Stakes                                                                                                       | Default if unanswered                                                                                                                                                           |
| --- | -------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Q1  | Do we need a separate web search provider (SerpAPI), or can we rely on Qwen model's built-in web search capability?  | If Qwen can search natively, we can simplify the Research agent by dropping the web search service entirely. | Keep the `WebSearchService` abstraction but implement it as a Qwen web search enricher — inject search results into the prompt if enabled.                                      |
| Q2  | Should Video and Voice agents run in parallel within Phase 3?                                                        | Parallel reduces latency but requires async/concurrency changes and is listed as a future phase.             | **Sequential** — keep Video and Voice running one after another. Parallel execution deferred.                                                                                   |
| Q3  | Where should retry logic live — inside each concrete service or as a decorator/wrapper?                              | Centralized wrapper is DRY but harder to tune per-provider. Per-service decorator is simple and explicit.    | **Per-service decorator** using `tenacity` inside concrete service classes.                                                                                                     |
| Q4  | What should the fallback stub mode do when an API is unavailable — generate placeholder media or fail with an error? | Empty files may break downstream consumers; generating valid placeholder media requires FFmpeg.              | **Error when fallback is disabled** — if `FALLBACK_STUBS` is false (default), the agent raises and the pipeline fails. If enabled, generate minimal valid MP3/MP4 using FFmpeg. |
| Q5  | Should `ResearchAgent` fail if web search is enabled but the search API errors?                                      | Failing makes missing API obvious; falling back to LLM-only is more resilient.                               | **Fall back to LLM-only** — if web search fails, log a warning and continue with LLM-only research. The research is still useful without web search.                            |
| Q6  | Should the agent output models include absolute paths or relative paths?                                             | Absolute paths break if outputs are moved. Relative paths require the consumer to know the base directory.   | **Relative paths** inside `outputs/{job_id}/...`; base directory is known to storage and API.                                                                                   |

---

## 5. Recommended Next Steps

1. **Resolve Q1 and Q4** — pick a web search provider and decide stub file format.
2. **Define output models** (`VideoOutput`, `VoiceOutput`) so agents have a typed contract.
3. **Implement `WebSearchService`** as an ABC + stub + optional SerpAPI concrete.
4. **Add retry policy** using `tenacity` to the three external service classes.
5. **Implement `VideoAgent` and `VoiceAgent`** following the established agent pattern.
6. **Wire fallback stub mode** behind the `FALLBACK_STUBS` env flag.
7. **Write tests** for each agent, service retry behavior, and stub fallback.
8. **Run end-to-end pipeline** with stub mode to verify Editor can consume Phase 3 outputs.

---

## 6. Resolved Decisions (for implementation plan)

| Decision            | Resolution                                                                                                                          |
| ------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| Execution mode      | **Sequential** — Video and Voice agents run one after another. Parallel execution deferred.                                         |
| Web search provider | **Qwen native** — Research agent uses Qwen model's built-in web search capability if available; otherwise LLM-only.                 |
| Web search failure  | **Graceful fallback** — if search fails, log a warning and continue with LLM-only research.                                         |
| Retry policy        | **`tenacity` per service** — 3 attempts, exponential backoff, only on transient errors.                                             |
| Fallback stubs      | **Error when disabled** — `FALLBACK_STUBS=false` (default) raises if API unavailable; `FALLBACK_STUBS=true` generates placeholders. |
| Asset paths         | **`video/clips/shot_XXX.mp4`**, **`voice/audio/scene_XXX.mp3`** with zero-padded 3-digit indices.                                   |
| Output models       | **`VideoOutput`** (list of `VideoClip`) and **`VoiceOutput`** (list of `AudioTrack`).                                               |
