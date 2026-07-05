"""
Portfolio example: refresh a long-running lakehouse transition branch.

The script can either rebase or merge the transition branch onto the latest
target branch. In a migration program this runs on a GitLab schedule so branch
drift and conflicts are discovered before a large cutover window.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Sequence

import requests


def run(args: Sequence[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(args))
    return subprocess.run(args, text=True, check=check, capture_output=False)


def output(args: Sequence[str]) -> str:
    return subprocess.check_output(args, text=True).strip()


def notify(message: str) -> None:
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        print(message)
        return

    response = requests.post(webhook_url, json={"text": message}, timeout=10)
    response.raise_for_status()


def ensure_clean_worktree() -> None:
    status = output(["git", "status", "--porcelain"])
    if status:
        raise RuntimeError(
            "Working tree is not clean. Refusing to refresh transition branch."
        )


def configure_git_identity() -> None:
    git_user_name = os.getenv("GIT_USER_NAME", "migration-automation")
    git_user_email = os.getenv("GIT_USER_EMAIL", "migration-automation@example.com")
    run(["git", "config", "user.name", git_user_name])
    run(["git", "config", "user.email", git_user_email])


def refresh_branch() -> None:
    remote = os.getenv("GIT_REMOTE_NAME", "origin")
    target_branch = os.getenv("TARGET_BRANCH", "main")
    transition_branch = os.getenv("TRANSITION_BRANCH", "lakehouse-transition")
    strategy = os.getenv("UPDATE_STRATEGY", "rebase").lower()

    if strategy not in {"rebase", "merge"}:
        raise ValueError("UPDATE_STRATEGY must be either 'rebase' or 'merge'.")

    ensure_clean_worktree()
    configure_git_identity()

    run(["git", "fetch", remote, "--prune"])
    run(["git", "checkout", transition_branch])
    run(["git", "reset", "--hard", f"{remote}/{transition_branch}"])

    try:
        if strategy == "rebase":
            run(["git", "rebase", f"{remote}/{target_branch}"])
            run(["git", "push", "--force-with-lease", remote, transition_branch])
        else:
            run(["git", "merge", "--no-edit", f"{remote}/{target_branch}"])
            run(["git", "push", remote, transition_branch])
    except subprocess.CalledProcessError:
        conflicts = output(["git", "diff", "--name-only", "--diff-filter=U"])
        message = (
            f"Transition branch refresh failed for '{transition_branch}'. "
            f"Resolve conflicts with '{target_branch}' before continuing cutover."
        )
        if conflicts:
            message += f"\n\nConflicting files:\n{conflicts}"
        notify(message)
        raise

    notify(
        f"Transition branch '{transition_branch}' refreshed from '{target_branch}' "
        f"using {strategy}."
    )


def main() -> int:
    try:
        refresh_branch()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
