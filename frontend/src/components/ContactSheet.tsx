import { clipVideoUrl } from "../api"
import type { JobDetailsResponse } from "../types"
import { IdleArtwork } from "./IdleArtwork"

export interface ContactSheetProps {
  details: JobDetailsResponse | null
}

interface ContactFrame {
  number: number
  prompt: string
  camera?: string
  duration?: number
  rendered: boolean
  videoUrl?: string
}

function records(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> =>
      Boolean(item) && typeof item === "object")
    : []
}

export function ContactSheet({ details }: ContactSheetProps) {
  const shots = records(details?.agent_results.storyboard?.output_data.shots)
  const clips = records(details?.agent_results.video?.output_data.clips)
  const frames: ContactFrame[] = shots.map((shot, index) => {
    const number = Number(shot.shot_number || index + 1)
    const clip = clips.find((item) => Number(item.shot_number) === number)
    return {
      number,
      prompt: String(shot.visual_prompt || "Planned frame"),
      camera: shot.camera ? String(shot.camera) : undefined,
      duration: typeof shot.duration === "number" ? shot.duration : undefined,
      rendered: Boolean(clip),
      videoUrl: clip && details
        ? clipVideoUrl(details.job_id, number)
        : undefined,
    }
  })

  return (
    <section className="contact-section" aria-labelledby="contact-heading">
      <div className="section-heading section-heading--compact">
        <div>
          <span className="eyebrow">Storyboard register</span>
          <h2 id="contact-heading">Contact sheet</h2>
        </div>
        <span className="section-count">{shots.length || 0} shots</span>
      </div>
      {frames.length ? (
        <div className="contact-sheet">
          {frames.map((frame) => (
            <article className="contact-frame" key={frame.number}>
              <div className="contact-image">
                {frame.videoUrl ? (
                  <video
                    controls
                    playsInline
                    preload="metadata"
                    title={`Generated video for shot ${frame.number}`}
                  >
                    <source src={frame.videoUrl} type="video/mp4" />
                    Your browser does not support MP4 playback.
                  </video>
                ) : (
                  <IdleArtwork />
                )}
                <span className="frame-number">{String(frame.number).padStart(2, "0")}</span>
              </div>
              <div className="contact-copy">
                <strong>{frame.prompt}</strong>
                <span>
                  {[frame.camera, frame.duration && `${frame.duration}s`, frame.rendered ? "Rendered" : "Planned"]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <p className="empty-note">Frames appear after the storyboard pass.</p>
      )}
    </section>
  )
}
