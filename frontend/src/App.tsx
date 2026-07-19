import { useState } from "react"

import { generateJob, getJobDetails, getJobResult, resumeJob } from "./api"
import { ContactSheet } from "./components/ContactSheet"
import { Masthead } from "./components/Masthead"
import { ProductionLedger } from "./components/ProductionLedger"
import { PromptComposer } from "./components/PromptComposer"
import { VideoWorkspace } from "./components/VideoWorkspace"
import type { JobDetailsResponse, ResultResponse } from "./types"

export default function App() {
  const [prompt, setPrompt] = useState("")
  const [jobId, setJobId] = useState<string | null>(null)
  const [details, setDetails] = useState<JobDetailsResponse | null>(null)
  const [result, setResult] = useState<ResultResponse | null>(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [playbackError, setPlaybackError] = useState(false)

  async function refresh(id: string) {
    const next = await getJobDetails(id)
    setDetails(next)
    setResult(next.status === "completed" ? await getJobResult(id) : null)
  }

  async function handleGenerate() {
    const clean = prompt.trim()
    if (!clean) {
      setError("Enter a production brief.")
      return
    }
    setRunning(true)
    setError(null)
    setPlaybackError(false)
    setDetails(null)
    setResult(null)
    try {
      const created = await generateJob(clean)
      setJobId(created.job_id)
      await refresh(created.job_id)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to start production.")
    } finally {
      setRunning(false)
    }
  }

  async function handleResume() {
    if (!jobId) return
    setRunning(true)
    setError(null)
    try {
      await resumeJob(jobId)
      await refresh(jobId)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to resume production.")
    } finally {
      setRunning(false)
    }
  }

  function handleNewProduction() {
    setJobId(null)
    setDetails(null)
    setResult(null)
    setError(null)
    setPlaybackError(false)
  }

  const status = running
    ? "running"
    : details?.status === "completed"
      ? "completed"
      : details?.status === "failed"
        ? "failed"
        : "idle"
  const composerMode = details?.status === "failed"
    ? "resume"
    : result
      ? "new"
      : "generate"
  const handleSubmit = composerMode === "resume"
    ? handleResume
    : composerMode === "new"
      ? handleNewProduction
      : handleGenerate
  const visibleError = error || (details?.status === "failed" ? details.error : null)

  return (
    <div className="app-shell">
      <Masthead jobId={jobId} status={status} />
      <main className="workspace">
        <div className="media-column">
          <VideoWorkspace
            jobId={jobId}
            running={running}
            completed={Boolean(result)}
            onPlaybackError={() => setPlaybackError(true)}
          />
          {playbackError && (
            <p className="form-error" role="alert">
              Preview unavailable. Download the MP4 to view it locally.
            </p>
          )}
          <ContactSheet details={details} />
        </div>
        <aside className="ledger-column">
          <ProductionLedger details={details} />
        </aside>
        <PromptComposer
          prompt={prompt}
          mode={composerMode}
          disabled={running}
          error={visibleError}
          onPromptChange={setPrompt}
          onSubmit={handleSubmit}
        />
        <p className="sr-only" aria-live="polite">
          {running ? "Production running" : "Production idle"}
        </p>
      </main>
    </div>
  )
}
