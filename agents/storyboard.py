"""Storyboard agent — converts script scenes into a shot list with visual prompts."""

import math

from models.enums import AgentName
from models.agent_result import AgentResult, ArtifactRef
from models.brief import CreativeBrief
from models.script import Script
from models.storyboard import Storyboard
from models.workflow_state import WorkflowState
from storage.base import StorageBackend
from tools.llm import LLMService


STORYBOARD_PROMPT_TEMPLATE = """You are the Storyboard agent in a video production pipeline.
Given the creative brief and script, convert each scene into detailed shot descriptions for video generation.

Creative brief:
{brief_json}

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
{shot_count_rule}
Use visible, renderable details only: subject geometry/material, environment,
composition, visible action, camera, lighting, and color.
Avoid brand/style-owner names, authenticity claims, texture-resolution claims,
sound instructions, and exact frame timing.
For voxel or block-game visuals, explicitly request cubic geometry, flat pixel textures,
clean square edges, and no photorealistic foliage.
Respond ONLY with valid JSON. No explanation, no markdown, no commentary."""


class StoryboardAgent:
    name = AgentName.STORYBOARD

    def __init__(self, llm_service: LLMService, storage: StorageBackend | None = None) -> None:
        self.llm_service = llm_service
        self.storage = storage

    @staticmethod
    def _parse(raw_response: str) -> Storyboard:
        try:
            return Storyboard.model_validate_json(raw_response)
        except Exception as exc:
            raise ValueError(
                "Storyboard agent failed to parse LLM response as "
                f"Storyboard: {exc}"
            ) from exc

    @staticmethod
    def _constraint_errors(
        storyboard: Storyboard,
        script: Script,
        requested_shot_count: int | None,
    ) -> list[str]:
        errors: list[str] = []
        if (
            requested_shot_count is not None
            and len(storyboard.shots) != requested_shot_count
        ):
            noun = "shot" if requested_shot_count == 1 else "shots"
            errors.append(
                f"Storyboard must contain exactly {requested_shot_count} "
                f"{noun}; received {len(storyboard.shots)}"
            )

        scene_numbers = {scene.scene_number for scene in script.scenes}
        for shot in storyboard.shots:
            if shot.scene_number not in scene_numbers:
                errors.append(
                    f"Storyboard shot {shot.shot_number} references unknown "
                    f"script scene {shot.scene_number}"
                )

        for scene in script.scenes:
            durations = [
                shot.duration
                for shot in storyboard.shots
                if shot.scene_number == scene.scene_number
            ]
            if not durations:
                errors.append(
                    f"Storyboard must cover script scene {scene.scene_number}"
                )
            elif not math.isclose(
                sum(durations),
                scene.duration_hint,
                rel_tol=0.10,
                abs_tol=0.25,
            ):
                errors.append(
                    f"Storyboard scene {scene.scene_number} duration must be "
                    f"approximately {scene.duration_hint}s; received "
                    f"{sum(durations)}s"
                )
        return errors

    def run(self, context: WorkflowState) -> WorkflowState:
        if AgentName.SCRIPT not in context.agent_results:
            raise ValueError("Storyboard agent requires Script output in context")
        if AgentName.DIRECTOR not in context.agent_results:
            raise ValueError("Storyboard agent requires Director output in context")

        brief = CreativeBrief.model_validate(
            context.agent_results[AgentName.DIRECTOR].output_data
        )
        script = Script.model_validate(
            context.agent_results[AgentName.SCRIPT].output_data
        )

        shot_count_rule = (
            f"Produce exactly {brief.requested_shot_count} total "
            f"{'shot' if brief.requested_shot_count == 1 else 'shots'}."
            if brief.requested_shot_count is not None
            else "Choose the shot count that best fits the script."
        )
        prompt = STORYBOARD_PROMPT_TEMPLATE.format(
            brief_json=brief.model_dump_json(),
            script_json=script.model_dump_json(),
            shot_count_rule=shot_count_rule,
        )
        raw_response = self.llm_service.generate(prompt, self.name)
        storyboard = self._parse(raw_response)
        errors = self._constraint_errors(
            storyboard,
            script,
            brief.requested_shot_count,
        )
        if errors:
            correction_prompt = (
                f"{prompt}\n\nYour previous JSON violated these constraints: "
                f"{'; '.join(errors)}. Return a corrected complete Storyboard "
                "JSON object only."
            )
            storyboard = self._parse(
                self.llm_service.generate(correction_prompt, self.name)
            )
            errors = self._constraint_errors(
                storyboard,
                script,
                brief.requested_shot_count,
            )
            if errors:
                raise ValueError("; ".join(errors))

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
