# Redshift to Trino + Apache Iceberg Lakehouse Migration

This repository documents a warehouse-to-lakehouse migration pattern: Redshift
models and workloads were moved behind a Trino/Starburst query layer backed by
Apache Iceberg tables.

The hard part was not only moving data. The hard part was keeping thousands of
modeled objects, downstream dependencies, and business metrics stable while the
platform changed underneath them.

The migration system had four parts:

1. A control plane that tracked which objects had moved.
2. A dbt translation layer that converted Redshift-oriented code to
   Trino/Iceberg-compatible code.
3. GitLab branch and CI controls that caught migration problems before merge.
4. Automated parity checks that proved readiness before cutover.

Implementation files are anonymized and kept as readable migration patterns
rather than packaged software.

## Target Architecture

![Warehouse to lakehouse cutover architecture](technical-architecture/warehouse-lakehouse-architecture.png)

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
        PARITY[Parity validation]
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
    CI --> PARITY
    PARITY --> TRINO
```

## Migration Control Plane

The migration tracker created a single source of truth for object progress. It
joined the source warehouse/dbt inventory to the target Iceberg catalog and
classified each object as migrated or not migrated.

![Migration progress dashboard](tableau-tracker/migration-progress-dashboard.png)

The tracker supported progress by schema or folder, object-level cutover status,
dashboard counts, high-usage object prioritization, and exception handling for
intentionally retired objects.

```sql
CASE
    WHEN t.target_table IS NOT NULL THEN 'migrated'
    WHEN m.is_required_for_cutover THEN 'required_not_migrated'
    ELSE 'optional_not_migrated'
END AS migration_status
```

Full example: [tableau-tracker/migration-tracker.sql](tableau-tracker/migration-tracker.sql)

## dbt Translation Layer

Changing the connection profile from Redshift to Trino was not enough. The code
migration needed deterministic handling for known SQL dialect and adapter
differences.

| Redshift-oriented pattern | Trino/Iceberg migration concern |
| --- | --- |
| `dist`, `sort`, `distribution` configs | Not valid or not useful for Trino/Iceberg |
| Redshift date functions | Function signatures differ in Trino |
| `::type` casts | Prefer explicit `CAST(expr AS type)` |
| warehouse-specific schemas | Need migration-aware source routing |
| table rebuild assumptions | Iceberg has snapshot and maintenance behavior |
| incremental model strategy | Adapter-specific merge/delete behavior differs |

The translation layer rendered dbt/Jinja first, governed config keys, routed
source references through migration-aware mappings, translated known dialect
patterns, and parsed the rendered SQL before build.

```jinja
{{ config(
    materialized='incremental',
    unique_key='payment_id',
    on_schema_change='sync_all_columns'
) }}
```

```jinja
{% macro migration_relation(schema_name, table_name) %}
    {% if var('lakehouse_enabled', false) %}
        {{ return(source('lakehouse', schema_name ~ '__' ~ table_name)) }}
    {% else %}
        {{ return(source('warehouse', schema_name ~ '__' ~ table_name)) }}
    {% endif %}
{% endmacro %}
```

Examples:

- [dbt-translation-engine/translation-pattern.md](dbt-translation-engine/translation-pattern.md)
- [dbt-translation-engine/translation-rules.md](dbt-translation-engine/translation-rules.md)
- [dbt-translation-engine/dbt-jinja-processor.ipynb](dbt-translation-engine/dbt-jinja-processor.ipynb)

## GitLab Transition Branch Strategy

The migration used a long-running transition branch to isolate platform changes
without freezing normal development. `main` continued to receive production
changes while the migration branch translated and validated models against the
lakehouse target.

The scheduled refresh job kept the transition branch close to `main` and
surfaced conflicts early.

```python
run(["git", "fetch", remote, "--prune"])
run(["git", "checkout", transition_branch])
run(["git", "reset", "--hard", f"{remote}/{transition_branch}"])
run(["git", "rebase", f"{remote}/{target_branch}"])
run(["git", "push", "--force-with-lease", remote, transition_branch])
```

The CI workflow checked branch freshness, unsupported config keys, dependency
rules, SQL rendering/parsing, dbt build output, and parity results before
cutover.

Examples:

- [gitlab-transition-branch/branch-controls.md](gitlab-transition-branch/branch-controls.md)
- [gitlab-transition-branch/transition-branch-refresh.py](gitlab-transition-branch/transition-branch-refresh.py)
- [gitlab-transition-branch/gitlab-ci.transition-branch-refresh.yml](gitlab-transition-branch/gitlab-ci.transition-branch-refresh.yml)
- [gitlab-transition-branch/migration-readiness-gate.sql](gitlab-transition-branch/migration-readiness-gate.sql)

## Parity Validation

The validation layer compared source and target objects before downstream
consumers were moved. The goal was to prove object parity before cutover, not
discover issues after dashboards or jobs had already moved.

Validation categories:

- object existence,
- column existence,
- data type compatibility,
- row-count parity,
- metric parity,
- missing-column risk based on non-null values,
- known-system-column exclusions.

```python
def normalize_dtype(dtype: str | None) -> str | None:
    if dtype is None or pd.isna(dtype):
        return None

    value = str(dtype).lower().strip()
    if "timestamp" in value:
        return "timestamp"
    value = re.sub(r"varchar\(\d+\)", "varchar", value)
    value = re.sub(r"decimal\([\d,\s]+\)", "decimal", value)
    return value
```

Full example: [parity-validation/parity-validation.py](parity-validation/parity-validation.py)
