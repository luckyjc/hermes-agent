#!/usr/bin/env python3
"""Launch a new Hermes continuation from a session handoff file.

Conservative defaults:
- Outside tmux: run a one-shot `launcher chat -q <handoff>` unless --background is used.
- Inside tmux with --tmux-interactive: open a new interactive launcher window,
  paste the handoff prompt into it, submit it, then optionally /exit the old pane.

The helper only sends /exit to the old pane when explicitly requested, tmux is
verified, and the continuation launch/paste succeeds.
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path


def run(cmd: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check)


def tmux_current_pane() -> str | None:
    if not os.environ.get("TMUX"):
        return None
    proc = run(["tmux", "display-message", "-p", "#{pane_id}"])
    if proc.returncode != 0:
        return None
    pane = proc.stdout.strip()
    return pane or None


def tmux_pane_exists(pane_id: str) -> bool:
    proc = run(["tmux", "display-message", "-t", pane_id, "-p", "#{pane_id}"])
    return proc.returncode == 0 and proc.stdout.strip() == pane_id


def wait_for_tmux_prompt(pane_id: str, prompt_marker: str, timeout: float) -> bool:
    """Wait until the interactive Hermes prompt is visible in the pane."""
    deadline = time.monotonic() + max(0.0, timeout)
    markers = [prompt_marker, "Type your message or /help for commands"]
    while time.monotonic() <= deadline:
        proc = run(["tmux", "capture-pane", "-t", pane_id, "-p", "-S", "-80"])
        if proc.returncode == 0 and any(marker and marker in proc.stdout for marker in markers):
            return True
        time.sleep(0.5)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Start Hermes continuation from handoff file")
    parser.add_argument("handoff_file", help="Path to SESSION HANDOFF markdown/text file")
    parser.add_argument("--launcher", default="hcc", help="Hermes launcher command, default: hcc")
    parser.add_argument("--background", action="store_true", help="Start one-shot continuation in background")
    parser.add_argument("--tmux-interactive", action="store_true", help="When in tmux, start interactive launcher in a new window, paste handoff, submit")
    parser.add_argument("--tmux-window-name", default="session-handoff", help="Name for tmux interactive continuation window")
    parser.add_argument("--tmux-exit-old", action="store_true", help="After interactive continuation starts, send /exit to the old pane")
    parser.add_argument("--startup-wait", type=float, default=1.0, help="Minimum seconds to wait before checking/pasting into new interactive window")
    parser.add_argument("--prompt-wait-timeout", type=float, default=30.0, help="Seconds to wait for the interactive prompt before pasting")
    parser.add_argument("--dry-run", action="store_true", help="Print what would run without executing")
    args = parser.parse_args()

    handoff_path = Path(args.handoff_file).expanduser().resolve()
    if not handoff_path.exists():
        print(f"handoff file not found: {handoff_path}", file=sys.stderr)
        return 2

    prompt = handoff_path.read_text(encoding="utf-8")
    if not prompt.strip():
        print(f"handoff file is empty: {handoff_path}", file=sys.stderr)
        return 2

    launcher_path = run(["bash", "-lc", f"command -v {shlex.quote(args.launcher)}"])
    if launcher_path.returncode != 0 or not launcher_path.stdout.strip():
        print(f"launcher not found: {args.launcher}", file=sys.stderr)
        return 2

    current_pane = tmux_current_pane()
    one_shot_cmd = [args.launcher, "chat", "-q", prompt]
    one_shot_printable = f"{args.launcher} chat -q $(cat {shlex.quote(str(handoff_path))})"

    if args.dry_run:
        print(f"handoff_file={handoff_path}")
        print(f"launcher={launcher_path.stdout.strip()}")
        print(f"tmux_current_pane={current_pane or '(not in tmux)'}")
        if args.tmux_interactive:
            print(f"would_tmux_interactive={'yes' if current_pane else 'no (not in tmux)'}")
            print(f"would_start_window={args.tmux_window_name}")
            print(f"would_run_interactive={args.launcher}")
            print(f"would_paste_handoff_file={handoff_path}")
            print(f"would_exit_old_pane={'yes' if args.tmux_exit_old and current_pane else 'no'}")
        else:
            print(f"would_run={one_shot_printable}")
            if args.tmux_exit_old:
                print("would_exit_old_pane=no (requires --tmux-interactive)")
        return 0

    if args.tmux_interactive:
        if not current_pane:
            print("--tmux-interactive requested but TMUX/current pane was not detected", file=sys.stderr)
            return 2

        # Start plain interactive launcher. -P -F returns the new pane id so we can target it safely.
        proc = run([
            "tmux", "new-window", "-P", "-F", "#{pane_id}",
            "-n", args.tmux_window_name,
            args.launcher,
        ])
        if proc.returncode != 0:
            print(proc.stderr or proc.stdout, file=sys.stderr)
            return proc.returncode or 1
        new_pane = proc.stdout.strip()
        if not new_pane or not tmux_pane_exists(new_pane):
            print(f"new tmux pane was not verified: {new_pane!r}", file=sys.stderr)
            return 1

        time.sleep(max(0.0, args.startup_wait))
        prompt_marker = f"{Path(args.launcher).name}>"
        if not wait_for_tmux_prompt(new_pane, prompt_marker, args.prompt_wait_timeout):
            print(
                f"interactive prompt was not detected in tmux pane {new_pane} "
                f"within {args.prompt_wait_timeout:.1f}s; not pasting or exiting old pane",
                file=sys.stderr,
            )
            return 1

        # Load a dedicated tmux buffer from file and paste it into the new pane.
        # This avoids command-line/history exposure and handles multi-line prompts better than send-keys.
        buffer_name = f"session-handoff-{os.getpid()}"
        load = run(["tmux", "load-buffer", "-b", buffer_name, str(handoff_path)])
        if load.returncode != 0:
            print(load.stderr or load.stdout, file=sys.stderr)
            return load.returncode or 1
        paste = run(["tmux", "paste-buffer", "-d", "-b", buffer_name, "-t", new_pane])
        if paste.returncode != 0:
            print(paste.stderr or paste.stdout, file=sys.stderr)
            return paste.returncode or 1
        submit = run(["tmux", "send-keys", "-t", new_pane, "Enter"])
        if submit.returncode != 0:
            print(submit.stderr or submit.stdout, file=sys.stderr)
            return submit.returncode or 1

        print(f"started interactive continuation in tmux pane {new_pane} from {handoff_path}")
        if args.tmux_exit_old:
            exit_proc = run(["tmux", "send-keys", "-t", current_pane, "/exit", "Enter"])
            if exit_proc.returncode != 0:
                print(exit_proc.stderr or exit_proc.stdout, file=sys.stderr)
                return exit_proc.returncode or 1
            print(f"sent /exit to old tmux pane {current_pane}")
        return 0

    if args.background:
        proc = subprocess.Popen(one_shot_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        print(f"started background one-shot continuation pid={proc.pid} from {handoff_path}")
        return 0

    print(f"running: {one_shot_printable}", file=sys.stderr)
    proc = subprocess.run(one_shot_cmd)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
