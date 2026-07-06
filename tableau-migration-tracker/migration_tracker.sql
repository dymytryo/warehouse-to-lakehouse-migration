{{ config(
    materialized='table',
    tags=['migration_tracking', 'lakehouse_cutover']
) }}

/*
This model compares the source warehouse/dbt inventory against the target
Iceberg catalog so a migration dashboard can show object-level progress.
*/

WITH source_models AS (
    SELECT
        model_name,
        source_schema,
        source_path,
        owner,
        is_required_for_cutover
    FROM {{ ref('source_dbt_model_inventory') }}
),

target_iceberg_tables AS (
    SELECT
        table_schema AS target_schema,
        table_name AS target_table
    FROM {{ source('lakehouse_catalog', 'information_schema_tables') }}
    WHERE table_type = 'BASE TABLE'
),

mapped_objects AS (
    SELECT
        source_schema,
        model_name,
        source_path,
        owner,
        is_required_for_cutover,
        source_schema AS expected_target_schema,
        model_name AS expected_target_table
    FROM source_models
),

migration_status AS (
    SELECT
        m.source_schema,
        m.model_name,
        m.source_path,
        m.owner,
        m.is_required_for_cutover,
        t.target_schema,
        t.target_table,
        CASE
            WHEN t.target_table IS NOT NULL THEN 'migrated'
            WHEN m.is_required_for_cutover THEN 'required_not_migrated'
            ELSE 'optional_not_migrated'
        END AS migration_status
    FROM mapped_objects m
    LEFT JOIN target_iceberg_tables t
        ON m.expected_target_schema = t.target_schema
       AND m.expected_target_table = t.target_table
)

SELECT
    source_schema,
    model_name,
    source_path,
    owner,
    is_required_for_cutover,
    target_schema,
    target_table,
    migration_status
FROM migration_status;
