# dbt Translation Engine Prototype

This folder holds the notebook prototype for deterministic dbt/Jinja cleanup and
Redshift-to-Trino syntax translation during a warehouse-to-lakehouse migration.

The notebook is intentionally preserved as the exploratory artifact. The table
below captures the rule matrix that should eventually be extracted into a
cleaner script or YAML-driven translation layer.

## What the Processor Was Trying To Do

- Preserve dbt/Jinja constructs like `ref`, `source`, `var`, and `dbt_utils`
  while cleaning unsupported model configuration.
- Remove Redshift-only dbt config such as `dist`, `sort`, `distkey`, `sortkey`,
  and related variants.
- Remove or rewrite incremental logic when a model is intentionally converted to
  a Trino/Iceberg view.
- Apply deterministic SQL syntax rewrites for known Redshift-to-Trino
  differences.
- Keep the transformation reviewable rather than relying on manual ad hoc edits.

## Deterministic Translation Matrix

Some rows are exact syntax translations. Others are rewrite patterns that still
need model context, especially window functions, JSON paths, array logic, and
case-insensitive regular expressions.

| Redshift | Trino | Notes |
| --- | --- | --- |
| `ADD_MONTHS(x, n)` | `DATE_ADD('month', n, x)` |  |
| `ARRAY(x, y, ...)` | `ARRAY[x, y, ...]` |  |
| `ARRAY(array) IS NOT NULL` | `ELEMENT_AT(FILTER(array, x -> x IS NOT NULL), 1) IS NOT NULL` | Checks whether at least one array element is non-null. |
| `ASCII(str)` | `CODEPOINT(str)` | `CODEPOINT()` returns a Unicode code point. |
| `BIT_AND()` | `BITWISE_AND()` plus `GROUP BY` | Usually needs a two-step aggregate rewrite. |
| `BOOL_OR()` | `SUM(CASE WHEN expression THEN 1 ELSE 0 END) > 0` | If any row evaluates true, return true; otherwise false. |
| `DATE(x) - DATE(y)` | `DATE_DIFF('day', DATE(y), DATE(x))` | Trino returns `end - start`; verify sign when translating date subtraction. |
| `DATEADD(day, x, y)` | `DATE_ADD('day', x, y)` |  |
| `DATEDIFF(day, x, y)` | `DATE_DIFF('day', x, y)` |  |
| `DATE_PART(x, y)` | `EXTRACT(x FROM y)` |  |
| `DATEPART(dow, createddate_pst) = 6` | `day_of_week(createddate_pst) = 6` | Saturday in both conventions. |
| `DATEPART(dow, createddate_pst) = 0` | `day_of_week(createddate_pst) = 7` | Redshift Sunday is `0`; Trino Sunday is `7`. |
| `DATEPART(dow, createddate_pst_adj) = 5` | `day_of_week(createddate_pst_adj) = 5` | Friday in both conventions. |
| `DATE_PART(dayofweek, y)` | `CASE WHEN day_of_week(y) = 7 THEN 0 ELSE day_of_week(y) END` | Redshift returns `0` for Sunday through `6` for Saturday. Trino returns `1` for Monday through `7` for Sunday. |
| `DECODE()` | `CASE` statement |  |
| `DISTINCT ON (x)` | `DISTINCT` or window-function filter | Use full-row `DISTINCT`, or `ROW_NUMBER()` when the Redshift behavior depends on ordering. |
| `FLOAT` | `REAL` |  |
| `FROM x, y` | `FROM x CROSS JOIN UNNEST(y) AS t(z)` | For comma-style array expansion. |
| `GETDATE()` | `CURRENT_TIMESTAMP` |  |
| `JSON_EXTRACT_ARRAY_ELEMENT_TEXT(json_str, index [, null_if_invalid])` | `JSON_ARRAY_GET(json_str, index)` | Optional `null_if_invalid` can usually be skipped if invalid input should return null. |
| `JSON_EXTRACT_PATH_TEXT(json_str, path [, 'path' [, ...]] [, null_if_invalid])` | `JSON_EXTRACT(json_str, '$.path')` | Trino expects JSONPath syntax such as `'$.path'`. |
| `INTERVAL 'n hour'` | `INTERVAL 'n' hour` |  |
| `LAST_DAY()` | `LAST_DAY_OF_MONTH()` |  |
| `LEFT(str, 1)` | `SUBSTRING(str, 1, 1)` |  |
| `LEN(str)` | `LENGTH(str)` |  |
| `LISTAGG(x, 'delimiter')` | `ARRAY_JOIN(ARRAY_AGG(x), 'delimiter')` | Add ordering explicitly if deterministic order matters. |
| `MEDIAN(x)` | `APPROX_PERCENTILE(x, 0.5)` | Approximate, not exact. |
| `MOD(number1, number2)` | `number1 % number2` | Modulo operator returns the division remainder. |
| `NVL()` | `COALESCE()` | Returns the first non-null value. |
| `REGEXP_SUBSTR(string, pattern [, position [, occurrence [, parameters]]])` | `REGEXP_EXTRACT(string, pattern [, position])` | `occurrence` is often `1`. Flags such as case-insensitive matching should be represented in the pattern. |
| `REGEXP_SUBSTR(x, 'pattern', y)` | `ELEMENT_AT(REGEXP_EXTRACT_ALL(x, 'pattern'), y)` | Use when the occurrence argument matters. |
| `PERCENTILE_CONT(percentile) WITHIN GROUP (ORDER BY expr) OVER ([PARTITION BY expr_list])` | `APPROX_PERCENTILE(expr, percentile) OVER (PARTITION BY expr_list)` | Approximate percentile; verify if exact percentile is required. |
| `REPEAT('x', n)` | `'xxxxxxxxxxxxxxx'` | In environments where repeat is unavailable, materialize the repeated literal. |
| `TRY_NUMERIC(x)` | `TRY(CAST(x AS REAL))` |  |
| `CHARACTER VARYING(x)` | `VARCHAR` |  |
| `'YYYY-MM-DD''T''HH:MM:SS''Z'''` | `'YYYY-MM-DD HH:MM:SS'` | ISO timestamps use `T` between date and time. `Z` means UTC. Offsets can also be represented, for example `2024-07-04T13:46:08+02:00`. |
| `IS_VALID_JSON(json_str)` | `TRY(JSON_PARSE(json_str)) IS NOT NULL` | Use `TRY(JSON_EXTRACT(json_str, '$.path'))` when validating a specific path. |
| `RIGHT(x, n)` | `SUBSTRING(x, -n)` |  |
| `SHA2(x, bits)` | `sha256(to_utf8(x))` | `sha256()` expects `varbinary` input. |
| `SUBSTR(str, start, end)` | `SUBSTRING(str, start, end)` |  |
| `SUPER` | `JSON` | `SUPER` is a Redshift proprietary data type. |
| `SPLIT_TO_ARRAY(x, delimiter)` | `SPLIT(x, delimiter)` |  |
| `x::BIGINT` | `CAST(x AS BIGINT)` | Trino does not support Redshift/Postgres-style `::` casts. |
| `str ~ pattern` | `REGEXP_LIKE(str, pattern)` |  |
| `str ~* pattern` | `REGEXP_LIKE(str, '(?i)' || pattern)` | `~*` is case-insensitive. Inline `(?i)` works when the pattern is a literal or can be safely prefixed. |
| `TEXT` | `VARCHAR` |  |
| `TIMESTAMP 'epoch'` | `TIMESTAMP '1970-01-01 00:00:00'` |  |
| `TIMESTAMP 'epoch' + unixtime / 1000 * INTERVAL '1 second'` | `FROM_UNIXTIME(unixtime / 1000)` |  |
| `TO_CHAR(x, 'YYYY-MM')` | `DATE_FORMAT(x, '%Y-%m')` |  |
| `TO_DATE(x, 'MM/DD/YY')` | `DATE_PARSE(x, '%m/%d/%Y')` |  |
| `QUALIFY` | `ROW_NUMBER()` plus subquery | Replace `QUALIFY` with a nested query that filters on the window-function result. |
| `WITH RECURSIVE` | Manual rewrite | Replace recursion with an iterative staging model, seed table, date spine, or bounded expansion pattern. |

## Next Refactor

The notebook should eventually become a small, public-safe script:

```text
dbt_translation_engine/
  README.md
  dbt_jinja_processor.py
  redshift_to_trino_rules.yml
  examples/
    before.sql
    after.sql
```

That would make the deterministic translation story easier to inspect without
requiring someone to open a notebook.
