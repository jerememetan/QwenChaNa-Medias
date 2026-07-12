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
            raise ValueError(
                f"Research agent failed to parse LLM response as ResearchNotes: {exc}"
            ) from exc

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
