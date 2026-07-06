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

## Files

| Area | Files |
| --- | --- |
| Translation engine | [translation-engine/dbt_jinja_processor.py](translation-engine/dbt_jinja_processor.py), [translation-engine/redshift-to-trino-function-mapping.md](translation-engine/redshift-to-trino-function-mapping.md) |
| Transition branch automation | [gitlab-autorebase-transition-branch/transition_branch_refresh.py](gitlab-autorebase-transition-branch/transition_branch_refresh.py), [gitlab-autorebase-transition-branch/gitlab-ci.transition-branch-refresh.yml](gitlab-autorebase-transition-branch/gitlab-ci.transition-branch-refresh.yml) |
| Migration tracker | [tableau-migration-tracker/migration_tracker.sql](tableau-migration-tracker/migration_tracker.sql), [tableau-migration-tracker/Migration tracker.png](<tableau-migration-tracker/Migration tracker.png>) |

## Target Architecture

```mermaid
flowchart TB
    subgraph Source["Source warehouse"]
        RS[Redshift schemas and dbt models]
        RSQ[Historical query patterns]
    end

    subgraph Migration["Migration control plane"]
        INV[Object inventory]
        MAP[Schema and table mapping]
        TRANS[dbt SQL translation]
        BRANCH[Transition branch]
        CI[GitLab CI quality gates]
        READY[Cutover readiness]
    end

    subgraph Lakehouse["Target lakehouse"]
        S3[Object storage]
        ICE[Apache Iceberg tables]
        CAT[Catalog / metadata]
        TRINO[Trino / Starburst]
    end

    subgraph Consumers["Consumers"]
        BI[BI dashboards]
        JOBS[Batch jobs]
        AI[AI and semantic access]
    end

    RS --> INV
    RSQ --> INV
    INV --> MAP
    MAP --> TRANS
    TRANS --> BRANCH
    BRANCH --> CI
    CI --> ICE
    S3 --> ICE
    CAT --> ICE
    ICE --> TRINO
    TRINO --> BI
    TRINO --> JOBS
    TRINO --> AI
    CI --> READY
    READY --> TRINO
```

## Migration Tracker

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

![Migration tracker](<tableau-migration-tracker/Migration tracker.png>)

The dbt model behind the tracker is
[migration_tracker.sql](tableau-migration-tracker/migration_tracker.sql).

## dbt Translation Layer

The code migration required more than changing the connection profile from
Redshift to Trino. The translation layer handled predictable differences:

| Redshift-oriented construct | Trino/Iceberg migration concern |
| --- | --- |
| `dist`, `sort`, `distribution` configs | Not valid or not useful for Trino/Iceberg |
| Redshift date functions | Function signatures differ in Trino |
| `::type` casts | Prefer explicit `CAST(expr AS type)` |
| warehouse-specific schemas | Need migration-aware source routing |
| table rebuild assumptions | Iceberg has snapshot and maintenance behavior |
| incremental model strategy | Adapter-specific merge/delete behavior differs |

The translation process:

1. Preserve `ref`, `source`, `var`, `dbt_utils`, and known project macros while
   cleaning the parts that are warehouse-specific.
2. Remove Redshift-only dbt config such as `dist`, `sort`, `distkey`, and
   `sortkey`.
3. Add or standardize target config where needed, such as converting selected
   models to Trino/Iceberg views.
4. Remove incremental-only SQL when the target object is intentionally rebuilt
   as a view.
5. Apply known Redshift-to-Trino SQL rewrites.
6. Parse and compile the result against the Trino target before cutover.

The cleanup script is
[dbt_jinja_processor.py](translation-engine/dbt_jinja_processor.py).
The function and syntax mapping table is in
[redshift-to-trino-function-mapping.md](translation-engine/redshift-to-trino-function-mapping.md).

```bash
python translation-engine/dbt_jinja_processor.py models --materialized view
```

Use `--dry-run` to validate processing without writing files.

### Config Cleanup

Redshift models often contain physical layout config that does not apply to
Trino/Iceberg.

```jinja
{{ config(
    materialized='incremental',
    unique_key='payment_id',
    dist='company_id',
    sort=['created_at']
) }}
```

For Trino/Iceberg, the migrated model keeps logical behavior and removes
warehouse-specific physical layout keys:

```jinja
{{ config(
    materialized='incremental',
    unique_key='payment_id'
) }}
```

### Migration-Aware Source Routing

During transition, some objects may still read from the warehouse while others
read from the lakehouse. A small macro made that routing explicit.

```jinja
{% macro migration_relation(schema_name, table_name) %}
    {% if var('lakehouse_enabled', false) %}
        {{ return(source('lakehouse', schema_name ~ '__' ~ table_name)) }}
    {% else %}
        {{ return(source('warehouse', schema_name ~ '__' ~ table_name)) }}
    {% endif %}
{% endmacro %}
```

Then models use the migration-aware relation:

```sql
SELECT
    payment_id,
    company_id,
    amount,
    created_at
FROM {{ migration_relation('finance', 'payments') }}
```

## GitLab Transition Branch

The migration used a long-running transition branch to isolate platform changes
without freezing normal development. `main` continued to receive production
changes while the migration branch translated and validated models against the
lakehouse target.

The automation has two pieces:

- [transition_branch_refresh.py](gitlab-autorebase-transition-branch/transition_branch_refresh.py)
  runs the branch refresh. It checks that the CI worktree is clean, configures
  the automation git identity, fetches the latest remote branches, resets the
  transition branch to its remote state, then rebases or merges it onto `main`.
  On conflict, it collects the conflicting file list and sends the failure to a
  Slack webhook when `SLACK_WEBHOOK_URL` is configured. On success, it sends the
  successful refresh message through the same notification path.
- [gitlab-ci.transition-branch-refresh.yml](gitlab-autorebase-transition-branch/gitlab-ci.transition-branch-refresh.yml)
  wires the script into GitLab schedules. It defines the maintenance stage,
  uses a Python image, installs `git` and `requests`, runs the refresh script,
  keeps full git history with `GIT_DEPTH: "0"`, and limits execution to
  scheduled pipelines where `RUN_TRANSITION_BRANCH_REFRESH=true`.

```mermaid
flowchart TB
    A[Main branch] -->|scheduled refresh| B[Transition branch]
    B --> C[Render dbt/Jinja SQL]
    C --> D[Validate translated SQL]
    D --> E[Check dbt config keys]
    E --> F[Check model dependencies]
    F --> G[Compile/build on Trino target]
    G --> H[Run parity validation]
    H --> I[Publish migration status]

    B -->|merge/rebase conflict| J[Notify owner]
    H -->|parity gap| K[Block cutover]
    H -->|parity pass| L[Ready for consumer migration]
```

The key controls were:

- scheduled branch refresh from `main`,
- conflict notifications when source and migration edits diverged,
- merge request branch freshness checks,
- compile and parse checks on changed SQL,
- config-key checks for adapter-specific drift,
- dependency checks to preserve dbt layering rules.
