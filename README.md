# QwenChaNa Medias

AI-native short-form video generation platform. Transforms a text prompt into a fully produced MP4 video using a multi-agent pipeline.

## Quick Start

```bash
# 1. Clone and install
git clone <repo-url> && cd QwenChaNa-Medias
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env with your API keys

# 3. Build the demo workspace and run
npm --prefix frontend install
npm --prefix frontend run build
uvicorn backend.main:app --reload
```

Open `http://127.0.0.1:8000/` for the demo workspace. For two-terminal frontend
development, run FastAPI in one terminal and Vite in another:

```powershell
.\venv\Scripts\python.exe -m uvicorn backend.main:app --reload
npm --prefix frontend run dev
```

`imageio-ffmpeg` installs a bundled FFmpeg executable, so Windows users do not
need a separate FFmpeg installation.

## Final Output

Successful jobs produce:

```text
outputs/{job_id}/editor/final/final_video.mp4
```

- `GET /result/{job_id}` returns final artifact metadata.
- `GET /result/{job_id}/download` downloads the MP4.
- `GET /details/{job_id}` returns persisted outputs from all seven agents.
- `POST /resume/{job_id}` resumes a failed job from its first incomplete agent.

Run quota-free tests with:

```powershell
venv\Scripts\python.exe -m pytest tests/ -v
```

`run_test.py` calls live Alibaba models and consumes quota; use it only for an
intentional live smoke test.

## Architecture

See [docs/architecture.md](docs/architecture.md) for the full system design.

```
User Prompt → Director → Research → Script → Storyboard
                                            ├── Video Agent
                                            └── Voice Agent
                                                      ↓
                                                  Editor → Final MP4
```

## Project Structure

| Directory | Purpose |
|-----------|---------|
| `backend/` | FastAPI application, routes, config |
| `frontend/` | React/Vite demo workspace |
| `agents/` | Pipeline agents (Director, Research, Script, Storyboard, Video, Voice, Editor) |
| `tools/` | External service wrappers (LLM, TTS, video gen, FFmpeg) |
| `workflow/` | LangGraph orchestration, job context, and resume logic |
| `models/` | Pydantic schemas and data contracts |
| `storage/` | Artifact persistence (local disk, cloud) |
| `tests/` | Unit, integration, and end-to-end tests |
| `docs/` | Architecture, API reference, deployment guides |
| `outputs/` | Runtime artifacts (git-ignored) |
| `scripts/` | CLI helpers for local development |

## Documentation

- [Architecture](docs/architecture.md)
- [Agent Contracts](docs/agent-contracts.md)
- [API Reference](docs/api.md)
- [Deployment](docs/deployment.md)
- [Roadmap](docs/roadmap.md)
