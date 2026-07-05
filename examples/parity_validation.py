"""
Portfolio example: warehouse-to-lakehouse parity validation.

This is an anonymized pattern based on migration checks used to compare a source
warehouse and a Trino/Iceberg target. It focuses on readable migration logic,
not packaging or deployment.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

import pandas as pd
from trino.auth import BasicAuthentication
from trino.dbapi import connect


@dataclass(frozen=True)
class CatalogPair:
    source_catalog: str
    target_catalog: str
    output_schema: str


def trino_connection():
    user = os.environ["TRINO_USER"]
    password = os.environ["TRINO_PASSWORD"]

    return connect(
        host=os.environ["TRINO_HOST"],
        port=int(os.getenv("TRINO_PORT", "443")),
        user=user,
        auth=BasicAuthentication(user, password),
        http_scheme=os.getenv("TRINO_SCHEME", "https"),
        request_timeout=int(os.getenv("TRINO_TIMEOUT_SECONDS", "120")),
    )


def normalize_dtype(dtype: str | None) -> str | None:
    if dtype is None or pd.isna(dtype):
        return None

    value = str(dtype).lower().strip()
    if "timestamp" in value:
        return "timestamp"
    value = re.sub(r"varchar\(\d+\)", "varchar", value)
    value = re.sub(r"decimal\([\d,\s]+\)", "decimal", value)
    return value


def list_tables(conn, catalog: str) -> pd.DataFrame:
    return pd.read_sql(
        f"""
        SELECT table_schema, table_name
        FROM {catalog}.information_schema.tables
        WHERE table_schema NOT IN ('information_schema')
          AND table_type = 'BASE TABLE'
        """,
        conn,
    )


def common_tables(conn, pair: CatalogPair) -> pd.DataFrame:
    source = list_tables(conn, pair.source_catalog)
    target = list_tables(conn, pair.target_catalog)

    source["join_schema"] = source["table_schema"].str.lower().str.strip()
    source["join_table"] = source["table_name"].str.lower().str.strip()
    target["join_schema"] = target["table_schema"].str.lower().str.strip()
    target["join_table"] = target["table_name"].str.lower().str.strip()

    return source.merge(
        target,
        on=["join_schema", "join_table"],
        suffixes=("_source", "_target"),
    )


def row_count_parity(conn, pair: CatalogPair, mapping: pd.DataFrame) -> pd.DataFrame:
    rows = []

    for _, item in mapping.iterrows():
        source_table = (
            f'{pair.source_catalog}."{item["table_schema_source"]}"."{item["table_name_source"]}"'
        )
        target_table = (
            f'{pair.target_catalog}."{item["table_schema_target"]}"."{item["table_name_target"]}"'
        )

        source_count = pd.read_sql(
            f"SELECT COUNT(*) AS row_count FROM {source_table}", conn
        )["row_count"][0]
        target_count = pd.read_sql(
            f"SELECT COUNT(*) AS row_count FROM {target_table}", conn
        )["row_count"][0]

        rows.append(
            {
                "source_schema": item["table_schema_source"],
                "target_schema": item["table_schema_target"],
                "table_name": item["table_name_source"],
                "source_row_count": int(source_count),
                "target_row_count": int(target_count),
                "row_count_diff": int(target_count) - int(source_count),
            }
        )

    result = pd.DataFrame(rows)
    result["row_count_pct_diff"] = (
        result["row_count_diff"]
        / result[["source_row_count", "target_row_count"]].max(axis=1)
    ).round(4)
    return result


def columns_for_table(conn, catalog: str, schema: str, table: str) -> pd.DataFrame:
    return pd.read_sql(
        f"""
        SELECT column_name, data_type
        FROM {catalog}.information_schema.columns
        WHERE table_schema = '{schema}'
          AND table_name = '{table}'
        """,
        conn,
    )


def column_parity(conn, pair: CatalogPair, mapping: pd.DataFrame) -> pd.DataFrame:
    comparisons = []
    ignored_system_columns = {
        "_fivetran_deleted",
        "_fivetran_synced",
        "_loaded_at",
        "_deleted_at",
    }

    for _, item in mapping.iterrows():
        source_cols = columns_for_table(
            conn,
            pair.source_catalog,
            item["table_schema_source"],
            item["table_name_source"],
        )
        target_cols = columns_for_table(
            conn,
            pair.target_catalog,
            item["table_schema_target"],
            item["table_name_target"],
        )

        merged = source_cols.merge(
            target_cols,
            on="column_name",
            how="outer",
            suffixes=("_source", "_target"),
        )
        merged["table_name"] = item["table_name_source"]
        merged["source_schema"] = item["table_schema_source"]
        merged["target_schema"] = item["table_schema_target"]
        comparisons.append(merged)

    result = pd.concat(comparisons, ignore_index=True)
    result = result[~result["column_name"].str.lower().isin(ignored_system_columns)]
    result["source_type_normalized"] = result["data_type_source"].map(normalize_dtype)
    result["target_type_normalized"] = result["data_type_target"].map(normalize_dtype)

    result["status"] = "match"
    result.loc[result["data_type_source"].isna(), "status"] = "missing_in_source"
    result.loc[result["data_type_target"].isna(), "status"] = "missing_in_target"
    result.loc[
        result["source_type_normalized"] != result["target_type_normalized"],
        "status",
    ] = "type_mismatch"

    return result


def main() -> None:
    pair = CatalogPair(
        source_catalog=os.getenv("SOURCE_CATALOG", "source_warehouse"),
        target_catalog=os.getenv("TARGET_CATALOG", "lakehouse"),
        output_schema=os.getenv("OUTPUT_SCHEMA", "migration_audit"),
    )

    with trino_connection() as conn:
        mapping = common_tables(conn, pair)
        row_results = row_count_parity(conn, pair, mapping)
        column_results = column_parity(conn, pair, mapping)

    print("Row-count parity summary")
    print(row_results.head(20).to_string(index=False))
    print("\nColumn parity issues")
    print(
        column_results[column_results["status"] != "match"]
        .head(20)
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()
