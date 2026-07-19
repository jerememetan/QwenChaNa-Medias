# Phase 4.1 Constraint-Aware Timing Design

## Problem

Job `353205a6-aa09-40a2-a26a-dc58c13f4ce0` exposed three contract failures:

- The user requested one five-second scene and one shot, but Storyboard emitted two shots. Video therefore made two paid Wan calls.
- Storyboard planned durations of 0.65s and 4.35s, while Wan returned two 5.37s clips. Editor concatenated full clips instead of trimming them to planned durations.
- Narration lasted 1.89s. Editor used narration as the entire scene duration, producing a 1.90s final video that ended during shot 1. Shot 2 never appeared.

The same job also showed prompt-quality problems: Minecraft-style instructions became photorealistic moss and a dark crystal. Research invented unverifiable sources and marked several claims verified despite having no retrieval tool.

## Goals

1. Enforce explicit user scene and shot counts before any paid video generation.
2. Preserve storyboard timing even when generated clips have fixed or inaccurate durations.
3. Preserve narration without letting short narration shorten the planned video.
4. Avoid unnecessary Research calls and fabricated verification for simple creative prompts.
5. Produce visual prompts that describe visible geometry and motion instead of brand or implementation claims.

## Non-Goals

- Reviewer Agent or automatic video regeneration.
- Semantic scoring of generated video quality.
- LangGraph branching or parallel execution.
- General natural-language parsing outside constraints extracted by Director.
- Changing Wan or CosyVoice providers.

## Selected Approach

Use structured constraints plus deterministic validation and timing. Prompt-only enforcement is too unreliable; a Reviewer/regeneration loop would consume more credits and belongs in Phase 5.

### Creative Brief Constraints

Extend `CreativeBrief` with:

```python
requested_scene_count: int | None = Field(default=None, ge=1)
requested_shot_count: int | None = Field(default=None, ge=1)
requires_research: bool = True
```

Director must extract counts only when the user states them explicitly. It sets `requires_research=false` for fictional, promotional, aesthetic, or otherwise creative prompts that need no factual claims. Informational prompts retain `requires_research=true`.

### Honest Research Behavior

Research Agent remains in the sequential pipeline so downstream contracts do not change.

- When `requires_research=false`, it emits empty `ResearchNotes` locally and does not call the LLM.
- When research is required, LLM-only notes cannot claim external verification. Research Agent normalizes every returned note to `source=None` and `verified=false`. A future retrieval-backed implementation may preserve real citations.

### Script and Storyboard Enforcement

Script receives the requested scene count in its prompt. Storyboard receives both the script and Creative Brief, including requested total shot count.

After parsing:

- Script must contain exactly `requested_scene_count` scenes when set.
- Storyboard must contain exactly `requested_shot_count` shots when set.
- Every Script scene must have at least one Storyboard shot.
- Shot durations for each scene must sum approximately to that scene's duration hint.

For an explicit count mismatch, the agent makes one inexpensive correction call with the validation error and required count. If the corrected response still violates the constraint, the job fails at Script or Storyboard before Video Agent runs.

### Model-Friendly Storyboard Prompts

Storyboard visual prompts must contain only renderable visual information:

- subject shape and material;
- environment and composition;
- visible action;
- camera framing and movement;
- lighting and color.

They must avoid owner/style names, unverifiable authenticity claims, texture-resolution claims, sound instructions, and frame-accurate timing. For voxel or block-game requests, prompts explicitly require cubic geometry, flat pixel textures, and no photorealistic foliage.

Example transformation:

```text
Before: Mojang-authentic pixel-perfect 16×16 Minecraft grass block.
After: A sharp cubic grass-and-soil block in a bright voxel game world,
flat pixel textures, clean square edges, no realistic leaves or photography.
```

## Editor Timing Contract

Replace parallel clip path/duration assumptions with explicit media values:

```python
class ClipMedia(BaseModel):
    shot_number: int = Field(ge=1)
    file_path: str = Field(min_length=1)
    planned_duration: float = Field(gt=0)


class SceneMedia(BaseModel):
    scene_number: int = Field(ge=1)
    clips: list[ClipMedia] = Field(min_length=1)
    narration_path: str = Field(min_length=1)
    planned_duration: float = Field(gt=0)
```

Editor maps each `VideoClip` to its Storyboard shot and copies the Storyboard duration into `ClipMedia.planned_duration`. `SceneMedia.planned_duration` is the sum of its planned clip durations.

FFmpeg processes a scene as follows:

1. Trim each generated clip to its `planned_duration` before concatenation.
2. Concatenate trimmed clips in Storyboard order.
3. Probe actual narration duration.
4. Set `target_duration = max(scene.planned_duration, narration_duration)`.
5. Hold the final visual frame when trimmed visuals are shorter than target.
6. Pad narration with silence when narration is shorter than target.
7. Render exactly `target_duration` seconds.

For the observed job, this would either enforce one five-second shot or, if two shots were allowed, trim them to 0.65s and 4.35s. The 1.89s narration would be followed by silence, and the final video would remain five seconds.

## Failure Behavior

- Invalid explicit counts fail before Video Agent, preventing wasted video calls.
- Missing scene coverage, missing media, invalid durations, or FFmpeg probe failures remain typed pipeline failures with persisted context.
- Constraint correction is attempted once only; no unbounded LLM retries.
- Existing resume behavior reruns the first failed agent while preserving successful upstream work.

## Testing

- Director model and prompt tests for explicit counts and `requires_research`.
- Research tests proving creative prompts make zero LLM calls and factual LLM-only notes cannot claim verification.
- Script and Storyboard tests for valid counts, one correction call, and failure after a second violation.
- Pipeline test proving Video Agent is not called after Storyboard constraint failure.
- Editor tests proving Storyboard durations enter `ClipMedia` in order.
- Real local FFmpeg test with a 5s generated clip, 2s planned duration, and 1s narration; final duration must be approximately 2s with audio present.
- Local seven-agent E2E test for exactly one five-second scene and one shot.
- Full quota-free test suite; live Alibaba smoke testing remains manual.

## Deferred Work

Generated-video semantic review, automated regeneration, negative-prompt provider support, retrieval-backed citations, and cost-aware routing remain future work.
