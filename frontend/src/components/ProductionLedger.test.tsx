import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import type { JobDetailsResponse } from "../types"
import { ProductionLedger } from "./ProductionLedger"

const details: JobDetailsResponse = {
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
      output_data: { title: "Voxel" },
      artifacts: [],
    },
  },
}

describe("ProductionLedger", () => {
  it("renders seven stages and a failed agent", () => {
    render(<ProductionLedger details={details} />)
    expect(screen.getAllByRole("button")).toHaveLength(7)
    expect(screen.getByText("Video").closest("button")).toHaveAttribute(
      "data-state",
      "failed",
    )
  })

  it("expands persisted output details", () => {
    render(<ProductionLedger details={details} />)
    fireEvent.click(screen.getByRole("button", { name: /Director/ }))
    expect(screen.getByText("Title")).toBeInTheDocument()
    expect(screen.getByText("Voxel")).toBeInTheDocument()
  })
})
