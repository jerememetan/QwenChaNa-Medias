# Demo Frontend Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a lean editorial React workspace that runs the existing synchronous pipeline, displays all seven agent results, plays the real final MP4, and resumes failed jobs.

**Architecture:** A small React/Vite application owns browser state and calls the existing FastAPI routes plus one new read-only Details route. Pure selectors translate persisted `AgentResult` objects into ledger rows, focused components render the approved Figma-derived composition, and FastAPI optionally serves `frontend/dist` after API routes are registered.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, React 18, TypeScript, Vite 6, Vitest, React Testing Library, plain CSS, Lucide React.

---

## Implementation constraints

- Use TDD for every backend and frontend behavior: write one focused test,
  observe the expected failure, implement the minimum, rerun.
- Never call Alibaba, Wan, CosyVoice, or another paid provider in automated or
  visual tests.
- Keep `/generate` and `/resume` synchronous.
- Do not fabricate live per-agent progress while a synchronous request waits.
- Do not commit or import the ignored `Figma_Reference_UI/` directory.
- Do not copy the generated shadcn component dump or dependency list.
- Keep existing Generate, Status, Result, Download, and Resume response schemas
  compatible.
- Do not add authentication, job history, background workers, SSE/WebSockets,
  individual clip streaming, or mobile-specific screens.
- Commit after each task using only the files named by that task.

## File map

### Backend

- `backend/api/schemas.py`: typed read-only job details response.
- `backend/api/routes.py`: Details endpoint and optional static frontend mount.
- `backend/main.py`: locate and pass `frontend/dist` when built.
- `tests/test_api/test_schemas.py`: Details schema contract.
- `tests/test_api/test_routes.py`: Details and static-serving route behavior.
- `tests/test_backend/test_main.py`: production static-directory wiring.

### Frontend

- `frontend/package.json`: minimal scripts and dependencies.
- `frontend/package-lock.json`: npm-resolved dependency lock.
- `frontend/index.html`: Vite document entry.
- `frontend/tsconfig.json`: strict browser TypeScript configuration.
- `frontend/vite.config.ts`: React, Vitest/jsdom, and FastAPI dev proxies.
- `frontend/src/main.tsx`: React root.
- `frontend/src/types.ts`: API-facing browser types.
- `frontend/src/api.ts`: fetch wrapper and endpoint functions.
- `frontend/src/jobView.ts`: canonical stages, status mapping, and safe summaries.
- `frontend/src/App.tsx`: generate/resume state machine and composition.
- `frontend/src/components/IdleArtwork.tsx`: compact Figma-derived idle SVG.
- `frontend/src/components/Masthead.tsx`: brand and job metadata.
- `frontend/src/components/VideoWorkspace.tsx`: idle/running/final video states.
- `frontend/src/components/ContactSheet.tsx`: truthful storyboard metadata frames.
- `frontend/src/components/ProductionLedger.tsx`: stage rows and inspectors.
- `frontend/src/components/PromptComposer.tsx`: prompt and primary action.
- `frontend/src/styles.css`: tokens, layout, motion, responsive fallback.
- `frontend/src/test/setup.ts`: DOM assertion setup.
- `frontend/src/**/*.test.ts(x)`: pure and component behavior tests.

### Documentation

- `README.md`: frontend build/run instructions and current directory purpose.
- `docs/api.md`: Details endpoint.
- `PROJECT_SPEC.md`: Phase 6 demo UI completion checklist and scope cleanup.
- `QWEN.md`: mark frontend and LangGraph as implemented rather than future.

## Task 1: Add the read-only job Details contract

**Files:**

- Modify: `backend/api/schemas.py`
- Modify: `backend/api/routes.py`
- Modify: `tests/test_api/test_schemas.py`
- Modify: `tests/test_api/test_routes.py`

- [ ] **Step 1: Write the failing schema test**

Add imports in `tests/test_api/test_schemas.py`:

```python
from backend.api.schemas import JobDetailsResponse
from models.agent_result import AgentResult
```

Add:

```python
class TestJobDetailsResponse:
    def test_details_preserves_typed_agent_results(self):
        result = AgentResult(
            agent_name=AgentName.DIRECTOR,
            success=True,
            output_data={"title": "Voxel"},
        )
        response = JobDetailsResponse(
            job_id="job-1",
            prompt="Make a voxel video",
            status=JobStatus.COMPLETED,
            agent_results={AgentName.DIRECTOR: result},
        )

        data = response.model_dump(mode="json")

        assert data["agent_results"]["director"]["output_data"] == {
            "title": "Voxel"
        }
        assert data["failed_agent"] is None
        assert data["error"] is None
```

- [ ] **Step 2: Run the schema test and verify RED**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_api/test_schemas.py -k "details_preserves" -q
```

Expected: collection fails because `JobDetailsResponse` does not exist.

- [ ] **Step 3: Add the Details response schema**

In `backend/api/schemas.py`, import `AgentResult` and add:

```python
from models.agent_result import AgentResult


class JobDetailsResponse(BaseModel):
    job_id: str
    prompt: str
    status: JobStatus
    current_agent: AgentName | None = None
    failed_agent: AgentName | None = None
    error: str | None = None
    agent_results: dict[AgentName, AgentResult]
```

- [ ] **Step 4: Run the schema test and verify GREEN**

Run the Step 2 command. Expected: one matching test passes.

- [ ] **Step 5: Write failing Details route tests**

In `tests/test_api/test_routes.py`, add:

```python
class TestDetailsEndpoint:
    def test_details_returns_persisted_agent_outputs(self):
        storage = InMemoryStorage()
        context = WorkflowState(
            job_id="details-job",
            prompt="Make a voxel video",
            status=JobStatus.FAILED,
            failed_agent=AgentName.VIDEO,
            error="video quota",
        )
        context.agent_results[AgentName.DIRECTOR] = AgentResult(
            agent_name=AgentName.DIRECTOR,
            success=True,
            output_data={"title": "Voxel"},
        )
        storage.save(
            "details-job",
            "pipeline",
            "context.json",
            context.model_dump(mode="json"),
        )
        job_store = {
            "details-job": JobRecord(
                job_id="details-job",
                prompt="Make a voxel video",
                status=JobStatus.FAILED,
                failed_agent=AgentName.VIDEO,
                error="video quota",
            )
        }
        client = TestClient(create_app(storage, job_store))

        response = client.get("/details/details-job")

        assert response.status_code == 200
        body = response.json()
        assert body["failed_agent"] == "video"
        assert body["error"] == "video quota"
        assert body["agent_results"]["director"]["output_data"] == {
            "title": "Voxel"
        }

    def test_details_returns_404_for_unknown_job(self):
        client, _, _ = _make_test_app()

        response = client.get("/details/missing")

        assert response.status_code == 404

    def test_details_returns_404_when_context_is_missing(self):
        storage = InMemoryStorage()
        job_store = {
            "missing-context": JobRecord(
                job_id="missing-context",
                prompt="test",
            )
        }
        client = TestClient(create_app(storage, job_store))

        response = client.get("/details/missing-context")

        assert response.status_code == 404
        assert response.json()["detail"] == "Job context not found"
```

- [ ] **Step 6: Run route tests and verify RED**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_api/test_routes.py -k "DetailsEndpoint" -q
```

Expected: tests receive `404` because the route is not registered.

- [ ] **Step 7: Implement the Details route**

Import `JobDetailsResponse` in `backend/api/routes.py` and register this before
the frontend static mount added later:

```python
    @app.get("/details/{job_id}", response_model=JobDetailsResponse)
    def details(job_id: str) -> JobDetailsResponse:
        record = job_store.get(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Job not found")
        context_data = storage.load(job_id, "pipeline", "context.json")
        if context_data is None:
            raise HTTPException(status_code=404, detail="Job context not found")
        context = WorkflowState.model_validate(context_data)
        return JobDetailsResponse(
            job_id=context.job_id,
            prompt=context.prompt,
            status=context.status,
            current_agent=context.current_agent,
            failed_agent=context.failed_agent,
            error=context.error,
            agent_results=context.agent_results,
        )
```

- [ ] **Step 8: Run focused backend tests**

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_api/test_schemas.py tests/test_api/test_routes.py -q
```

Expected: all schema and route tests pass.

- [ ] **Step 9: Commit Details API**

```powershell
git add backend/api/schemas.py backend/api/routes.py tests/test_api/test_schemas.py tests/test_api/test_routes.py
git commit -m "feat(api): expose persisted job details"
```

## Task 2: Scaffold the minimal frontend toolchain

**Files:**

- Create: `frontend/package.json`
- Create: `frontend/package-lock.json`
- Create: `frontend/index.html`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/styles.css`
- Create: `frontend/src/test/setup.ts`

- [ ] **Step 1: Create the minimal package manifest**

Create `frontend/package.json`:

```json
{
  "name": "qwenchana-medias-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "test": "vitest run"
  },
  "dependencies": {
    "lucide-react": "0.487.0",
    "react": "18.3.1",
    "react-dom": "18.3.1"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "6.6.3",
    "@testing-library/react": "16.3.0",
    "@types/react": "18.3.18",
    "@types/react-dom": "18.3.5",
    "@vitejs/plugin-react": "4.7.0",
    "jsdom": "26.1.0",
    "typescript": "5.7.3",
    "vite": "6.3.5",
    "vitest": "3.2.4"
  }
}
```

- [ ] **Step 2: Add Vite and TypeScript configuration**

Create `frontend/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "allowJs": false,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "allowSyntheticDefaultImports": true,
    "strict": true,
    "forceConsistentCasingInFileNames": true,
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx"
  },
  "include": ["src", "vite.config.ts"]
}
```

Create `frontend/vite.config.ts`:

```typescript
import react from "@vitejs/plugin-react"
import { defineConfig } from "vitest/config"

const apiTarget = "http://127.0.0.1:8000"

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/generate": apiTarget,
      "/details": apiTarget,
      "/status": apiTarget,
      "/result": apiTarget,
      "/resume": apiTarget,
      "/health": apiTarget,
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: true,
  },
})
```

- [ ] **Step 3: Add document and React entry files**

Create `frontend/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="theme-color" content="#f3efe6" />
    <title>QwenChaNa Medias</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

Create `frontend/src/main.tsx`:

```typescript
import { StrictMode } from "react"
import { createRoot } from "react-dom/client"

import App from "./App"
import "./styles.css"

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
```

Create `frontend/src/App.tsx`:

```typescript
export default function App() {
  return <main><h1>QwenChaNa Medias</h1></main>
}
```

Create `frontend/src/styles.css`:

```css
@import url("https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=Newsreader:opsz,wght@6..72,400;6..72,500&display=swap");

:root {
  color: #171714;
  background: #f3efe6;
  font-family: "IBM Plex Sans", sans-serif;
}

* { box-sizing: border-box; }
body { margin: 0; }
button, textarea { font: inherit; }
```

Create `frontend/src/test/setup.ts`:

```typescript
import "@testing-library/jest-dom/vitest"
```

- [ ] **Step 4: Install only declared dependencies**

```powershell
Set-Location frontend
npm install
Set-Location ..
```

Expected: `frontend/package-lock.json` and `frontend/node_modules/` are created;
no generated shadcn files appear.

- [ ] **Step 5: Ignore frontend build products**

Add to `.gitignore`:

```text
# ---- Frontend ----
frontend/node_modules/
frontend/dist/
```

- [ ] **Step 6: Verify scaffold**

```powershell
npm --prefix frontend run build
npm --prefix frontend test
```

Expected: build succeeds and Vitest exits `0` with no test files.

- [ ] **Step 7: Commit frontend scaffold**

```powershell
git add .gitignore frontend/package.json frontend/package-lock.json frontend/index.html frontend/tsconfig.json frontend/vite.config.ts frontend/src/main.tsx frontend/src/App.tsx frontend/src/styles.css frontend/src/test/setup.ts
git commit -m "build(frontend): add minimal React workspace"
```

## Task 3: Add typed frontend API access

**Files:**

- Create: `frontend/src/types.ts`
- Create: `frontend/src/api.ts`
- Create: `frontend/src/api.test.ts`

- [ ] **Step 1: Write failing API client tests**

Create `frontend/src/api.test.ts`:

```typescript
import { afterEach, describe, expect, it, vi } from "vitest"

import { ApiError, generateJob, getJobDetails, resultDownloadUrl } from "./api"

afterEach(() => vi.unstubAllGlobals())

describe("frontend API", () => {
  it("posts a production prompt", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ job_id: "job-1" }), {
        status: 202,
        headers: { "Content-Type": "application/json" },
      }),
    )
    vi.stubGlobal("fetch", fetchMock)

    await expect(generateJob("Voxel reveal")).resolves.toEqual({ job_id: "job-1" })
    expect(fetchMock).toHaveBeenCalledWith("/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt: "Voxel reveal" }),
    })
  })

  it("returns typed details", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        job_id: "job-1",
        prompt: "Voxel reveal",
        status: "failed",
        current_agent: null,
        failed_agent: "video",
        error: "quota",
        agent_results: {},
      }), { status: 200, headers: { "Content-Type": "application/json" } }),
    ))

    const details = await getJobDetails("job-1")

    expect(details.failed_agent).toBe("video")
  })

  it("surfaces FastAPI error details", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "Job not found" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      }),
    ))

    await expect(getJobDetails("missing")).rejects.toEqual(
      new ApiError(404, "Job not found"),
    )
  })

  it("encodes final download URLs", () => {
    expect(resultDownloadUrl("job with spaces")).toBe(
      "/result/job%20with%20spaces/download",
    )
  })
})
```

- [ ] **Step 2: Run API tests and verify RED**

```powershell
npm --prefix frontend test -- api.test.ts
```

Expected: import fails because `api.ts` does not exist.

- [ ] **Step 3: Define browser API types**

Create `frontend/src/types.ts`:

```typescript
export type AgentName =
  | "director" | "research" | "script" | "storyboard"
  | "video" | "voice" | "editor"

export type JobStatus = "pending" | "running" | "completed" | "failed"

export interface ArtifactRef {
  agent_name: AgentName
  filename: string
  content_type: string
  size_bytes?: number | null
}

export interface AgentResult {
  agent_name: AgentName
  success: boolean
  output_data: Record<string, unknown>
  artifacts: ArtifactRef[]
  error?: string | null
  duration_seconds?: number | null
}

export interface GenerateResponse { job_id: string }
export interface ResumeResponse { job_id: string }

export interface JobDetailsResponse {
  job_id: string
  prompt: string
  status: JobStatus
  current_agent: AgentName | null
  failed_agent: AgentName | null
  error: string | null
  agent_results: Partial<Record<AgentName, AgentResult>>
}

export interface ResultResponse {
  job_id: string
  status: "completed"
  output_path: string
  download_url: string
  artifacts: ArtifactRef[]
}
```

- [ ] **Step 4: Implement the fetch wrapper**

Create `frontend/src/api.ts`:

```typescript
import type {
  GenerateResponse,
  JobDetailsResponse,
  ResultResponse,
  ResumeResponse,
} from "./types"

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = "ApiError"
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  const body = await response.json().catch(() => null) as
    | { detail?: string }
    | T
    | null
  if (!response.ok) {
    const detail = body && typeof body === "object" && "detail" in body
      ? body.detail
      : undefined
    throw new ApiError(response.status, detail || `Request failed (${response.status})`)
  }
  return body as T
}

export function generateJob(prompt: string): Promise<GenerateResponse> {
  return request("/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
  })
}

export function getJobDetails(jobId: string): Promise<JobDetailsResponse> {
  return request(`/details/${encodeURIComponent(jobId)}`)
}

export function getJobResult(jobId: string): Promise<ResultResponse> {
  return request(`/result/${encodeURIComponent(jobId)}`)
}

export function resumeJob(jobId: string): Promise<ResumeResponse> {
  return request(`/resume/${encodeURIComponent(jobId)}`, { method: "POST" })
}

export function resultDownloadUrl(jobId: string): string {
  return `/result/${encodeURIComponent(jobId)}/download`
}
```

- [ ] **Step 5: Run API tests and build**

```powershell
npm --prefix frontend test -- api.test.ts
npm --prefix frontend run build
```

Expected: four API tests pass and TypeScript build succeeds.

- [ ] **Step 6: Commit frontend API client**

```powershell
git add frontend/src/types.ts frontend/src/api.ts frontend/src/api.test.ts
git commit -m "feat(frontend): add typed pipeline API client"
```

## Task 4: Map persisted results to truthful ledger views

**Files:**

- Create: `frontend/src/jobView.ts`
- Create: `frontend/src/jobView.test.ts`

- [ ] **Step 1: Write failing selector tests**

Create `frontend/src/jobView.test.ts` with fixtures containing Director and
Storyboard results, then add:

```typescript
import { describe, expect, it } from "vitest"
import { buildLedger, inspectorEntries } from "./jobView"
import type { JobDetailsResponse } from "./types"

const failed: JobDetailsResponse = {
  job_id: "job-1",
  prompt: "Voxel",
  status: "failed",
  current_agent: null,
  failed_agent: "video",
  error: "quota",
  agent_results: {
    director: {
      agent_name: "director",
      success: true,
      output_data: { title: "Voxel", duration_seconds: 5 },
      artifacts: [],
    },
    storyboard: {
      agent_name: "storyboard",
      success: true,
      output_data: { shots: [{ shot_number: 1, duration: 5 }] },
      artifacts: [],
    },
  },
}

describe("job view mapping", () => {
  it("marks saved, failed, and downstream stages honestly", () => {
    const rows = buildLedger(failed)
    expect(rows.find((row) => row.name === "director")?.state).toBe("complete")
    expect(rows.find((row) => row.name === "video")?.state).toBe("failed")
    expect(rows.find((row) => row.name === "editor")?.state).toBe("pending")
  })

  it("summarizes real output data", () => {
    const rows = buildLedger(failed)
    expect(rows[0].summary).toBe("Voxel · 5 seconds")
    expect(rows[3].summary).toBe("1 shot · 5 seconds")
  })

  it("creates safe inspector entries for nested data", () => {
    const entries = inspectorEntries(failed.agent_results.storyboard!)
    expect(entries[0].label).toBe("Shots")
    expect(entries[0].value).toContain("Shot 01")
  })
})
```

- [ ] **Step 2: Run selector tests and verify RED**

```powershell
npm --prefix frontend test -- jobView.test.ts
```

Expected: import fails because `jobView.ts` does not exist.

- [ ] **Step 3: Implement canonical stage mapping**

Create `frontend/src/jobView.ts` with:

```typescript
import type { AgentName, AgentResult, JobDetailsResponse } from "./types"

export type LedgerState = "pending" | "complete" | "failed"

export interface LedgerRow {
  id: number
  name: AgentName
  label: string
  state: LedgerState
  summary: string
  result?: AgentResult
}

export interface InspectorEntry { label: string; value: string }

const STAGES: Array<[AgentName, string]> = [
  ["director", "Director"], ["research", "Research"],
  ["script", "Script"], ["storyboard", "Storyboard"],
  ["video", "Video"], ["voice", "Voice"], ["editor", "Editor"],
]

function objects(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> =>
        Boolean(item) && typeof item === "object")
    : []
}

function number(value: unknown): number {
  return typeof value === "number" ? value : 0
}

function plural(count: number, one: string): string {
  return `${count} ${count === 1 ? one : `${one}s`}`
}

function summarize(name: AgentName, result?: AgentResult): string {
  if (!result) return "—"
  const data = result.output_data
  if (name === "director") {
    return `${String(data.title || "Creative brief")} · ${number(data.duration_seconds)} seconds`
  }
  if (name === "research") {
    const notes = objects(data.notes)
    return notes.length ? plural(notes.length, "note") : "Skipped · creative prompt"
  }
  if (name === "script") {
    const scenes = objects(data.scenes)
    return plural(scenes.length, "scene")
  }
  if (name === "storyboard") {
    const shots = objects(data.shots)
    const duration = shots.reduce((sum, shot) => sum + number(shot.duration), 0)
    return `${plural(shots.length, "shot")} · ${duration} seconds`
  }
  if (name === "video") return `${plural(objects(data.clips).length, "clip")} rendered`
  if (name === "voice") return `${plural(objects(data.tracks).length, "track")} ready`
  return "Final MP4 assembled"
}

export function buildLedger(details: JobDetailsResponse | null): LedgerRow[] {
  return STAGES.map(([name, label], index) => {
    const result = details?.agent_results[name]
    const state: LedgerState = result?.success
      ? "complete"
      : details?.failed_agent === name ? "failed" : "pending"
    return { id: index + 1, name, label, state, summary: summarize(name, result), result }
  })
}

function format(value: unknown): string {
  if (value == null) return "—"
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value)
  }
  if (Array.isArray(value)) {
    return value.map((item, index) => {
      if (item && typeof item === "object") {
        const record = item as Record<string, unknown>
        const numberValue = record.shot_number ?? record.scene_number ?? index + 1
        const detail = record.visual_prompt ?? record.narration ?? record.file_path ?? "Ready"
        return `${record.shot_number ? "Shot" : "Scene"} ${String(numberValue).padStart(2, "0")}: ${detail}`
      }
      return String(item)
    }).join("\n")
  }
  return JSON.stringify(value)
}

export function inspectorEntries(result: AgentResult): InspectorEntry[] {
  return Object.entries(result.output_data).map(([key, value]) => ({
    label: key.replaceAll("_", " "),
    value: format(value),
  }))
}
```

- [ ] **Step 4: Run selectors and build**

```powershell
npm --prefix frontend test -- jobView.test.ts
npm --prefix frontend run build
```

Expected: three selector tests pass and build succeeds.

- [ ] **Step 5: Commit ledger mapping**

```powershell
git add frontend/src/jobView.ts frontend/src/jobView.test.ts
git commit -m "feat(frontend): map persisted agent results"
```

## Task 5: Build the editorial workspace components

**Files:**

- Create: `frontend/src/components/IdleArtwork.tsx`
- Create: `frontend/src/components/Masthead.tsx`
- Create: `frontend/src/components/VideoWorkspace.tsx`
- Create: `frontend/src/components/ContactSheet.tsx`
- Create: `frontend/src/components/ProductionLedger.tsx`
- Create: `frontend/src/components/PromptComposer.tsx`
- Create: `frontend/src/components/ProductionLedger.test.tsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Write failing ledger component tests**

Create `frontend/src/components/ProductionLedger.test.tsx`:

```typescript
import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { ProductionLedger } from "./ProductionLedger"
import type { JobDetailsResponse } from "../types"

const details: JobDetailsResponse = {
  job_id: "job-1", prompt: "Voxel", status: "failed",
  current_agent: null, failed_agent: "video", error: "quota",
  agent_results: {
    director: {
      agent_name: "director", success: true,
      output_data: { title: "Voxel" }, artifacts: [],
    },
  },
}

describe("ProductionLedger", () => {
  it("renders seven stages and a failed agent", () => {
    render(<ProductionLedger details={details} />)
    expect(screen.getAllByRole("button")).toHaveLength(7)
    expect(screen.getByText("Video").closest("button")).toHaveAttribute(
      "data-state", "failed",
    )
  })

  it("expands persisted output details", () => {
    render(<ProductionLedger details={details} />)
    fireEvent.click(screen.getByRole("button", { name: /Director/ }))
    expect(screen.getByText("title")).toBeInTheDocument()
    expect(screen.getByText("Voxel")).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run component tests and verify RED**

```powershell
npm --prefix frontend test -- ProductionLedger.test.tsx
```

Expected: import fails because the component does not exist.

- [ ] **Step 3: Implement compact focused components**

Implement each named component with these exact public props:

```typescript
// Masthead.tsx
export interface MastheadProps {
  jobId: string | null
  status: "idle" | "running" | "completed" | "failed"
}

// VideoWorkspace.tsx
export interface VideoWorkspaceProps {
  jobId: string | null
  running: boolean
  completed: boolean
  onPlaybackError: () => void
}

// ContactSheet.tsx
export interface ContactSheetProps {
  details: JobDetailsResponse | null
}

// ProductionLedger.tsx
export interface ProductionLedgerProps {
  details: JobDetailsResponse | null
}

// PromptComposer.tsx
export interface PromptComposerProps {
  prompt: string
  mode: "generate" | "resume" | "new"
  disabled: boolean
  error: string | null
  onPromptChange: (value: string) => void
  onSubmit: () => void
}
```

`ProductionLedger` must call `buildLedger`, keep only one expanded row in local
state, render seven semantic buttons, set `data-state`, use `aria-expanded`, and
render `inspectorEntries` inside the selected row. `ContactSheet` reads actual
Storyboard shots and Video clips from `details`, labels them with real metadata,
and uses `IdleArtwork` only as neutral frame art. `VideoWorkspace` renders a
native `<video controls>` only for completed jobs and uses
`resultDownloadUrl(jobId)` as its source.

Use a compact SVG in `IdleArtwork.tsx` with `role="img"`, title `Voxel production
preview`, a dark rectangular sky, and three isometric polygons for the grass
block. Do not copy the reference file's full decorative SVG.

- [ ] **Step 4: Implement the approved CSS system**

Replace `frontend/src/styles.css` with CSS that includes:

```css
@import url("https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=Newsreader:opsz,wght@6..72,400;6..72,500&display=swap");

:root {
  --paper: #f3efe6;
  --paper-raised: #faf8f2;
  --ink: #171714;
  --muted-ink: #68645b;
  --rule: #c9c1b3;
  --vermilion: #c43b2f;
  --video-black: #10100e;
  color: var(--ink);
  background: var(--paper);
  font-family: "IBM Plex Sans", sans-serif;
}

* { box-sizing: border-box; }
body { margin: 0; min-width: 320px; background: var(--paper); }
button, textarea { font: inherit; }
button:focus-visible, textarea:focus-visible {
  outline: 2px solid var(--ink);
  outline-offset: 3px;
}

.app-shell { min-height: 100vh; }
.masthead {
  min-height: 64px; padding: 0 64px; display: flex;
  align-items: center; justify-content: space-between;
  border-bottom: 1px solid var(--rule); background: var(--paper-raised);
}
.wordmark { font-family: "Newsreader", serif; font-size: 1.45rem; }
.workspace {
  max-width: 1440px; margin: 0 auto; padding: 24px 64px 40px;
  display: grid; grid-template-columns: minmax(0, 8fr) minmax(320px, 4fr);
  gap: 24px;
}
.media-column { min-width: 0; }
.ledger-column { border-left: 1px solid var(--rule); padding-left: 24px; }
.video-frame { aspect-ratio: 16 / 9; background: var(--video-black); }
.video-frame video, .idle-art { width: 100%; height: 100%; display: block; }
.ledger-row { border-bottom: 1px solid var(--rule); }
.ledger-row > button {
  width: 100%; min-height: 48px; display: grid;
  grid-template-columns: 28px 88px 1fr 14px; gap: 8px;
  align-items: center; border: 0; background: transparent; color: var(--ink);
  text-align: left; cursor: pointer;
}
.ledger-row > button:hover { background: var(--paper-raised); }
.ledger-row > button[data-state="failed"] { border-left: 2px solid var(--vermilion); }
.ledger-inspector { padding: 8px 12px 16px 28px; background: var(--paper-raised); }
.inspector-entry { display: grid; grid-template-columns: 92px 1fr; gap: 12px; }
.inspector-value { white-space: pre-wrap; overflow-wrap: anywhere; }
.contact-sheet { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.contact-frame { border: 1px solid var(--ink); transition: transform 140ms ease; }
.contact-frame:hover { transform: translateY(-2px); }
.prompt-composer { margin-top: 20px; border-top: 1px solid var(--rule); padding-top: 18px; }
.prompt-composer textarea {
  width: 100%; min-height: 92px; resize: vertical; padding: 12px;
  border: 1px solid var(--rule); border-radius: 0;
  background: var(--paper-raised); color: var(--ink);
}
.primary-action {
  min-height: 44px; padding: 0 22px; border: 0; border-radius: 0;
  background: var(--vermilion); color: var(--paper-raised);
  font-size: .75rem; font-weight: 600; letter-spacing: .14em;
  text-transform: uppercase; cursor: pointer;
}
.primary-action:disabled { opacity: .55; cursor: wait; }
.working-rule { height: 2px; background: var(--vermilion); animation: working 1.2s ease-in-out infinite; }
@keyframes working { 0%, 100% { transform: scaleX(.15); transform-origin: left; } 50% { transform: scaleX(1); } }
@media (max-width: 960px) {
  .masthead { padding-inline: 24px; }
  .workspace { padding: 20px 24px 32px; grid-template-columns: 1fr; }
  .ledger-column { border-left: 0; border-top: 1px solid var(--rule); padding: 20px 0 0; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: .01ms !important; animation-iteration-count: 1 !important; transition: none !important; }
}
```

Add small utility selectors needed by component markup, but do not introduce
cards, gradients in application chrome, rounded pills, or shadow stacks.

- [ ] **Step 5: Run component tests and build**

```powershell
npm --prefix frontend test -- ProductionLedger.test.tsx
npm --prefix frontend run build
```

Expected: two component tests pass and build succeeds.

- [ ] **Step 6: Commit workspace components**

```powershell
git add frontend/src/components frontend/src/styles.css
git commit -m "feat(frontend): build editorial production workspace"
```

## Task 6: Connect the Generate and completed-result flow

**Files:**

- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/App.test.tsx`

- [ ] **Step 1: Write a failing completed-generation test**

Create `frontend/src/App.test.tsx`, mock `./api`, and add:

```typescript
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import App from "./App"
import * as api from "./api"

vi.mock("./api")

const completed = {
  job_id: "job-1", prompt: "Voxel reveal", status: "completed" as const,
  current_agent: null, failed_agent: null, error: null,
  agent_results: {
    editor: {
      agent_name: "editor" as const, success: true,
      output_data: { final_path: "final.mp4", scene_count: 1 }, artifacts: [],
    },
  },
}

describe("App generation", () => {
  beforeEach(() => vi.clearAllMocks())

  it("submits the prompt and displays the completed production", async () => {
    vi.mocked(api.generateJob).mockResolvedValue({ job_id: "job-1" })
    vi.mocked(api.getJobDetails).mockResolvedValue(completed)
    vi.mocked(api.getJobResult).mockResolvedValue({
      job_id: "job-1", status: "completed", output_path: "final.mp4",
      download_url: "/result/job-1/download", artifacts: [],
    })
    render(<App />)
    fireEvent.change(screen.getByLabelText("Production brief"), {
      target: { value: "Voxel reveal" },
    })

    fireEvent.click(screen.getByRole("button", { name: "Generate video" }))

    expect(await screen.findByText("Production complete")).toBeInTheDocument()
    expect(api.generateJob).toHaveBeenCalledWith("Voxel reveal")
    expect(api.getJobDetails).toHaveBeenCalledWith("job-1")
    await waitFor(() => expect(screen.getByTitle("Final generated video")).toBeInTheDocument())
  })
})
```

- [ ] **Step 2: Run App test and verify RED**

```powershell
npm --prefix frontend test -- App.test.tsx
```

Expected: the minimal App has no prompt control or generation behavior.

- [ ] **Step 3: Implement the page state machine**

Replace `frontend/src/App.tsx` with a component that owns:

```typescript
const [prompt, setPrompt] = useState("")
const [jobId, setJobId] = useState<string | null>(null)
const [details, setDetails] = useState<JobDetailsResponse | null>(null)
const [result, setResult] = useState<ResultResponse | null>(null)
const [running, setRunning] = useState(false)
const [error, setError] = useState<string | null>(null)
const [playbackError, setPlaybackError] = useState(false)
```

Implement:

```typescript
async function refresh(id: string) {
  const next = await getJobDetails(id)
  setDetails(next)
  setResult(next.status === "completed" ? await getJobResult(id) : null)
}

async function handleGenerate() {
  const clean = prompt.trim()
  if (!clean) {
    setError("Enter a production brief.")
    return
  }
  setRunning(true)
  setError(null)
  setResult(null)
  try {
    const created = await generateJob(clean)
    setJobId(created.job_id)
    await refresh(created.job_id)
  } catch (cause) {
    setError(cause instanceof Error ? cause.message : "Unable to start production.")
  } finally {
    setRunning(false)
  }
}
```

Compose `Masthead`, `VideoWorkspace`, `ContactSheet`, `ProductionLedger`, and
`PromptComposer`. Use `result` to decide completed playback. While `running`,
show `Production running` globally, keep all unsaved ledger stages pending, and
disable prompt submission.

- [ ] **Step 4: Run App test and build**

```powershell
npm --prefix frontend test -- App.test.tsx
npm --prefix frontend run build
```

Expected: completed generation test passes and build succeeds.

- [ ] **Step 5: Commit Generate integration**

```powershell
git add frontend/src/App.tsx frontend/src/App.test.tsx
git commit -m "feat(frontend): connect synchronous generation flow"
```

## Task 7: Connect failed jobs and quota-safe Resume

**Files:**

- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/components/PromptComposer.tsx`

- [ ] **Step 1: Write a failing Resume flow test**

Add to `App.test.tsx`:

```typescript
it("resumes a failed job and refreshes the final result", async () => {
  const failed = {
    ...completed,
    status: "failed" as const,
    failed_agent: "video" as const,
    error: "video quota",
    agent_results: {},
  }
  vi.mocked(api.generateJob).mockResolvedValue({ job_id: "job-1" })
  vi.mocked(api.getJobDetails)
    .mockResolvedValueOnce(failed)
    .mockResolvedValueOnce(completed)
  vi.mocked(api.resumeJob).mockResolvedValue({ job_id: "job-1" })
  vi.mocked(api.getJobResult).mockResolvedValue({
    job_id: "job-1", status: "completed", output_path: "final.mp4",
    download_url: "/result/job-1/download", artifacts: [],
  })
  render(<App />)
  fireEvent.change(screen.getByLabelText("Production brief"), {
    target: { value: "Voxel reveal" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Generate video" }))

  expect(await screen.findByText("video quota")).toBeInTheDocument()
  fireEvent.click(screen.getByRole("button", { name: "Resume production" }))

  expect(await screen.findByText("Production complete")).toBeInTheDocument()
  expect(api.resumeJob).toHaveBeenCalledWith("job-1")
  expect(api.getJobDetails).toHaveBeenCalledTimes(2)
})
```

Add another test where `generateJob` rejects with `new ApiError(422,
"prompt must not be empty")` and assert the message is visible and the prompt
value remains.

- [ ] **Step 2: Run App tests and verify RED**

```powershell
npm --prefix frontend test -- App.test.tsx
```

Expected: Resume button or handler is missing.

- [ ] **Step 3: Implement Resume and new-production actions**

Add:

```typescript
async function handleResume() {
  if (!jobId) return
  setRunning(true)
  setError(null)
  try {
    await resumeJob(jobId)
    await refresh(jobId)
  } catch (cause) {
    setError(cause instanceof Error ? cause.message : "Unable to resume production.")
  } finally {
    setRunning(false)
  }
}

function handleNewProduction() {
  setJobId(null)
  setDetails(null)
  setResult(null)
  setError(null)
  setPlaybackError(false)
}
```

Pass `mode="resume"` only when Details is failed, `mode="new"` only when a
Result is complete, otherwise `mode="generate"`. The PromptComposer calls the
matching handler. Failed copy must include `Completed assets will be reused.`
and render `details.error` next to the recovery action.

- [ ] **Step 4: Run all frontend tests and build**

```powershell
npm --prefix frontend test
npm --prefix frontend run build
```

Expected: API, selector, component, Generate, Resume, and validation tests pass.

- [ ] **Step 5: Commit recovery flow**

```powershell
git add frontend/src/App.tsx frontend/src/App.test.tsx frontend/src/components/PromptComposer.tsx
git commit -m "feat(frontend): resume failed productions"
```

## Task 8: Serve the built frontend without shadowing APIs

**Files:**

- Modify: `backend/api/routes.py`
- Modify: `backend/main.py`
- Modify: `tests/test_api/test_routes.py`
- Modify: `tests/test_backend/test_main.py`

- [ ] **Step 1: Write failing static-serving tests**

Add to `tests/test_api/test_routes.py`:

```python
class TestFrontendStaticServing:
    def test_frontend_index_is_served_without_shadowing_health(self, tmp_path):
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "index.html").write_text(
            "<h1>QwenChaNa UI</h1>",
            encoding="utf-8",
        )
        app = create_app(InMemoryStorage(), {}, frontend_dist=dist)
        client = TestClient(app)

        assert client.get("/").text == "<h1>QwenChaNa UI</h1>"
        assert client.get("/health").json() == {"status": "ok"}

    def test_missing_frontend_directory_keeps_api_only_app(self, tmp_path):
        app = create_app(
            InMemoryStorage(),
            {},
            frontend_dist=tmp_path / "missing",
        )

        assert TestClient(app).get("/health").status_code == 200
```

Update `tests/test_backend/test_main.py` capture function to accept
`frontend_dist`, save it, and assert its name is `dist`.

- [ ] **Step 2: Run static tests and verify RED**

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_api/test_routes.py -k "FrontendStaticServing" tests/test_backend/test_main.py -q
```

Expected: `create_app` rejects the new `frontend_dist` argument.

- [ ] **Step 3: Add optional static mounting**

In `backend/api/routes.py` import `StaticFiles`, add
`frontend_dist: str | Path | None = None` to `create_app`, and place this after
all API route declarations:

```python
    if frontend_dist is not None:
        frontend_path = Path(frontend_dist)
        if frontend_path.is_dir():
            app.mount(
                "/",
                StaticFiles(directory=frontend_path, html=True),
                name="frontend",
            )
```

Because the mount is registered last, exact API routes continue to win.

- [ ] **Step 4: Wire production frontend directory**

In `backend/main.py` define:

```python
frontend_dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
```

Import `Path` and pass `frontend_dist=frontend_dist` to `create_app`. Do not
require the directory to exist at import time; `create_app` performs that check.

- [ ] **Step 5: Run backend wiring tests**

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_api/test_routes.py tests/test_backend/test_main.py -q
```

Expected: all route and production-app tests pass.

- [ ] **Step 6: Build frontend and smoke the mounted index**

```powershell
npm --prefix frontend run build
.\venv\Scripts\python.exe -m pytest tests/test_api/test_routes.py -k "FrontendStaticServing" -q
```

Expected: `frontend/dist/index.html` exists and static tests pass.

- [ ] **Step 7: Commit static serving**

```powershell
git add backend/api/routes.py backend/main.py tests/test_api/test_routes.py tests/test_backend/test_main.py
git commit -m "feat(web): serve built demo workspace"
```

## Task 9: Document, visually verify, and run full acceptance

**Files:**

- Modify: `README.md`
- Modify: `docs/api.md`
- Modify: `PROJECT_SPEC.md`
- Modify: `QWEN.md`

- [ ] **Step 1: Update API and run documentation**

Add `GET /details/{job_id}` to `docs/api.md`, explaining that it returns the
persisted context's typed agent results and returns `404` for an unknown job or
missing context.

Add these commands to `README.md`:

```powershell
npm --prefix frontend install
npm --prefix frontend run build
.\venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

Document optional two-terminal development:

```powershell
.\venv\Scripts\python.exe -m uvicorn backend.main:app --reload
npm --prefix frontend run dev
```

Change the README directory description from `Web UI (future)` to
`React/Vite demo workspace`.

- [ ] **Step 2: Update living project scope**

In `PROJECT_SPEC.md`, add:

```markdown
### Phase 6 — Demo Frontend

- [x] Build the editorial single-workspace React UI.
- [x] Connect Generate, Details, Result, Download, and Resume.
- [x] Display persisted outputs for all seven agents.
- [x] Serve the built frontend through FastAPI.
- [x] Verify the UI without paid provider calls.
```

Remove Web UI from MVP out-of-scope wording and update stale statements that
still call LangGraph or Video/Voice parallelism future work. In `QWEN.md`, mark
`frontend/` and the LangGraph graph as current directories.

- [ ] **Step 3: Run fresh frontend verification**

```powershell
npm --prefix frontend test
npm --prefix frontend run build
```

Expected: all frontend tests pass and Vite creates `frontend/dist`.

- [ ] **Step 4: Run fresh backend verification**

```powershell
.\venv\Scripts\python.exe -m pytest -q
```

Expected: complete quota-free Python suite passes with zero failures.

- [ ] **Step 5: Start the local app for visual inspection**

Run the FastAPI server in a long-lived execution session:

```powershell
.\venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/` using the available browser control. Do not press
Generate because the production app may contain real provider credentials.
Capture one screenshot of the idle workspace at 1440px width.

Check:

- Wordmark and final-video canvas dominate the first viewport.
- Ledger has seven rows and no card grid.
- Paper/ink/vermilion palette matches the reference.
- Prompt, focus, and working states remain readable.
- No purple gradients, glass effects, pill clusters, or chatbot motifs appear.
- At 960px width the ledger moves below the media workspace.

Stop the server session after the screenshot.

- [ ] **Step 6: Run static and repository checks**

```powershell
git diff --check
rg -n "Figma_Reference_UI|@radix-ui|@mui|shadcn" frontend backend tests
git status --short
```

Expected:

- `git diff --check` emits nothing.
- dependency search finds no generated UI imports.
- `Figma_Reference_UI/` remains ignored and absent from staged files.
- only the four named documentation files remain changed.

- [ ] **Step 7: Commit documentation and acceptance state**

```powershell
git add README.md docs/api.md PROJECT_SPEC.md QWEN.md
git commit -m "docs: complete demo frontend phase"
```

## Optional paid smoke test

Do not run during implementation. After quota-free verification, the user may
submit one minimal one-scene, one-shot prompt through the browser. Confirm the
request waits honestly, the final MP4 plays with audio, Download works, and a
failed provider job offers Resume without regenerating valid assets.
