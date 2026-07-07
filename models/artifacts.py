from models.enums import AgentName


def agent_output_dir(job_id: str, agent_name: AgentName) -> str:
    return f"outputs/{job_id}/{agent_name.value}"


def artifact_path(job_id: str, agent_name: AgentName, filename: str) -> str:
    return f"outputs/{job_id}/{agent_name.value}/{filename}"


def context_path(job_id: str) -> str:
    return f"outputs/{job_id}/context.json"
