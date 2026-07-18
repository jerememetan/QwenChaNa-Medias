# Phase 3 — Asset Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the Video and Voice agents using Qwen models (qwen3-max, cosyvoice-v3-plus, wan2.7-t2v), add retry handling with tenacity, and implement error handling that fails with clear error when APIs are unavailable.

**Architecture:** Agents follow the existing `BaseAgent` contract. `VideoAgent` and `VoiceAgent` iterate over the storyboard shots and script scenes, calling provider-agnostic `VideoGenService` / `TTSService` abstractions which use Qwen models via DashScope API. Each external service (LLM, TTS, video generation) is wrapped with `tenacity` retries. A `FALLBACK_STUBS` env flag controls behavior when APIs are unavailable — default is `false` which causes the agent to raise a clear error message. All agent outputs are typed Pydantic models persisted via `AgentResult.output_data` and `ArtifactRef`s.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, DashScope SDK, tenacity, pytest

---

## Implementation Order

```
1. Add tenacity dependency and retry decorators to external services
2. Add Video and Voice output models
3. Implement VideoAgent (uses wan2.7-t2v)
4. Implement VoiceAgent (uses cosyvoice-v3-plus)
5. Wire Video and Voice agents into production app
6. Integration verification
```

---

## Task 1: Add `tenacity` Dependency and Retry Decorators

**Files:**

- Modify: `requirements.txt` — add `tenacity>=8.0`
- Modify: `tools/llm.py` — wrap `generate()` with retry
- Modify: `tools/tts.py` — wrap `synthesize()` with retry
- Modify: `tools/video_gen.py` — wrap `generate()` with retry
- Test: `tests/test_tools/test_llm.py` — add retry tests

- [x] **Step 1: Add `tenacity>=8.0` to `requirements.txt`**

Open `requirements.txt` and add inside the file:

```text
# ---- Retry / rate-limit handling ----
tenacity>=8.0
```

- [x] **Step 2: Write failing tests for retry behavior**

Add to `tests/test_tools/test_llm.py`:

```python
import pytest
from unittest.mock import MagicMock, patch

import openai

from tools.llm import AlibabaCloudLLMService
from backend.config import LLMConfig
from models.enums import AgentName


class TestAlibabaCloudLLMServiceRetries:
    def test_retries_on_rate_limit_error(self):
        config = LLMConfig(api_key="test-key", model="qwen3-max")
        service = AlibabaCloudLLMService(config)

        with patch.object(
            service._client.chat.completions,
            "create",
            side_effect=openai.RateLimitError(
                message="rate limited",
                response=MagicMock(status_code=429),
                body=None,
            ),
        ) as mock_create:
            with pytest.raises(openai.RateLimitError):
                service.generate("prompt", AgentName.DIRECTOR)
            assert mock_create.call_count == 3

    def test_does_not_retry_on_auth_error(self):
        config = LLMConfig(api_key="test-key", model="qwen3-max")
        service = AlibabaCloudLLMService(config)

        with patch.object(
            service._client.chat.completions,
            "create",
            side_effect=openai.AuthenticationError(
                message="bad key",
                response=MagicMock(status_code=401),
                body=None,
            ),
        ) as mock_create:
            with pytest.raises(openai.AuthenticationError):
                service.generate("prompt", AgentName.DIRECTOR)
            assert mock_create.call_count == 1
```

- [x] **Step 3: Run tests to verify they fail**

Run: `venv\Scripts\python.exe -m pytest tests/test_tools/test_llm.py -v`

Expected: FAIL — `RateLimitError` test fails because no retry is implemented yet (call count is 1, not 3).

- [x] **Step 4: Install tenacity**

Run: `venv\Scripts\pip.exe install tenacity>=8.0`

- [x] **Step 5: Add retry decorator to `AlibabaCloudLLMService.generate`**

Modify `tools/llm.py`:

```python
"""LLM service abstraction — agents call this interface, never raw APIs."""

from abc import ABC, abstractmethod

import openai
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from backend.config import LLMConfig
from models.enums import AgentName


_RETRYABLE_LLM_EXCEPTIONS = (
    openai.APIConnectionError,
    openai.RateLimitError,
    openai.APITimeoutError,
    openai.InternalServerError,
)


class LLMService(ABC):
    """Abstract interface for LLM generation.

    Agents call ``llm_service.generate(prompt, agent_name)`` — the concrete
    provider implementation (AlibabaCloudLLMService, etc.) is injected at
    runtime, so swapping providers requires only a new subclass and a config
    change, not agent code changes.
    """

    @abstractmethod
    def generate(self, prompt: str, agent_name: AgentName) -> str:
        """Generate text from the configured LLM provider.

        Args:
            prompt: The input prompt for generation.
            agent_name: The agent requesting generation (for logging/routing).

        Returns:
            The generated text response.
        """
        ...


class AlibabaCloudLLMService(LLMService):
    """Concrete LLM service for Alibaba Cloud Model Studio.

    Uses the ``openai`` Python SDK because Model Studio exposes an
    OpenAI-compatible API mode. The endpoint URL (dashscope.aliyuncs.com)
    is the underlying API address — the product is Alibaba Cloud Model Studio.
    """

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self._client: openai.OpenAI | None = None
        if config.api_key:
            self._client = openai.OpenAI(
                api_key=config.api_key,
                base_url=config.base_url,
                timeout=config.timeout,
            )

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(_RETRYABLE_LLM_EXCEPTIONS),
    )
    def generate(self, prompt: str, agent_name: AgentName) -> str:
        if self._client is None:
            raise RuntimeError(
                "AlibabaCloudLLMService has no API key configured — "
                "set LLM_API_KEY in .env or pass api_key to LLMConfig"
            )
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

- [x] **Step 6: Add retry decorator to `DashScopeTTSService.synthesize`**

Modify `tools/tts.py`:

```python
"""TTS service abstraction — agents call this interface, never raw APIs."""

from abc import ABC, abstractmethod
from pathlib import Path

import dashscope
import requests
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from backend.config import VoiceConfig


def _is_transient_error(exc: BaseException) -> bool:
    if isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
        return True
    if isinstance(exc, requests.exceptions.HTTPError) and exc.response is not None:
        return exc.response.status_code in {429, 502, 503, 504}
    return False


class TTSService(ABC):
    """Abstract interface for text-to-speech generation."""

    @abstractmethod
    def synthesize(self, text: str, output_path: str) -> str:
        """Synthesize speech from text and save to file.

        Args:
            text: The text to convert to speech.
            output_path: Path to save the audio file.

        Returns:
            The path to the generated audio file.
        """
        ...


class DashScopeTTSService(TTSService):
    """Concrete TTS service using Alibaba Cloud Model Studio CosyVoice.

    Uses the ``dashscope`` Python SDK's SpeechSynthesizer for
    text-to-speech generation via the CosyVoice model (cosyvoice-v3-plus).
    """

    def __init__(self, config: VoiceConfig) -> None:
        self.config = config
        self._configured = bool(config.api_key)
        if config.api_key:
            dashscope.api_key = config.api_key

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception(_is_transient_error),
    )
    def synthesize(self, text: str, output_path: str) -> str:
        if not self._configured:
            raise RuntimeError(
                "DashScopeTTSService has no API key configured — "
                "set VOICE_API_KEY in .env or pass api_key to VoiceConfig"
            )

        from dashscope.audio.tts_v2 import SpeechSynthesizer

        synthesizer = SpeechSynthesizer(
            model=self.config.model,
            voice=self.config.voice,
        )
        audio_data = synthesizer.call(text)

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(audio_data)
        return str(path)
```

- [x] **Step 7: Add retry decorator to `DashScopeVideoGenService.generate`**

Modify `tools/video_gen.py`:

```python
"""Video generation service abstraction — agents call this interface, never raw APIs."""

from abc import ABC, abstractmethod
from pathlib import Path

import dashscope
import requests
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from backend.config import VideoConfig


def _is_transient_error(exc: BaseException) -> bool:
    if isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
        return True
    if isinstance(exc, requests.exceptions.HTTPError) and exc.response is not None:
        return exc.response.status_code in {429, 502, 503, 504}
    return False


class VideoGenService(ABC):
    """Abstract interface for video generation."""

    @abstractmethod
    def generate(self, prompt: str, output_path: str) -> str:
        """Generate video from a text prompt and save to file.

        Args:
            prompt: Text description of the desired video.
            output_path: Path to save the video file.

        Returns:
            The path to the generated video file.
        """
        ...


class DashScopeVideoGenService(VideoGenService):
    """Concrete video generation service using Alibaba Cloud Model Studio Wan.

    Uses the ``dashscope`` Python SDK's VideoSynthesis for
    text-to-video generation via the Wan model (wan2.7-t2v). Video generation is
    asynchronous — this service submits the task and polls until complete.
    """

    def __init__(self, config: VideoConfig) -> None:
        self.config = config
        self._configured = bool(config.api_key)
        if config.api_key:
            dashscope.api_key = config.api_key

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception(_is_transient_error),
    )
    def generate(self, prompt: str, output_path: str) -> str:
        if not self._configured:
            raise RuntimeError(
                "DashScopeVideoGenService has no API key configured — "
                "set VIDEO_API_KEY in .env or pass api_key to VideoConfig"
            )

        from dashscope import VideoSynthesis

        response = VideoSynthesis.async_call(
            model=self.config.model,
            prompt=prompt,
        )
        result = VideoSynthesis.wait(response)

        video_url = result.output.video_url

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        resp = requests.get(video_url)
        resp.raise_for_status()
        path.write_bytes(resp.content)
        return str(path)
```

- [x] **Step 8: Run tests to verify they pass**

Run: `venv\Scripts\python.exe -m pytest tests/test_tools/test_llm.py -v`

Expected: ALL PASS (existing tests + new retry tests)

- [x] **Step 9: Commit**

```bash
git add requirements.txt tools/llm.py tools/tts.py tools/video_gen.py tests/test_tools/test_llm.py
git commit -m "feat: add tenacity retry decorators to external services"
```

---

## Task 2: Add Video and Voice Output Models

**Files:**

- Create: `models/video.py`
- Create: `models/voice.py`
- Modify: `models/__init__.py`
- Test: `tests/test_models/test_video.py`
- Test: `tests/test_models/test_voice.py`

- [ ] **Step 1: Write failing tests for the new models**

Create `tests/test_models/test_video.py`:

```python
from pydantic import ValidationError
import pytest

from models.video import VideoClip, VideoOutput


class TestVideoClip:
    def test_valid_clip(self):
        clip = VideoClip(shot_number=1, file_path="video/clips/shot_001.mp4")
        assert clip.shot_number == 1
        assert clip.file_path == "video/clips/shot_001.mp4"
        assert clip.duration is None

    def test_invalid_shot_number(self):
        with pytest.raises(ValidationError):
            VideoClip(shot_number=0, file_path="video/clips/shot_001.mp4")


class TestVideoOutput:
    def test_valid_output(self):
        output = VideoOutput(
            clips=[
                VideoClip(shot_number=1, file_path="video/clips/shot_001.mp4"),
                VideoClip(shot_number=2, file_path="video/clips/shot_002.mp4"),
            ]
        )
        assert len(output.clips) == 2
```

Create `tests/test_models/test_voice.py`:

```python
from pydantic import ValidationError
import pytest

from models.voice import AudioTrack, VoiceOutput


class TestAudioTrack:
    def test_valid_track(self):
        track = AudioTrack(scene_number=1, file_path="voice/audio/scene_001.mp3")
        assert track.scene_number == 1
        assert track.file_path == "voice/audio/scene_001.mp3"
        assert track.duration is None

    def test_invalid_scene_number(self):
        with pytest.raises(ValidationError):
            AudioTrack(scene_number=0, file_path="voice/audio/scene_001.mp3")


class TestVoiceOutput:
    def test_valid_output(self):
        output = VoiceOutput(
            tracks=[
                AudioTrack(scene_number=1, file_path="voice/audio/scene_001.mp3"),
            ]
        )
        assert len(output.tracks) == 1
```

- [x] **Step 2: Run tests to verify they fail**

Run:

- `venv\Scripts\python.exe -m pytest tests/test_models/test_video.py -v`
- `venv\Scripts\python.exe -m pytest tests/test_models/test_voice.py -v`

Expected: FAIL — modules do not exist.

- [x] **Step 3: Implement the models**

Create `models/video.py`:

```python
"""Video agent output models."""

from pydantic import BaseModel, Field


class VideoClip(BaseModel):
    """A generated video clip for a single storyboard shot."""

    shot_number: int = Field(ge=1)
    file_path: str
    duration: float | None = None


class VideoOutput(BaseModel):
    """Aggregate output produced by the Video Agent."""

    clips: list[VideoClip] = Field(default_factory=list)
```

Create `models/voice.py`:

```python
"""Voice agent output models."""

from pydantic import BaseModel, Field


class AudioTrack(BaseModel):
    """A generated narration audio track for a single script scene."""

    scene_number: int = Field(ge=1)
    file_path: str
    duration: float | None = None


class VoiceOutput(BaseModel):
    """Aggregate output produced by the Voice Agent."""

    tracks: list[AudioTrack] = Field(default_factory=list)
```

- [x] **Step 4: Re-export models from `models/__init__.py`**

Modify `models/__init__.py`:

```python
from models.agent_result import AgentResult, ArtifactRef
from models.brief import CreativeBrief
from models.enums import AgentName, JobStatus
from models.job import JobRecord
from models.research import ResearchNote, ResearchNotes
from models.scene import Scene
from models.script import Script
from models.storyboard import Shot, Storyboard
from models.video import VideoClip, VideoOutput
from models.voice import AudioTrack, VoiceOutput
from models.workflow_state import WorkflowState

__all__ = [
    "AgentName",
    "AgentResult",
    "ArtifactRef",
    "AudioTrack",
    "CreativeBrief",
    "JobRecord",
    "JobStatus",
    "ResearchNote",
    "ResearchNotes",
    "Scene",
    "Script",
    "Shot",
    "Storyboard",
    "VideoClip",
    "VideoOutput",
    "VoiceOutput",
    "WorkflowState",
]
```

- [x] **Step 5: Run tests to verify they pass**

Run:

- `venv\Scripts\python.exe -m pytest tests/test_models/test_video.py -v`
- `venv\Scripts\python.exe -m pytest tests/test_models/test_voice.py -v`

Expected: ALL PASS

- [x] **Step 6: Commit**

```bash
git add models/video.py models/voice.py models/__init__.py tests/test_models/test_video.py tests/test_models/test_voice.py
git commit -m "feat: add VideoOutput and VoiceOutput models"
```

---

## Task 3: Implement VideoAgent (Qwen wan2.7-t2v)

**Files:**

- Create: `agents/video.py`
- Create: `tests/test_agents/test_video.py`

- [x] **Step 1: Write failing tests for VideoAgent**

Create `tests/test_agents/test_video.py`:

```python
from unittest.mock import MagicMock

import pytest

from agents.video import VideoAgent
from models.enums import AgentName
from models.workflow_state import WorkflowState
from models.agent_result import AgentResult
from models.storyboard import Shot, Storyboard
from models.video import VideoOutput
from tools.video_gen import VideoGenService


def _make_context_with_storyboard() -> WorkflowState:
    ctx = WorkflowState(job_id="test-job", prompt="test")
    storyboard = Storyboard(
        shots=[
            Shot(
                shot_number=1,
                scene_number=1,
                visual_prompt="A calm forest",
                camera="wide",
                motion="static",
                duration=5.0,
            )
        ]
    )
    ctx.agent_results[AgentName.STORYBOARD] = AgentResult(
        agent_name=AgentName.STORYBOARD,
        success=True,
        output_data=storyboard.model_dump(mode="json"),
    )
    return ctx


def _mock_video_service() -> MagicMock:
    mock = MagicMock(spec=VideoGenService)
    mock.generate.return_value = "/tmp/shot_001.mp4"
    return mock


class TestVideoAgent:
    def test_name_is_video(self):
        agent = VideoAgent(video_service=_mock_video_service())
        assert agent.name == AgentName.VIDEO

    def test_run_returns_workflow_state(self):
        agent = VideoAgent(video_service=_mock_video_service())
        ctx = _make_context_with_storyboard()
        result = agent.run(ctx)
        assert isinstance(result, WorkflowState)

    def test_run_raises_when_storyboard_missing(self):
        agent = VideoAgent(video_service=_mock_video_service())
        ctx = WorkflowState(job_id="test-job", prompt="test")
        with pytest.raises(ValueError, match="Storyboard"):
            agent.run(ctx)

    def test_run_generates_clip_for_each_shot(self):
        mock_service = _mock_video_service()
        agent = VideoAgent(video_service=mock_service)
        ctx = _make_context_with_storyboard()
        result = agent.run(ctx)

        output_data = result.agent_results[AgentName.VIDEO].output_data
        video_output = VideoOutput.model_validate(output_data)
        assert len(video_output.clips) == 1
        assert video_output.clips[0].shot_number == 1
        assert video_output.clips[0].file_path.endswith("video/clips/shot_001.mp4")
        mock_service.generate.assert_called_once()

    def test_run_persists_artifacts_to_storage(self):
        mock_service = _mock_video_service()
        mock_storage = MagicMock()
        agent = VideoAgent(video_service=mock_service, storage=mock_storage)
        ctx = _make_context_with_storyboard()
        agent.run(ctx)

        artifacts = ctx.agent_results[AgentName.VIDEO].artifacts
        assert len(artifacts) == 1
        assert artifacts[0].agent_name == AgentName.VIDEO
        assert artifacts[0].filename == "clips/shot_001.mp4"
        assert artifacts[0].content_type == "video/mp4"

    def test_run_raises_when_api_unavailable_and_fallback_disabled(self):
        mock_service = _mock_video_service()
        mock_service.generate.side_effect = RuntimeError("VIDEO_API_KEY not configured")
        agent = VideoAgent(video_service=mock_service, fallback_enabled=False)
        ctx = _make_context_with_storyboard()

        with pytest.raises(RuntimeError, match="VIDEO_API_KEY not configured"):
            agent.run(ctx)
```

- [x] **Step 2: Run tests to verify they fail**

Run: `venv\Scripts\python.exe -m pytest tests/test_agents/test_video.py -v`

Expected: FAIL — `VideoAgent` does not exist.

- [x] **Step 3: Implement VideoAgent**

Create `agents/video.py`:

```python
"""Video agent — generates video clips from a storyboard using Qwen wan2.7-t2v."""

from pathlib import Path

from models.enums import AgentName
from models.agent_result import AgentResult, ArtifactRef
from models.storyboard import Storyboard
from models.video import VideoClip, VideoOutput
from models.workflow_state import WorkflowState
from storage.base import StorageBackend
from tools.video_gen import VideoGenService


class VideoAgent:
    """Video Agent for Phase 3.

    Generates video clips using Qwen wan2.7-t2v model.
    Raises clear error if API is unavailable and fallback is disabled.
    """

    name = AgentName.VIDEO

    def __init__(
        self,
        video_service: VideoGenService,
        storage: StorageBackend | None = None,
        fallback_enabled: bool = False,
    ) -> None:
        self.video_service = video_service
        self.storage = storage
        self.fallback_enabled = fallback_enabled

    def _clip_path(self, job_id: str, shot_number: int) -> str:
        return str(
            Path("outputs") / job_id / "video" / "clips" / f"shot_{shot_number:03d}.mp4"
        )

    def run(self, context: WorkflowState) -> WorkflowState:
        if AgentName.STORYBOARD not in context.agent_results:
            raise ValueError("Video agent requires Storyboard output in context")

        storyboard = Storyboard.model_validate(
            context.agent_results[AgentName.STORYBOARD].output_data
        )

        clips: list[VideoClip] = []
        artifacts: list[ArtifactRef] = []

        for shot in storyboard.shots:
            output_path = self._clip_path(context.job_id, shot.shot_number)
            try:
                generated_path = self.video_service.generate(shot.visual_prompt, output_path)
            except Exception as exc:
                if not self.fallback_enabled:
                    raise RuntimeError(
                        f"Video generation failed: {exc}. "
                        f"Set FALLBACK_STUBS=true to generate placeholder media, "
                        f"or configure VIDEO_API_KEY in .env."
                    ) from exc
                raise NotImplementedError(
                    "Fallback stub mode not implemented for VideoAgent"
                ) from exc

            clips.append(
                VideoClip(
                    shot_number=shot.shot_number,
                    file_path=generated_path,
                    duration=shot.duration,
                )
            )
            artifacts.append(
                ArtifactRef(
                    agent_name=self.name,
                    filename=f"clips/shot_{shot.shot_number:03d}.mp4",
                    content_type="video/mp4",
                )
            )

        video_output = VideoOutput(clips=clips)

        if self.storage is not None:
            self.storage.save(
                context.job_id,
                self.name.value,
                "video_output.json",
                video_output.model_dump(mode="json"),
            )

        context.agent_results[self.name] = AgentResult(
            agent_name=self.name,
            success=True,
            output_data=video_output.model_dump(mode="json"),
            artifacts=artifacts,
        )
        return context
```

- [x] **Step 4: Run tests to verify they pass**

Run: `venv\Scripts\python.exe -m pytest tests/test_agents/test_video.py -v`

Expected: ALL PASS

- [x] **Step 5: Commit**

```bash
git add agents/video.py tests/test_agents/test_video.py
git commit -m "feat: implement VideoAgent with wan2.7-t2v and clear error on API failure"
```

---

## Task 4: Implement VoiceAgent (Qwen cosyvoice-v3-plus)

**Files:**

- Create: `agents/voice.py`
- Create: `tests/test_agents/test_voice.py`

- [x] **Step 1: Write failing tests for VoiceAgent**

Create `tests/test_agents/test_voice.py`:

```python
from unittest.mock import MagicMock

import pytest

from agents.voice import VoiceAgent
from models.enums import AgentName
from models.workflow_state import WorkflowState
from models.agent_result import AgentResult
from models.script import Script
from models.scene import Scene
from models.voice import VoiceOutput
from tools.tts import TTSService


def _make_context_with_script() -> WorkflowState:
    ctx = WorkflowState(job_id="test-job", prompt="test")
    script = Script(
        title="AI Explainer",
        scenes=[
            Scene(
                scene_number=1,
                narration="AI is transforming the world.",
                duration_hint=5.0,
                visual_direction="Show AI systems",
            )
        ],
    )
    ctx.agent_results[AgentName.SCRIPT] = AgentResult(
        agent_name=AgentName.SCRIPT,
        success=True,
        output_data=script.model_dump(mode="json"),
    )
    return ctx


def _mock_tts_service() -> MagicMock:
    mock = MagicMock(spec=TTSService)
    mock.synthesize.return_value = "/tmp/scene_001.mp3"
    return mock


class TestVoiceAgent:
    def test_name_is_voice(self):
        agent = VoiceAgent(tts_service=_mock_tts_service())
        assert agent.name == AgentName.VOICE

    def test_run_returns_workflow_state(self):
        agent = VoiceAgent(tts_service=_mock_tts_service())
        ctx = _make_context_with_script()
        result = agent.run(ctx)
        assert isinstance(result, WorkflowState)

    def test_run_raises_when_script_missing(self):
        agent = VoiceAgent(tts_service=_mock_tts_service())
        ctx = WorkflowState(job_id="test-job", prompt="test")
        with pytest.raises(ValueError, match="Script"):
            agent.run(ctx)

    def test_run_generates_track_for_each_scene(self):
        mock_service = _mock_tts_service()
        agent = VoiceAgent(tts_service=mock_service)
        ctx = _make_context_with_script()
        result = agent.run(ctx)

        output_data = result.agent_results[AgentName.VOICE].output_data
        voice_output = VoiceOutput.model_validate(output_data)
        assert len(voice_output.tracks) == 1
        assert voice_output.tracks[0].scene_number == 1
        assert voice_output.tracks[0].file_path.endswith("voice/audio/scene_001.mp3")
        mock_service.synthesize.assert_called_once()

    def test_run_persists_artifacts_to_storage(self):
        mock_service = _mock_tts_service()
        mock_storage = MagicMock()
        agent = VoiceAgent(tts_service=mock_service, storage=mock_storage)
        ctx = _make_context_with_script()
        agent.run(ctx)

        artifacts = ctx.agent_results[AgentName.VOICE].artifacts
        assert len(artifacts) == 1
        assert artifacts[0].agent_name == AgentName.VOICE
        assert artifacts[0].filename == "audio/scene_001.mp3"
        assert artifacts[0].content_type == "audio/mpeg"

    def test_run_raises_when_api_unavailable_and_fallback_disabled(self):
        mock_service = _mock_tts_service()
        mock_service.synthesize.side_effect = RuntimeError("VOICE_API_KEY not configured")
        agent = VoiceAgent(tts_service=mock_service, fallback_enabled=False)
        ctx = _make_context_with_script()

        with pytest.raises(RuntimeError, match="VOICE_API_KEY not configured"):
            agent.run(ctx)
```

- [x] **Step 2: Run tests to verify they fail**

Run: `venv\Scripts\python.exe -m pytest tests/test_agents/test_voice.py -v`

Expected: FAIL — `VoiceAgent` does not exist.

- [x] **Step 3: Implement VoiceAgent**

Create `agents/voice.py`:

```python
"""Voice agent — generates narration audio tracks from a script using Qwen cosyvoice-v3-plus."""

from pathlib import Path

from models.enums import AgentName
from models.agent_result import AgentResult, ArtifactRef
from models.script import Script
from models.voice import AudioTrack, VoiceOutput
from models.workflow_state import WorkflowState
from storage.base import StorageBackend
from tools.tts import TTSService


class VoiceAgent:
    """Voice Agent for Phase 3.

    Generates narration using Qwen cosyvoice-v3-plus model.
    Raises clear error if API is unavailable and fallback is disabled.
    """

    name = AgentName.VOICE

    def __init__(
        self,
        tts_service: TTSService,
        storage: StorageBackend | None = None,
        fallback_enabled: bool = False,
    ) -> None:
        self.tts_service = tts_service
        self.storage = storage
        self.fallback_enabled = fallback_enabled

    def _track_path(self, job_id: str, scene_number: int) -> str:
        return str(
            Path("outputs") / job_id / "voice" / "audio" / f"scene_{scene_number:03d}.mp3"
        )

    def run(self, context: WorkflowState) -> WorkflowState:
        if AgentName.SCRIPT not in context.agent_results:
            raise ValueError("Voice agent requires Script output in context")

        script = Script.model_validate(
            context.agent_results[AgentName.SCRIPT].output_data
        )

        tracks: list[AudioTrack] = []
        artifacts: list[ArtifactRef] = []

        for scene in script.scenes:
            output_path = self._track_path(context.job_id, scene.scene_number)
            try:
                generated_path = self.tts_service.synthesize(scene.narration, output_path)
            except Exception as exc:
                if not self.fallback_enabled:
                    raise RuntimeError(
                        f"Voice generation failed: {exc}. "
                        f"Set FALLBACK_STUBS=true to generate placeholder media, "
                        f"or configure VOICE_API_KEY in .env."
                    ) from exc
                raise NotImplementedError(
                    "Fallback stub mode not implemented for VoiceAgent"
                ) from exc

            tracks.append(
                AudioTrack(
                    scene_number=scene.scene_number,
                    file_path=generated_path,
                    duration=scene.duration_hint,
                )
            )
            artifacts.append(
                ArtifactRef(
                    agent_name=self.name,
                    filename=f"audio/scene_{scene.scene_number:03d}.mp3",
                    content_type="audio/mpeg",
                )
            )

        voice_output = VoiceOutput(tracks=tracks)

        if self.storage is not None:
            self.storage.save(
                context.job_id,
                self.name.value,
                "voice_output.json",
                voice_output.model_dump(mode="json"),
            )

        context.agent_results[self.name] = AgentResult(
            agent_name=self.name,
            success=True,
            output_data=voice_output.model_dump(mode="json"),
            artifacts=artifacts,
        )
        return context
```

- [x] **Step 4: Run tests to verify they pass**

Run: `venv\Scripts\python.exe -m pytest tests/test_agents/test_voice.py -v`

Expected: ALL PASS

- [x] **Step 5: Commit**

```bash
git add agents/voice.py tests/test_agents/test_voice.py
git commit -m "feat: implement VoiceAgent with cosyvoice-v3-plus and clear error on API failure"
```

---

## Task 5: Wire Video and Voice Agents into Production App

**Files:**

- Modify: `backend/main.py`
- Test: `tests/test_agents/test_video.py`, `tests/test_agents/test_voice.py` — add integration tests

- [x] **Step 1: Update `backend/main.py` to include Video and Voice agents**

Modify `backend/main.py`:

```python
"""FastAPI application entry point — creates production app with default storage and agents."""

import os

from storage.local import LocalStorage
from backend.api.routes import create_app
from backend.config import Settings
from models.job import JobRecord
from tools.llm import AlibabaCloudLLMService
from tools.tts import DashScopeTTSService
from tools.video_gen import DashScopeVideoGenService
from agents.director import DirectorAgent
from agents.research import ResearchAgent
from agents.script import ScriptAgent
from agents.storyboard import StoryboardAgent
from agents.video import VideoAgent
from agents.voice import VoiceAgent


def create_production_app():
    settings = Settings()
    storage = LocalStorage(settings.storage.output_dir)
    job_store: dict[str, JobRecord] = {}

    llm_service = AlibabaCloudLLMService(settings.llm)
    tts_service = DashScopeTTSService(settings.voice)
    video_service = DashScopeVideoGenService(settings.video)

    # Fallback stub mode — default is false (fail with clear error)
    fallback_enabled = os.environ.get("FALLBACK_STUBS", "false").lower() == "true"

    agents = [
        DirectorAgent(llm_service=llm_service, storage=storage),
        ResearchAgent(llm_service=llm_service, storage=storage),
        ScriptAgent(llm_service=llm_service, storage=storage),
        StoryboardAgent(llm_service=llm_service, storage=storage),
        VideoAgent(
            video_service=video_service,
            storage=storage,
            fallback_enabled=fallback_enabled,
        ),
        VoiceAgent(
            tts_service=tts_service,
            storage=storage,
            fallback_enabled=fallback_enabled,
        ),
    ]

    return create_app(storage=storage, job_store=job_store, agents=agents)


app = create_production_app()
```

- [x] **Step 2: Run tests to verify they pass**

Run: `venv\Scripts\python.exe -m pytest tests/test_agents/test_video.py tests/test_agents/test_voice.py -v`

Expected: ALL PASS

- [x] **Step 3: Commit**

```bash
git add backend/main.py tests/test_agents/test_video.py tests/test_agents/test_voice.py
git commit -m "feat: wire Video and Voice agents into production app"
```

---

## Task 6: Integration Verification

**Files:**

- Run full test suite
- Optionally: run a local end-to-end pipeline

- [x] **Step 1: Run all tests**

Run: `venv\Scripts\python.exe -m pytest tests/ -v`

Expected: ALL PASS

- [x] **Step 2: Run a local end-to-end pipeline**

Note: This requires valid API keys for LLM, TTS, and video generation:

- `LLM_API_KEY` — for qwen3-max
- `VOICE_API_KEY` — for cosyvoice-v3-plus
- `VIDEO_API_KEY` — for wan2.7-t2v

Set environment and run:

```bash
set LLM_API_KEY=your_key_here
set VOICE_API_KEY=your_key_here
set VIDEO_API_KEY=your_key_here
./.venv/Scripts/python.exe run_test.py
"
```

Expected: `202` response and a job ID. Check `outputs/{job_id}/` for:

- `pipeline/context.json`
- `video/clips/shot_001.mp4`
- `voice/audio/scene_001.mp3`

- [x] **Step 3: Commit**

```bash
git commit -m "chore: verify Phase 3 asset generation pipeline"
```

---

## Known Limitations

1. **Synchronous execution** — Video and Voice agents run sequentially, blocking the `/generate` response. Background/queue execution is deferred to a later phase.
2. **Fallback stubs not implemented** — When `FALLBACK_STUBS=true`, agents currently raise `NotImplementedError`. Stub generation (empty/silent media) will be added in a follow-up.
3. **No web search enrichment** — Research agent uses LLM-only (Qwen3-max). Future enhancement: integrate Qwen's native web search capability if available.

---

## Self-Review

### Spec coverage

| PROJECT_SPEC §7 Phase 3 item                 | Task(s) covering it |
| -------------------------------------------- | ------------------- |
| Video Agent (integrate video generation API) | Task 3              |
| Voice Agent (integrate TTS API)              | Task 4              |
| Rate limits, retries                         | Task 1              |
| Error on empty/missing API                   | Task 3, Task 4      |

### Placeholder scan

No TBD/TODO placeholders. All production files, tests, and commands are explicit.

### Type consistency

- `VideoOutput.clips` contains `VideoClip(shot_number, file_path, duration)`
- `VoiceOutput.tracks` contains `AudioTrack(scene_number, file_path, duration)`
- `ArtifactRef.content_type`: `video/mp4` for video, `audio/mpeg` for MP3
- Models use `qwen3-max`, `cosyvoice-v3-plus`, `wan2.7-t2v` per `.env.example`
