# GitLab Auto-Rebase Transition Branch

This folder shows the branch automation behind the long-running
`lakehouse-transition` branch. The goal was to let normal production work
continue on `main` while migration-specific Trino/Iceberg changes were kept
fresh, tested, and conflict-visible before cutover.

## Files

- [transition_branch_refresh.py](transition_branch_refresh.py) - scheduled
  branch refresh script with merge or rebase mode and conflict notification.
- [gitlab-ci.transition-branch-refresh.yml](gitlab-ci.transition-branch-refresh.yml)
  - GitLab scheduled pipeline job that runs the refresh.
- [gitlab_shift_left_flow.mmd](gitlab_shift_left_flow.mmd) - Mermaid source for
  the shift-left control flow.

## Why It Matters

The transition branch prevented migration changes from blocking ordinary
development, while scheduled refreshes exposed drift and conflicts early enough
to resolve them before a cutover window.
