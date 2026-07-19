import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import * as api from "./api"
import App from "./App"
import type { JobDetailsResponse } from "./types"

vi.mock("./api")

const completed: JobDetailsResponse = {
  job_id: "job-1",
  prompt: "Voxel reveal",
  status: "completed",
  current_agent: null,
  failed_agent: null,
  error: null,
  agent_results: {
    editor: {
      agent_name: "editor",
      success: true,
      output_data: { final_path: "final.mp4", scene_count: 1 },
      artifacts: [],
    },
  },
}

describe("App generation", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(api.resultDownloadUrl).mockReturnValue("/result/job-1/download")
  })

  it("submits the prompt and displays the completed production", async () => {
    vi.mocked(api.generateJob).mockResolvedValue({ job_id: "job-1" })
    vi.mocked(api.getJobDetails).mockResolvedValue(completed)
    vi.mocked(api.getJobResult).mockResolvedValue({
      job_id: "job-1",
      status: "completed",
      output_path: "final.mp4",
      download_url: "/result/job-1/download",
      artifacts: [],
    })
    render(<App />)
    fireEvent.change(screen.getByLabelText("Production prompt"), {
      target: { value: "Voxel reveal" },
    })

    fireEvent.click(screen.getByRole("button", { name: "Begin production" }))

    expect(await screen.findByText("Final cut ready")).toBeInTheDocument()
    expect(api.generateJob).toHaveBeenCalledWith("Voxel reveal")
    expect(api.getJobDetails).toHaveBeenCalledWith("job-1")
    await waitFor(() => {
      expect(screen.getByTitle("Final generated video")).toBeInTheDocument()
    })
  })
})
