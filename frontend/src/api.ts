import type {
  GenerateResponse,
  JobDetailsResponse,
  ResultResponse,
  ResumeResponse,
} from "./types"

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = "ApiError"
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  const body = await response.json().catch(() => null) as
    | { detail?: string }
    | T
    | null
  if (!response.ok) {
    const detail = body && typeof body === "object" && "detail" in body
      ? body.detail
      : undefined
    throw new ApiError(
      response.status,
      detail || `Request failed (${response.status})`,
    )
  }
  return body as T
}

export function generateJob(prompt: string): Promise<GenerateResponse> {
  return request("/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
  })
}

export function getJobDetails(jobId: string): Promise<JobDetailsResponse> {
  return request(`/details/${encodeURIComponent(jobId)}`)
}

export function getJobResult(jobId: string): Promise<ResultResponse> {
  return request(`/result/${encodeURIComponent(jobId)}`)
}

export function resumeJob(jobId: string): Promise<ResumeResponse> {
  return request(`/resume/${encodeURIComponent(jobId)}`, { method: "POST" })
}

export function resultDownloadUrl(jobId: string): string {
  return `/result/${encodeURIComponent(jobId)}/download`
}

export function clipVideoUrl(jobId: string, shotNumber: number): string {
  return `/result/${encodeURIComponent(jobId)}/clips/${shotNumber}`
}
