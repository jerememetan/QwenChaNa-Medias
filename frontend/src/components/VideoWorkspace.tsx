import { Download } from "lucide-react"

import { resultDownloadUrl } from "../api"
import { IdleArtwork } from "./IdleArtwork"

export interface VideoWorkspaceProps {
  jobId: string | null
  running: boolean
  completed: boolean
  onPlaybackError: () => void
}

export function VideoWorkspace({
  jobId,
  running,
  completed,
  onPlaybackError,
}: VideoWorkspaceProps) {
  const videoUrl = jobId ? resultDownloadUrl(jobId) : null

  return (
    <section className="video-workspace" aria-labelledby="final-cut-heading">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Output 01</span>
          <h1 id="final-cut-heading">Final video</h1>
        </div>
        {completed && videoUrl && (
          <a className="text-action" href={videoUrl} download="final_video.mp4">
            <Download size={15} aria-hidden="true" />
            Download MP4
          </a>
        )}
      </div>
      <div className="video-frame">
        {completed && videoUrl ? (
          <video
            controls
            preload="metadata"
            title="Final generated video"
            onError={onPlaybackError}
          >
            <source src={videoUrl} type="video/mp4" />
            Your browser does not support MP4 playback.
          </video>
        ) : (
          <IdleArtwork />
        )}
        {!completed && (
          <div className="frame-caption">
            <span>{running ? "Rendering production" : "Awaiting production brief"}</span>
            <span>1280 × 720</span>
          </div>
        )}
      </div>
      {running && <div className="working-rule" aria-hidden="true" />}
    </section>
  )
}
