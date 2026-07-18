# CosyVoice Synthesis Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Phase 3 narration generation call Alibaba Cloud Model Studio's Singapore CosyVoice WebSocket inference API and persist valid MP3 audio.

**Architecture:** Keep `VoiceAgent` and its data contracts unchanged. Correct only the provider wrapper boundary so DashScope receives its API key and WebSocket inference endpoint through the SDK-supported module settings, then add regression coverage around SDK construction and audio output validation.

**Tech Stack:** Python 3.12, DashScope Python SDK, pytest, unittest.mock, Pydantic settings

---

## File Map

- Create `tests/test_tools/test_tts.py`: regression tests for the concrete DashScope TTS wrapper.
- Modify `tools/tts.py`: configure the WebSocket client correctly and validate returned audio.
- Modify `.env.example`: document the Singapore WebSocket inference URL and built-in MVP voice.
- Modify `.env`: point the local runtime at the workspace WebSocket inference URL without changing credentials.

### Task 1: Correct DashScope WebSocket synthesis

**Files:**
- Create: `tests/test_tools/test_tts.py`
- Modify: `tools/tts.py`

- [ ] **Step 1: Write the failing provider-contract test**

```python
from unittest.mock import MagicMock, patch

import dashscope

from backend.config import VoiceConfig
from tools.tts import DashScopeTTSService


def test_synthesize_configures_websocket_client_and_writes_audio(
    tmp_path, monkeypatch
):
    endpoint = "wss://workspace.ap-southeast-1.maas.aliyuncs.com/api-ws/v1/inference"
    config = VoiceConfig(
        api_key="test-key",
        base_url=endpoint,
        model="cosyvoice-v3-plus",
        voice="longanhuan",
    )
    service = DashScopeTTSService(config)
    output_path = tmp_path / "scene_001.mp3"
    synthesizer = MagicMock()
    synthesizer.call.return_value = b"mp3-audio"
    monkeypatch.setattr(dashscope, "api_key", None)
    monkeypatch.setattr(dashscope, "base_websocket_api_url", "")

    with patch(
        "dashscope.audio.tts_v2.SpeechSynthesizer",
        return_value=synthesizer,
    ) as synthesizer_class:
        result = service.synthesize("Narration", str(output_path))

    assert dashscope.api_key == "test-key"
    assert dashscope.base_websocket_api_url == endpoint
    synthesizer_class.assert_called_once_with(
        model="cosyvoice-v3-plus",
        voice="longanhuan",
    )
    synthesizer.call.assert_called_once_with("Narration")
    assert output_path.read_bytes() == b"mp3-audio"
    assert result == str(output_path)
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
venv\Scripts\python.exe -m pytest tests/test_tools/test_tts.py::test_synthesize_configures_websocket_client_and_writes_audio -v
```

Expected: FAIL because the current wrapper sets `base_http_api_url` and passes the unsupported `api_key` constructor argument.

- [ ] **Step 3: Implement the minimal SDK correction**

Replace the concrete wrapper configuration and synthesis body in `tools/tts.py` with:

```python
class DashScopeTTSService(TTSService):
    """Generate CosyVoice speech through Alibaba Model Studio WebSockets."""

    def __init__(self, config: VoiceConfig) -> None:
        self.config = config
        self._configured = bool(config.api_key)

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

        dashscope.api_key = self.config.api_key
        if self.config.base_url:
            dashscope.base_websocket_api_url = self.config.base_url.rstrip("/")

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

Also remove the unused `HTTPStatus` import and update the class docstring to describe WebSocket inference.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run:

```powershell
venv\Scripts\python.exe -m pytest tests/test_tools/test_tts.py::test_synthesize_configures_websocket_client_and_writes_audio -v
```

Expected: `1 passed`.

- [ ] **Step 5: Commit the provider correction**

```powershell
git add tests/test_tools/test_tts.py tools/tts.py
git commit -m "fix: use CosyVoice WebSocket inference"
```

### Task 2: Reject invalid audio responses

**Files:**
- Modify: `tests/test_tools/test_tts.py`
- Modify: `tools/tts.py`

- [ ] **Step 1: Write the failing empty-audio test**

```python
import pytest


def test_synthesize_rejects_empty_audio(tmp_path):
    service = DashScopeTTSService(
        VoiceConfig(api_key="test-key", model="cosyvoice-v3-plus", voice="longanhuan")
    )
    output_path = tmp_path / "scene_001.mp3"
    synthesizer = MagicMock()
    synthesizer.call.return_value = b""

    with patch(
        "dashscope.audio.tts_v2.SpeechSynthesizer",
        return_value=synthesizer,
    ):
        with pytest.raises(RuntimeError, match="empty audio"):
            service.synthesize("Narration", str(output_path))

    assert not output_path.exists()
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
venv\Scripts\python.exe -m pytest tests/test_tools/test_tts.py::test_synthesize_rejects_empty_audio -v
```

Expected: FAIL because the current implementation writes an empty file and returns success.

- [ ] **Step 3: Add minimal response validation**

Insert immediately after `synthesizer.call(text)`:

```python
        if not isinstance(audio_data, bytes) or not audio_data:
            raise RuntimeError("Voice synthesis returned empty audio data")
```

- [ ] **Step 4: Add missing-key regression coverage**

```python
def test_synthesize_requires_api_key(tmp_path):
    service = DashScopeTTSService(VoiceConfig(api_key=""))

    with pytest.raises(RuntimeError, match="VOICE_API_KEY"):
        service.synthesize("Narration", str(tmp_path / "scene_001.mp3"))
```

- [ ] **Step 5: Run all TTS tests and verify GREEN**

Run:

```powershell
venv\Scripts\python.exe -m pytest tests/test_tools/test_tts.py -v
```

Expected: `3 passed`.

- [ ] **Step 6: Commit response validation**

```powershell
git add tests/test_tools/test_tts.py tools/tts.py
git commit -m "fix: reject empty TTS artifacts"
```

### Task 3: Correct endpoint configuration and verify integration

**Files:**
- Modify: `.env.example`
- Modify: `.env`
- Test: `tests/test_tools/test_tts.py`
- Test: `tests/test_agents/test_voice.py`

- [ ] **Step 1: Document the WebSocket inference settings**

Set the voice section in `.env.example` to:

```dotenv
# ---- Voice / TTS ----
VOICE_PROVIDER=dashscope
VOICE_API_KEY=...
VOICE_BASE_URL=wss://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com/api-ws/v1/inference
VOICE_MODEL=cosyvoice-v3-plus
VOICE_VOICE=longanhuan
```

- [ ] **Step 2: Correct the local runtime endpoint**

Set only `VOICE_BASE_URL` in `.env` to:

```dotenv
VOICE_BASE_URL=wss://ws-pd7pxz3ci9h4zpr0.ap-southeast-1.maas.aliyuncs.com/api-ws/v1/inference
```

Keep the existing API key and `cosyvoice-v3-plus` model unchanged. Set the voice to the Singapore-supported `longanhuan`.

- [ ] **Step 3: Run focused integration tests**

Run:

```powershell
venv\Scripts\python.exe -m pytest tests/test_tools/test_tts.py tests/test_agents/test_voice.py tests/test_backend/test_config.py -v
```

Expected: all selected tests pass.

- [ ] **Step 4: Run the full regression suite**

Run:

```powershell
venv\Scripts\python.exe -m pytest tests -v
```

Expected: all tests pass with no failures.

- [ ] **Step 5: Review the final diff for secrets and scope**

Run:

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors; `.env` is not staged or shown in the tracked diff; only the plan, TTS wrapper, TTS tests, and `.env.example` are tracked changes.

- [ ] **Step 6: Commit configuration documentation**

```powershell
git add .env.example docs/superpowers/plans/2026-07-18-cosyvoice-synthesis-fix.md
git commit -m "docs: configure Singapore CosyVoice inference"
```

## Self-Review

- Spec coverage: provider configuration, built-in voice scope, audio validation, error propagation, and focused/full verification are covered.
- Placeholder scan: no deferred implementation steps or ambiguous error-handling instructions remain.
- Type consistency: tests and implementation use `VoiceConfig.base_url`, `DashScopeTTSService.synthesize(text, output_path)`, and byte audio output consistently.
