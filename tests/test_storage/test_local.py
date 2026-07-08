import json

import pytest

from storage.local import LocalStorage


@pytest.fixture
def local_storage(tmp_path):
    return LocalStorage(output_dir=str(tmp_path))


class TestLocalStorage:
    def test_local_save_creates_file(self, local_storage, tmp_path):
        data = {"title": "Test Brief", "tone": "informative"}
        local_storage.save("job123", "director", "brief.json", data)
        file_path = tmp_path / "job123" / "director" / "brief.json"
        assert file_path.exists()
        assert json.loads(file_path.read_text()) == data

    def test_local_save_creates_directories(self, local_storage, tmp_path):
        data = {"key": "value"}
        local_storage.save("job456", "research", "notes.json", data)
        dir_path = tmp_path / "job456" / "research"
        assert dir_path.exists()
        assert dir_path.is_dir()

    def test_local_load_reads_file(self, local_storage):
        data = {"scene_number": 1, "narration": "Opening scene"}
        local_storage.save("job123", "script", "scene1.json", data)
        result = local_storage.load("job123", "script", "scene1.json")
        assert result == data

    def test_local_load_returns_none_for_missing(self, local_storage):
        result = local_storage.load("nonexistent", "director", "brief.json")
        assert result is None

    def test_local_exists_returns_true_for_existing(self, local_storage):
        local_storage.save("job123", "director", "brief.json", {"title": "test"})
        assert local_storage.exists("job123", "director", "brief.json") is True

    def test_local_exists_returns_false_for_missing(self, local_storage):
        assert local_storage.exists("nonexistent", "director", "brief.json") is False

    def test_local_save_and_load_roundtrip(self, local_storage):
        data = {"title": "Complex Brief", "scenes": [1, 2, 3], "nested": {"key": "val"}}
        local_storage.save("job789", "director", "brief.json", data)
        result = local_storage.load("job789", "director", "brief.json")
        assert result == data

    def test_local_list_artifacts_returns_filenames(self, local_storage):
        local_storage.save("job123", "director", "brief.json", {"a": 1})
        local_storage.save("job123", "director", "notes.json", {"b": 2})
        artifacts = local_storage.list_artifacts("job123", "director")
        assert set(artifacts) == {"brief.json", "notes.json"}

    def test_local_list_artifacts_empty_directory(self, local_storage):
        artifacts = local_storage.list_artifacts("nonexistent", "director")
        assert artifacts == []
