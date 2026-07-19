import type { AgentName, AgentResult, JobDetailsResponse } from "./types"

export type LedgerState = "pending" | "complete" | "failed"

export interface LedgerRow {
  id: number
  name: AgentName
  label: string
  state: LedgerState
  summary: string
  result?: AgentResult
}

export interface InspectorEntry {
  label: string
  value: string
}

const STAGES: Array<[AgentName, string]> = [
  ["director", "Director"],
  ["research", "Research"],
  ["script", "Script"],
  ["storyboard", "Storyboard"],
  ["video", "Video"],
  ["voice", "Voice"],
  ["editor", "Editor"],
]

function objects(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> =>
      Boolean(item) && typeof item === "object")
    : []
}

function number(value: unknown): number {
  return typeof value === "number" ? value : 0
}

function plural(count: number, one: string): string {
  return `${count} ${count === 1 ? one : `${one}s`}`
}

function summarize(name: AgentName, result?: AgentResult): string {
  if (!result) return "—"
  const data = result.output_data
  if (name === "director") {
    return `${String(data.title || "Creative brief")} · ${number(data.duration_seconds)} seconds`
  }
  if (name === "research") {
    const notes = objects(data.notes)
    return notes.length ? plural(notes.length, "note") : "Skipped · creative prompt"
  }
  if (name === "script") {
    return plural(objects(data.scenes).length, "scene")
  }
  if (name === "storyboard") {
    const shots = objects(data.shots)
    const duration = shots.reduce((sum, shot) => sum + number(shot.duration), 0)
    return `${plural(shots.length, "shot")} · ${duration} seconds`
  }
  if (name === "video") {
    return `${plural(objects(data.clips).length, "clip")} rendered`
  }
  if (name === "voice") {
    return `${plural(objects(data.tracks).length, "track")} ready`
  }
  return "Final MP4 assembled"
}

export function buildLedger(details: JobDetailsResponse | null): LedgerRow[] {
  return STAGES.map(([name, label], index) => {
    const result = details?.agent_results[name]
    const state: LedgerState = result?.success
      ? "complete"
      : details?.failed_agent === name ? "failed" : "pending"
    return {
      id: index + 1,
      name,
      label,
      state,
      summary: summarize(name, result),
      result,
    }
  })
}

function format(value: unknown): string {
  if (value == null) return "—"
  if (
    typeof value === "string"
    || typeof value === "number"
    || typeof value === "boolean"
  ) {
    return String(value)
  }
  if (Array.isArray(value)) {
    return value.map((item, index) => {
      if (item && typeof item === "object") {
        const record = item as Record<string, unknown>
        const numberValue = record.shot_number ?? record.scene_number ?? index + 1
        const detail = record.visual_prompt
          ?? record.narration
          ?? record.file_path
          ?? "Ready"
        const kind = record.shot_number ? "Shot" : "Scene"
        return `${kind} ${String(numberValue).padStart(2, "0")}: ${detail}`
      }
      return String(item)
    }).join("\n")
  }
  return JSON.stringify(value)
}

export function inspectorEntries(result: AgentResult): InspectorEntry[] {
  return Object.entries(result.output_data).map(([key, value]) => {
    const label = key.replaceAll("_", " ")
    return {
      label: label.charAt(0).toUpperCase() + label.slice(1),
      value: format(value),
    }
  })
}
