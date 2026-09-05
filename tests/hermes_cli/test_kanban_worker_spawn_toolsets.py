from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


def _make_task(kb, *, assignee: str):
    return kb.Task(
        id="t_spawn_tools",
        title="spawn tools",
        body=None,
        assignee=assignee,
        status="running",
        priority=0,
        created_by="test",
        created_at=1,
        started_at=None,
        completed_at=None,
        workspace_kind="dir",
        workspace_path=None,
        claim_lock="lock",
        claim_expires=None,
        tenant=None,
        current_run_id=7,
    )


def _capture_spawn_env(kb, kbd, monkeypatch, workspace, *, assignee):
    monkeypatch.setattr(kbd, "_resolve_hermes_argv", lambda: ["hermes"])
    captured = {}

    class FakeProc:
        pid = 4242

    def fake_popen(cmd, *args, **kwargs):
        captured["cmd"] = list(cmd)
        captured["env"] = dict(kwargs.get("env") or {})
        captured["cwd"] = kwargs.get("cwd")
        return FakeProc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    pid = kbd._default_spawn(_make_task(kb, assignee=assignee), str(workspace))
    return pid, captured


def _write_profile(root, name, home_mode):
    profile = root / "profiles" / name
    (profile / "home").mkdir(parents=True)
    profile.joinpath("config.yaml").write_text(
        f"terminal:\n  home_mode: {home_mode}\ntoolsets:\n  - kanban\n",
        encoding="utf-8",
    )
    return profile


def test_default_spawn_allow_only_environment_contract(monkeypatch, tmp_path):
    root = tmp_path / ".hermes"
    (root / "home").mkdir(parents=True)
    root.joinpath("config.yaml").write_text("toolsets:\n  - kanban\n", encoding="utf-8")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    real_home = tmp_path / "real-home"
    real_home.mkdir()
    dispatcher = _write_profile(root, "dispatcher", "profile")
    expected_homes = {
        "worker-profile": _write_profile(root, "worker-profile", "profile") / "home",
        "worker-real": real_home,
        "worker-auto": _write_profile(root, "worker-auto", "auto") / "home",
    }
    _write_profile(root, "worker-real", "real")
    attachments_root = tmp_path / "custom-attachments"
    monkeypatch.setenv("HERMES_HOME", str(root))
    monkeypatch.setenv("HERMES_REAL_HOME", str(real_home))
    monkeypatch.setenv("HOME", str(real_home))
    monkeypatch.setenv("TERMINAL_HOME_MODE", "profile")
    monkeypatch.setenv("UNREGISTERED_GATEWAY_SENTINEL", "must-not-cross")
    monkeypatch.setenv("OPENAI_API_KEY", "parent-provider-secret")
    monkeypatch.setenv("PATH", "/safe/bin")
    monkeypatch.setenv("TERMUX_VERSION", "test")
    monkeypatch.setenv("PREFIX", "/data/data/com.termux/files/usr")
    monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "10.43.0.1")
    monkeypatch.setenv("HERMES_KANBAN_ATTACHMENTS_ROOT", str(attachments_root))

    import hermes_constants
    from hermes_constants import reset_hermes_home_override, set_hermes_home_override
    from hermes_cli import kanban_db as kb
    from hermes_cli import kanban_db_dispatch as kbd

    monkeypatch.setattr(hermes_constants, "is_container", lambda: True)
    token = set_hermes_home_override(str(dispatcher))
    try:
        for assignee, expected_home in expected_homes.items():
            _, captured = _capture_spawn_env(
                kb, kbd, monkeypatch, workspace, assignee=assignee
            )
            env = captured["env"]
            assert "UNREGISTERED_GATEWAY_SENTINEL" not in env
            assert "OPENAI_API_KEY" not in env
            assert env["PATH"].split(os.pathsep)[-1] == "/safe/bin"
            assert env["TERMUX_VERSION"] == "test"
            assert env["PREFIX"] == "/data/data/com.termux/files/usr"
            assert env["KUBERNETES_SERVICE_HOST"] == "10.43.0.1"
            assert env["HERMES_HOME"] == str(root / "profiles" / assignee)
            assert env["HOME"] == str(expected_home)
            assert env["HERMES_KANBAN_TASK"] == "t_spawn_tools"
            assert env["HERMES_KANBAN_ATTACHMENTS_ROOT"] == str(attachments_root)
    finally:
        reset_hermes_home_override(token)


def test_default_spawn_real_child_reloads_profile_provider(monkeypatch, tmp_path):
    root = tmp_path / ".hermes"
    root.mkdir()
    root.joinpath("config.yaml").write_text("toolsets:\n  - kanban\n", encoding="utf-8")
    profile = _write_profile(root, "elias", "real")
    profile.joinpath(".env").write_text(
        "OPENAI_API_KEY=profile-provider-secret\n", encoding="utf-8"
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    result_path = tmp_path / "worker-env-result.json"
    repo_root = Path(__file__).resolve().parents[2]
    probe = tmp_path / "worker_env_probe.py"
    probe.write_text(
        "\n".join([
            "import json, os, sys",
            "from pathlib import Path",
            f"sys.path.insert(0, {str(repo_root)!r})",
            "parent_unknown = 'UNREGISTERED_GATEWAY_SENTINEL' in os.environ",
            "parent_provider = 'OPENAI_API_KEY' in os.environ",
            "from hermes_cli.env_loader import load_hermes_dotenv",
            "load_hermes_dotenv(load_external_secrets=False)",
            f"Path({str(result_path)!r}).write_text(json.dumps({{",
            "    'unknown_parent': parent_unknown,",
            "    'provider_parent': parent_provider,",
            "    'profile_provider': os.environ.get('OPENAI_API_KEY') == 'profile-provider-secret',",
            "    'task': os.environ.get('HERMES_KANBAN_TASK'),",
            "    'home': os.environ.get('HERMES_HOME'),",
            "}), encoding='utf-8')",
        ])
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(root))
    monkeypatch.setenv("UNREGISTERED_GATEWAY_SENTINEL", "must-not-cross")
    monkeypatch.setenv("OPENAI_API_KEY", "parent-provider-secret")

    from hermes_cli import kanban_db as kb
    from hermes_cli import kanban_db_dispatch as kbd

    monkeypatch.setattr(
        kbd, "_resolve_hermes_argv", lambda: [sys.executable, str(probe)]
    )
    real_popen = subprocess.Popen
    spawned = {}

    def tracking_popen(*args, **kwargs):
        proc = real_popen(*args, **kwargs)
        spawned["proc"] = proc
        return proc

    monkeypatch.setattr(subprocess, "Popen", tracking_popen)
    pid = kbd._default_spawn(_make_task(kb, assignee="elias"), str(workspace))

    assert pid is not None
    returncode = spawned["proc"].wait(timeout=10)
    log_path = kb.worker_logs_dir() / "t_spawn_tools.log"
    assert returncode == 0, log_path.read_text(encoding="utf-8", errors="replace")
    assert result_path.exists(), "spawned environment probe did not complete"
    assert json.loads(result_path.read_text(encoding="utf-8")) == {
        "unknown_parent": False,
        "provider_parent": False,
        "profile_provider": True,
        "task": "t_spawn_tools",
        "home": str(profile),
    }


def test_default_spawn_pins_assignee_profile_cli_toolsets(monkeypatch, tmp_path):
    """Manual profile assignment should keep that profile's CLI tools.

    Regression guard for dispatcher-spawned workers that boot with
    HERMES_KANBAN_TASK: the worker must not collapse to only kanban lifecycle
    tools when the assigned profile's top-level ``toolsets`` is the default
    composite. The spawned CLI gets an explicit --toolsets pin resolved from
    platform_toolsets.cli; model_tools appends task-scoped kanban tools later.
    """
    root = tmp_path / ".hermes"
    profile = root / "profiles" / "elias"
    profile.mkdir(parents=True)
    profile.joinpath("config.yaml").write_text(
        """
platform_toolsets:
  cli:
    - clarify
    - code_execution
    - delegation
    - file
    - memory
    - session_search
    - skills
    - terminal
    - web
toolsets:
  - hermes-cli
agent:
  disabled_toolsets: []
""".lstrip(),
        encoding="utf-8",
    )
    root.joinpath("config.yaml").write_text("toolsets:\n  - kanban\n", encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(root))

    from hermes_cli import kanban_db as kb
    from hermes_cli import kanban_db_dispatch as kbd

    monkeypatch.setattr(kbd, "_resolve_hermes_argv", lambda: ["hermes"])

    captured = {}

    class FakeProc:
        pid = 4242

    def fake_popen(cmd, *args, **kwargs):
        captured["cmd"] = list(cmd)
        captured["env"] = dict(kwargs.get("env") or {})
        captured["cwd"] = kwargs.get("cwd")
        return FakeProc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    pid = kbd._default_spawn(_make_task(kb, assignee="elias"), str(workspace))

    assert pid == 4242
    assert captured["env"]["HERMES_HOME"] == str(profile)
    assert captured["env"]["HERMES_KANBAN_TASK"] == "t_spawn_tools"
    assert "--toolsets" in captured["cmd"]
    pinned = captured["cmd"][captured["cmd"].index("--toolsets") + 1].split(",")
    for required in ("terminal", "web", "file", "skills", "code_execution", "delegation"):
        assert required in pinned


def test_default_spawn_model_override_survives_real_cli_parse(monkeypatch, tmp_path):
    """The dispatcher's pre-``chat`` model flag must reach ``args.model``.

    This is an integration contract between Kanban's worker argv builder and
    the real CLI parser. A parser default once erased the explicit override,
    silently sending the worker to its profile default or fallback instead.
    """
    root = tmp_path / ".hermes"
    (root / "profiles" / "elias").mkdir(parents=True)
    root.joinpath("config.yaml").write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(root))

    from hermes_cli import kanban_db as kb
    from hermes_cli import kanban_db_dispatch as kbd
    from hermes_cli._parser import build_top_level_parser

    monkeypatch.setattr(kbd, "_resolve_hermes_argv", lambda: ["hermes"])
    captured = {}

    class FakeProc:
        pid = 4244

    def fake_popen(cmd, *args, **kwargs):
        captured["cmd"] = list(cmd)
        return FakeProc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    task = _make_task(kb, assignee="elias")
    task.model_override = "gpt-5.6-sol"
    kbd._default_spawn(task, str(workspace))

    parser, _subparsers, _chat_parser = build_top_level_parser()
    # Profile selection is attached by the outer CLI bootstrap rather than
    # build_top_level_parser(); remove that already-validated prefix and parse
    # the worker flags/subcommand through the real shared parser.
    assert captured["cmd"][1:3] == ["-p", "elias"]
    args = parser.parse_args(captured["cmd"][3:])

    assert args.command == "chat"
    assert args.model == "gpt-5.6-sol"
    assert args.query == "work kanban task t_spawn_tools"


def test_resolve_worker_cli_toolsets_uses_profile_home_not_parent_config(monkeypatch, tmp_path):
    root = tmp_path / ".hermes"
    profile = root / "profiles" / "elias"
    profile.mkdir(parents=True)
    root.joinpath("config.yaml").write_text("platform_toolsets:\n  cli:\n    - kanban\n", encoding="utf-8")
    profile.joinpath("config.yaml").write_text(
        """
platform_toolsets:
  cli:
    - terminal
    - web
toolsets:
  - hermes-cli
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(root))

    from hermes_cli import kanban_db as kb
    from hermes_cli import kanban_db_dispatch as kbd

    resolved = kbd._resolve_worker_cli_toolsets(str(profile))

    assert resolved is not None
    assert "terminal" in resolved
    assert "web" in resolved
    assert "kanban" in resolved  # recovered worker lifecycle surface
    assert resolved != ["kanban"]
