from backend.config import Settings
from backend.factory import build_production_agents
from models.enums import AgentName
from storage.local import LocalStorage


def test_build_production_agents_uses_supplied_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEO_MODEL", "wan-test")
    monkeypatch.setenv("VOICE_MODEL", "cosy-test")
    monkeypatch.setenv("VOICE_VOICE", "longqiang_v3")
    settings = Settings()
    storage = LocalStorage(str(tmp_path))

    agents = build_production_agents(
        settings,
        storage,
        output_dir=tmp_path,
    )

    indexed = {agent.name: agent for agent in agents}
    assert indexed[AgentName.VIDEO].video_service.config.model == "wan-test"
    assert indexed[AgentName.VOICE].tts_service.config.model == "cosy-test"
    assert indexed[AgentName.VOICE].tts_service.config.voice == "longqiang_v3"
    assert len(agents) == 7


def test_new_settings_instance_reads_changed_dotenv(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VIDEO_MODEL", raising=False)
    monkeypatch.delenv("VOICE_MODEL", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "VIDEO_MODEL=wan-first\nVOICE_MODEL=cosy-first\n",
        encoding="utf-8",
    )
    storage = LocalStorage(str(tmp_path / "outputs"))
    first = build_production_agents(
        Settings(),
        storage,
        output_dir=tmp_path / "outputs",
    )
    env_file.write_text(
        "VIDEO_MODEL=wan-second\nVOICE_MODEL=cosy-second\n",
        encoding="utf-8",
    )
    second = build_production_agents(
        Settings(),
        storage,
        output_dir=tmp_path / "outputs",
    )
    first_by_name = {agent.name: agent for agent in first}
    second_by_name = {agent.name: agent for agent in second}

    assert first_by_name[AgentName.VIDEO].video_service.config.model == "wan-first"
    assert second_by_name[AgentName.VIDEO].video_service.config.model == "wan-second"
    assert first_by_name[AgentName.VOICE].tts_service.config.model == "cosy-first"
    assert second_by_name[AgentName.VOICE].tts_service.config.model == "cosy-second"
