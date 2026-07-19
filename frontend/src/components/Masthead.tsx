export interface MastheadProps {
  jobId: string | null
  status: "idle" | "running" | "completed" | "failed"
}

const statusLabels: Record<MastheadProps["status"], string> = {
  idle: "Ready for brief",
  running: "In production",
  completed: "Final cut ready",
  failed: "Production paused",
}

export function Masthead({ jobId, status }: MastheadProps) {
  return (
    <header className="masthead">
      <div className="brand-lockup">
        <span className="edition-mark" aria-hidden="true">QC</span>
        <div>
          <div className="wordmark">QwenChaNa Medias</div>
          <div className="brand-caption">Autonomous film desk</div>
        </div>
      </div>
      <div className="masthead-meta" aria-live="polite">
        <span className={`status-dot status-dot--${status}`} aria-hidden="true" />
        <span>{statusLabels[status]}</span>
        {jobId && <code title={jobId}>#{jobId.slice(0, 8)}</code>}
      </div>
    </header>
  )
}
