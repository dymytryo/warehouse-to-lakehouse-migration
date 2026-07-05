-- CI readiness gate for the lakehouse transition branch.
--
-- Expected result: zero rows.
-- Any returned row is a required model that should block cutover or merge.
-- Replace migration_audit.model_readiness with the metadata table produced by
-- the team's dbt build, parity, and migration-tracker jobs.

WITH required_models AS (
    SELECT
        model_name,
        source_path,
        owner,
        migration_status,
        object_parity_status,
        schema_parity_status,
        row_count_status,
        metric_parity_status,
        last_validated_at
    FROM migration_audit.model_readiness
    WHERE is_required_for_cutover = true
),
failing_models AS (
    SELECT
        model_name,
        source_path,
        owner,
        migration_status,
        object_parity_status,
        schema_parity_status,
        row_count_status,
        metric_parity_status,
        last_validated_at,
        array_join(
            filter(
                ARRAY[
                    CASE
                        WHEN coalesce(migration_status, 'missing') <> 'migrated'
                            THEN 'object_not_migrated'
                    END,
                    CASE
                        WHEN coalesce(object_parity_status, 'missing') <> 'pass'
                            THEN 'object_parity_failed'
                    END,
                    CASE
                        WHEN coalesce(schema_parity_status, 'missing') <> 'pass'
                            THEN 'schema_parity_failed'
                    END,
                    CASE
                        WHEN coalesce(row_count_status, 'missing') <> 'pass'
                            THEN 'row_count_parity_failed'
                    END,
                    CASE
                        WHEN coalesce(metric_parity_status, 'missing') <> 'pass'
                            THEN 'metric_parity_failed'
                    END,
                    CASE
                        WHEN last_validated_at IS NULL
                            THEN 'not_validated'
                        WHEN last_validated_at < current_timestamp - INTERVAL '48' HOUR
                            THEN 'validation_stale'
                    END
                ],
                reason -> reason IS NOT NULL
            ),
            ', '
        ) AS failure_reasons
    FROM required_models
)

SELECT
    model_name,
    source_path,
    owner,
    failure_reasons,
    migration_status,
    object_parity_status,
    schema_parity_status,
    row_count_status,
    metric_parity_status,
    last_validated_at
FROM failing_models
WHERE failure_reasons <> ''
ORDER BY owner, source_path, model_name;
