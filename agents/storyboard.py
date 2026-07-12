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
            raise ValueError(
                f"Storyboard agent failed to parse LLM response as Storyboard: {exc}"
            ) from exc

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
