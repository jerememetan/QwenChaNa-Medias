export type AgentName =
  | "director"
  | "research"
  | "script"
  | "storyboard"
  | "video"
  | "voice"
  | "editor"

export type JobStatus = "pending" | "running" | "completed" | "failed"

export interface ArtifactRef {
  agent_name: AgentName
  filename: string
  content_type: string
  size_bytes?: number | null
}

export interface AgentResult {
  agent_name: AgentName
  success: boolean
  output_data: Record<string, unknown>
  artifacts: ArtifactRef[]
  error?: string | null
  duration_seconds?: number | null
}

export interface GenerateResponse {
  job_id: string
}

export interface ResumeResponse {
  job_id: string
}

export interface JobDetailsResponse {
  job_id: string
  prompt: string
  status: JobStatus
  current_agent: AgentName | null
  failed_agent: AgentName | null
  error: string | null
  agent_results: Partial<Record<AgentName, AgentResult>>
}

export interface ResultResponse {
  job_id: string
  status: "completed"
  output_path: string
  download_url: string
  artifacts: ArtifactRef[]
}
