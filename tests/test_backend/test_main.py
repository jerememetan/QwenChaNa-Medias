"""Production app wiring tests."""

import backend.main as main_module
from models.enums import AgentName


def test_production_app_includes_editor_as_seventh_agent(monkeypatch):
    captured = {}

    def capture_app(storage, job_store, agents):
        captured["agents"] = agents
        return object()

    monkeypatch.setattr(main_module, "create_app", capture_app)

    main_module.create_production_app()

    assert [agent.name for agent in captured["agents"]] == [
        AgentName.DIRECTOR,
        AgentName.RESEARCH,
        AgentName.SCRIPT,
        AgentName.STORYBOARD,
        AgentName.VIDEO,
        AgentName.VOICE,
        AgentName.EDITOR,
    ]
