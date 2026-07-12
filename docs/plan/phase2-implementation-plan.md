# Phase 2 — Core Agents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Director, Research, Script, and Storyboard agents with real LLM calls via AlibabaCloudLLMService, and wire `/generate` to run the pipeline synchronously.

**Architecture:** Agents follow BaseAgent contract (`run(context) -> context`). Each agent constructs a structured prompt, calls LLMService.generate(), parses the response into its typed Pydantic model, persists the model JSON via storage, and writes AgentResult into context. AlibabaCloudLLMService uses the OpenAI SDK against DashScope's compatible endpoint. `/generate` route calls Pipeline.run() synchronously.

**Orchestration decision:** Pipeline orchestrates execution order. Director is a **content agent** (produces CreativeBrief), not a planner. The `CreativeBrief` indirectly directs downstream agents via its fields (tone, duration, audience, style_keywords), but Director never decides which agents run or in what order. LangGraph will replace Pipeline as orchestrator in a future phase — at that point, the graph defines conditional edges, and Director's contract stays unchanged (`run(context) -> context`). No competing orchestrators.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, OpenAI SDK (`openai>=1.0`), pytest

---

## Implementation Order

```
1. AlibabaCloudLLMService   ✅ DONE
2. Director Agent            ✅ DONE
3. Research Agent            ✅ DONE
4. Script Agent              ✅ DONE
5. Storyboard Agent          ✅ DONE
6. Wire /generate → Pipeline ✅ DONE
7. Sync JobRecord status     ✅ DONE
```

---

## Task 1: AlibabaCloudLLMService

**Files:**

- Modify: `tools/llm.py` — add `AlibabaCloudLLMService` class
- Modify: `requirements.txt` — add `openai>=1.0`
- Test: `tests/test_tools/test_llm.py` — add tests for concrete implementation

- [x] **Step 1: Add `openai>=1.0` to requirements.txt**

Open `requirements.txt` and replace the `# ---- LLM ----` comment block (lines 8–11) with:

```
# ---- LLM ----
openai>=1.0
```

- [x] **Step 2: Write failing tests for AlibabaCloudLLMService**

Add to `tests/test_tools/test_llm.py`:

```python
import pytest
from unittest.mock import MagicMock, patch

from tools.llm import AlibabaCloudLLMService
from models.enums import AgentName
from backend.config import LLMConfig


class TestAlibabaCloudLLMService:
    def test_can_be_instantiated_with_config(self):
        config = LLMConfig(api_key="test-key", model="qwen-plus")
        service = AlibabaCloudLLMService(config)
        assert service.config.api_key == "test-key"
        assert service.config.model == "qwen-plus"

    def test_generate_calls_openai_client(self):
        config = LLMConfig(api_key="test-key", model="qwen-plus", base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
        service = AlibabaCloudLLMService(config)
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Generated text response"

        with patch.object(service._client.chat.completions, "create", return_value=mock_response) as mock_create:
            result = service.generate("test prompt", AgentName.DIRECTOR)
            mock_create.assert_called_once()
            assert result == "Generated text response"

    def test_generate_raises_on_api_error(self):
        config = LLMConfig(api_key="test-key", model="qwen-plus")
        service = AlibabaCloudLLMService(config)

        import openai
        with patch.object(service._client.chat.completions, "create", side_effect=openai.APIConnectionError(request=MagicMock())):
            with pytest.raises(openai.APIConnectionError):
                service.generate("test prompt", AgentName.DIRECTOR)

    def test_generate_passes_model_and_prompt(self):
        config = LLMConfig(api_key="test-key", model="qwen-plus", base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
        service = AlibabaCloudLLMService(config)
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "response"

        with patch.object(service._client.chat.completions, "create", return_value=mock_response) as mock_create:
            service.generate("my prompt text", AgentName.RESEARCH)
            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["model"] == "qwen-plus"
            assert call_kwargs["messages"][1]["content"] == "my prompt text"

    def test_generate_includes_agent_name_in_system_prompt(self):
        config = LLMConfig(api_key="test-key", model="qwen-plus")
        service = AlibabaCloudLLMService(config)
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "response"

        with patch.object(service._client.chat.completions, "create", return_value=mock_response) as mock_create:
            service.generate("prompt", AgentName.DIRECTOR)
            call_kwargs = mock_create.call_args.kwargs
            system_msg = call_kwargs["messages"][0]
            assert "director" in system_msg["content"].lower()
```

- [x] **Step 3: Run tests to verify they fail**

Run: `venv\Scripts\python.exe -m pytest tests/test_tools/test_llm.py -v`
Expected: FAIL — `AlibabaCloudLLMService` doesn't exist yet (ImportError)

- [x] **Step 4: Install openai package**

Run: `venv\Scripts\pip.exe install openai>=1.0`

- [x] **Step 5: Implement AlibabaCloudLLMService**

Add to `tools/llm.py` after the `LLMService` ABC:

```python
import openai
from backend.config import LLMConfig


class AlibabaCloudLLMService(LLMService):
    """Concrete LLM service using OpenAI-compatible SDK against Alibaba Cloud DashScope."""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self._client = openai.OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout,
        )

    def generate(self, prompt: str, agent_name: AgentName) -> str:
        response = self._client.chat.completions.create(
            model=self.config.model,
            messages=[
                {
                    "role": "system",
                    "content": f"You are the {agent_name.value} agent in a video production pipeline. Respond with structured JSON matching the expected output schema.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content
```

- [x] **Step 6: Run tests to verify they pass**

Run: `venv\Scripts\python.exe -m pytest tests/test_tools/test_llm.py -v`
Expected: ALL PASS (4 original + 5 new = 9 tests)

- [x] **Step 7: Commit**

```bash
git add tools/llm.py tests/test_tools/test_llm.py requirements.txt
git commit -m "feat: implement AlibabaCloudLLMService with OpenAI SDK"
```

---

## Task 2: Director Agent

**Files:**

- Modify: `agents/director.py` — implement DirectorAgent
- Test: `tests/test_agents/test_director.py` — create new test file

- [x] **Step 1: Write failing tests for DirectorAgent**

Create `tests/test_agents/test_director.py`:

```python
import pytest
from unittest.mock import MagicMock

from agents.director import DirectorAgent
from models.enums import AgentName, JobStatus
from models.workflow_state import WorkflowState
from models.agent_result import AgentResult
from models.brief import CreativeBrief
from tools.llm import LLMService


def _make_context(prompt: str = "Create a 30-second explainer about AI") -> WorkflowState:
    return WorkflowState(job_id="test-job", prompt=prompt)


def _mock_llm_service(response: str) -> MagicMock:
    mock = MagicMock(spec=LLMService)
    mock.generate.return_value = response
    return mock


class TestDirectorAgent:
    def test_name_is_director(self):
        agent = DirectorAgent(llm_service=_mock_llm_service("irrelevant"))
        assert agent.name == AgentName.DIRECTOR

    def test_run_returns_workflow_state(self):
        brief_json = '{"title":"AI Explainer","prompt":"Create a 30-second explainer about AI","tone":"informative","audience":"general","duration_seconds":30.0,"summary":"A brief overview of artificial intelligence"}'
        agent = DirectorAgent(llm_service=_mock_llm_service(brief_json))
        ctx = _make_context()
        result = agent.run(ctx)
        assert isinstance(result, WorkflowState)

    def test_run_writes_agent_result_to_context(self):
        brief_json = '{"title":"AI Explainer","prompt":"Create a 30-second explainer about AI","tone":"informative","audience":"general","duration_seconds":30.0,"summary":"A brief overview of artificial intelligence"}'
        agent = DirectorAgent(llm_service=_mock_llm_service(brief_json))
        ctx = _make_context()
        result = agent.run(ctx)
        assert AgentName.DIRECTOR in result.agent_results
        agent_result = result.agent_results[AgentName.DIRECTOR]
        assert agent_result.success is True
        assert agent_result.agent_name == AgentName.DIRECTOR

    def test_run_stores_brief_in_output_data(self):
        brief_json = '{"title":"AI Explainer","prompt":"Create a 30-second explainer about AI","tone":"informative","audience":"general","duration_seconds":30.0,"summary":"A brief overview of artificial intelligence"}'
        agent = DirectorAgent(llm_service=_mock_llm_service(brief_json))
        ctx = _make_context()
        result = agent.run(ctx)
        output_data = result.agent_results[AgentName.DIRECTOR].output_data
        brief = CreativeBrief.model_validate(output_data)
        assert brief.title == "AI Explainer"
        assert brief.duration_seconds == 30.0

    def test_run_raises_on_invalid_llm_response(self):
        agent = DirectorAgent(llm_service=_mock_llm_service("not valid json at all"))
        ctx = _make_context()
        with pytest.raises(ValueError):
            agent.run(ctx)

    def test_run_raises_on_llm_service_error(self):
        mock_llm = MagicMock(spec=LLMService)
        mock_llm.generate.side_effect = RuntimeError("LLM API timeout")
        agent = DirectorAgent(llm_service=mock_llm)
        ctx = _make_context()
        with pytest.raises(RuntimeError, match="LLM API timeout"):
            agent.run(ctx)

    def test_prompt_includes_user_prompt(self):
        brief_json = '{"title":"AI Explainer","prompt":"Create a 30-second explainer about AI","tone":"informative","audience":"general","duration_seconds":30.0,"summary":"A brief overview of artificial intelligence"}'
        mock_llm = _mock_llm_service(brief_json)
        agent = DirectorAgent(llm_service=mock_llm)
        ctx = _make_context(prompt="My custom video prompt")
        agent.run(ctx)
        call_prompt = mock_llm.generate.call_args.args[0]
        assert "My custom video prompt" in call_prompt

    def test_run_persists_brief_json_to_storage(self):
        brief_json = '{"title":"AI Explainer","prompt":"Create a 30-second explainer about AI","tone":"informative","audience":"general","duration_seconds":30.0,"summary":"A brief overview of artificial intelligence"}'
        mock_llm = _mock_llm_service(brief_json)
        mock_storage = MagicMock()
        agent = DirectorAgent(llm_service=mock_llm, storage=mock_storage)
        ctx = _make_context()
        agent.run(ctx)
        mock_storage.save.assert_called_once()
        call_args = mock_storage.save.call_args
        assert call_args.kwargs["job_id"] == "test-job"
        assert call_args.kwargs["agent_name"] == "director"
        assert call_args.kwargs["filename"] == "creative_brief.json"
```

- [x] **Step 2: Run tests to verify they fail**

- [x] **Step 3: Implement DirectorAgent**

Write `agents/director.py`:

```python
"""Director agent — enriches user prompt into a structured creative brief."""

from models.enums import AgentName
from models.agent_result import AgentResult, ArtifactRef
from models.brief import CreativeBrief
from models.workflow_state import WorkflowState
from storage.base import StorageBackend
from tools.llm import LLMService


DIRECTOR_PROMPT_TEMPLATE = """You are the Director agent in a video production pipeline.
Given the user's prompt, produce a creative brief as JSON matching this exact schema:

{{
  "title": string — concise title for the video,
  "prompt": string — the original user prompt (echo it back),
  "tone": string — desired tone (e.g., "informative", "dramatic", "humorous"),
  "audience": string — target audience description,
  "duration_seconds": number — target video length in seconds (must be > 0),
  "summary": string — one-sentence summary of the video concept,
  "aspect_ratio": string — optional, default "16:9",
  "style_keywords": list of strings — optional visual style tags
}}

User prompt: {prompt}

Respond ONLY with valid JSON. No explanation, no markdown, no commentary."""


class DirectorAgent:
    name = AgentName.DIRECTOR

    def __init__(self, llm_service: LLMService, storage: StorageBackend | None = None) -> None:
        self.llm_service = llm_service
        self.storage = storage

    def run(self, context: WorkflowState) -> WorkflowState:
        prompt = DIRECTOR_PROMPT_TEMPLATE.format(prompt=context.prompt)
        raw_response = self.llm_service.generate(prompt, self.name)

        try:
            brief = CreativeBrief.model_validate_json(raw_response)
        except Exception as exc:
            raise ValueError(f"Director agent failed to parse LLM response as CreativeBrief: {exc}") from exc

        if self.storage is not None:
            self.storage.save(
                context.job_id,
                self.name.value,
                "creative_brief.json",
                brief.model_dump(mode="json"),
            )

        artifact = ArtifactRef(
            agent_name=self.name,
            filename="creative_brief.json",
            content_type="application/json",
        )
        context.agent_results[self.name] = AgentResult(
            agent_name=self.name,
            success=True,
            output_data=brief.model_dump(mode="json"),
            artifacts=[artifact],
        )
        return context
```

- [x] **Step 4: Update `BaseAgent.__init__` to accept agents with constructor args**

The current `BaseAgent.__init__` only checks `name`. Agents now take constructor args (`llm_service`, `storage`). The `__init__` doesn't need changes — `DirectorAgent.__init__` calls `super().__init__()` implicitly via the `name` class attribute check. But we need to make sure `DirectorAgent` passes the `BaseAgent.__init__` check. Modify `agents/director.py` to call `super().__init__()`:

Actually, the current `BaseAgent.__init__` checks `self.name` which is a class attribute, so it works. No change needed to BaseAgent.

- [x] **Step 5: Run tests to verify they pass**

Run: `venv\Scripts\python.exe -m pytest tests/test_agents/test_director.py -v`
Expected: ALL PASS (8 tests)

- [x] **Step 6: Commit**

---

## Task 3: Research Agent

**Files:**

- Modify: `agents/research.py` — implement ResearchAgent
- Test: `tests/test_agents/test_research.py` — create new test file

- [x] **Step 1: Write failing tests for ResearchAgent**

Create `tests/test_agents/test_research.py`:

```python
import pytest
from unittest.mock import MagicMock

from agents.research import ResearchAgent
from models.enums import AgentName
from models.workflow_state import WorkflowState
from models.agent_result import AgentResult
from models.brief import CreativeBrief
from models.research import ResearchNotes
from tools.llm import LLMService
from storage.base import StorageBackend


def _make_context_with_brief() -> WorkflowState:
    ctx = WorkflowState(job_id="test-job", prompt="Create a 30s explainer about AI")
    brief = CreativeBrief(
        title="AI Explainer",
        prompt="Create a 30s explainer about AI",
        tone="informative",
        audience="general",
        duration_seconds=30.0,
        summary="A brief overview of artificial intelligence",
    )
    ctx.agent_results[AgentName.DIRECTOR] = AgentResult(
        agent_name=AgentName.DIRECTOR,
        success=True,
        output_data=brief.model_dump(mode="json"),
    )
    return ctx


def _mock_llm_service(response: str) -> MagicMock:
    mock = MagicMock(spec=LLMService)
    mock.generate.return_value = response
    return mock


class TestResearchAgent:
    def test_name_is_research(self):
        agent = ResearchAgent(llm_service=_mock_llm_service("irrelevant"))
        assert agent.name == AgentName.RESEARCH

    def test_run_returns_workflow_state(self):
        research_json = '{"brief_summary":"AI overview","notes":[{"topic":"AI definition","content":"Artificial intelligence is...","source":"Wikipedia","verified":true}],"overall_confidence":0.8}'
        agent = ResearchAgent(llm_service=_mock_llm_service(research_json))
        ctx = _make_context_with_brief()
        result = agent.run(ctx)
        assert isinstance(result, WorkflowState)

    def test_run_writes_agent_result(self):
        research_json = '{"brief_summary":"AI overview","notes":[{"topic":"AI definition","content":"Artificial intelligence is..."}],"overall_confidence":0.7}'
        agent = ResearchAgent(llm_service=_mock_llm_service(research_json))
        ctx = _make_context_with_brief()
        result = agent.run(ctx)
        assert AgentName.RESEARCH in result.agent_results
        assert result.agent_results[AgentName.RESEARCH].success is True

    def test_run_stores_research_in_output_data(self):
        research_json = '{"brief_summary":"AI overview","notes":[{"topic":"AI definition","content":"Artificial intelligence is machine simulation of human intelligence","source":"Stanford","verified":true}],"overall_confidence":0.85}'
        agent = ResearchAgent(llm_service=_mock_llm_service(research_json))
        ctx = _make_context_with_brief()
        result = agent.run(ctx)
        output_data = result.agent_results[AgentName.RESEARCH].output_data
        notes = ResearchNotes.model_validate(output_data)
        assert notes.brief_summary == "AI overview"
        assert len(notes.notes) == 1

    def test_run_raises_when_director_output_missing(self):
        agent = ResearchAgent(llm_service=_mock_llm_service("irrelevant"))
        ctx = WorkflowState(job_id="test-job", prompt="test")
        with pytest.raises(ValueError, match="Director"):
            agent.run(ctx)

    def test_run_raises_on_invalid_llm_response(self):
        agent = ResearchAgent(llm_service=_mock_llm_service("garbage response"))
        ctx = _make_context_with_brief()
        with pytest.raises(ValueError):
            agent.run(ctx)

    def test_run_persists_to_storage(self):
        research_json = '{"brief_summary":"AI overview","notes":[],"overall_confidence":0.5}'
        mock_llm = _mock_llm_service(research_json)
        mock_storage = MagicMock(spec=StorageBackend)
        agent = ResearchAgent(llm_service=mock_llm, storage=mock_storage)
        ctx = _make_context_with_brief()
        agent.run(ctx)
        mock_storage.save.assert_called_once()
        call_args = mock_storage.save.call_args.kwargs
        assert call_args["agent_name"] == "research"
        assert call_args["filename"] == "research_notes.json"
```

- [x] **Step 2: Run tests to verify they fail**

- [x] **Step 3: Implement ResearchAgent**

Write `agents/research.py`:

```python
"""Research agent — gathers facts and references based on the creative brief."""

from models.enums import AgentName
from models.agent_result import AgentResult, ArtifactRef
from models.brief import CreativeBrief
from models.research import ResearchNotes
from models.workflow_state import WorkflowState
from storage.base import StorageBackend
from tools.llm import LLMService


RESEARCH_PROMPT_TEMPLATE = """You are the Research agent in a video production pipeline.
Given the creative brief, gather relevant facts, statistics, and talking points.

Creative brief:
{brief_json}

Produce research notes as JSON matching this exact schema:

{{
  "brief_summary": string — one-sentence summary of what the research covers,
  "notes": [
    {{
      "topic": string — the specific topic or claim,
      "content": string — the research finding or fact,
      "source": string or null — where the info comes from,
      "verified": boolean — whether the fact is verified (default false)
    }}
  ],
  "overall_confidence": number — your confidence level 0.0 to 1.0
}}

Respond ONLY with valid JSON. No explanation, no markdown, no commentary."""


class ResearchAgent:
    name = AgentName.RESEARCH

    def __init__(self, llm_service: LLMService, storage: StorageBackend | None = None) -> None:
        self.llm_service = llm_service
        self.storage = storage

    def run(self, context: WorkflowState) -> WorkflowState:
        if AgentName.DIRECTOR not in context.agent_results:
            raise ValueError("Research agent requires Director output in context")

        brief = CreativeBrief.model_validate(
            context.agent_results[AgentName.DIRECTOR].output_data
        )
        prompt = RESEARCH_PROMPT_TEMPLATE.format(brief_json=brief.model_dump_json())
        raw_response = self.llm_service.generate(prompt, self.name)

        try:
            notes = ResearchNotes.model_validate_json(raw_response)
        except Exception as exc:
            raise ValueError(f"Research agent failed to parse LLM response as ResearchNotes: {exc}") from exc

        if self.storage is not None:
            self.storage.save(
                context.job_id,
                self.name.value,
                "research_notes.json",
                notes.model_dump(mode="json"),
            )

        artifact = ArtifactRef(
            agent_name=self.name,
            filename="research_notes.json",
            content_type="application/json",
        )
        context.agent_results[self.name] = AgentResult(
            agent_name=self.name,
            success=True,
            output_data=notes.model_dump(mode="json"),
            artifacts=[artifact],
        )
        return context
```

- [x] **Step 4: Run tests to verify they pass**

Run: `venv\Scripts\python.exe -m pytest tests/test_agents/test_research.py -v`
Expected: ALL PASS (7 tests)

- [x] **Step 5: Commit**

```bash
git add agents/research.py tests/test_agents/test_research.py
git commit -m "feat: implement Research agent with LLM-powered fact gathering"
```

---

## Task 4: Script Agent

**Files:**

- Modify: `agents/script.py` — implement ScriptAgent
- Test: `tests/test_agents/test_script.py` — create new test file

- [x] **Step 1: Write failing tests for ScriptAgent**

Create `tests/test_agents/test_script.py`:

```python
import pytest
from unittest.mock import MagicMock

from agents.script import ScriptAgent
from models.enums import AgentName
from models.workflow_state import WorkflowState
from models.agent_result import AgentResult
from models.brief import CreativeBrief
from models.research import ResearchNotes, ResearchNote
from models.script import Script
from tools.llm import LLMService
from storage.base import StorageBackend


def _make_context_with_upstream() -> WorkflowState:
    ctx = WorkflowState(job_id="test-job", prompt="Create a 30s explainer about AI")
    brief = CreativeBrief(
        title="AI Explainer",
        prompt="Create a 30s explainer about AI",
        tone="informative",
        audience="general",
        duration_seconds=30.0,
        summary="A brief overview of AI",
    )
    ctx.agent_results[AgentName.DIRECTOR] = AgentResult(
        agent_name=AgentName.DIRECTOR, success=True, output_data=brief.model_dump(mode="json"),
    )
    notes = ResearchNotes(
        brief_summary="AI overview",
        notes=[ResearchNote(topic="AI definition", content="AI simulates human intelligence")],
        overall_confidence=0.7,
    )
    ctx.agent_results[AgentName.RESEARCH] = AgentResult(
        agent_name=AgentName.RESEARCH, success=True, output_data=notes.model_dump(mode="json"),
    )
    return ctx


def _mock_llm_service(response: str) -> MagicMock:
    mock = MagicMock(spec=LLMService)
    mock.generate.return_value = response
    return mock


class TestScriptAgent:
    def test_name_is_script(self):
        agent = ScriptAgent(llm_service=_mock_llm_service("irrelevant"))
        assert agent.name == AgentName.SCRIPT

    def test_run_returns_workflow_state(self):
        script_json = '{"title":"AI Explainer","scenes":[{"scene_number":1,"narration":"AI is transforming the world","duration_hint":15.0,"visual_direction":"Show AI systems in action"}]}'
        agent = ScriptAgent(llm_service=_mock_llm_service(script_json))
        ctx = _make_context_with_upstream()
        result = agent.run(ctx)
        assert isinstance(result, WorkflowState)

    def test_run_writes_agent_result(self):
        script_json = '{"title":"AI Explainer","scenes":[{"scene_number":1,"narration":"AI is transforming the world","duration_hint":15.0,"visual_direction":"Show AI systems in action"}]}'
        agent = ScriptAgent(llm_service=_mock_llm_service(script_json))
        ctx = _make_context_with_upstream()
        result = agent.run(ctx)
        assert AgentName.SCRIPT in result.agent_results
        assert result.agent_results[AgentName.SCRIPT].success is True

    def test_run_stores_script_in_output_data(self):
        script_json = '{"title":"AI Explainer","scenes":[{"scene_number":1,"narration":"AI is transforming the world","duration_hint":15.0,"visual_direction":"Show AI systems in action","mood":"inspiring"}]}'
        agent = ScriptAgent(llm_service=_mock_llm_service(script_json))
        ctx = _make_context_with_upstream()
        result = agent.run(ctx)
        script = Script.model_validate(result.agent_results[AgentName.SCRIPT].output_data)
        assert script.title == "AI Explainer"
        assert len(script.scenes) == 1
        assert script.scenes[0].narration == "AI is transforming the world"

    def test_run_raises_when_director_missing(self):
        agent = ScriptAgent(llm_service=_mock_llm_service("irrelevant"))
        ctx = WorkflowState(job_id="test-job", prompt="test")
        with pytest.raises(ValueError, match="Director"):
            agent.run(ctx)

    def test_run_raises_when_research_missing(self):
        agent = ScriptAgent(llm_service=_mock_llm_service("irrelevant"))
        ctx = WorkflowState(job_id="test-job", prompt="test")
        brief = CreativeBrief(title="T", prompt="P", tone="t", audience="a", duration_seconds=10.0, summary="s")
        ctx.agent_results[AgentName.DIRECTOR] = AgentResult(
            agent_name=AgentName.DIRECTOR, success=True, output_data=brief.model_dump(mode="json"),
        )
        with pytest.raises(ValueError, match="Research"):
            agent.run(ctx)

    def test_run_raises_on_invalid_llm_response(self):
        agent = ScriptAgent(llm_service=_mock_llm_service("not json"))
        ctx = _make_context_with_upstream()
        with pytest.raises(ValueError):
            agent.run(ctx)

    def test_run_persists_to_storage(self):
        script_json = '{"title":"AI Explainer","scenes":[{"scene_number":1,"narration":"AI is transforming the world","duration_hint":15.0,"visual_direction":"Show AI systems in action"}]}'
        mock_llm = _mock_llm_service(script_json)
        mock_storage = MagicMock(spec=StorageBackend)
        agent = ScriptAgent(llm_service=mock_llm, storage=mock_storage)
        ctx = _make_context_with_upstream()
        agent.run(ctx)
        mock_storage.save.assert_called_once()
        call_args = mock_storage.save.call_args.kwargs
        assert call_args["agent_name"] == "script"
        assert call_args["filename"] == "script.json"
```

- [x] **Step 2: Run tests to verify they fail**

- [x] **Step 3: Implement ScriptAgent**

Write `agents/script.py`:

```python
"""Script agent — writes a scene-by-scene script from brief and research."""

from models.enums import AgentName
from models.agent_result import AgentResult, ArtifactRef
from models.brief import CreativeBrief
from models.research import ResearchNotes
from models.script import Script
from models.workflow_state import WorkflowState
from storage.base import StorageBackend
from tools.llm import LLMService


SCRIPT_PROMPT_TEMPLATE = """You are the Script agent in a video production pipeline.
Given the creative brief and research notes, write a scene-by-scene script.

Creative brief:
{brief_json}

Research notes:
{research_json}

Produce a script as JSON matching this exact schema:

{{
  "title": string — script title,
  "scenes": [
    {{
      "scene_number": integer — starts at 1, must be >= 1,
      "narration": string — the narration text for this scene,
      "duration_hint": number — estimated duration in seconds (must be > 0),
      "visual_direction": string — description of what should appear visually,
      "mood": string or null — optional mood tag
    }}
  ],
  "total_estimated_duration": number or null — sum of scene durations
}}

Total scene durations should approximately match the brief's duration_seconds ({duration_target}s).
Respond ONLY with valid JSON. No explanation, no markdown, no commentary."""


class ScriptAgent:
    name = AgentName.SCRIPT

    def __init__(self, llm_service: LLMService, storage: StorageBackend | None = None) -> None:
        self.llm_service = llm_service
        self.storage = storage

    def run(self, context: WorkflowState) -> WorkflowState:
        if AgentName.DIRECTOR not in context.agent_results:
            raise ValueError("Script agent requires Director output in context")
        if AgentName.RESEARCH not in context.agent_results:
            raise ValueError("Script agent requires Research output in context")

        brief = CreativeBrief.model_validate(
            context.agent_results[AgentName.DIRECTOR].output_data
        )
        research = ResearchNotes.model_validate(
            context.agent_results[AgentName.RESEARCH].output_data
        )

        prompt = SCRIPT_PROMPT_TEMPLATE.format(
            brief_json=brief.model_dump_json(),
            research_json=research.model_dump_json(),
            duration_target=brief.duration_seconds,
        )
        raw_response = self.llm_service.generate(prompt, self.name)

        try:
            script = Script.model_validate_json(raw_response)
        except Exception as exc:
            raise ValueError(f"Script agent failed to parse LLM response as Script: {exc}") from exc

        if self.storage is not None:
            self.storage.save(
                context.job_id,
                self.name.value,
                "script.json",
                script.model_dump(mode="json"),
            )

        artifact = ArtifactRef(
            agent_name=self.name,
            filename="script.json",
            content_type="application/json",
        )
        context.agent_results[self.name] = AgentResult(
            agent_name=self.name,
            success=True,
            output_data=script.model_dump(mode="json"),
            artifacts=[artifact],
        )
        return context
```

- [x] **Step 4: Run tests to verify they pass**

Run: `venv\Scripts\python.exe -m pytest tests/test_agents/test_script.py -v`
Expected: ALL PASS (8 tests)

- [x] **Step 5: Commit**

```bash
git add agents/script.py tests/test_agents/test_script.py
git commit -m "feat: implement Script agent with LLM-powered scene generation"
```

---

## Task 5: Storyboard Agent

**Files:**

- Modify: `agents/storyboard.py` — implement StoryboardAgent
- Test: `tests/test_agents/test_storyboard.py` — create new test file

- [x] **Step 1: Write failing tests for StoryboardAgent**

Create `tests/test_agents/test_storyboard.py`:

```python
import pytest
from unittest.mock import MagicMock

from agents.storyboard import StoryboardAgent
from models.enums import AgentName
from models.workflow_state import WorkflowState
from models.agent_result import AgentResult
from models.brief import CreativeBrief
from models.research import ResearchNotes, ResearchNote
from models.script import Script
from models.scene import Scene
from models.storyboard import Storyboard
from tools.llm import LLMService
from storage.base import StorageBackend


def _make_context_with_upstream() -> WorkflowState:
    ctx = WorkflowState(job_id="test-job", prompt="Create a 30s explainer about AI")
    brief = CreativeBrief(
        title="AI Explainer", prompt="Create a 30s explainer about AI",
        tone="informative", audience="general", duration_seconds=30.0, summary="AI overview",
    )
    ctx.agent_results[AgentName.DIRECTOR] = AgentResult(
        agent_name=AgentName.DIRECTOR, success=True, output_data=brief.model_dump(mode="json"),
    )
    notes = ResearchNotes(brief_summary="AI overview", notes=[], overall_confidence=0.7)
    ctx.agent_results[AgentName.RESEARCH] = AgentResult(
        agent_name=AgentName.RESEARCH, success=True, output_data=notes.model_dump(mode="json"),
    )
    script = Script(
        title="AI Explainer",
        scenes=[Scene(scene_number=1, narration="AI is transforming the world", duration_hint=15.0, visual_direction="Show AI systems")],
    )
    ctx.agent_results[AgentName.SCRIPT] = AgentResult(
        agent_name=AgentName.SCRIPT, success=True, output_data=script.model_dump(mode="json"),
    )
    return ctx


def _mock_llm_service(response: str) -> MagicMock:
    mock = MagicMock(spec=LLMService)
    mock.generate.return_value = response
    return mock


class TestStoryboardAgent:
    def test_name_is_storyboard(self):
        agent = StoryboardAgent(llm_service=_mock_llm_service("irrelevant"))
        assert agent.name == AgentName.STORYBOARD

    def test_run_returns_workflow_state(self):
        sb_json = '{"shots":[{"shot_number":1,"scene_number":1,"visual_prompt":"A futuristic AI lab","camera":"medium shot","motion":"slow pan","duration":15.0}]}'
        agent = StoryboardAgent(llm_service=_mock_llm_service(sb_json))
        ctx = _make_context_with_upstream()
        result = agent.run(ctx)
        assert isinstance(result, WorkflowState)

    def test_run_writes_agent_result(self):
        sb_json = '{"shots":[{"shot_number":1,"scene_number":1,"visual_prompt":"A futuristic AI lab","camera":"medium shot","motion":"slow pan","duration":15.0}]}'
        agent = StoryboardAgent(llm_service=_mock_llm_service(sb_json))
        ctx = _make_context_with_upstream()
        result = agent.run(ctx)
        assert AgentName.STORYBOARD in result.agent_results
        assert result.agent_results[AgentName.STORYBOARD].success is True

    def test_run_stores_storyboard_in_output_data(self):
        sb_json = '{"shots":[{"shot_number":1,"scene_number":1,"visual_prompt":"A futuristic AI lab","camera":"medium shot","motion":"slow pan","duration":15.0,"mood":"inspiring"}]}'
        agent = StoryboardAgent(llm_service=_mock_llm_service(sb_json))
        ctx = _make_context_with_upstream()
        result = agent.run(ctx)
        sb = Storyboard.model_validate(result.agent_results[AgentName.STORYBOARD].output_data)
        assert len(sb.shots) == 1
        assert sb.shots[0].visual_prompt == "A futuristic AI lab"

    def test_run_raises_when_script_missing(self):
        agent = StoryboardAgent(llm_service=_mock_llm_service("irrelevant"))
        ctx = WorkflowState(job_id="test-job", prompt="test")
        with pytest.raises(ValueError, match="Script"):
            agent.run(ctx)

    def test_run_raises_on_invalid_llm_response(self):
        agent = StoryboardAgent(llm_service=_mock_llm_service("not json"))
        ctx = _make_context_with_upstream()
        with pytest.raises(ValueError):
            agent.run(ctx)

    def test_run_persists_to_storage(self):
        sb_json = '{"shots":[{"shot_number":1,"scene_number":1,"visual_prompt":"A futuristic AI lab","camera":"medium shot","motion":"slow pan","duration":15.0}]}'
        mock_llm = _mock_llm_service(sb_json)
        mock_storage = MagicMock(spec=StorageBackend)
        agent = StoryboardAgent(llm_service=mock_llm, storage=mock_storage)
        ctx = _make_context_with_upstream()
        agent.run(ctx)
        mock_storage.save.assert_called_once()
        call_args = mock_storage.save.call_args.kwargs
        assert call_args["agent_name"] == "storyboard"
        assert call_args["filename"] == "storyboard.json"
```

- [x] **Step 2: Run tests to verify they fail**

- [x] **Step 3: Implement StoryboardAgent**

Write `agents/storyboard.py`:

```python
"""Storyboard agent — converts script scenes into a shot list with visual prompts."""

from models.enums import AgentName
from models.agent_result import AgentResult, ArtifactRef
from models.script import Script
from models.storyboard import Storyboard
from models.workflow_state import WorkflowState
from storage.base import StorageBackend
from tools.llm import LLMService


STORYBOARD_PROMPT_TEMPLATE = """You are the Storyboard agent in a video production pipeline.
Given the script, convert each scene into detailed shot descriptions for video generation.

Script:
{script_json}

Produce a storyboard as JSON matching this exact schema:

{{
  "shots": [
    {{
      "shot_number": integer — starts at 1, must be >= 1,
      "scene_number": integer — which script scene this shot belongs to, must be >= 1,
      "visual_prompt": string — detailed description for image/video generation,
      "camera": string — camera angle/type (e.g., "medium shot", "close-up", "wide angle"),
      "motion": string — camera motion or subject motion (e.g., "slow pan", "static", "zoom in"),
      "duration": number — shot duration in seconds, must be > 0,
      "mood": string or null — optional mood/atmosphere tag
    }}
  ],
  "total_duration": number or null — sum of shot durations
}}

Each scene should have at least one shot. Shot durations should match scene duration hints.
Respond ONLY with valid JSON. No explanation, no markdown, no commentary."""


class StoryboardAgent:
    name = AgentName.STORYBOARD

    def __init__(self, llm_service: LLMService, storage: StorageBackend | None = None) -> None:
        self.llm_service = llm_service
        self.storage = storage

    def run(self, context: WorkflowState) -> WorkflowState:
        if AgentName.SCRIPT not in context.agent_results:
            raise ValueError("Storyboard agent requires Script output in context")

        script = Script.model_validate(
            context.agent_results[AgentName.SCRIPT].output_data
        )

        prompt = STORYBOARD_PROMPT_TEMPLATE.format(script_json=script.model_dump_json())
        raw_response = self.llm_service.generate(prompt, self.name)

        try:
            storyboard = Storyboard.model_validate_json(raw_response)
        except Exception as exc:
            raise ValueError(f"Storyboard agent failed to parse LLM response as Storyboard: {exc}") from exc

        if self.storage is not None:
            self.storage.save(
                context.job_id,
                self.name.value,
                "storyboard.json",
                storyboard.model_dump(mode="json"),
            )

        artifact = ArtifactRef(
            agent_name=self.name,
            filename="storyboard.json",
            content_type="application/json",
        )
        context.agent_results[self.name] = AgentResult(
            agent_name=self.name,
            success=True,
            output_data=storyboard.model_dump(mode="json"),
            artifacts=[artifact],
        )
        return context
```

- [x] **Step 4: Run tests to verify they pass**

Run: `venv\Scripts\python.exe -m pytest tests/test_agents/test_storyboard.py -v`
Expected: ALL PASS (7 tests)

- [x] **Step 5: Commit**

```bash
git add agents/storyboard.py tests/test_agents/test_storyboard.py
git commit -m "feat: implement Storyboard agent with LLM-powered shot generation"
```

---

## Task 6: Wire `/generate` to Run Pipeline

**Files:**

- Modify: `backend/api/routes.py` — call Pipeline.run() in generate endpoint
- Modify: `backend/main.py` — inject agents into the production app
- Modify: `tests/test_api/test_routes.py` — update existing tests + add new ones for pipeline execution
- Modify: `tests/test_api/test_app.py` — update if needed

- [x] **Step 1: Write failing test for pipeline execution on /generate**

Add to `tests/test_api/test_routes.py`:

```python
from unittest.mock import MagicMock, patch
from agents.director import DirectorAgent
from agents.research import ResearchAgent
from agents.script import ScriptAgent
from agents.storyboard import StoryboardAgent
from tools.llm import LLMService
from storage.base import StorageBackend


class TestGeneratePipelineExecution:
    def test_generate_runs_pipeline_and_returns_completed_status(self):
        """POST /generate should run all 4 Phase 2 agents and return a completed job."""
        brief_json = '{"title":"AI Explainer","prompt":"Make an AI video","tone":"informative","audience":"general","duration_seconds":30.0,"summary":"AI overview"}'
        research_json = '{"brief_summary":"AI overview","notes":[],"overall_confidence":0.7}'
        script_json = '{"title":"AI Explainer","scenes":[{"scene_number":1,"narration":"AI transforms the world","duration_hint":15.0,"visual_direction":"Show AI systems"}]}'
        storyboard_json = '{"shots":[{"shot_number":1,"scene_number":1,"visual_prompt":"AI lab","camera":"medium","motion":"pan","duration":15.0}]}'

        mock_llm = MagicMock(spec=LLMService)
        mock_llm.generate.side_effect = [brief_json, research_json, script_json, storyboard_json]

        storage = LocalStorage(str(tmp_path))
        job_store: dict[str, JobRecord] = {}

        agents = [
            DirectorAgent(llm_service=mock_llm, storage=storage),
            ResearchAgent(llm_service=mock_llm, storage=storage),
            ScriptAgent(llm_service=mock_llm, storage=storage),
            StoryboardAgent(llm_service=mock_llm, storage=storage),
        ]

        app = create_app_with_agents(storage, job_store, agents)
        client = TestClient(app)

        resp = client.post("/generate", json={"prompt": "Make an AI video"})
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]

        status_resp = client.get(f"/status/{job_id}")
        assert status_resp.json()["status"] == "completed"
```

Note: This requires a new `create_app_with_agents` factory or modifying `create_app` to accept agents. We'll add that.

- [x] **Step 2: Update `create_app` to accept agents and run pipeline**

Modify `backend/api/routes.py` — change `create_app` signature and the `generate` endpoint:

```python
from agents.base import BaseAgent
from tools.llm import LLMService
from workflow.pipeline import Pipeline


def create_app(
    storage: StorageBackend,
    job_store: dict[str, JobRecord],
    agents: list[BaseAgent] | None = None,
) -> FastAPI:
    app = FastAPI()
    pipeline = Pipeline(storage) if agents else None

    @app.post("/generate", status_code=202, response_model=GenerateResponse)
    def generate(req: GenerateRequest) -> GenerateResponse:
        job_id = str(uuid.uuid4())
        job_record = JobRecord(job_id=job_id, prompt=req.prompt)
        job_store[job_id] = job_record
        ctx = WorkflowState(job_id=job_id, prompt=req.prompt)

        if pipeline is not None:
            ctx = pipeline.run(job_id, agents, ctx)
            job_record.status = ctx.status
            job_record.updated_at = ctx.updated_at
            if ctx.failed_agent:
                job_record.failed_agent = ctx.failed_agent
            if ctx.error:
                job_record.error = ctx.error

        storage.save(job_id, "pipeline", "context.json", ctx.model_dump(mode="json"))
        return GenerateResponse(job_id=job_id)
```

- [x] **Step 3: Update `backend/main.py` to inject agents**

Modify `backend/main.py`:

```python
"""FastAPI application entry point — creates production app with default storage and agents."""

from storage.local import LocalStorage
from backend.api.routes import create_app
from backend.config import Settings
from models.job import JobRecord
from tools.llm import AlibabaCloudLLMService
from agents.director import DirectorAgent
from agents.research import ResearchAgent
from agents.script import ScriptAgent
from agents.storyboard import StoryboardAgent


def create_production_app():
    settings = Settings()
    storage = LocalStorage(settings.storage.output_dir)
    job_store: dict[str, JobRecord] = {}

    llm_service = AlibabaCloudLLMService(settings.llm)
    agents = [
        DirectorAgent(llm_service=llm_service, storage=storage),
        ResearchAgent(llm_service=llm_service, storage=storage),
        ScriptAgent(llm_service=llm_service, storage=storage),
        StoryboardAgent(llm_service=llm_service, storage=storage),
    ]

    return create_app(storage=storage, job_store=job_store, agents=agents)


app = create_production_app()
```

- [x] **Step 4: Run all existing route tests to verify they still pass**

Run: `venv\Scripts\python.exe -m pytest tests/test_api/test_routes.py -v`
Expected: Existing 14 tests still pass (they use `create_app(storage, job_store)` without agents — `agents=None`, pipeline won't run, behavior unchanged)

- [x] **Step 5: Run the new pipeline execution test**

Run: `venv\Scripts\python.exe -m pytest tests/test_api/test_routes.py::TestGeneratePipelineExecution -v`
Expected: PASS

- [x] **Step 6: Run all API tests together**

Run: `venv\Scripts\python.exe -m pytest tests/test_api/ -v`
Expected: ALL PASS (14 original + 1 new = 15 route tests, 6 app tests)

- [x] **Step 7: Commit**

```bash
git add backend/api/routes.py backend/main.py tests/test_api/test_routes.py
git commit -m "feat: wire /generate endpoint to run Pipeline with Phase 2 agents"
```

---

## Task 7: Sync JobRecord Status from WorkflowState

**Files:**

- Modify: `backend/api/routes.py` — sync status in status/result/resume endpoints
- Test: `tests/test_api/test_routes.py` — add tests for status consistency

- [x] **Step 1: Write failing tests for status sync**

Add to `tests/test_api/test_routes.py`:

```python
class TestStatusConsistency:
    def test_status_reflects_pipeline_completed_state(self):
        """When pipeline completes, /status should return 'completed'."""
        brief_json = '{"title":"T","prompt":"P","tone":"t","audience":"a","duration_seconds":10.0,"summary":"s"}'
        research_json = '{"brief_summary":"s","notes":[],"overall_confidence":0.5}'
        script_json = '{"title":"T","scenes":[{"scene_number":1,"narration":"n","duration_hint":5.0,"visual_direction":"v"}]}'
        storyboard_json = '{"shots":[{"shot_number":1,"scene_number":1,"visual_prompt":"v","camera":"c","motion":"m","duration":5.0}]}'

        mock_llm = MagicMock(spec=LLMService)
        mock_llm.generate.side_effect = [brief_json, research_json, script_json, storyboard_json]

        storage = LocalStorage(str(tmp_path))
        job_store: dict[str, JobRecord] = {}
        agents = [
            DirectorAgent(llm_service=mock_llm, storage=storage),
            ResearchAgent(llm_service=mock_llm, storage=storage),
            ScriptAgent(llm_service=mock_llm, storage=storage),
            StoryboardAgent(llm_service=mock_llm, storage=storage),
        ]
        app = create_app(storage=storage, job_store=job_store, agents=agents)
        client = TestClient(app)

        resp = client.post("/generate", json={"prompt": "test prompt"})
        job_id = resp.json()["job_id"]

        status_resp = client.get(f"/status/{job_id}")
        data = status_resp.json()
        assert data["status"] == "completed"

    def test_status_reflects_pipeline_failed_state(self):
        """When an agent fails, /status should return 'failed' with failed_agent."""
        mock_llm = MagicMock(spec=LLMService)
        mock_llm.generate.side_effect = RuntimeError("LLM timeout")

        storage = LocalStorage(str(tmp_path))
        job_store: dict[str, JobRecord] = {}
        agents = [
            DirectorAgent(llm_service=mock_llm, storage=storage),
        ]
        app = create_app(storage=storage, job_store=job_store, agents=agents)
        client = TestClient(app)

        resp = client.post("/generate", json={"prompt": "test prompt"})
        job_id = resp.json()["job_id"]

        status_resp = client.get(f"/status/{job_id}")
        data = status_resp.json()
        assert data["status"] == "failed"
        assert data["failed_agent"] == "director"

    def test_result_returns_200_for_completed_job_with_artifacts(self):
        """When pipeline completes, /result should return artifacts from all agents."""
        brief_json = '{"title":"T","prompt":"P","tone":"t","audience":"a","duration_seconds":10.0,"summary":"s"}'
        research_json = '{"brief_summary":"s","notes":[],"overall_confidence":0.5}'
        script_json = '{"title":"T","scenes":[{"scene_number":1,"narration":"n","duration_hint":5.0,"visual_direction":"v"}]}'
        storyboard_json = '{"shots":[{"shot_number":1,"scene_number":1,"visual_prompt":"v","camera":"c","motion":"m","duration":5.0}]}'

        mock_llm = MagicMock(spec=LLMService)
        mock_llm.generate.side_effect = [brief_json, research_json, script_json, storyboard_json]

        storage = LocalStorage(str(tmp_path))
        job_store: dict[str, JobRecord] = {}
        agents = [
            DirectorAgent(llm_service=mock_llm, storage=storage),
            ResearchAgent(llm_service=mock_llm, storage=storage),
            ScriptAgent(llm_service=mock_llm, storage=storage),
            StoryboardAgent(llm_service=mock_llm, storage=storage),
        ]
        app = create_app(storage=storage, job_store=job_store, agents=agents)
        client = TestClient(app)

        resp = client.post("/generate", json={"prompt": "test"})
        job_id = resp.json()["job_id"]

        result_resp = client.get(f"/result/{job_id}")
        assert result_resp.status_code == 200
        data = result_resp.json()
        assert data["status"] == "completed"
        assert len(data["artifacts"]) == 4  # brief, research, script, storyboard
```

- [x] **Step 2: Update `/result` endpoint to return actual artifacts from WorkflowState**

Modify the `result` endpoint in `routes.py` to load artifacts from the WorkflowState:

```python
    @app.get("/result/{job_id}", response_model=ResultResponse)
    def result(job_id: str) -> ResultResponse:
        record = job_store.get(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Job not found")
        if record.status != JobStatus.COMPLETED:
            raise HTTPException(
                status_code=409,
                detail=f"Job is {record.status.value}, not completed",
            )
        context_data = storage.load(job_id, "pipeline", "context.json")
        artifacts = []
        if context_data is not None:
            ctx = WorkflowState.model_validate(context_data)
            for agent_result in ctx.agent_results.values():
                artifacts.extend(agent_result.artifacts)
        return ResultResponse(
            job_id=record.job_id,
            status=record.status,
            output_path=f"./outputs/{job_id}",
            artifacts=artifacts,
        )
```

- [x] **Step 3: Run tests to verify they pass**

Run: `venv\Scripts\python.exe -m pytest tests/test_api/test_routes.py -v`
Expected: ALL PASS (14 original + 1 pipeline + 3 status consistency = 18 tests)

- [x] **Step 4: Commit**

```bash
git add backend/api/routes.py tests/test_api/test_routes.py
git commit -m "feat: sync JobRecord status from Pipeline and return real artifacts in /result"
```

---

## Task 8: Full Integration Verification

**Files:**

- No new files — just run the full test suite and verify

- [ ] **Step 1: Run complete test suite**

Run: `venv\Scripts\python.exe -m pytest -v`
Expected: ALL PASS — Phase 1 (115) + Phase 2 new tests

- [ ] **Step 2: Run with coverage**

Run: `venv\Scripts\python.exe -m pytest --cov=agents --cov=tools --cov=backend --cov=workflow --cov=models --cov=storage --cov-report=term-missing`
Expected: High coverage on all Phase 2 agent and LLM code

- [ ] **Step 3: Manual smoke test — start server and hit endpoints**

```bash
venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

Then in another terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/generate -ContentType "application/json" -Body '{"prompt":"Create a 30-second explainer about artificial intelligence"}'
```

Expected: This will make real LLM calls (requires `LLM_API_KEY` in `.env`). If API key is missing, the pipeline will fail — that's expected. Verify `/status` shows `failed` with appropriate error.

- [ ] **Step 4: Commit (if any fixes needed from smoke test)**

```bash
git add -A
git commit -m "fix: any adjustments from integration verification"
```

---

## Test Count Summary

| Layer                  | File                                   | Tests        |
| ---------------------- | -------------------------------------- | ------------ |
| AlibabaCloudLLMService | `tests/test_tools/test_llm.py`         | +5 (total 9) |
| Director Agent         | `tests/test_agents/test_director.py`   | +8           |
| Research Agent         | `tests/test_agents/test_research.py`   | +7           |
| Script Agent           | `tests/test_agents/test_script.py`     | +8           |
| Storyboard Agent       | `tests/test_agents/test_storyboard.py` | +7           |
| Pipeline Wiring        | `tests/test_api/test_routes.py`        | +1           |
| Status Sync            | `tests/test_api/test_routes.py`        | +3           |
| **Phase 2 Total**      |                                        | **+31**      |
| **Phase 1 + 2 Total**  |                                        | **146**      |

---

## Self-Review Checklist

1. **Spec coverage:** Each Phase 2 requirement (Director, Research, Script, Storyboard, LLM service, API wiring) has corresponding tasks. ✅
2. **Placeholder scan:** No TBD, TODO, or "implement later" in any step. All code shown explicitly. ✅
3. **Type consistency:** `DirectorAgent`, `ResearchAgent`, `ScriptAgent`, `StoryboardAgent` all use `AgentResult.output_data` as dict with `model_dump(mode="json")`. Downstream agents validate with `model_validate()`. `AlibabaCloudLLMService.generate()` returns `str`, agents parse with `model_validate_json()`. ✅
