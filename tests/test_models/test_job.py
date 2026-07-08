import pytest
from models.enums import AgentName, JobStatus
from models.job import JobRecord


class TestEnums:
    def test_job_status_enum_values(self):
        expected = {"pending", "running", "completed", "failed"}
        actual = set(JobStatus)
        assert actual == expected

    def test_agent_name_enum_values(self):
        expected = {"director", "research", "script", "storyboard", "video", "voice", "editor"}
        actual = set(AgentName)
        assert actual == expected

    def test_agent_name_serializes_as_string(self):
        assert AgentName.DIRECTOR.value == "director"
        assert AgentName.DIRECTOR == "director"

    def test_job_status_serializes_as_string(self):
        assert JobStatus.PENDING.value == "pending"
        assert JobStatus.PENDING == "pending"


class TestJobRecord:
    def test_job_record_creation(self):
        record = JobRecord(job_id="abc", prompt="test")
        assert record.status == JobStatus.PENDING

    def test_job_record_default_timestamps(self):
        record = JobRecord(job_id="abc", prompt="test")
        assert record.created_at is not None
        assert record.updated_at is not None

    def test_job_record_serialization(self):
        record = JobRecord(job_id="abc", prompt="test")
        json_str = record.model_dump_json()
        restored = JobRecord.model_validate_json(json_str)
        assert restored.job_id == record.job_id
        assert restored.prompt == record.prompt
        assert restored.status == record.status

    def test_job_record_tracks_failure(self):
        record = JobRecord(job_id="abc", prompt="test")
        assert record.failed_agent is None
        assert record.error is None
        record.failed_agent = AgentName.SCRIPT
        record.error = "LLM timeout"
        assert record.failed_agent == AgentName.SCRIPT
        assert record.error == "LLM timeout"

    def test_job_record_status_transition(self):
        record = JobRecord(job_id="abc", prompt="test")
        assert record.status == JobStatus.PENDING
        record.status = JobStatus.RUNNING
        assert record.status == JobStatus.RUNNING
        record.status = JobStatus.COMPLETED
        assert record.status == JobStatus.COMPLETED
