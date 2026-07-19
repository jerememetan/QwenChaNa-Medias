import { render } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import styles from "../styles.css?raw"
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

  it("keeps the complete hand inside the masthead mark", () => {
    const scale = styles.match(/\.brand-mark img\s*{[^}]*scale\(([^)]+)\)/s)?.[1]

    expect(Number(scale)).toBeLessThanOrEqual(1.6)
  })
})
