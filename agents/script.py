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
{scene_count_rule}
Respond ONLY with valid JSON. No explanation, no markdown, no commentary."""


class ScriptAgent:
    name = AgentName.SCRIPT

    def __init__(self, llm_service: LLMService, storage: StorageBackend | None = None) -> None:
        self.llm_service = llm_service
        self.storage = storage

    @staticmethod
    def _parse(raw_response: str) -> Script:
        try:
            return Script.model_validate_json(raw_response)
        except Exception as exc:
            raise ValueError(
                f"Script agent failed to parse LLM response as Script: {exc}"
            ) from exc

    @staticmethod
    def _count_error(
        script: Script,
        requested_count: int | None,
    ) -> str | None:
        if requested_count is None or len(script.scenes) == requested_count:
            return None
        noun = "scene" if requested_count == 1 else "scenes"
        return (
            f"Script must contain exactly {requested_count} {noun}; "
            f"received {len(script.scenes)}"
        )

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

        scene_count_rule = (
            f"Produce exactly {brief.requested_scene_count} "
            f"{'scene' if brief.requested_scene_count == 1 else 'scenes'}."
            if brief.requested_scene_count is not None
            else "Choose the scene count that best fits the brief."
        )
        prompt = SCRIPT_PROMPT_TEMPLATE.format(
            brief_json=brief.model_dump_json(),
            research_json=research.model_dump_json(),
            duration_target=brief.duration_seconds,
            scene_count_rule=scene_count_rule,
        )
        raw_response = self.llm_service.generate(prompt, self.name)
        script = self._parse(raw_response)
        error = self._count_error(script, brief.requested_scene_count)
        if error is not None:
            correction_prompt = (
                f"{prompt}\n\nYour previous JSON violated this constraint: "
                f"{error}. Return a corrected complete Script JSON object only."
            )
            script = self._parse(
                self.llm_service.generate(correction_prompt, self.name)
            )
            error = self._count_error(script, brief.requested_scene_count)
            if error is not None:
                raise ValueError(error)

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
