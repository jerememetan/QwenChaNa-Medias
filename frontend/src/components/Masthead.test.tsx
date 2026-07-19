import { render } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { Masthead } from "./Masthead"

describe("Masthead", () => {
  it("uses the selected OK-hand brand mark", () => {
    const { container } = render(<Masthead jobId={null} status="idle" />)

    expect(container.querySelector(".brand-mark img")).toHaveAttribute(
      "src",
      "/qwenchana-ok-hand.png",
    )
    expect(container).not.toHaveTextContent("QC")
  })
})
