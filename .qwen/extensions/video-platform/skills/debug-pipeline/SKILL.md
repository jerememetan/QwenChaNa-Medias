---
name: debug-pipeline
description: Systematically diagnose pipeline failures and resume from checkpoints. Use when a job fails, an agent errors, or output quality is poor.
---

This skill provides a systematic approach to debugging pipeline failures.

## When to Use

- A job fails with an error
- An agent produces unexpected output
- Output quality is poor (bad video, wrong narration, etc.)
- Pipeline hangs or times out
- Need to resume a failed job

## Debugging Workflow

### Step 1: Identify the Failing Agent

Check the job's context file to see which agents completed:

```bash
cat outputs/<job_id>/context.json | jq '.completed_agents'
```

The failing agent is the first one NOT in `completed_agents`.

### Step 2: Check Agent Logs

Each agent logs to `outputs/<job_id>/<agent_name>/agent.log`:

```bash
cat outputs/<job_id>/<failing_agent>/agent.log
```

Look for:
- API errors (401, 429, 500)
- Validation errors (missing fields, schema mismatches)
- Timeout errors
- File I/O errors

### Step 3: Inspect Intermediate Artifacts

Check what the failing agent received as input:

```bash
# Check upstream output
cat outputs/<job_id>/<upstream_agent>/<output_file>.json | jq .
```

Common issues:
- **Director**: Check `creative_brief.json` — is it well-formed?
- **Research**: Check `research_notes.json` — did it get relevant info?
- **Script**: Check `script.json` — are scenes properly structured?
- **Storyboard**: Check `storyboard.json` — are visual prompts detailed?
- **Video**: Check `clips/` — did all shots generate?
- **Voice**: Check `audio/` — did all narrations generate?

### Step 4: Common Failure Patterns

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| `401 Unauthorized` | Missing or invalid API key | Check `.env` file |
| `429 Too Many Requests` | Rate limit hit | Add retry with backoff |
| `ValidationError` | LLM returned malformed JSON | Add structured output schema |
| `FileNotFoundError` | Upstream agent didn't produce artifact | Check upstream agent logs |
| `TimeoutError` | API took too long | Increase timeout in service client |
| Empty video/audio | Generation API returned empty | Check API response, retry |

### Step 5: Resume the Job

Once the issue is fixed, resume from the failing agent:

```python
from app.orchestrator.resume import resume_job

await resume_job("<job_id>", start_from="<failing_agent>")
```

The resume logic will:
1. Load `context.json` from the last completed state
2. Skip agents that already completed
3. Re-run the failing agent with the same inputs
4. Continue the pipeline

### Step 6: Validate Output Quality

After fixing, validate the output:

```bash
# Check video file
ffprobe outputs/<job_id>/editor/final/final_video.mp4

# Check audio
ffprobe outputs/<job_id>/voice/audio/scene_001.mp3

# Check video clips
ls -la outputs/<job_id>/video/clips/
```

## Quick Debug Commands

```bash
# List all jobs and their status
ls outputs/ | while read job; do echo "$job: $(cat outputs/$job/context.json | jq -r '.status')"; done

# Find failed jobs
find outputs/ -name "context.json" -exec grep -l '"status": "failed"' {} \;

# Check disk usage
du -sh outputs/<job_id>/
```

## Prevention Tips

1. **Add validation** at agent boundaries — catch malformed data early
2. **Set appropriate timeouts** — don't let APIs hang indefinitely
3. **Implement retries** — transient failures shouldn't kill the pipeline
4. **Log everything** — agent inputs, outputs, and errors
5. **Test with mocks** — catch integration issues before production
