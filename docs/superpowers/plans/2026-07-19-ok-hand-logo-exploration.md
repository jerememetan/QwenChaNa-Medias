# OK Hand Logo Exploration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate four separate symbol-only OK-hand logo candidates for QwenChaNa Medias.

**Architecture:** Each candidate uses the same approved continuous-line concept and palette while varying one controlled formal property. The four independent raster previews are selection artifacts; no application code or final vector asset changes in this step.

**Tech Stack:** OpenAI image generation, PNG output.

---

### Task 1: Generate the Four-Candidate Exploration

**Files:**

- Create: four generated PNG preview assets returned through the conversation
- Reference: `docs/superpowers/specs/2026-07-19-ok-hand-logo-design.md`

- [ ] **Step 1: Generate candidate A — balanced upright**

Create a centered, upright continuous-line OK hand with medium black stroke,
relaxed finger spacing, and a solid vermilion thumb-index opening.

- [ ] **Step 2: Generate candidate B — compact stamp-like**

Create a more compact hand with heavier black stroke, tighter finger spacing,
and a smaller vermilion opening while retaining an unboxed silhouette.

- [ ] **Step 3: Generate candidate C — expressive angled**

Create a slightly clockwise-tilted hand with subtle hand-drawn irregularity,
longer fingers, and a vermilion outlined opening.

- [ ] **Step 4: Generate candidate D — geometric minimal**

Create the most reduced geometric hand, using uniform black monoline geometry
and a precise vermilion opening, optimized for favicon legibility.

- [ ] **Step 5: Verify candidate constraints**

Confirm every image contains one isolated OK-hand symbol on warm off-white,
with no words, letters, face, mascot, badge, gradient, shadow, camera, sparkle,
brain, circuit, or chatbot motif.

- [ ] **Step 6: Present all four candidates**

Return the four images as A, B, C, and D so the user can select one silhouette
for final PNG and SVG production.
