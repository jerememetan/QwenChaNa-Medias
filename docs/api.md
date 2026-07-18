# API Reference

## `POST /generate`

Accepts `{"prompt": "..."}` and returns `202` with a `job_id`. The current MVP
runs its seven agents synchronously before returning. Prompt length must be
1–5000 non-whitespace characters.

## `GET /status/{job_id}`

Returns job status (`pending`, `running`, `completed`, or `failed`), current or
failed agent, and persisted error text. Unknown jobs return `404`.

## `GET /result/{job_id}`

For a completed job, returns artifact metadata, exact `output_path`, and:

```json
{"download_url": "/result/{job_id}/download"}
```

Incomplete jobs return `409`. A completed context without an Editor result
returns `404`.

## `GET /result/{job_id}/download`

Returns `final_video.mp4` as `video/mp4`. Missing files return `404`.

## `POST /resume/{job_id}`

Loads persisted context, skips successful agents, executes remaining agents,
and updates job status. Running or completed jobs return `409`; an app created
without configured agents returns `503`.

## `GET /health`

Returns `{"status": "ok"}`.
