# Warehouse-to-Lakehouse Migration Technical Deep Dive

This repository documents the technical mechanics behind a large Redshift to
Trino/Starburst and Apache Iceberg migration. The slide deck tells the executive
story; this repository shows how the migration was organized, validated, and
cut over.

## Executive Summary

The migration moved a 200+ TB Redshift warehouse into an Apache Iceberg
lakehouse queried through Trino/Starburst. The hard part was not only moving
data. The hard part was keeping thousands of modeled objects, downstream
dependencies, and business metrics stable while the platform changed underneath
them.

The migration system had three parts:

1. A control plane that tracked which objects had moved.
2. A dbt translation layer that converted Redshift-oriented code to
   Trino/Iceberg-compatible code.
3. GitLab branch and CI controls that caught migration problems before merge.

## Impact

- Migrated a 200+ TB Redshift warehouse to a Trino/Starburst query layer backed
  by Apache Iceberg tables.
- Replatformed 2,000+ dbt-modeled objects while preserving object-level parity.
- Used a hot-swap cutover so existing BI, analytics, and downstream jobs did not
  need repeated repointing.
- Built shift-left controls so translation, branch freshness, dependency, and
  validation issues were caught before production users depended on the new
  lakehouse objects.
- Reduced platform cost by roughly 60% while keeping existing workflows stable.

## Repository Map

| Area | What it contains |
| --- | --- |
| [translation-engine](translation-engine/) | Redshift-to-Trino rules, dbt/Jinja cleanup process, and standalone processor script |
| [gitlab-autorebase-transition-branch](gitlab-autorebase-transition-branch/) | Scheduled transition-branch refresh, GitLab CI job, and shift-left flow |
| [tableau-migration-tracker](tableau-migration-tracker/) | Migration tracker screenshot and dbt SQL model for object status |

## Target Architecture

```mermaid
flowchart LR
    A[Redshift warehouse] --> B[Source object inventory]
    B --> C[Migration mapping]
    C --> D[dbt translation layer]
    D --> E[GitLab transition branch]
    E --> F[CI validation gates]
    F --> G[dbt build on Trino]
    G --> H[Apache Iceberg tables]
    H --> I[Trino / Starburst]
    I --> J[BI, analytics, AI, and jobs]

    F --> K[Schema parity]
    F --> L[Row-count parity]
    F --> M[Metric parity]
    K --> N[Cutover readiness]
    L --> N
    M --> N
```

## Migration Control Plane

The migration tracker created a single source of truth for object progress. It
joined the source warehouse/dbt inventory to the target Iceberg catalog and
classified each object as migrated, required but not migrated, or intentionally
held.

The tracker supported:

- progress by schema or folder,
- object-level cutover status,
- counts for dashboarding,
- prioritization of high-usage objects,
- exception handling for intentionally retired or on-hold objects.

See [tableau-migration-tracker](tableau-migration-tracker/).

## dbt Translation Layer

The code migration required more than changing the connection profile from
Redshift to Trino. A safer translation layer handled predictable differences:

| Redshift-oriented pattern | Trino/Iceberg migration concern |
| --- | --- |
| `dist`, `sort`, `distribution` configs | Not valid or not useful for Trino/Iceberg |
| Redshift date functions | Function signatures differ in Trino |
| `::type` casts | Prefer explicit `CAST(expr AS type)` |
| warehouse-specific schemas | Need migration-aware source routing |
| table rebuild assumptions | Iceberg has snapshot and maintenance behavior |
| incremental model strategy | Adapter-specific merge/delete behavior differs |

The translation layer was built around dbt/Jinja rendering, config governance,
and SQL parsing:

- extract dbt `config(...)` keys and block unsupported Redshift-only config,
- render dbt models before parsing,
- parse generated SQL to catch translation failures,
- route source references through a migration mapping,
- standardize function and cast translation with explicit macros.

See [translation-engine](translation-engine/).

## GitLab Transition Branch Strategy

The migration used a long-running transition branch to isolate platform changes
without freezing normal development. `main` continued to receive production
changes while the migration branch translated and validated models against the
lakehouse target.

The key controls were:

- scheduled branch refresh from `main`,
- conflict notifications when source and migration edits diverged,
- merge request branch freshness checks,
- compile and parse checks on changed SQL,
- config-key checks for adapter-specific drift,
- dependency checks to preserve dbt layering rules.

See [gitlab-autorebase-transition-branch](gitlab-autorebase-transition-branch/).
