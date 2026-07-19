# Alibaba ECS Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package QwenChaNa Medias for a reproducible single-instance Alibaba ECS deployment, publish it safely through Nginx, document operations and proof, and add a submission-ready architecture diagram.

**Architecture:** A multi-stage Docker image builds the React frontend and runs the FastAPI application as one non-root process with one Uvicorn worker. Docker Compose runs that image behind an Nginx container on the existing Singapore ECS instance, while a host bind mount persists generated media and a checked-in Mermaid diagram documents the browser, ECS, agent, Model Studio, and storage boundaries.

**Tech Stack:** Docker, Docker Compose, Nginx, Python 3.12, FastAPI, Uvicorn, Node.js 22, React/Vite, Mermaid, pytest, Alibaba Cloud ECS, Alibaba Cloud Model Studio

---

## File Map

- Create `.dockerignore`: keep secrets, generated media, caches, and local-only assets out of Docker build context.
- Create `Dockerfile`: build the frontend and create the non-root FastAPI runtime image.
- Create `compose.yaml`: run the app and Nginx with health checks and persistent output storage.
- Create `deploy/nginx.conf`: proxy the public HTTP endpoint to the private app service with long media-generation timeouts.
- Create `tests/test_deployment/__init__.py`: mark the deployment-contract test package.
- Create `tests/test_deployment/test_image_contract.py`: verify the image excludes secrets and runs the application safely.
- Create `tests/test_deployment/test_proxy_contract.py`: verify only Nginx publishes a host port and generation timeouts are configured.
- Create `tests/test_deployment/test_architecture_contract.py`: verify the required architecture participants and rendered asset exist.
- Create `docs/architecture.mmd`: canonical Mermaid source for the architecture diagram.
- Create `docs/assets/architecture-diagram.svg`: rendered diagram for README and submission use.
- Replace `docs/architecture.md`: explain runtime boundaries and embed the rendered diagram.
- Replace `docs/deployment.md`: provide the Ubuntu 22.04 ECS deployment, update, rollback, verification, and shutdown runbook.
- Modify `README.md`: identify the AI Showrunner track and link the public deployment, diagram, deployment proof, and Alibaba API code.

### Task 1: Build a safe application image

**Files:**

- Create: `tests/test_deployment/__init__.py`
- Create: `tests/test_deployment/test_image_contract.py`
- Create: `.dockerignore`
- Create: `Dockerfile`

- [ ] **Step 1: Write the failing image-contract tests**

Create `tests/test_deployment/__init__.py` as an empty file.

Create `tests/test_deployment/test_image_contract.py`:

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read_repo_file(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_dockerfile_builds_frontend_and_runs_one_app_worker() -> None:
    dockerfile = read_repo_file("Dockerfile")

    assert "npm ci" in dockerfile
    assert "npm run build" in dockerfile
    assert "COPY --from=frontend-build" in dockerfile
    assert 'USER app' in dockerfile
    assert '"backend.main:app"' in dockerfile
    assert '"--workers", "1"' in dockerfile
    assert "HEALTHCHECK" in dockerfile


def test_dockerignore_excludes_secrets_and_generated_files() -> None:
    ignored = set(read_repo_file(".dockerignore").splitlines())

    assert ".env" in ignored
    assert ".env.*" in ignored
    assert "outputs/" in ignored
    assert ".git/" in ignored
    assert "venv/" in ignored
    assert "frontend/node_modules/" in ignored
```

- [ ] **Step 2: Run the image-contract tests and verify they fail**

Run:

```powershell
venv\Scripts\python.exe -m pytest tests/test_deployment/test_image_contract.py -v
```

Expected: two failures because `Dockerfile` and `.dockerignore` do not exist.

- [ ] **Step 3: Add the minimal Docker build context exclusions**

Create `.dockerignore`:

```text
.git/
.github/
.env
.env.*
.pytest_cache/
.coverage
htmlcov/
__pycache__/
*.py[cod]
.venv/
venv/
ENV/
outputs/
frontend/node_modules/
frontend/dist/
Figma_Reference_UI/
docs/superpowers/
*.log
```

- [ ] **Step 4: Add the multi-stage application image**

Create `Dockerfile`:

```dockerfile
FROM node:22-bookworm-slim AS frontend-build

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home --shell /usr/sbin/nologin app

COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

COPY agents/ ./agents/
COPY backend/ ./backend/
COPY models/ ./models/
COPY storage/ ./storage/
COPY tools/ ./tools/
COPY workflow/ ./workflow/
COPY --from=frontend-build /build/frontend/dist ./frontend/dist

RUN mkdir -p /app/outputs \
    && chown -R app:app /app

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"]

CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

- [ ] **Step 5: Run the image-contract tests and verify they pass**

Run:

```powershell
venv\Scripts\python.exe -m pytest tests/test_deployment/test_image_contract.py -v
```

Expected: `2 passed`.

- [ ] **Step 6: Build the application image locally**

Run:

```powershell
docker build --tag qwenchana-medias:test .
```

Expected: the frontend production build succeeds and Docker creates
`qwenchana-medias:test`.

- [ ] **Step 7: Commit the image packaging**

```bash
git add .dockerignore Dockerfile tests/test_deployment/__init__.py tests/test_deployment/test_image_contract.py
git commit -m "build: package app for container deployment"
```

### Task 2: Add the Nginx and Compose runtime

**Files:**

- Create: `tests/test_deployment/test_proxy_contract.py`
- Create: `compose.yaml`
- Create: `deploy/nginx.conf`

- [ ] **Step 1: Write the failing proxy-contract tests**

Create `tests/test_deployment/test_proxy_contract.py`:

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read_repo_file(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_compose_keeps_app_private_and_persists_outputs() -> None:
    compose = read_repo_file("compose.yaml")

    assert "./outputs:/app/outputs" in compose
    assert "./.env:/app/.env:ro" not in compose
    assert '"8000:8000"' not in compose
    assert '"80:80"' in compose
    assert "condition: service_healthy" in compose
    assert "restart: unless-stopped" in compose


def test_nginx_allows_long_generation_requests() -> None:
    nginx = read_repo_file("deploy/nginx.conf")

    assert "server app:8000" in nginx
    assert "proxy_read_timeout 3600s" in nginx
    assert "proxy_send_timeout 3600s" in nginx
    assert "proxy_buffering off" in nginx
    assert "proxy_set_header X-Forwarded-For" in nginx
```

- [ ] **Step 2: Run the proxy-contract tests and verify they fail**

Run:

```powershell
venv\Scripts\python.exe -m pytest tests/test_deployment/test_proxy_contract.py -v
```

Expected: two failures because `compose.yaml` and `deploy/nginx.conf` do not
exist.

- [ ] **Step 3: Add the reverse-proxy configuration**

Create `deploy/nginx.conf`:

```nginx
events {}

http {
    upstream qwenchana_app {
        server app:8000;
    }

    server {
        listen 80 default_server;
        server_name _;

        location / {
            proxy_pass http://qwenchana_app;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_connect_timeout 60s;
            proxy_send_timeout 3600s;
            proxy_read_timeout 3600s;
            proxy_buffering off;
        }
    }
}
```

- [ ] **Step 4: Add the Compose runtime**

Create `compose.yaml`:

```yaml
name: qwenchana-medias

services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
    env_file:
      - .env
    volumes:
      - ./outputs:/app/outputs
    expose:
      - "8000"
    init: true
    restart: unless-stopped
    healthcheck:
      test:
        - CMD
        - python
        - -c
        - import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)
      interval: 30s
      timeout: 5s
      start_period: 20s
      retries: 3

  nginx:
    image: nginx:1.28-alpine
    depends_on:
      app:
        condition: service_healthy
    ports:
      - "80:80"
    volumes:
      - ./deploy/nginx.conf:/etc/nginx/nginx.conf:ro
    restart: unless-stopped
```

- [ ] **Step 5: Run the proxy-contract tests and validate Compose**

Run:

```powershell
venv\Scripts\python.exe -m pytest tests/test_deployment/test_proxy_contract.py -v
docker compose config --quiet
```

Expected: `2 passed`; Compose exits with code `0` and prints no configuration or
secret values.

- [ ] **Step 6: Start the local stack and verify proxy health**

Run:

```powershell
New-Item -ItemType Directory -Force outputs | Out-Null
docker compose up --build --detach
docker compose ps
Invoke-RestMethod http://127.0.0.1/health
```

Expected: both services are running, `app` is healthy, and the response is:

```text
status
------
ok
```

- [ ] **Step 7: Stop the local stack without deleting outputs**

Run:

```powershell
docker compose down
```

Expected: containers and the private network are removed; `outputs/` remains.

- [ ] **Step 8: Commit the runtime topology**

```bash
git add compose.yaml deploy/nginx.conf tests/test_deployment/test_proxy_contract.py
git commit -m "build: add ECS container runtime"
```

### Task 3: Generate the hackathon architecture diagram

**Files:**

- Create: `tests/test_deployment/test_architecture_contract.py`
- Create: `docs/architecture.mmd`
- Create: `docs/assets/architecture-diagram.svg`
- Replace: `docs/architecture.md`

- [ ] **Step 1: Write the failing architecture-contract test**

Create `tests/test_deployment/test_architecture_contract.py`:

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_architecture_diagram_covers_runtime_and_model_boundaries() -> None:
    source = (ROOT / "docs" / "architecture.mmd").read_text(encoding="utf-8")
    page = (ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
    svg = (ROOT / "docs" / "assets" / "architecture-diagram.svg")

    for label in (
        "Judge / Creator",
        "Alibaba Cloud ECS",
        "Nginx",
        "FastAPI + React",
        "LangGraph Showrunner",
        "Qwen",
        "Wan",
        "CosyVoice",
        "Persistent Outputs",
    ):
        assert label in source

    assert "architecture-diagram.svg" in page
    assert svg.is_file()
    assert "<svg" in svg.read_text(encoding="utf-8")[:1000]
```

- [ ] **Step 2: Run the architecture-contract test and verify it fails**

Run:

```powershell
venv\Scripts\python.exe -m pytest tests/test_deployment/test_architecture_contract.py -v
```

Expected: failure because the Mermaid source and SVG do not exist and the
architecture page is still a placeholder.

- [ ] **Step 3: Add the canonical Mermaid diagram source**

Create `docs/architecture.mmd`:

```mermaid
flowchart LR
    user["Judge / Creator"]

    subgraph ecs["Alibaba Cloud ECS · Singapore"]
        nginx["Nginx<br/>Public HTTP :80"]
        web["FastAPI + React<br/>Single Uvicorn worker"]
        graph["LangGraph Showrunner"]

        subgraph agents["Seven-Agent Production Team"]
            director["Director"]
            research["Research"]
            script["Script"]
            storyboard["Storyboard"]
            video["Video"]
            voice["Voice"]
            editor["Editor + FFmpeg"]
        end

        outputs[("Persistent Outputs<br/>JSON · Clips · Audio · MP4")]
    end

    subgraph modelstudio["Alibaba Cloud Model Studio · Singapore"]
        qwen["Qwen<br/>Reasoning + Narrative"]
        wan["Wan<br/>Video Generation"]
        cosy["CosyVoice<br/>Narration"]
    end

    user -->|"Prompt / Review / Download"| nginx
    nginx -->|"Private Docker network"| web
    web --> graph
    graph --> director --> research --> script --> storyboard
    storyboard --> video
    storyboard --> voice
    video --> editor
    voice --> editor
    director -.-> qwen
    research -.-> qwen
    script -.-> qwen
    storyboard -.-> qwen
    video -.-> wan
    voice -.-> cosy
    editor --> outputs
    outputs -->|"Final MP4 + artifacts"| web

    classDef person fill:#111827,color:#ffffff,stroke:#111827,stroke-width:2px;
    classDef edge fill:#fff7ed,color:#9a3412,stroke:#f97316,stroke-width:2px;
    classDef app fill:#eff6ff,color:#1e3a8a,stroke:#3b82f6,stroke-width:2px;
    classDef agent fill:#f5f3ff,color:#5b21b6,stroke:#8b5cf6;
    classDef model fill:#ecfdf5,color:#065f46,stroke:#10b981,stroke-width:2px;
    classDef data fill:#fefce8,color:#854d0e,stroke:#eab308,stroke-width:2px;

    class user person;
    class nginx edge;
    class web,graph app;
    class director,research,script,storyboard,video,voice,editor agent;
    class qwen,wan,cosy model;
    class outputs data;
```

- [ ] **Step 4: Replace the architecture page with the diagram and explanation**

Replace `docs/architecture.md` with:

```markdown
# Architecture

QwenChaNa Medias is an AI showrunner that turns one prompt into a researched,
scripted, storyboarded, narrated, generated, and edited short-form video. The
public application runs on Alibaba Cloud ECS in Singapore; Qwen, Wan, and
CosyVoice are invoked through Alibaba Cloud Model Studio.

![QwenChaNa Medias architecture](assets/architecture-diagram.svg)

The editable Mermaid source is available in
[`architecture.mmd`](architecture.mmd).

## Runtime boundaries

- Nginx is the only publicly exposed container and forwards HTTP requests to
  FastAPI over a private Docker network.
- FastAPI serves the compiled React workspace and runs one LangGraph workflow
  worker because generation is synchronous and job state is process-local.
- The Director, Research, Script, and Storyboard agents use Qwen for structured
  narrative work.
- The Video and Voice agents orchestrate Wan and CosyVoice concurrently after
  storyboarding.
- The Editor assembles generated assets with bundled FFmpeg.
- A host-mounted `outputs/` directory persists workflow JSON, clips, narration,
  and final MP4 files across container recreation.

## Detailed design references

- [Agent contracts](agent-contracts.md)
- [API reference](api.md)
- [Data model](data-model-design.md)
- [Alibaba ECS deployment](deployment.md)
```

- [ ] **Step 5: Render the SVG asset from Mermaid source**

Run from the repository root:

```powershell
New-Item -ItemType Directory -Force docs\assets | Out-Null
npx --yes @mermaid-js/mermaid-cli -i docs/architecture.mmd -o docs/assets/architecture-diagram.svg -b transparent
```

Expected: Mermaid exits successfully and creates a non-empty
`docs/assets/architecture-diagram.svg`.

- [ ] **Step 6: Run the architecture-contract test**

Run:

```powershell
venv\Scripts\python.exe -m pytest tests/test_deployment/test_architecture_contract.py -v
```

Expected: `1 passed`.

- [ ] **Step 7: Visually inspect the SVG**

Open `docs/assets/architecture-diagram.svg` and verify:

- All labels fit within their nodes.
- The ECS and Model Studio boundaries are visually distinct.
- Both Video and Voice converge on Editor.
- The final-output path returns to FastAPI and the user.
- The diagram remains legible at README width.

If text clips, increase node label line breaks in `docs/architecture.mmd`, rerun
the exact render command, and inspect again.

- [ ] **Step 8: Commit the architecture diagram**

```bash
git add docs/architecture.md docs/architecture.mmd docs/assets/architecture-diagram.svg tests/test_deployment/test_architecture_contract.py
git commit -m "docs: add Alibaba showrunner architecture diagram"
```

### Task 4: Write the ECS operations runbook

**Files:**

- Replace: `docs/deployment.md`

- [ ] **Step 1: Replace the placeholder with the production runbook**

Replace `docs/deployment.md` with the following content:

````markdown
# Deploy to Alibaba Cloud ECS

The judged deployment runs on one Ubuntu 22.04 ECS instance in Alibaba Cloud's
Singapore region. Docker Compose starts the FastAPI/React application behind
Nginx and persists generated media in the host `outputs/` directory.

## Prerequisites

- Alibaba Cloud ECS running Ubuntu 22.04 in Singapore
- Public IPv4 address
- Security-group ingress for TCP 80 from `0.0.0.0/0`
- SSH through Alibaba Workbench or TCP 22 restricted to the operator's IP
- Alibaba Cloud Model Studio API keys for Qwen, Wan, and CosyVoice
- At least 2 vCPU, 4 GiB RAM, and 60 GiB disk

Never commit `.env`, API keys, SSH private keys, or generated `outputs/`.

## 1. Connect

Use ECS Workbench with the `ecs-user` account, or connect from PowerShell:

```powershell
ssh -i "C:\path\to\key.pem" ecs-user@47.237.255.203
```

## 2. Install Docker Engine and Git

Run on the ECS instance:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

Log out and reconnect so the Docker group membership takes effect. Verify:

```bash
docker --version
docker compose version
```

## 3. Clone the public repository

```bash
git clone https://github.com/jerememetan/QwenChaNa-Medias.git
cd QwenChaNa-Medias
git checkout jereme-phase2
```

Use the final submission branch instead if the deployment changes have already
been merged.

## 4. Configure Model Studio

```bash
cp .env.example .env
nano .env
```

Set the real Singapore Model Studio values. Keep these deployment settings:

```dotenv
LLM_PROVIDER=alibaba_cloud_model_studio
STORAGE_BACKEND=local
STORAGE_OUTPUT_DIR=/app/outputs
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
FALLBACK_STUBS=false
```

The Qwen, Wan, and CosyVoice model names, API keys, and Singapore endpoints must
match the models activated in the account. Then restrict the file:

```bash
chmod 600 .env
```

## 5. Prepare persistent output storage

The container runs as UID and GID `10001`:

```bash
mkdir -p outputs
sudo chown -R 10001:10001 outputs
```

## 6. Build and start

```bash
docker compose build
docker compose up -d
docker compose ps
```

Wait until `app` reports `healthy` and `nginx` reports `running`.

## 7. Verify

From ECS:

```bash
curl --fail http://127.0.0.1/health
```

Expected:

```json
{"status":"ok"}
```

From another computer, open:

- `http://47.237.255.203`
- `http://47.237.255.203/health`

If the local health check works but the public URL does not, verify that the ECS
security group allows inbound TCP 80.

## Logs and diagnostics

```bash
docker compose ps
docker compose logs --tail=200 app
docker compose logs --tail=100 nginx
docker compose logs --follow app
```

Do not paste logs publicly until checking that they contain no sensitive prompt
or provider information.

## Deploy an update

Do not update while a generation is active.

```bash
git fetch origin
git pull --ff-only
docker compose build app
docker compose up -d
docker compose ps
curl --fail http://127.0.0.1/health
```

The bind-mounted `outputs/` directory is not replaced.

## Roll back

Choose the last known-good commit from `git log --oneline`:

```bash
git switch --detach COMMIT_SHA
docker compose build app
docker compose up -d
curl --fail http://127.0.0.1/health
```

After diagnosing the problem, switch back to the deployment branch before the
next update.

## Stop or remove the deployment

Stop containers while retaining them:

```bash
docker compose stop
```

Remove containers and the private network while retaining host outputs:

```bash
docker compose down
```

Never run `docker compose down --volumes` as a cleanup shortcut. Although this
deployment uses a host bind mount, destructive cleanup commands make operational
mistakes more likely.

Stopping a pay-as-you-go ECS instance in standard mode may continue billing.
Use economical mode when appropriate, or release the instance only after backing
up any output that must be retained.

## Deployment proof

- Public health endpoint: `http://47.237.255.203/health`
- ECS runtime definition: [`../compose.yaml`](../compose.yaml)
- Alibaba model construction: [`../backend/factory.py`](../backend/factory.py)
- Qwen Model Studio client: [`../tools/llm.py`](../tools/llm.py)
- Wan Model Studio client: [`../tools/video_gen.py`](../tools/video_gen.py)
- CosyVoice Model Studio client: [`../tools/tts.py`](../tools/tts.py)
````

- [ ] **Step 2: Check documentation for placeholders and accidental secrets**

Run:

```powershell
rg -n "TO[D]O|TB[D]|API_KEY=[^.]|sk-|<YOUR" docs/deployment.md
```

Expected: no matches.

- [ ] **Step 3: Commit the deployment runbook**

```bash
git add docs/deployment.md
git commit -m "docs: add Alibaba ECS operations runbook"
```

### Task 5: Surface track, architecture, deployment, and proof in README

**Files:**

- Modify: `README.md`

- [ ] **Step 1: Add the submission identity below the README introduction**

After the introductory paragraph, add:

```markdown
## Qwen Hackathon Submission

**Track:** AI Showrunner

QwenChaNa Medias autonomously handles the short-drama production pipeline:
creative direction, web research, scriptwriting, storyboarding, Wan video
generation, CosyVoice narration, FFmpeg editing, progress inspection, and failed
job recovery.

- **Live deployment:** [http://47.237.255.203](http://47.237.255.203)
- **Health check:** [http://47.237.255.203/health](http://47.237.255.203/health)
- **Architecture diagram:** [docs/architecture.md](docs/architecture.md)
- **Alibaba ECS deployment:** [docs/deployment.md](docs/deployment.md)
- **Alibaba Cloud API proof:** [backend/factory.py](backend/factory.py)
```

- [ ] **Step 2: Replace the README ASCII architecture block with the rendered diagram**

Keep the existing `## Architecture` heading and replace its current explanatory
line and text diagram with:

```markdown
The production deployment connects a seven-agent LangGraph showrunner on Alibaba
Cloud ECS to Qwen, Wan, and CosyVoice in Alibaba Cloud Model Studio.

![QwenChaNa Medias architecture](docs/assets/architecture-diagram.svg)

See [docs/architecture.md](docs/architecture.md) for system boundaries and data
flow.
```

- [ ] **Step 3: Verify README links target tracked files**

Run:

```powershell
Test-Path docs\architecture.md
Test-Path docs\assets\architecture-diagram.svg
Test-Path docs\deployment.md
Test-Path backend\factory.py
```

Expected: four `True` values.

- [ ] **Step 4: Commit the submission-facing README**

```bash
git add README.md
git commit -m "docs: surface AI Showrunner deployment proof"
```

### Task 6: Run complete local verification

**Files:** none

- [ ] **Step 1: Run the quota-free Python suite**

Run:

```powershell
venv\Scripts\python.exe -m pytest tests -v
```

Expected: all tests pass with no Alibaba Cloud API calls.

- [ ] **Step 2: Run frontend tests**

Run:

```powershell
npm --prefix frontend test
```

Expected: all Vitest suites pass.

- [ ] **Step 3: Run the production frontend build**

Run:

```powershell
npm --prefix frontend run build
```

Expected: TypeScript validation and Vite production build pass.

- [ ] **Step 4: Check repository whitespace and secret exclusions**

Run:

```powershell
git diff --check
git status --short
git check-ignore .env outputs frontend/node_modules
```

Expected: no whitespace errors; only intended files are changed; `.env`,
`outputs`, and `frontend/node_modules` are ignored.

- [ ] **Step 5: Validate and smoke-test the container stack**

Run:

```powershell
docker compose config --quiet
docker compose up --build --detach
docker compose ps
Invoke-RestMethod http://127.0.0.1/health
docker compose down
```

Expected: Compose validates, both services start, health returns `ok`, and the
stack stops without deleting `outputs/`.

### Task 7: Deploy to the existing Alibaba ECS instance

**Files:** none on the local workstation; ECS receives the public repository and
a server-only `.env`.

- [ ] **Step 1: Push all implementation commits to the public deployment branch**

Run locally:

```powershell
git push origin jereme-phase2
```

Expected: the remote branch contains the Dockerfile, Compose runtime, diagram,
runbook, and README proof links.

- [ ] **Step 2: Install Docker and clone the repository on ECS**

Follow sections 1 through 3 of `docs/deployment.md` in Alibaba Workbench.

Expected: `docker --version`, `docker compose version`, and `git status` succeed
on Ubuntu 22.04.

- [ ] **Step 3: Create the ECS-only environment file**

Follow section 4 of `docs/deployment.md`; transfer values from the working local
`.env` manually through the private Workbench session.

Expected: `.env` has mode `600`, contains real Singapore Model Studio values,
and remains untracked by Git.

- [ ] **Step 4: Build and start the ECS stack**

Run on ECS:

```bash
mkdir -p outputs
sudo chown -R 10001:10001 outputs
docker compose build
docker compose up -d
docker compose ps
```

Expected: `app` becomes healthy and `nginx` is running.

- [ ] **Step 5: Verify the local and public health endpoints**

Run on ECS:

```bash
curl --fail http://127.0.0.1/health
curl --fail http://47.237.255.203/health
```

Run from Windows:

```powershell
Invoke-RestMethod http://47.237.255.203/health
```

Expected: every request returns `{"status":"ok"}` or the PowerShell object
equivalent.

- [ ] **Step 6: Verify the browser workspace**

Open `http://47.237.255.203` in a browser.

Expected: the QwenChaNa workspace loads without a Vite development server, and
browser network requests use the same public origin.

### Task 8: Run one intentional live production acceptance test

**Files:** runtime artifacts beneath ECS `outputs/`; these remain ignored by Git.

- [ ] **Step 1: Submit a short, bounded prompt**

Use the browser workspace with a concise prompt designed for the smallest
supported video duration, for example:

```text
Create a concise cinematic micro-drama about a night-shift radio host receiving
a call from their future self. Keep the story visually simple with one studio
location and a clear emotional turn.
```

Expected: the request is accepted and the production ledger shows the seven
agent stages.

- [ ] **Step 2: Monitor the server without interrupting generation**

Run in a separate Workbench terminal:

```bash
cd QwenChaNa-Medias
docker compose logs --follow app
```

Expected: Qwen, Wan, and CosyVoice stages complete without credential, quota,
timeout, or permission errors. Stop log following with `Ctrl+C`; do not stop the
container.

- [ ] **Step 3: Verify the final MP4 and persisted artifacts**

After completion, run:

```bash
find outputs -type f -maxdepth 5 | sort
```

Expected: the job directory contains persisted agent JSON, media assets, and an
editor final MP4. The browser can play or download the final video.

- [ ] **Step 4: Recreate the app container and verify persistence**

Only after the generation has completed, run:

```bash
docker compose up -d --force-recreate app
docker compose ps
find outputs -type f -maxdepth 5 | sort
```

Expected: the app returns to healthy state and the generated files remain on the
ECS host. The old in-memory job index is expected to be unavailable after this
restart; the files themselves must remain.

- [ ] **Step 5: Capture submission evidence**

Record or screenshot:

- The public browser workspace at `http://47.237.255.203`.
- A completed generated video.
- The public `/health` response.
- ECS console details showing the Singapore instance, while hiding account IDs
  and credentials.
- The repository architecture diagram and Alibaba API proof links.

Expected: evidence demonstrates both a functioning AI Showrunner and an Alibaba
Cloud-hosted backend without revealing secrets.

## Plan Self-Review

- Spec coverage: container build, reverse proxy, persistent outputs, secret
  handling, health checks, ECS runbook, diagram, proof links, local verification,
  public verification, live model test, and persistence test are each assigned to
  an implementation task.
- Placeholder scan: the plan contains no implementation placeholders. The
  rollback token `COMMIT_SHA` is an explicit operator-selected argument, not
  missing design work.
- Type and naming consistency: Compose service names are `app` and `nginx`; Nginx
  resolves `app:8000`; the container user is UID/GID `10001`; the persistent path
  is consistently `./outputs:/app/outputs`; architecture source and output paths
  are consistently `docs/architecture.mmd` and
  `docs/assets/architecture-diagram.svg`.
