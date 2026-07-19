# Qwen Hackathon Showcase Video Script Design

## Goal

Create a word-for-word live narration and recording script for a public Qwen
Hackathon submission video of approximately three minutes. The video must prove
that QwenChaNa Medias is a functioning Track 2: AI Showrunner project, demonstrate
a genuine end-to-end generation on Alibaba Cloud ECS, and finish with the final
generated MP4 and open-source repository evidence.

## Recording Format

- The creator narrates live while recording the screen.
- A new production is genuinely submitted during the recording.
- Only the model waiting period is cut or time-compressed.
- The video contains no cold open.
- A short on-screen caption discloses the edit: `Generation time compressed — no
  stages skipped.`
- The uploaded edit targets 2:50–3:00 so platform encoding or title cards do not
  push it materially beyond three minutes.

## Story Structure

### 0:00–0:20 — Introduction

Open on the idle QwenChaNa workspace. State the product name, identify Track 2:
AI Showrunner, and describe the outcome in one sentence: one production brief
becomes a finished short-form video.

### 0:20–0:45 — Product and Agent Pipeline

Explain that seven specialized agents handle direction, research, scriptwriting,
storyboarding, video, voice, and editing. Keep the UI visible and point briefly
to the empty production ledger rather than switching to slides.

### 0:45–1:00 — Live Brief and Generation

Enter a concise, visually controlled prompt with one location and a clear
emotional turn. State that the application is running on Alibaba Cloud ECS in
Singapore, then click `Begin production`.

### 1:00–1:08 — Waiting-Time Edit

Show the rendering state briefly. Cut or compress the silent waiting interval and
display the disclosure caption. Do not imply that generation completed in eight
seconds.

### 1:08–1:48 — Inspectable Production Record

Show the completed `7/7` production ledger. Expand representative agent records
to demonstrate structured outputs, then show the contact sheet. Prioritize
Director, Script or Storyboard, Video or Voice, and Editor rather than spending
equal time on every row.

### 1:48–2:08 — Architecture

Display the architecture diagram. Explain that LangGraph coordinates the agents
on the ECS backend, Qwen performs narrative reasoning, Wan generates video,
CosyVoice generates narration, FFmpeg assembles the final cut, and persistent
storage retains artifacts. Do not claim multiple ECS instances, OSS storage, a
database, or asynchronous workers.

### 2:08–2:40 — Final Output

Return to the application, play the strongest 20–25 seconds of the newly
generated final video, and show the `Download MP4` control. The narration should
pause while the generated clip speaks or plays audio.

### 2:40–2:55 — Submission Evidence

Show the public GitHub repository briefly. Point to the MIT license, container or
Compose deployment definition, architecture diagram, and concrete Alibaba Cloud
Model Studio integration. Avoid scrolling through implementation details.

### 2:55–3:00 — Close

End with a single value statement: QwenChaNa Medias turns one idea into a complete
short drama through an inspectable AI production team.

## Narration Style

- Conversational and confident, not a list of technologies.
- Short sentences that are easy to deliver live.
- Outcome first, implementation detail second.
- Use product-visible terms such as `production brief`, `production ledger`,
  `contact sheet`, and `final video`.
- Identify model responsibilities precisely: Qwen for reasoning and narrative,
  Wan for video, and CosyVoice for narration.
- Leave intentional silence during clicks, transitions, and final-video playback.

## Recording Prompt

Use a low-complexity prompt to reduce generation risk while still demonstrating
narrative ability:

> Create a cinematic micro-drama about a night-shift radio host who receives a
> call from their future self. Use one dimly lit studio location, restrained
> camera movement, moody blue light, and a clear emotional turn from fear to
> hope.

The creator may adjust wording before recording, but should preserve one location,
one principal character, and one visual style.

## Failure and Editing Plan

- Record a completed backup run before the final take.
- If the live request fails, use the application's `Resume production` behavior
  only if the failure can be corrected quickly; otherwise restart the recording.
- If generation exceeds the expected duration, keep the recording running, stay
  silent, and remove or accelerate only that waiting section during editing.
- If the final video playback fails, use the visible MP4 download and play the
  downloaded file locally, while retaining the application in the recording.
- Do not substitute an unrelated old output without disclosing the substitution.

## Security and Submission Hygiene

- Never show `.env`, API keys, SSH private keys, terminal history containing
  secrets, or Alibaba account identifiers.
- Crop or blur sensitive ECS console fields if the console is shown.
- Keep the browser at a readable zoom and disable notifications before recording.
- Use the public repository and public application only after confirming they are
  reachable in a clean browser session.

## Acceptance Criteria

- Spoken narration fits within approximately 155–170 words per minute.
- The edited video is about three minutes and has no cold open.
- A real generation begins on camera and its waiting-time cut is disclosed.
- The completed ledger, representative agent outputs, contact sheet, architecture,
  final video, MP4 download, repository, license, deployment proof, and Alibaba
  integration are all visible.
- The script contains explicit pauses for UI actions and final-video playback.
- Every infrastructure and model claim matches the implemented application.
- No secrets or private account details appear in the recording.
