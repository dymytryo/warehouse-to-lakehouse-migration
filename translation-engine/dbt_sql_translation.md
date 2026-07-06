# dbt SQL Translation Pattern

This is a public-safe example of the dbt translation layer used in a
Redshift-to-Trino/Iceberg migration.

The goal is not blind string replacement. The safer pattern is:

1. Render dbt/Jinja.
2. Extract and validate `config(...)` keys.
3. Normalize Redshift-only config.
4. Route table references through a migration-aware mapping.
5. Translate known SQL dialect differences.
6. Parse rendered SQL with an AST parser.
7. Compile/build against the Trino target.

## Redshift-Specific Config Cleanup

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

For Trino/Iceberg, the migrated model should keep logical behavior and remove
warehouse-specific physical layout keys:

```jinja
{{ config(
    materialized='incremental',
    unique_key='payment_id',
    on_schema_change='sync_all_columns'
) }}
```

## Migration-Aware Source Routing

During transition, some objects may still read from the warehouse while others
read from the lakehouse. A small template abstraction makes that explicit.

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

## SQL Dialect Translation Examples

The full deterministic rule matrix lives with the notebook prototype:
[README.md](README.md).

| Redshift pattern | Trino/Iceberg pattern |
| --- | --- |
| `getdate()` | `current_timestamp` |
| `nvl(a, b)` | `coalesce(a, b)` |
| `isnull(a, b)` | `coalesce(a, b)` |
| `dateadd(day, -7, current_date)` | `date_add('day', -7, current_date)` |
| `col::varchar` | `CAST(col AS varchar)` |
| `dist`, `sort`, `distribution` config | remove or replace with Iceberg partition strategy |

## CI Validation Shape

The translation layer should fail fast when a migrated model is invalid:

```text
changed dbt model
  -> render dbt SQL
  -> parse SQL AST using Trino dialect
  -> validate config keys
  -> compile/build against Trino target
  -> run row-count and metric parity checks
```

## Why This Matters

The migration becomes repeatable because developers are not manually guessing
which Redshift patterns are safe in Trino. The template layer captures the
known platform differences, and CI proves that translated models still compile,
parse, and match source data.
