# Contact Sheet Video Previews Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace completed contact-sheet placeholders with manually playable generated shot videos.

**Architecture:** FastAPI resolves a positive shot number from the persisted Video agent result and streams only that MP4. React joins storyboard shots to clip metadata, builds same-origin URLs, renders native manual video controls for generated shots, and preserves the planned-state artwork for unmatched shots.

**Tech Stack:** FastAPI, Pydantic, React 18, TypeScript, Vitest, Testing Library, pytest

---

## File Map

- Modify `backend/api/routes.py`: add validated per-shot MP4 response.
- Modify `tests/test_api/test_routes.py`: cover success and every missing state.
- Modify `frontend/src/api.ts`: add encoded clip URL helper.
- Modify `frontend/src/api.test.ts`: verify URL formatting.
- Modify `frontend/src/components/ContactSheet.tsx`: join all shots to clips and render manual video players.
- Create `frontend/src/components/ContactSheet.test.tsx`: verify rendered and planned cards.
- Modify `frontend/src/styles.css`: make clip videos fill the existing media area.

### Task 1: Stream a persisted shot clip

**Files:**
- Modify: `tests/test_api/test_routes.py`
- Modify: `backend/api/routes.py`

- [ ] **Step 1: Write failing route tests**

Add `VideoOutput` and `VideoClip` test fixtures that persist a `WorkflowState`
with `AgentName.VIDEO`, then assert:

```python
response = client.get(f"/result/{job_id}/clips/1")
assert response.status_code == 200
assert response.headers["content-type"].startswith("video/mp4")
assert response.content == b"shot-mp4"
```

Add separate `404` assertions for an unknown job, missing context, no Video
result, unknown shot, and a missing stored file. Assert the stable details from
the design specification.

- [ ] **Step 2: Verify RED**

Run:

```powershell
venv\Scripts\python.exe -m pytest tests/test_api/test_routes.py -k "clip" -v
```

Expected: route tests fail with `404` because no clip endpoint exists.

- [ ] **Step 3: Implement the endpoint**

In `backend/api/routes.py`, import `VideoOutput` and add before the frontend
static mount:

```python
    @app.get("/result/{job_id}/clips/{shot_number}")
    def download_clip(job_id: str, shot_number: int) -> FileResponse:
        if job_id not in job_store:
            raise HTTPException(status_code=404, detail="Job not found")
        context_data = storage.load(job_id, "pipeline", "context.json")
        if context_data is None:
            raise HTTPException(status_code=404, detail="Job context not found")
        context = WorkflowState.model_validate(context_data)
        video_result = context.agent_results.get(AgentName.VIDEO)
        if video_result is None or not video_result.success:
            raise HTTPException(status_code=404, detail="Video clip not found")
        video = VideoOutput.model_validate(video_result.output_data)
        clip = next(
            (item for item in video.clips if item.shot_number == shot_number),
            None,
        )
        if clip is None:
            raise HTTPException(status_code=404, detail="Video clip not found")
        clip_path = Path(clip.file_path)
        if not clip_path.is_file():
            raise HTTPException(
                status_code=404,
                detail="Video clip file not found",
            )
        return FileResponse(
            path=clip_path,
            media_type="video/mp4",
            filename=f"shot-{shot_number:02d}.mp4",
        )
```

Use `shot_number: int` with an explicit FastAPI `Path(ge=1)` constraint if the
existing route style supports importing `Path` under a non-conflicting alias.

- [ ] **Step 4: Verify GREEN**

Run:

```powershell
venv\Scripts\python.exe -m pytest tests/test_api/test_routes.py -k "clip" -v
```

Expected: all clip-route tests pass.

### Task 2: Render all generated clips with manual controls

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/api.test.ts`
- Modify: `frontend/src/components/ContactSheet.tsx`
- Create: `frontend/src/components/ContactSheet.test.tsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Write failing URL-helper and component tests**

In `api.test.ts`, assert:

```typescript
expect(clipVideoUrl("job with spaces", 3)).toBe(
  "/result/job%20with%20spaces/clips/3",
)
```

Create `ContactSheet.test.tsx` with a six-shot `JobDetailsResponse`, five matching
clip records, and assertions that:

```typescript
expect(screen.getAllByRole("article")).toHaveLength(6)
const videos = screen.getAllByTitle(/Generated video for shot/)
expect(videos).toHaveLength(5)
expect(videos[0]).toHaveAttribute("controls")
expect(videos[0]).toHaveAttribute("preload", "metadata")
expect(videos[0]).not.toHaveAttribute("autoplay")
expect(screen.getByTitle("Voxel production preview")).toBeInTheDocument()
expect(screen.getByText(/Planned/)).toBeInTheDocument()
```

Assert the first `<source>` URL is `/result/job-1/clips/1`.

- [ ] **Step 2: Verify RED**

Run:

```powershell
npm --prefix frontend test -- api.test.ts ContactSheet.test.tsx
```

Expected: helper import is missing and the component renders four placeholders.

- [ ] **Step 3: Add the URL helper**

In `frontend/src/api.ts`:

```typescript
export function clipVideoUrl(jobId: string, shotNumber: number): string {
  return `/result/${encodeURIComponent(jobId)}/clips/${shotNumber}`
}
```

- [ ] **Step 4: Replace rendered placeholders with video controls**

Update `ContactFrame` with `videoUrl?: string`, remove `.slice(0, 4)`, match each
shot to a clip, and set the URL through `clipVideoUrl(details.job_id, number)`.
Render:

```tsx
{frame.videoUrl ? (
  <video
    controls
    playsInline
    preload="metadata"
    title={`Generated video for shot ${frame.number}`}
  >
    <source src={frame.videoUrl} type="video/mp4" />
    Your browser does not support MP4 playback.
  </video>
) : (
  <IdleArtwork />
)}
```

Keep the shot-number overlay and existing metadata/status copy.

- [ ] **Step 5: Style the clip player**

Add beside the existing contact image rule:

```css
.contact-image video {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  background: var(--video-black);
}
```

- [ ] **Step 6: Verify GREEN**

Run:

```powershell
npm --prefix frontend test -- api.test.ts ContactSheet.test.tsx
```

Expected: helper and component tests pass.

### Task 3: Full verification and deployment handoff

**Files:** none

- [ ] **Step 1: Run backend tests**

```powershell
venv\Scripts\python.exe -m pytest tests -v
```

- [ ] **Step 2: Run frontend tests and production build**

```powershell
npm --prefix frontend test
npm --prefix frontend run build
```

- [ ] **Step 3: Check the diff and secret exclusions**

```powershell
git diff --check
git status --short
git check-ignore .env outputs
```

- [ ] **Step 4: Commit the verified implementation**

```bash
git add backend/api/routes.py tests/test_api/test_routes.py frontend/src/api.ts frontend/src/api.test.ts frontend/src/components/ContactSheet.tsx frontend/src/components/ContactSheet.test.tsx frontend/src/styles.css
git commit -m "feat: show generated videos in contact sheet"
```

## Plan Self-Review

- Spec coverage: safe clip streaming, all missing states, every storyboard shot,
  manual controls, no autoplay, planned fallback, styling, and quota-free tests
  are covered.
- Placeholder scan: no incomplete implementation steps remain.
- Naming consistency: backend uses `shot_number`; frontend uses `shotNumber` and
  `clipVideoUrl`; route format is consistently `/result/{job_id}/clips/{shot}`.
