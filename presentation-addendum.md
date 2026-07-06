# Presentation Addendum

The existing slide deck tells the high-level migration story. To make it stronger
for a technical audience, add a short appendix that explains how the migration
actually worked.

## Suggested Appendix Slides

### 1. Migration Control Plane

Show how source objects were tracked against target Iceberg objects.

Include:

- object inventory from dbt/warehouse metadata,
- target existence checks from the Trino/Iceberg catalog,
- migrated vs not migrated status,
- schema/folder progress,
- dashboard output for cutover readiness.

### 2. GitLab Transition Branch Strategy

Explain the long-running migration branch.

Include:

- `main` continues normal production development,
- `transition` branch applies Trino/Iceberg changes,
- scheduled branch refresh keeps transition current,
- conflicts are surfaced early,
- CI checks block stale or invalid migration changes.

### 3. dbt SQL Translation Layer

Show that this was not manual one-off rewriting.

Include:

- Redshift-specific config cleanup,
- Jinja/dbt rendering,
- migration-aware source routing,
- Redshift-to-Trino function and cast patterns,
- SQL AST parsing after translation,
- compile/build validation against the Trino target.

### 4. Shift-Left CI Gates

Show the gates that ran before cutover.

Include:

- branch freshness,
- config key validation,
- dependency checks,
- SQL render and parse,
- dbt compile/build,
- schema and row-count parity,
- business metric parity.

### 5. Parity Validation Framework

Show the evidence that the migration was correct.

Include:

- object parity,
- column parity,
- type normalization,
- row-count comparison,
- metric comparison,
- missing-column data-loss risk scoring.

### 6. Operating Model After Cutover

Show that the lakehouse was operationalized.

Include:

- Iceberg maintenance,
- table statistics collection,
- Starburst/Trino query metadata,
- cost and performance monitoring,
- stale table detection,
- downstream usage tracking.

## Resume-Friendly Framing

Use this language:

> Led a 200+ TB Redshift-to-Trino/Apache Iceberg lakehouse migration, building a
> shift-left migration framework with GitLab branch automation, dbt SQL
> translation, schema and row-count parity validation, and business metric
> reconciliation. Delivered 100% object parity while reducing platform cost by
> roughly 60%.

## Interview-Friendly Framing

Use this version when asked how the migration worked:

> We treated the migration as a software delivery problem, not only a data copy
> problem. We kept a transition branch for Trino/Iceberg changes, refreshed it
> from main on a schedule, translated dbt models through a controlled template
> layer, rendered and parsed SQL in CI, then validated source and target objects
> with schema, row-count, and metric parity checks before cutover.
