import { describe, expect, it } from "vitest"

import { buildLedger, inspectorEntries } from "./jobView"
import type { JobDetailsResponse } from "./types"

const failed: JobDetailsResponse = {
  job_id: "job-1",
  prompt: "Voxel",
  status: "failed",
  current_agent: null,
  failed_agent: "video",
  error: "quota",
  agent_results: {
    director: {
      agent_name: "director",
      success: true,
      output_data: { title: "Voxel", duration_seconds: 5 },
      artifacts: [],
    },
    storyboard: {
      agent_name: "storyboard",
      success: true,
      output_data: { shots: [{ shot_number: 1, duration: 5 }] },
      artifacts: [],
    },
  },
}

describe("job view mapping", () => {
  it("marks saved, failed, and downstream stages honestly", () => {
    const rows = buildLedger(failed)
    expect(rows.find((row) => row.name === "director")?.state).toBe("complete")
    expect(rows.find((row) => row.name === "video")?.state).toBe("failed")
    expect(rows.find((row) => row.name === "editor")?.state).toBe("pending")
  })

  it("summarizes real output data", () => {
    const rows = buildLedger(failed)
    expect(rows[0].summary).toBe("Voxel · 5 seconds")
    expect(rows[3].summary).toBe("1 shot · 5 seconds")
  })

  it("creates safe inspector entries for nested data", () => {
    const entries = inspectorEntries(failed.agent_results.storyboard!)
    expect(entries[0].label).toBe("Shots")
    expect(entries[0].value).toContain("Shot 01")
  })
})
