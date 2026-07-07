# QwenChaNa Medias — Technical Lead Guidelines

These rules apply to every session that writes, reviews, or plans code in this repository.

---

## Core Principles

1. **Maintain clean architecture** — clear boundaries between layers. `backend/` owns HTTP, `agents/` owns agent logic, `tools/` owns external services, `workflow/` owns orchestration, `models/` owns data contracts, `storage/` owns persistence. No cross-layer imports.
2. **Avoid unnecessary complexity** — no premature abstraction, no over-engineering. Write the simplest code that satisfies the current requirement. YAGNI is the default.
3. **Prefer SOLID principles** — single responsibility, open for extension / closed for modification, depend on abstractions not concretions. Each agent, tool, and module should have one reason to change.
4. **Prefer modular design** — every component is independently testable and replaceable. Agents implement a common interface. Tools are swappable behind wrappers. Storage is behind an abstraction.
5. **Document everything** — docstrings on every public class and method. Comments explain *why*, not *what*. Keep `docs/` in sync with implementation.
6. **Never generate placeholder code** unless the user explicitly requests it. If you don't know the implementation, say so and leave it as a TODO with a clear description of what's needed.
7. **Explain architectural decisions** — when introducing a new module, pattern, or dependency, explain why it belongs where it is and what alternatives were considered.
8. **Think like a senior software engineer** — consider error paths, edge cases, backward compatibility, and the cost of future changes. Ask "what breaks when this changes?" before committing to a design.
9. **Optimize for maintainability over quick hacks** — readable names, small functions, explicit types. A working solution that's hard to understand or change is worse than a working solution that's easy to understand and change.

---

## Project Structure

```
backend/          FastAPI HTTP layer (routes, config, utils)
frontend/         Web UI (future — placeholder for now)
agents/           Pipeline agents (director, research, script, storyboard, video, voice, editor)
tools/            External service wrappers (llm, tts, video_gen, ffmpeg, web_search)
workflow/         Pipeline orchestration, job context, resume logic, LangGraph graph (future)
models/           All Pydantic data contracts and schemas
storage/          Artifact persistence abstraction (local, cloud)
tests/            Mirrors source structure. Unit, integration, and e2e tests.
docs/             Architecture, API reference, agent contracts, deployment, roadmap
outputs/          Runtime artifacts (git-ignored). outputs/{job_id}/{agent}/...
scripts/          CLI helpers for local development
```

### Import Rules

| Layer | May Import From | Must NOT Import From |
|-------|----------------|---------------------|
| `backend/api/` | `models/`, `workflow/`, `storage/`, `backend/utils/` | `agents/`, `tools/` |
| `backend/utils/` | `models/` | `agents/`, `tools/`, `workflow/` |
| `agents/` | `models/`, `tools/`, `storage/` | `backend/`, `workflow/` |
| `tools/` | `models/` | `agents/`, `backend/`, `workflow/`, `storage/` |
| `workflow/` | `models/`, `agents/`, `storage/` | `backend/`, `tools/` |
| `storage/` | `models/` | `agents/`, `backend/`, `tools/`, `workflow/` |
| `models/` | nothing in this project | anything above |

If a module needs something from a forbidden layer, introduce an interface or restructure. Don't violate the boundary.

---

## Agent Contract

Every agent in `agents/` must:

1. Inherit from `BaseAgent` (defined in `agents/base.py`).
2. Set a `name` attribute matching an `AgentName` enum value.
3. Implement `run(context: WorkflowState) -> WorkflowState`.
4. Read required inputs from `context`.
5. Write outputs to `context` AND persist to disk under `outputs/{job_id}/{agent_name}/`.
6. Return the updated `context`.
7. Raise a typed exception on failure (never swallow errors).

See `docs/agent-contracts.md` for per-agent input/output specifications.

---

## Data Models

All shared data models live in `models/`. They are Pydantic v2 `BaseModel` classes with no business logic.

- `models/__init__.py` re-exports all public models.
- Models validate shape, not behavior.
- No model should depend on another model outside `models/`.
- Agent-specific output models (`CreativeBrief`, `Script`, `Storyboard`, etc.) live in their own files.
- `WorkflowState` is the pipeline's internal state — persisted after each agent.
- `JobRecord` is the API-facing job metadata — returned by `/status` and `/result`.

See `docs/data-model-design.md` for the complete model inventory and rationale.

---

## Testing

- **TDD is mandatory.** Write the test first, watch it fail, write minimal code to pass, refactor.
- Test files mirror source structure: `tests/test_agents/`, `tests/test_workflow/`, etc.
- Use real code, not mocks, unless an external API call is involved.
- See `docs/phase1-test-plan.md` for the Phase 1 test inventory and execution order.

---

## Code Style

| Rule | Detail |
|------|--------|
| Type hints | Required on all function signatures and class attributes |
| Docstrings | Required on every public class and method |
| Naming | `snake_case` for functions/variables, `PascalCase` for classes |
| Imports | Standard library → third-party → project. Alphabetical within groups |
| Line length | 120 characters max |
| Functions | Keep under 30 lines. If longer, extract. |
| Files | Keep under 300 lines. If longer, split. |

---

## Before Committing

- [ ] All tests pass (`pytest`)
- [ ] No unused imports or dead code
- [ ] No commented-out code blocks
- [ ] Docstrings present on public interfaces
- [ ] Import rules followed (no cross-layer violations)
- [ ] Commit message describes *what changed* and *why*
