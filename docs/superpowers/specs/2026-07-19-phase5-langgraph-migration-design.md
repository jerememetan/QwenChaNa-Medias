# Phase 5 LangGraph Migration Design

## Purpose

Phase 5 replaces the sequential loop inside `Pipeline` with LangGraph orchestration while preserving the working API, artifact layout, and local JSON resume model. It adds quota-safe conditional routing, parallel Video and Voice execution, per-asset resume, and live configuration reload for resumed jobs.

This is an internal orchestration migration for a single-job hackathon demo. It does not make `/generate` asynchronous and does not add a worker queue, UI, or deployment infrastructure.

## Goals

1. Model the seven-agent workflow as a LangGraph state graph.
2. Preserve the public `Pipeline.run(job_id, agents, context)` contract.
3. Route creative briefs around the Research LLM call while preserving a successful Research result for Script.
4. Run Video and Voice concurrently, then join both branches before Editor.
5. Preserve completed parallel work when one branch fails.
6. Persist each completed video clip and narration track so resume generates only missing assets.
7. Reload `.env` and rebuild provider services when `/resume/{job_id}` is called.
8. Keep `context.json` and agent artifact JSON files as the authoritative persisted state.

## Non-Goals

- Asynchronous `/generate` execution or background workers.
- LangGraph SQLite or other checkpoint storage.
- Human approval endpoints or interrupts.
- Automatic retries for Wan, CosyVoice, or other paid providers.
- A Reviewer Agent or automatic semantic regeneration.
- A second orchestration mode or rollback environment flag.
- Expanded status or failure response schemas.
- Compatibility with unmanifested partial assets from pre-Phase-5 jobs.
- Changes to current Alibaba provider choices, `longqiang_v3`, FFmpeg behavior, or output formats.

## Dependency

Add the stable LangGraph 1.2 minor line:

```text
langgraph>=1.2,<1.3
```

Python 3.12 is supported. Pinning the minor line avoids unreviewed API changes during the hackathon.

## Selected Architecture

`Pipeline` retains its existing constructor and `run` method. Its implementation invokes a compiled LangGraph built in `workflow/graph.py`.

```text
START
  |
Director
  |-- requires_research=true --> Research -----|
  `-- requires_research=false -> Skip Research-|
                                                |
                                              Script
                                                |
                                            Storyboard
                                             /       \
                                          Video     Voice
                                             \       /
                                               Join
                                                |
                                              Editor
                                                |
                                               END
```

The migration does not duplicate the old sequential orchestrator. `Pipeline` remains the compatibility boundary used by API and tests; LangGraph replaces its internal scheduling.

### File Responsibilities

- `workflow/graph.py` defines graph state, reducers, node adapters, routing functions, parallel fan-out, join behavior, and graph compilation.
- `workflow/pipeline.py` preserves the public orchestration API, invokes the graph, translates the graph result into `WorkflowState`, and persists final state.
- `workflow/resume.py` loads persisted state and invokes a freshly built production agent set.
- `backend/factory.py` owns provider/service/agent construction from a supplied `Settings` value. Both app startup and resume use this factory.
- `agents/video.py` and `agents/voice.py` persist successful assets incrementally and reuse safe manifest entries.
- Existing agent model files remain the typed contracts for artifacts and workflow state.

## Graph State and Isolation

Existing agents mutate a `WorkflowState`, which is unsafe if two parallel nodes share the same object. Each graph node therefore:

1. Creates a deep copy of the current workflow state.
2. Runs exactly one existing agent against that copy.
3. Extracts only that agent's `AgentResult` and state timestamps.
4. Returns an isolated graph update.
5. Lets graph reducers merge updates by `AgentName`.

Parallel nodes never mutate a shared `WorkflowState` instance. The graph state includes:

- the base workflow fields needed to reconstruct `WorkflowState`;
- `agent_results`, merged as a mapping keyed by `AgentName`;
- branch failures, merged as a list for the Video/Voice super-step;
- the injected agent mapping, used only for the current invocation.

No LangGraph checkpointer is compiled. `outputs/{job_id}/pipeline/context.json` remains the source of truth between invocations.

## Conditional Research Routing

After Director completes, a conditional edge reads `CreativeBrief.requires_research`.

- `true` routes to the existing Research Agent.
- `false` routes to a `skip_research` graph node.

`skip_research` creates the same empty, successful `ResearchNotes` and Research `AgentResult` currently produced by Research Agent's local creative-prompt branch. Script therefore continues to require and receive Research output regardless of route.

This conditional edge avoids an LLM call without changing downstream contracts or the expected seven-agent result set.

## Parallel Video and Voice Routing

After Storyboard succeeds, routing inspects completed results:

- neither complete: schedule Video and Voice together;
- only Video complete: schedule Voice;
- only Voice complete: schedule Video;
- both complete: proceed directly to join.

The join proceeds to Editor only when both successful results exist. While parallel work is active, `WorkflowState.current_agent` is `None`; the single-agent API schema is not expanded.

### Parallel Failure Rules

Video and Voice node adapters capture exceptions into branch-failure updates instead of allowing one exception to discard the sibling branch's successful result.

After the super-step:

- zero failures proceeds to Editor;
- one failure stops before Editor and records that agent;
- two failures choose Video as deterministic `failed_agent` and combine both labeled error messages into `error`;
- every successful sibling result and asset manifest remains persisted.

There are no automatic paid-provider retries. `/resume/{job_id}` is the only provider retry mechanism.

## Incremental Asset Persistence

Video and Voice treat their existing output JSON files as per-asset manifests:

- `video/video_output.json` accumulates successful `VideoClip` entries;
- `voice/voice_output.json` accumulates successful `AudioTrack` entries.

For each requested shot or scene, an asset is reusable only when all conditions hold:

1. Its identifier exists in the manifest.
2. Its provider call previously returned successfully.
3. Its referenced local path exists as a file.
4. The file size is greater than zero.

The agent loads its manifest at the start of `run`. Valid completed entries are skipped. Missing, empty, or absent entries are generated. After every successful provider return and non-empty-file check, the agent updates its typed output model and saves the manifest immediately, before starting the next asset.

If generation fails after earlier assets succeeded, the agent raises normally. It does not write a successful final `AgentResult`, but its partial manifest remains available to resume.

Pre-Phase-5 partial files without manifest entries are ignored. Completed upstream `AgentResult`s remain reusable because their contracts already prove agent completion.

## Live Configuration Reload on Resume

App startup and resume share a provider factory:

```text
Settings
  -> AlibabaCloudLLMService
  -> DashScopeVideoGenService
  -> DashScopeTTSService
  -> LocalFFmpegService
  -> seven configured agents
```

The production app builds its initial agents through this factory. `/resume/{job_id}` calls the factory again with a fresh `Settings()` instance. Pydantic Settings rereads process environment and `.env`, so changed model names or API keys apply without restarting the server.

Resume then:

1. Loads `context.json`.
2. Clears prior failure fields.
3. Builds fresh services and agents from current configuration.
4. Invokes `Pipeline.run` with the persisted workflow state.
5. Skips completed graph nodes and completed asset manifest entries.
6. Persists the new terminal state and synchronizes the existing `JobRecord`.

This live reload is global configuration for the resumed invocation; it does not mutate agents already used by other invocations. The demo runs one synchronous job, so multi-job configuration races are outside scope.

## Persistence Boundaries

Agents continue to persist their typed artifacts through `StorageBackend`. `Pipeline.run` consumes LangGraph's super-step stream, reconstructs merged `WorkflowState` after each emitted step, and persists `context.json` only at those safe boundaries. Concurrent branch threads never write `context.json` independently.

The required boundaries are:

- after each sequential node;
- after the Research/Skip Research branch rejoins;
- after Video and Voice finish or fail;
- after Editor;
- at final completed or failed state.

Per-asset Video and Voice manifests are safe to write from parallel branches because they use different agent directories and filenames.

## API Behavior

Existing API contracts remain unchanged:

- `POST /generate` runs synchronously and returns a job ID after graph termination.
- `GET /status/{job_id}` keeps the existing response schema.
- `GET /result/{job_id}` and download behavior remain unchanged.
- `POST /resume/{job_id}` keeps its request and response schema while gaining live settings reload and per-asset continuation.

`current_agent=None` is expected during the parallel Video/Voice super-step. `failed_agent` remains singular for compatibility.

## Error Handling

- Director, Research/Skip Research, Script, or Storyboard failure stops before paid asset generation when applicable.
- Storyboard validation failures continue to prevent Wan calls.
- Video/Voice failures preserve successful sibling work and partial manifests.
- Missing or empty manifest files are regenerated.
- Editor never runs until complete Video and Voice results exist.
- Graph construction or invocation errors become persisted pipeline failures with bounded error text.
- No retry loops or hidden provider calls are introduced.

## Testing Strategy

All automated verification is quota-free.

### Graph Tests

- Compile graph and verify the seven-agent topology.
- Route factual briefs through Research.
- Route creative briefs through Skip Research and still emit a Research result.
- Skip nodes already represented by successful `AgentResult`s.
- Use synchronization events to prove Video and Voice overlap without relying on elapsed-time thresholds.
- Prove parallel results merge without overwriting each other.
- Prove Editor waits for both branches.
- Prove one branch failure preserves the sibling result.
- Prove two branch failures use Video as `failed_agent` and combine labeled errors.

### Asset Resume Tests

- Fail Video after its first successful shot, verify immediate manifest persistence, resume, and assert only missing shots invoke the provider.
- Apply the same behavior to Voice scene tracks.
- Verify missing files, empty files, and manifest omissions trigger regeneration.
- Verify valid manifest entries are reused without provider calls.

### Configuration Tests

- Build agents with one set of environment model values.
- Change environment values.
- Invoke resume.
- Assert fresh provider configurations use the changed values and completed work remains skipped.

### Compatibility Tests

- Preserve `Pipeline.run(job_id, agents, context)` behavior.
- Preserve API status/result/download schemas.
- Preserve Editor resume behavior.
- Update the quota-free seven-agent E2E test to run through LangGraph.
- Run the complete existing test suite with zero external calls.

## Acceptance Criteria

1. The local seven-agent E2E pipeline still produces a narrated MP4.
2. Video and Voice execute in parallel after Storyboard.
3. Creative jobs make no Research LLM call but still contain a successful Research result.
4. Video/Voice partial successes persist before agent completion.
5. Resume does not regenerate any valid completed agent or asset.
6. Editing `.env` before resume changes models/API configuration without server restart.
7. A failed parallel branch prevents Editor while preserving successful sibling work.
8. Existing public API schemas and output paths remain unchanged.
9. Full automated verification makes no Alibaba calls.

## Deferred Work

- Background or distributed job execution.
- Multiple concurrent jobs with independently versioned configuration.
- Native LangGraph checkpoint persistence and time travel.
- Human approval interrupts and approval endpoints.
- Automatic retry policies and cost budgets.
- Reviewer-driven regeneration.
- Structured multiple-failure API fields.
- Media decoding/probing before asset reuse.
- Adoption of legacy unmanifested partial files.
