# Alibaba ECS Deployment Design

## Goal

Deploy the completed QwenChaNa Medias application to the existing Alibaba Cloud
ECS instance at `47.237.255.203` in the Singapore region. The deployment must be
publicly testable, reproducible from repository files, safe for API secrets, and
suitable as hackathon proof that the backend runs on Alibaba Cloud and invokes
Alibaba Cloud Model Studio services.

## Scope

This phase includes:

- Packaging the React frontend and FastAPI backend as one application image.
- Running the application and an Nginx reverse proxy with Docker Compose.
- Persisting generated artifacts on the ECS system disk.
- Configuring a public HTTP endpoint and application health check.
- Documenting initial provisioning, deployment, verification, updates, rollback,
  log access, and shutdown.
- Identifying stable repository links for Alibaba deployment and API proof.

This phase does not include:

- A custom domain, DNS, or TLS certificate.
- Horizontal scaling or multiple Uvicorn workers.
- Replacing local artifact storage with OSS.
- Replacing the in-memory job store with a database.
- Refactoring synchronous generation into a background queue.
- Continuous deployment from GitHub.

Those improvements remain optional follow-up work after the first judged
deployment is healthy.

## Current Constraints

`POST /generate` runs the full multi-agent pipeline synchronously. Job records
are held in process memory, while workflow context and media artifacts are
written beneath `outputs/`. The application therefore requires one Uvicorn
worker, extended reverse-proxy timeouts, persistent local storage, and no
restart while a generation is active.

Qwen language generation, Wan video generation, and CosyVoice narration run in
Alibaba Cloud Model Studio. The ECS instance does not require a GPU because it
orchestrates remote model calls and performs only local FFmpeg assembly.

## Architecture

```text
Judge browser
    |
    | HTTP :80
    v
Alibaba Cloud ECS, Singapore (47.237.255.203)
    |
    +-- Nginx container
    |      |
    |      | private Docker network :8000
    |      v
    +-- QwenChaNa app container
           +-- FastAPI API
           +-- compiled React frontend
           +-- seven-agent LangGraph pipeline
           +-- bundled FFmpeg
           |
           +--> Qwen through Alibaba Cloud Model Studio
           +--> Wan through Alibaba Cloud Model Studio
           +--> CosyVoice through Alibaba Cloud Model Studio
           |
           +--> /app/outputs
                    |
                    v
               ECS host ./outputs bind mount
```

Only Nginx publishes a host port. FastAPI port `8000` remains on the private
Compose network.

## Repository Components

### Application image

A root `Dockerfile` will use a multi-stage build:

1. A Node build stage installs the locked frontend dependencies and creates
   `frontend/dist`.
2. A Python runtime stage installs the pinned Python requirements, copies the
   backend and compiled frontend, creates a non-root runtime user, and starts a
   single Uvicorn worker on `0.0.0.0:8000`.

The image will include no credentials and no generated output.

### Compose topology

A root `compose.yaml` will define:

- `app`: builds the repository image, reads application variables from the
  server-only `.env`, bind-mounts `./outputs` at `/app/outputs`, exposes port
  `8000` only to the Compose network, has an HTTP health check, and restarts
  unless explicitly stopped.
- `nginx`: uses the official stable Nginx image, publishes host port `80`, reads
  the checked-in proxy configuration, waits for the app health check, and
  restarts unless explicitly stopped.

The services will share one private, project-scoped Docker network.

### Reverse proxy

`deploy/nginx.conf` will:

- Forward all browser and API requests to `app:8000`.
- Preserve forwarding headers.
- Disable response buffering for long-running generation responses.
- Allow generation, read, send, and connection timeouts long enough for a full
  Wan-backed production run.
- Serve a clear gateway error if the app is unavailable.

### Build context

`.dockerignore` will exclude Git metadata, virtual environments, test caches,
local secrets, generated media, frontend dependencies, and local design assets.
This keeps builds smaller and prevents accidental credential inclusion.

### Deployment documentation

`docs/deployment.md` will become the authoritative Ubuntu 22.04 ECS runbook. It
will include Docker installation, repository checkout, `.env` creation,
permissions for the output directory, image build, startup, health verification,
log inspection, safe updates, rollback, and cost-aware shutdown.

The runbook will record the Alibaba region and public endpoint but will not
contain credentials or account identifiers.

## Configuration and Secrets

The ECS host will contain a `.env` file copied from `.env.example` and populated
with the Model Studio credentials and Singapore endpoints. The file remains
excluded by `.gitignore` and is passed to the app container at runtime.

Required production settings are:

- `LLM_PROVIDER=alibaba_cloud_model_studio`
- A valid `LLM_API_KEY`
- The Singapore-compatible LLM base URL and model
- A valid `VOICE_API_KEY`, Singapore CosyVoice WebSocket endpoint, model, and
  voice
- A valid `VIDEO_API_KEY` and Wan model
- `STORAGE_BACKEND=local`
- `STORAGE_OUTPUT_DIR=/app/outputs`
- `SERVER_HOST=0.0.0.0`
- `SERVER_PORT=8000`
- `FALLBACK_STUBS=false`

No secret will be passed as a Docker build argument, copied into an image, added
to documentation, printed during deployment, or committed to Git.

## Request and Artifact Flow

1. The judge opens `http://47.237.255.203`.
2. Nginx proxies the request to FastAPI.
3. FastAPI serves the compiled React application.
4. The browser submits a prompt to `POST /generate`.
5. The single app process runs the LangGraph agent workflow.
6. Agents call Alibaba Cloud Model Studio through the existing service wrappers.
7. JSON state, clips, narration, and the final MP4 are written to
   `/app/outputs/{job_id}`.
8. The bind mount persists those files under `./outputs/{job_id}` on ECS.
9. The result endpoint streams the final MP4 through Nginx to the browser.

## Failure Handling and Operations

- Docker restarts a crashed service automatically.
- The app health check calls `/health`; Nginx starts only after the app becomes
  healthy.
- A failed model call remains visible through the existing job details and
  resume endpoints.
- Generated artifacts survive container replacement because they live on the
  host bind mount.
- A host restart restores both services through Docker's restart policy.
- App restarts lose the in-memory job index. Operators must avoid deploying
  during a generation and retain output artifacts for debugging.
- Deployment logs are available through `docker compose logs` without enabling
  a separate logging service.
- Rollback uses a known Git commit followed by an image rebuild and Compose
  recreation. The output bind mount is not deleted during rollback.

## Security and Cost Controls

- ECS security-group ingress permits public TCP 80 and restricts SSH TCP 22 to
  the owner's IP or Alibaba Workbench.
- Host port 8000 is not published.
- The app image runs as a non-root user.
- Secrets exist only in the host `.env` file with owner-only permissions.
- The public service intentionally provides no user authentication in this
  phase so judges can test it. The owner must monitor Model Studio usage and ECS
  outbound traffic while the endpoint is public.
- The instance should be stopped in economical mode or released only after the
  judging window. Releasing the instance permanently deletes its local outputs.

## Hackathon Deployment Proof

The submission will provide two complementary repository links:

1. The Compose or Docker deployment file, showing the backend packaging and
   runtime used on Alibaba ECS.
2. `tools/llm.py`, `tools/video_gen.py`, or `tools/tts.py`, showing concrete
   Alibaba Cloud Model Studio API integration.

The public `http://47.237.255.203/health` endpoint will demonstrate that the
deployed backend is reachable. The final README and submission description can
pair the public endpoint with the repository links without exposing Alibaba
credentials.

## Verification

Implementation is accepted when all of the following hold:

- The existing quota-free Python test suite passes.
- The existing frontend test suite and production build pass.
- `docker compose config` validates successfully without printing real secrets
  in recorded output.
- The application image builds successfully.
- Both Compose services report running and the app reports healthy on ECS.
- `http://47.237.255.203/health` returns `{"status":"ok"}`.
- `http://47.237.255.203` loads the React workspace.
- One intentional live prompt completes through Qwen, Wan, and CosyVoice and
  produces a downloadable MP4 after deployment.
- Recreating the app container preserves the generated output directory.
- No secret or generated media is tracked by Git.

## Follow-up Path

After the first deployment succeeds, the next production-hardening steps are a
domain and HTTPS, authentication or submission-specific access control, OSS
artifact storage, a persistent job database, and an asynchronous worker queue.
They are deliberately excluded from this deployment to keep the hackathon path
small and testable.
