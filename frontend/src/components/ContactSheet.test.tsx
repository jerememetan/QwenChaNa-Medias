import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import type { AgentResult, JobDetailsResponse } from "../types"
import { ContactSheet } from "./ContactSheet"

function agentResult(
  agentName: AgentResult["agent_name"],
  outputData: Record<string, unknown>,
): AgentResult {
  return {
    agent_name: agentName,
    success: true,
    output_data: outputData,
    artifacts: [],
  }
}

function completedDetails(): JobDetailsResponse {
  const shots = Array.from({ length: 6 }, (_, index) => ({
    shot_number: index + 1,
    scene_number: 1,
    visual_prompt: `Generated shot ${index + 1}`,
    camera: "medium close-up",
    motion: "static",
    duration: 5,
  }))
  const clips = shots.slice(0, 5).map((shot) => ({
    shot_number: shot.shot_number,
    file_path: `/app/outputs/job-1/video/shot-${shot.shot_number}.mp4`,
    duration: 5,
  }))
  return {
    job_id: "job-1",
    prompt: "Create a micro-drama",
    status: "completed",
    current_agent: null,
    failed_agent: null,
    error: null,
    agent_results: {
      storyboard: agentResult("storyboard", { shots }),
      video: agentResult("video", { clips }),
    },
  }
}

describe("ContactSheet", () => {
  it("renders every generated clip as a manually controlled video", () => {
    const { container } = render(<ContactSheet details={completedDetails()} />)

    expect(screen.getAllByRole("article")).toHaveLength(6)
    const videos = screen.getAllByTitle(/Generated video for shot/)
    expect(videos).toHaveLength(5)
    expect(videos[0]).toHaveAttribute("controls")
    expect(videos[0]).toHaveAttribute("preload", "metadata")
    expect(videos[0]).toHaveAttribute("playsinline")
    expect(videos[0]).not.toHaveAttribute("autoplay")
    expect(container.querySelector("video source")).toHaveAttribute(
      "src",
      "/result/job-1/clips/1",
    )
  })

  it("keeps planned artwork for a shot without a generated clip", () => {
    render(<ContactSheet details={completedDetails()} />)

    expect(screen.getByTitle("Voxel production preview")).toBeInTheDocument()
    expect(screen.getByText(/Planned/)).toBeInTheDocument()
  })
})
