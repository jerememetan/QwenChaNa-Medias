---
name: create-agent
description: Scaffold a new pipeline agent following the video platform architecture. Use when adding a new agent to the pipeline or replacing an existing one.
---

This skill creates a new pipeline agent that conforms to the video platform's architecture conventions.

## When to Use

- Adding a new agent to the video generation pipeline
- Replacing an existing agent with a new implementation
- Creating a utility agent (e.g., validator, reviewer)

## Steps

### 1. Create the Agent File

Create `app/agents/<agent_name>.py` with this structure:

```python
from app.agents.base import BaseAgent
from app.orchestrator.context import JobContext

class <AgentName>Agent(BaseAgent):
    """<One-line description of responsibility>."""
    
    agent_name = "<agent_name>"
    
    async def run(self, context: JobContext) -> JobContext:
        # 1. Read inputs from context
        input_data = context.get("<upstream_output_key>")
        
        # 2. Do work (LLM call, API call, etc.)
        result = await self.process(input_data)
        
        # 3. Persist artifacts to disk
        output_path = context.get_artifact_path(self.agent_name, "<filename>")
        await self.save_artifact(output_path, result)
        
        # 4. Update context with outputs
        context.set("<this_output_key>", result)
        
        return context
```

### 2. Register in Pipeline

Add the agent to `app/orchestrator/pipeline.py`:

```python
from app.agents.<agent_name> import <AgentName>Agent

PIPELINE_AGENTS = [
    ...
    <AgentName>Agent(),
]
```

### 3. Add Tests

Create `tests/test_agents/test_<agent_name>.py`:

```python
import pytest
from app.agents.<agent_name> import <AgentName>Agent
from app.orchestrator.context import JobContext

class Test<AgentName>Agent:
    @pytest.fixture
    def agent(self):
        return <AgentName>Agent()
    
    @pytest.fixture
    def context(self):
        ctx = JobContext(job_id="test-job")
        ctx.set("<required_input>", <mock_data>)
        return ctx
    
    async def test_run_produces_expected_output(self, agent, context):
        result = await agent.run(context)
        assert result.get("<output_key>") is not None
    
    async def test_run_persists_artifacts(self, agent, context, tmp_path):
        context.output_dir = tmp_path
        await agent.run(context)
        assert (tmp_path / "test-job" / "<agent_name>").exists()
```

### 4. Update PROJECT_SPEC.md

Add the agent to the Architecture diagram and Agent Responsibilities section.

## Checklist

- [ ] Agent inherits from `BaseAgent`
- [ ] `agent_name` class attribute is set (snake_case)
- [ ] `run()` is async and returns `JobContext`
- [ ] Reads inputs from context (not from constructor args)
- [ ] Writes outputs to context AND persists to disk
- [ ] Unit tests cover: happy path, missing input, artifact persistence
- [ ] Added to `PIPELINE_AGENTS` list in correct order
