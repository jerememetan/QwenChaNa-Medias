import { Check, ChevronDown, Circle, X } from "lucide-react"
import { useState } from "react"

import { buildLedger, inspectorEntries } from "../jobView"
import type { JobDetailsResponse } from "../types"

export interface ProductionLedgerProps {
  details: JobDetailsResponse | null
}

export function ProductionLedger({ details }: ProductionLedgerProps) {
  const [expanded, setExpanded] = useState<string | null>(null)
  const rows = buildLedger(details)

  return (
    <section aria-labelledby="ledger-heading">
      <div className="section-heading section-heading--compact">
        <div>
          <span className="eyebrow">Seven-agent record</span>
          <h2 id="ledger-heading">Production ledger</h2>
        </div>
        <span className="section-count">
          {rows.filter((row) => row.state === "complete").length}/7
        </span>
      </div>
      <div className="ledger-list">
        {rows.map((row) => {
          const isExpanded = expanded === row.name
          const entries = row.result ? inspectorEntries(row.result) : []
          return (
            <div className="ledger-row" key={row.name}>
              <button
                type="button"
                data-state={row.state}
                aria-expanded={isExpanded}
                onClick={() => setExpanded(isExpanded ? null : row.name)}
              >
                <span className="ledger-index">{String(row.id).padStart(2, "0")}</span>
                <span className="ledger-name">{row.label}</span>
                <span className="ledger-summary">{row.summary}</span>
                <span className="ledger-state" aria-label={row.state}>
                  {row.state === "complete" && <Check size={14} />}
                  {row.state === "failed" && <X size={14} />}
                  {row.state === "pending" && <Circle size={10} />}
                </span>
                <ChevronDown className="ledger-chevron" size={14} aria-hidden="true" />
              </button>
              {isExpanded && (
                <div className="ledger-inspector">
                  {entries.length ? entries.map((entry) => (
                    <div className="inspector-entry" key={entry.label}>
                      <strong>{entry.label}</strong>
                      <span className="inspector-value">{entry.value}</span>
                    </div>
                  )) : (
                    <span className="empty-note">No saved output yet.</span>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </section>
  )
}
