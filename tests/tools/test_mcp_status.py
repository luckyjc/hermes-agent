from tools import mcp_tool


class _FakeServer:
    session = object()
    _registered_tool_names = ["tool_a", "tool_b"]
    _tools = []
    _sampling = None


def test_get_mcp_status_returns_empty_when_no_servers_configured(monkeypatch):
    monkeypatch.setattr(mcp_tool, "_load_mcp_config", lambda: {})

    assert mcp_tool.get_mcp_status() == []


def test_get_mcp_status_surfaces_disabled_servers(monkeypatch):
    monkeypatch.setattr(
        mcp_tool,
        "_load_mcp_config",
        lambda: {
            "disabled-memory": {
                "command": "python",
                "args": ["server.py"],
                "enabled": False,
            },
            "disabled-filesystem": {
                "command": "python",
                "args": ["filesystem.py"],
                "enabled": "false",
            },
            "enabled-context": {
                "command": "npx",
                "args": ["context7"],
            },
        },
    )

    with mcp_tool._lock:
        old_servers = dict(mcp_tool._servers)
        mcp_tool._servers.clear()
        mcp_tool._servers["enabled-context"] = _FakeServer()
    try:
        status = mcp_tool.get_mcp_status()
    finally:
        with mcp_tool._lock:
            mcp_tool._servers.clear()
            mcp_tool._servers.update(old_servers)

    statuses = {entry["name"]: entry for entry in status}
    assert set(statuses) == {"disabled-memory", "disabled-filesystem", "enabled-context"}
    assert statuses["disabled-memory"]["status"] == "disabled"
    assert statuses["disabled-memory"]["disabled"] is True
    assert statuses["disabled-filesystem"]["status"] == "disabled"
    assert statuses["disabled-filesystem"]["disabled"] is True
    assert statuses["enabled-context"]["status"] == "connected"
    assert statuses["enabled-context"]["connected"] is True
    assert statuses["enabled-context"]["disabled"] is False
    assert statuses["enabled-context"]["tools"] == 2
