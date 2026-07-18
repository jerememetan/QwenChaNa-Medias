# CosyVoice Synthesis Fix Design

## Problem

The Phase 3 pipeline generates video clips but does not produce narration audio. Two conditions contribute to the observed behavior:

1. The sequential pipeline runs `VoiceAgent` only after every video clip succeeds. A video quota or generation failure therefore prevents voice synthesis from starting.
2. When voice synthesis is reached, `DashScopeTTSService` passes an unsupported `api_key` argument to `SpeechSynthesizer`. It also configures the HTTP voice-customization endpoint even though `SpeechSynthesizer` uses the WebSocket inference endpoint.

This change fixes the TTS integration. Pipeline ordering remains sequential as required by the current project phase.

## Scope

- Use the built-in `longanhuan` voice, the female `cosyvoice-v3-plus` voice available in the Singapore region.
- Keep the Singapore `cosyvoice-v3-plus` model.
- Do not add voice cloning or voice-enrollment behavior.
- Do not reorder or parallelize the pipeline.
- Do not change the video quota behavior.

## Service Configuration

`VOICE_BASE_URL` represents the DashScope WebSocket inference endpoint:

```text
wss://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com/api-ws/v1/inference
```

The local `.env` value will use the project's existing workspace ID. `.env.example` will document the expected WebSocket URL shape without including credentials or a real workspace ID.

## TTS Service Behavior

Before constructing `SpeechSynthesizer`, `DashScopeTTSService.synthesize` will:

1. Reject a missing API key using the existing clear configuration error.
2. Set `dashscope.api_key` from `VoiceConfig.api_key`.
3. Set `dashscope.base_websocket_api_url` from `VoiceConfig.base_url` when provided.
4. Construct `SpeechSynthesizer` with only the supported `model` and `voice` arguments.
5. Call the synthesizer and write the returned MP3 bytes to the requested output path.

The service will reject an empty or non-bytes audio response instead of creating a misleading empty artifact.

## Data Flow

```text
Script scene narration
  -> VoiceAgent
  -> DashScopeTTSService
  -> DashScope WebSocket inference endpoint
  -> MP3 bytes
  -> outputs/{job_id}/voice/audio/scene_XXX.mp3
```

`VoiceAgent`, `VoiceOutput`, and artifact metadata remain unchanged.

## Error Handling

- Configuration and SDK errors continue to propagate to `VoiceAgent`.
- `VoiceAgent` continues to wrap failures with scene-generation guidance.
- The pipeline records `failed_agent=voice` and the error in `context.json` when video has completed but TTS fails.
- A preceding video failure continues to record `failed_agent=video`; no voice request is attempted in that case.

## Testing

Focused unit tests for `DashScopeTTSService` will verify:

- Missing API keys fail before SDK invocation.
- The API key and WebSocket endpoint are applied to DashScope.
- `SpeechSynthesizer` receives only `model` and `voice`.
- Returned audio bytes are written to the requested path.
- Empty audio responses fail without creating a valid-looking artifact.

Existing voice-agent and full test suites will then verify that the integration change does not alter agent contracts or pipeline behavior.
