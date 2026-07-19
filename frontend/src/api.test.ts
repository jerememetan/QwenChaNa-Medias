import { afterEach, describe, expect, it, vi } from "vitest"

import {
  ApiError,
  clipVideoUrl,
  generateJob,
  getJobDetails,
  resultDownloadUrl,
} from "./api"

afterEach(() => vi.unstubAllGlobals())

describe("frontend API", () => {
  it("posts a production prompt", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ job_id: "job-1" }), {
        status: 202,
        headers: { "Content-Type": "application/json" },
      }),
    )
    vi.stubGlobal("fetch", fetchMock)

    await expect(generateJob("Voxel reveal")).resolves.toEqual({ job_id: "job-1" })
    expect(fetchMock).toHaveBeenCalledWith("/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt: "Voxel reveal" }),
    })
  })

  it("returns typed details", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        job_id: "job-1",
        prompt: "Voxel reveal",
        status: "failed",
        current_agent: null,
        failed_agent: "video",
        error: "quota",
        agent_results: {},
      }), { status: 200, headers: { "Content-Type": "application/json" } }),
    ))

    const details = await getJobDetails("job-1")

    expect(details.failed_agent).toBe("video")
  })

  it("surfaces FastAPI error details", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "Job not found" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      }),
    ))

    await expect(getJobDetails("missing")).rejects.toEqual(
      new ApiError(404, "Job not found"),
    )
  })

  it("encodes final download URLs", () => {
    expect(resultDownloadUrl("job with spaces")).toBe(
      "/result/job%20with%20spaces/download",
    )
  })

  it("encodes generated clip URLs", () => {
    expect(clipVideoUrl("job with spaces", 3)).toBe(
      "/result/job%20with%20spaces/clips/3",
    )
  })
})
