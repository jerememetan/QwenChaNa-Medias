export interface PromptComposerProps {
  prompt: string
  mode: "generate" | "resume" | "new"
  disabled: boolean
  error: string | null
  onPromptChange: (value: string) => void
  onSubmit: () => void
}

const actionLabels: Record<PromptComposerProps["mode"], string> = {
  generate: "Begin production",
  resume: "Resume production",
  new: "New production",
}

export function PromptComposer({
  prompt,
  mode,
  disabled,
  error,
  onPromptChange,
  onSubmit,
}: PromptComposerProps) {
  return (
    <section className="prompt-composer" aria-labelledby="brief-heading">
      <div className="prompt-copy">
        <span className="eyebrow">Production brief</span>
        <h2 id="brief-heading">What should we make?</h2>
        <p>One clear subject, visual direction, and mood is enough.</p>
      </div>
      <div className="prompt-field">
        <label className="sr-only" htmlFor="production-prompt">Production prompt</label>
        <textarea
          id="production-prompt"
          value={prompt}
          disabled={disabled || mode !== "generate"}
          maxLength={5000}
          placeholder="A miniature city waking at dawn, warm documentary light, slow aerial reveal…"
          onChange={(event) => onPromptChange(event.target.value)}
          onKeyDown={(event) => {
            if ((event.metaKey || event.ctrlKey) && event.key === "Enter") onSubmit()
          }}
        />
        <div className="composer-footer">
          <span className="prompt-count">{prompt.length}/5000</span>
          <button
            className="primary-action"
            type="button"
            disabled={disabled}
            onClick={onSubmit}
          >
            {disabled ? "Working…" : actionLabels[mode]}
          </button>
        </div>
        {error && <p className="form-error" role="alert">{error}</p>}
      </div>
    </section>
  )
}
