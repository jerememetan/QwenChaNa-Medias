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
