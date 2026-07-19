import { useId } from "react"

export function IdleArtwork() {
  const titleId = useId()

  return (
    <svg
      className="idle-art"
      viewBox="0 0 1280 720"
      role="img"
      aria-labelledby={titleId}
      preserveAspectRatio="xMidYMid slice"
    >
      <title id={titleId}>Voxel production preview</title>
      <rect width="1280" height="720" fill="#10100e" />
      <path d="M0 505 640 260l640 245v215H0Z" fill="#20201c" />
      <polygon points="640,248 920,362 640,482 360,362" fill="#7f9a43" />
      <polygon points="360,362 640,482 640,650 360,528" fill="#765338" />
      <polygon points="640,482 920,362 920,528 640,650" fill="#503927" />
      <path d="M455 363 640 438l185-75" fill="none" stroke="#b9d260" strokeWidth="3" opacity=".65" />
      <circle cx="1080" cy="145" r="42" fill="#c43b2f" />
    </svg>
  )
}
