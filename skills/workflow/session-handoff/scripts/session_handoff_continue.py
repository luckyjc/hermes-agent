#!/usr/bin/env python3
"""Launch a new Hermes continuation from a session handoff file.

Conservative defaults:
- Outside tmux: run a one-shot `launcher chat -q <handoff-file instruction>` unless --background is used.
- Inside tmux with --tmux-interactive: open a new interactive launcher window,
  paste a short instruction containing the handoff file location, submit it, then
  optionally /exit the old pane.

The helper only sends /exit to the old pane when explicitly requested, tmux is
verified, and the continuation launch/paste succeeds.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


def run(cmd: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check)


def tmux_current_pane() -> str | None:
    # Some Hermes terminal tool invocations run inside a tmux client but do not
    # preserve TMUX in the subprocess environment. Ask tmux directly first;
    # outside tmux this simply fails and we fall back to manual/background modes.
    proc = run(["tmux", "display-message", "-p", "#{pane_id}"])
    if proc.returncode != 0:
        return None
    pane = proc.stdout.strip()
    return pane or None


def tmux_target_exists(target: str) -> bool:
    proc = run(["tmux", "display-message", "-t", target, "-p", "#{pane_id}"])
    return proc.returncode == 0 and bool(proc.stdout.strip())


def tmux_session_for_target(target: str) -> str | None:
    proc = run(["tmux", "display-message", "-t", target, "-p", "#{session_id}"])
    if proc.returncode != 0:
        return None
    session = proc.stdout.strip()
    return session or None


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
    parser.add_argument("--launcher", default="hcc", help="Hermes launcher executable, default: hcc")
    parser.add_argument(
        "--launcher-arg",
        action="append",
        default=[],
        help="Additional argument to pass to the launcher executable. Repeat for multiple args.",
    )
    yolo_group = parser.add_mutually_exclusive_group()
    yolo_group.add_argument(
        "--yolo",
        dest="yolo",
        action="store_true",
        help="Launch with --yolo (default).",
    )
    yolo_group.add_argument(
        "--no-yolo",
        dest="yolo",
        action="store_false",
        help="Launch without --yolo.",
    )
    parser.set_defaults(yolo=True)
    parser.add_argument(
        "--manual",
        action="store_true",
        help="Validate and report the handoff file path without launching a continuation.",
    )
    parser.add_argument("--background", action="store_true", help="Start one-shot continuation in background")
    parser.add_argument("--tmux-interactive", action="store_true", help="When in tmux, start interactive launcher in a split pane by default, paste handoff, submit")
    parser.add_argument("--tmux-window-name", default="session-handoff", help="Name for tmux interactive continuation window")
    parser.add_argument("--tmux-window", action="store_true", help="When in tmux interactive mode, open a new window instead of the default split pane")
    parser.add_argument(
        "--tmux-target",
        help=(
            "tmux pane/window/session target to anchor the continuation to. "
            "Defaults to the pane detected when this helper starts. Splits land next to this target; "
            "new windows land in this target's session."
        ),
    )
    parser.add_argument(
        "--exit",
        "--tmux-exit-old",
        dest="tmux_exit_old",
        action="store_true",
        help="After the verified interactive continuation is ready, send /exit to the old pane.",
    )
    parser.add_argument("--startup-wait", type=float, default=1.0, help="Minimum seconds to wait before checking/pasting into new interactive window")
    parser.add_argument("--prompt-wait-timeout", type=float, default=30.0, help="Seconds to wait for the interactive prompt before pasting")
    parser.add_argument("--dry-run", action="store_true", help="Print what would run without executing")
    args = parser.parse_args()

    handoff_path = Path(args.handoff_file).expanduser().resolve()
    if not handoff_path.exists():
        print(f"handoff file not found: {handoff_path}", file=sys.stderr)
        return 2

    if not handoff_path.read_text(encoding="utf-8").strip():
        print(f"handoff file is empty: {handoff_path}", file=sys.stderr)
        return 2

    if args.manual:
        print(f"manual handoff requested; handoff_file={handoff_path}")
        return 0

    launcher_path = shutil.which(args.launcher)
    if not launcher_path:
        print(f"launcher not found: {args.launcher}", file=sys.stderr)
        return 2

    launcher_args = list(args.launcher_arg)
    if args.yolo:
        launcher_args.append("--yolo")
    launcher_cmd = [launcher_path, *launcher_args]
    launcher_printable = " ".join([args.launcher, *launcher_args])

    current_pane = tmux_current_pane()
    tmux_target = args.tmux_target or current_pane
    # Never inject the handoff body into a new terminal. Large multiline pastes
    # can be split or partially submitted by terminal/TUI layers. Every launch
    # mode receives only this short path instruction and must read the canonical
    # handoff file as its first action.
    handoff_file_instruction = (
        f"Read and follow the SESSION HANDOFF at {handoff_path}. "
        "Use tools to inspect the file first, then continue the work."
    )
    one_shot_cmd = [*launcher_cmd, "chat", "-q", handoff_file_instruction]
    background_cmd = [*launcher_cmd, "chat", "-q", handoff_file_instruction]
    one_shot_printable = f"{launcher_printable} chat -q '<handoff-file instruction>'"
    background_printable = f"{launcher_printable} chat -q '<handoff-file instruction>'"

    if args.dry_run:
        print(f"handoff_file={handoff_path}")
        print(f"launcher={launcher_path}")
        if launcher_args:
            print(f"launcher_args={' '.join(launcher_args)}")
        print(f"tmux_current_pane={current_pane or '(not in tmux)'}")
        print(f"tmux_target={tmux_target or '(none)'}")
        if args.tmux_interactive:
            print(f"would_tmux_interactive={'yes' if tmux_target else 'no (not in tmux)'}")
            print(f"would_start_{'window' if args.tmux_window else 'pane'}={args.tmux_window_name}")
            print(f"would_anchor_target={tmux_target or '(none)'}")
            print(f"would_run_interactive={launcher_printable}")
            print(f"would_paste_handoff_file_instruction={handoff_path}")
            print(f"would_exit_old_pane={'yes' if args.tmux_exit_old and current_pane else 'no'}")
        else:
            print(f"would_run={background_printable if args.background else one_shot_printable}")
            if args.tmux_exit_old:
                print("would_exit_old_pane=no (requires --tmux-interactive)")
        return 0

    if args.tmux_interactive:
        if not tmux_target:
            print("--tmux-interactive requested but TMUX/current pane was not detected and no --tmux-target was provided", file=sys.stderr)
            return 2
        if not tmux_target_exists(tmux_target):
            print(f"tmux target was not found: {tmux_target}", file=sys.stderr)
            return 2
        if args.tmux_exit_old and not current_pane:
            print("--exit requires the current tmux pane to be detected; not closing any pane", file=sys.stderr)
            return 2
        assert tmux_target is not None

        # Start plain interactive launcher anchored to the pane/window/session that
        # invoked the handoff. This keeps related continuations in the same IDE or
        # tmux instance even if another tmux client/window becomes active before
        # the helper runs. Use a new window only when explicitly requested.
        if args.tmux_window:
            target_session = tmux_session_for_target(tmux_target)
            if not target_session:
                print(f"could not resolve session for tmux target: {tmux_target}", file=sys.stderr)
                return 2
            proc = run([
                "tmux", "new-window", "-t", target_session,
                "-P", "-F", "#{pane_id}",
                "-n", args.tmux_window_name,
                *launcher_cmd,
            ])
        else:
            proc = run([
                "tmux", "split-window", "-t", tmux_target,
                "-P", "-F", "#{pane_id}",
                *launcher_cmd,
            ])
        if proc.returncode != 0:
            print(proc.stderr or proc.stdout, file=sys.stderr)
            return proc.returncode or 1
        new_pane = proc.stdout.strip()
        if not new_pane or not tmux_pane_exists(new_pane):
            print(f"new tmux pane was not verified: {new_pane!r}", file=sys.stderr)
            return 1

        time.sleep(max(0.0, args.startup_wait))
        prompt_marker = f"{Path(launcher_path).name}>"
        if not wait_for_tmux_prompt(new_pane, prompt_marker, args.prompt_wait_timeout):
            print(
                f"interactive prompt was not detected in tmux pane {new_pane} "
                f"within {args.prompt_wait_timeout:.1f}s; not pasting or exiting old pane",
                file=sys.stderr,
            )
            return 1

        # Paste only the short handoff-file instruction. Do not paste the
        # handoff body: large multiline input can be fragmented by the terminal
        # or TUI and disrupt the receiving agent. Bracketed paste remains useful
        # to preserve this instruction as one prompt.
        buffer_name = f"session-handoff-{os.getpid()}"
        load = run(["tmux", "set-buffer", "-b", buffer_name, handoff_file_instruction])
        if load.returncode != 0:
            print(load.stderr or load.stdout, file=sys.stderr)
            return load.returncode or 1
        paste = run(["tmux", "paste-buffer", "-p", "-r", "-d", "-b", buffer_name, "-t", new_pane])
        if paste.returncode != 0:
            print(paste.stderr or paste.stdout, file=sys.stderr)
            return paste.returncode or 1
        submit = run(["tmux", "send-keys", "-t", new_pane, "Enter"])
        if submit.returncode != 0:
            print(submit.stderr or submit.stdout, file=sys.stderr)
            return submit.returncode or 1

        print(
            f"started verified interactive continuation in tmux pane {new_pane} "
            f"from {handoff_path}"
        )
        if args.tmux_exit_old:
            exit_proc = run(["tmux", "send-keys", "-t", current_pane, "/exit", "Enter"])
            if exit_proc.returncode != 0:
                print(exit_proc.stderr or exit_proc.stdout, file=sys.stderr)
                return exit_proc.returncode or 1
            print(f"sent /exit to old tmux pane {current_pane}")
        return 0

    if args.background:
        proc = subprocess.Popen(background_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        print(f"started background one-shot continuation pid={proc.pid} from {handoff_path}")
        return 0

    print(f"running: {one_shot_printable}", file=sys.stderr)
    proc = subprocess.run(one_shot_cmd)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
