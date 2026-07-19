import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { VideoWorkspace } from "./VideoWorkspace"

describe("VideoWorkspace", () => {
  it("recreates the player when the completed job changes", () => {
    const props = {
      running: false,
      completed: true,
      onPlaybackError: vi.fn(),
    }
    const { rerender } = render(
      <VideoWorkspace {...props} jobId="job-one" />,
    )
    const firstPlayer = screen.getByTitle("Final generated video")

    rerender(<VideoWorkspace {...props} jobId="job-two" />)

    expect(screen.getByTitle("Final generated video")).not.toBe(firstPlayer)
  })
})
