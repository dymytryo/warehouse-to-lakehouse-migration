# Warehouse-to-Lakehouse Migration

This repository is a public-safe portfolio artifact for a Redshift to
Starburst/Trino + Apache Iceberg migration.

The structure is intentionally direct: first the technical architecture, then
the functional migration components that made the cutover possible. It is not an
installable package and does not use generic `examples`, `assets`, `docs`, or
`diagrams` buckets.

## Technical Architecture

The migration used a hot-swap pattern: rebuild the warehouse in Iceberg behind a
new Starburst catalog, validate the mirror, then rename catalogs so consumers
keep querying the same logical endpoint.

![Warehouse to lakehouse cutover architecture](technical-architecture/warehouse-lakehouse-architecture.png)

Source diagram:
[technical-architecture/warehouse-to-lakehouse-flow.mmd](technical-architecture/warehouse-to-lakehouse-flow.mmd)

## Functional Components

| Component | Purpose | Key files |
| --- | --- | --- |
| [technical-architecture](technical-architecture/) | End-to-end target-state architecture and hot-swap flow. | `warehouse-lakehouse-architecture.png`, `warehouse-to-lakehouse-flow.mmd` |
| [tableau-tracker](tableau-tracker/) | Migration control-plane view used to track object readiness by schema/folder. | `migration-progress-dashboard.png`, `migration-tracker.sql` |
| [gitlab-transition-branch](gitlab-transition-branch/) | Self-rebasing migration branch strategy and shift-left CI controls. | `gitlab-ci.transition-branch-refresh.yml`, `transition-branch-refresh.py`, `migration-readiness-gate.sql`, `branch-controls.md` |
| [dbt-translation-engine](dbt-translation-engine/) | Prototype for deterministic dbt/Jinja cleanup and Redshift-to-Trino translation. | `dbt-jinja-processor.ipynb`, `translation-pattern.md`, `translation-rules.md` |
| [parity-validation](parity-validation/) | Source-vs-target row, column, and type parity checks before cutover. | `parity-validation.py` |
| [cutover-observability](cutover-observability/) | Adoption and runtime screenshots used to validate operational impact after cutover. | `adoption-active-users.png`, `job-duration-post-cutover.png` |

## What This Demonstrates

- Catalog-level hot swap with a reversible rollback path.
- Tableau-facing migration tracking backed by a dbt model.
- A long-running transition branch kept current with `main` through scheduled
  rebase and `--force-with-lease`.
- CI gates that render dbt/Jinja, validate unsupported configs, parse translated
  SQL, build against Trino, and check readiness metadata.
- A dbt translation prototype with an explicit Redshift-to-Trino rule matrix.
- Parity validation across object existence, schema, normalized types, row
  counts, and metrics.

## Cutover Criteria

The migration was considered ready only when required objects were rebuilt in the
lakehouse, translated SQL compiled on Trino, parity checks passed, and consumer
dashboards/jobs showed stable runtime behavior.
