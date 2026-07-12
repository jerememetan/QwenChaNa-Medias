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
            raise ValueError(
                f"Director agent failed to parse LLM response as CreativeBrief: {exc}"
            ) from exc

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
