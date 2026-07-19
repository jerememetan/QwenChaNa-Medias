# Demo Frontend Integration Design

**Date:** 2026-07-19
**Status:** Approved concept; pending written-spec review

## Goal

Add a polished single-workspace demo UI to QwenChaNa Medias without changing
the synchronous job model or adding production-only infrastructure. The UI
must accept a prompt, run the existing pipeline, explain the seven agent
results, play and download the final MP4, and resume failed jobs.

The downloaded Figma Make export is a visual reference, not production source.
Its editorial composition is retained while its unused dependencies, generated
component dump, hard-coded job data, and monolithic component are discarded.

## Decisions already approved

- Visual direction: editorial production desk.
- Composition: asymmetric single-screen desktop workspace.
- Dominant visual: final 16:9 video canvas.
- Secondary area: seven-row production ledger.
- Typography: Newsreader plus IBM Plex Sans.
- Palette: warm paper, ink black, muted gray, one vermilion accent.
- Interaction: expandable ledger rows, restrained contact-sheet hover, working
  rule, final-video reveal, visible reduced-motion support.
- Technology: lean React, TypeScript, and Vite frontend.
- Backend execution remains synchronous.

## Reference audit

`Figma_Reference_UI/QwenChaNa-Medias` contains a useful visual prototype but is
not merged directly:

- `App.tsx` is approximately 1,100 lines with extensive inline styles.
- The export includes 48 unused shadcn UI component files.
- Its package manifest includes many unused Radix, MUI, chart, form, drag, and
  animation dependencies.
- All job data and UI transitions are local mock state.
- It makes no calls to the existing FastAPI routes.

The reference directory remains ignored by Git. Production code copies only
the approved layout, tokens, useful SVG placeholder art, and interaction ideas.

## Architecture

### Frontend

Create a new `frontend/` Vite application with these focused modules:

- `src/App.tsx`: owns page-level job state and composes the workspace.
- `src/api.ts`: typed calls to Generate, Details, Result, Resume, and Download.
- `src/types.ts`: API response and agent-output types used by the UI.
- `src/components/Masthead.tsx`: product name, job ID, status, output metadata.
- `src/components/VideoWorkspace.tsx`: idle art, working state, final video,
  download action, and result summary.
- `src/components/ContactSheet.tsx`: storyboard shot metadata and clip labels.
- `src/components/ProductionLedger.tsx`: seven agent rows and selected inspector.
- `src/components/PromptComposer.tsx`: prompt entry and primary action.
- `src/styles.css`: design tokens, layout, states, motion, focus, and responsive
  fallback.

Runtime dependencies are limited to React, React DOM, and Lucide React. Vite,
TypeScript, Vitest, jsdom, and React Testing Library remain development
dependencies. The production UI does not use Tailwind, shadcn, Radix, MUI, or
a motion library.

### Backend

Add one read-only endpoint:

```text
GET /details/{job_id}
```

It returns:

```json
{
  "job_id": "...",
  "prompt": "...",
  "status": "completed",
  "current_agent": null,
  "failed_agent": null,
  "error": null,
  "agent_results": {
    "director": {},
    "research": {},
    "script": {},
    "storyboard": {},
    "video": {},
    "voice": {},
    "editor": {}
  }
}
```

`agent_results` uses the existing `AgentResult` contract, including typed
output data and artifact metadata. Unknown jobs or missing persisted context
return `404`. This endpoint does not mutate job state or expose arbitrary file
paths through a new download route.

The existing final-video download endpoint remains the only media-serving
endpoint in this phase.

### Static serving

`create_app` accepts an optional frontend distribution directory. When present,
FastAPI mounts the built Vite assets after registering API routes and serves the
SPA at `/`. Tests and API-only callers may omit the directory.

The production app points to `frontend/dist`. Vite development mode proxies the
existing API paths to the FastAPI development server.

## Data flow

### Initial state

The page shows the Figma-derived voxel artwork as clearly decorative idle art,
an editable production brief, seven pending ledger rows, and `Generate video`.
No fake job ID or generated artifact is shown.

### Generate

1. User submits a non-empty prompt.
2. UI enters a generic `Production running` state and disables duplicate
   submission.
3. UI calls `POST /generate` and waits for its synchronous response.
4. The UI does not pretend to know which agent is running during this wait.
5. After receiving `job_id`, UI calls `GET /details/{job_id}`.
6. If completed, UI calls `GET /result/{job_id}` and loads the final MP4 from
   the returned download URL.
7. If failed, the ledger maps saved results to completed rows, marks
   `failed_agent`, and leaves downstream rows pending.

### Resume

1. Failed state shows the persisted error and `Resume production`.
2. UI calls `POST /resume/{job_id}` and waits synchronously.
3. UI refreshes Details and Result.
4. Copy states that completed assets will be reused.

### Ledger mapping

The ledger always uses canonical order:

1. Director
2. Research
3. Script
4. Storyboard
5. Video
6. Voice
7. Editor

An agent with a successful result is complete. `failed_agent` is failed. All
remaining agents are pending. During a synchronous request, the interface uses
one honest global working state rather than fabricated per-agent progress.

Inspectors render useful fields from existing output schemas:

- Director: title, tone, audience, duration, style and constraints.
- Research: skipped explanation, confidence, and notes.
- Script: title, scenes, narration, and duration hints.
- Storyboard: shot number, camera, motion, visual prompt, and duration.
- Video: shot number, file name, and duration.
- Voice: scene number, file name, and duration.
- Editor: final path, scene count, and export metadata.

## Contact sheet and media truthfulness

The final video player uses the actual `/result/{job_id}/download` response.
The contact sheet uses actual Storyboard and Video metadata but does not claim
to show extracted MP4 thumbnails. Until a safe per-clip media endpoint exists,
shot frames use a restrained neutral preview treatment derived from the idle
art and are labeled with their real shot data.

This avoids exposing arbitrary local files or presenting illustrative art as a
generated clip.

## Visual system

CSS variables define the approved tokens:

```css
--paper: #f3efe6;
--paper-raised: #faf8f2;
--ink: #171714;
--muted-ink: #68645b;
--rule: #c9c1b3;
--vermilion: #c43b2f;
--video-black: #10100e;
```

Layout uses a 12-column desktop grid, 64px outer margins, fine 1px rules, and
0-4px corner radii. It avoids gradients in application chrome, glass effects,
large rounded cards, pill clusters, decorative analytics, and chatbot motifs.

Primary target is a hackathon laptop or desktop display. Below 960px, the ledger
moves below the video workspace; no separate mobile product design is added.

## Interaction and accessibility

- Ledger rows are buttons with `aria-expanded` and keyboard focus.
- Prompt has a visible label, validation text, and disabled submission state.
- Every action has a 44px minimum target and visible focus ring.
- Status is communicated through text and shape, not color alone.
- Working-rule, shutter, and contact-sheet motions stop under
  `prefers-reduced-motion`.
- Final video uses native controls and an accessible title.
- Errors remain visible near the primary recovery action.

## Error handling

- `422`: show prompt validation without clearing the text.
- `404`: show that saved job data is unavailable and allow a new production.
- `409`: explain running/completed conflict and refresh Details.
- `503`: explain that resume agents are unavailable.
- Network or invalid JSON: show a recoverable connection error.
- Video load failure: retain Download action and show a concise playback error.
- Partial or unexpected agent output: show raw-safe summary text rather than
  crashing the ledger.

## Testing

All automated tests remain quota-free.

Backend tests cover:

- Details response for completed, failed, and unknown jobs.
- Existing Generate, Result, Download, and Resume contracts remain unchanged.
- Optional static mount does not shadow API routes.

Frontend tests cover:

- Agent-row state mapping.
- Generate success and failure refresh flow.
- Resume success and failure refresh flow.
- Result URL and download behavior.
- Empty prompt and recoverable API errors.

Verification includes:

- Frontend unit tests.
- `npm run build`.
- Existing Python suite.
- Local FastAPI plus built frontend smoke test.
- One browser screenshot comparison against the Figma Make reference.

No automated test calls Alibaba, Wan, CosyVoice, or another paid provider.

## Non-goals

- Background job execution or WebSocket/SSE progress.
- Concurrent-user production scheduling.
- Authentication, job history, or multi-tenant storage.
- Editing agent outputs before generation.
- Streaming individual video clips or audio tracks.
- Mobile-specific redesign.
- Two-way Figma synchronization or Code Connect.
- Directly committing the generated Figma export.

## Acceptance criteria

- A user can enter a prompt and run the existing pipeline from the browser.
- Completed jobs show all seven agent outputs and play the real final MP4.
- Failed jobs show completed work, failed agent, error, and Resume action.
- Resume uses existing quota-safe backend behavior.
- UI matches approved editorial design without generic AI-dashboard styling.
- Built UI is served by FastAPI without breaking API routes.
- All frontend and backend automated tests pass without paid API calls.
