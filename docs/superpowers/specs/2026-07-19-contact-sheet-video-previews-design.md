# Contact Sheet Video Previews Design

## Goal

Replace the repeated placeholder artwork in the completed contact sheet with
manually playable Wan-generated shot videos. Preserve the placeholder only for a
storyboard shot that does not have a generated clip.

## Current Behavior and Root Cause

The Video agent already persists one MP4 path per storyboard shot in
`VideoOutput.clips`. The details response includes that metadata, but the backend
exposes only the final edited MP4. `ContactSheet` therefore renders
`IdleArtwork` unconditionally and uses clip metadata only to label a shot as
`Rendered`.

This is an intentionally implemented placeholder and an incomplete product
feature, not a Wan generation failure.

## Backend Contract

Add:

```text
GET /result/{job_id}/clips/{shot_number}
```

The endpoint will:

1. Return `404 Job not found` when the job is not in the job store.
2. Load the persisted pipeline context and return `404 Job context not found`
   when it is absent.
3. Read the successful Video agent result and validate it as `VideoOutput`.
4. Select the clip whose `shot_number` exactly matches the positive route value.
5. Return `404 Video clip not found` when no result or matching clip exists.
6. Return `404 Video clip file not found` when the stored path is no longer a
   file.
7. Return the file through `FileResponse` with `video/mp4` and a stable filename
   such as `shot-01.mp4`.

The endpoint does not require the overall job to be completed. A clip that was
successfully persisted remains viewable when a later Voice or Editor stage
fails. The route exposes only a path selected from the persisted Video result;
it never accepts a caller-supplied filesystem path and never mounts the full
`outputs/` directory publicly.

## Frontend Contract

Add a same-origin API helper:

```text
clipVideoUrl(jobId, shotNumber)
  -> /result/{encoded job id}/clips/{positive shot number}
```

`ContactSheet` will join storyboard shots to Video clips by `shot_number` and
render every storyboard shot in storyboard order. The existing four-shot slice
will be removed.

For a rendered clip, the media area will contain:

```html
<video controls preload="metadata" playsinline>
  <source src="..." type="video/mp4">
</video>
```

The video will not use `autoPlay` or begin playback from hover. Users explicitly
click the native controls. `preload="metadata"` allows duration and seek controls
without eagerly downloading every full clip.

For a shot with no matching clip, the card retains `IdleArtwork` and the status
text `Planned`. Rendered cards continue to display the shot number, visual
prompt, camera, duration, and `Rendered` status.

The video element will fill the existing contact-sheet media region, use
`object-fit: cover`, retain the shot-number overlay, and use a black background.
The layout and typography outside the media area remain unchanged.

## Data Flow

```text
JobDetailsResponse
  -> storyboard shots + video clip metadata
  -> ContactSheet joins by shot_number
  -> rendered card builds same-origin clip URL
  -> browser requests /result/{job_id}/clips/{shot_number}
  -> FastAPI loads persisted VideoOutput
  -> FileResponse streams the stored Wan MP4
```

## Error Handling

- Planned shots without clips show the existing artwork rather than a broken
  media element.
- A missing file discovered only during playback produces the browser's normal
  video failure state; the surrounding shot metadata remains visible.
- The backend returns stable, non-sensitive error details and never includes
  arbitrary host paths in an error response.
- One broken clip does not prevent other contact-sheet clips or the final MP4
  from loading.

## Testing

Backend route tests will cover:

- A known job and shot streams exact MP4 bytes with a video content type.
- An unknown job returns `404`.
- A missing pipeline context returns `404`.
- A context without Video output returns `404`.
- An unknown shot number returns `404`.
- A stored clip whose file is missing returns `404`.

Frontend tests will cover:

- The URL helper encodes job IDs and formats shot numbers.
- Every storyboard shot is rendered, including more than four shots.
- A matched Video clip renders a `<video>` with controls,
  `preload="metadata"`, and the correct source URL.
- The video does not autoplay.
- An unmatched shot renders `IdleArtwork` and is labeled `Planned`.

The existing Python and frontend suites must remain quota-free and must not call
Alibaba Cloud APIs.

## Acceptance Criteria

- Completed contact-sheet cards show the actual generated shot videos instead
  of repeated cube artwork.
- Playback starts only when the user uses the video controls.
- All storyboard shots are displayed.
- Final-video playback and download remain unchanged.
- Only intended clip files are publicly retrievable.
- Backend and frontend regression suites pass without paid provider calls.
