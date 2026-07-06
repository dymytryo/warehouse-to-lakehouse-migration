#!/usr/bin/env python3
"""
Clean dbt model files for a Redshift-to-Trino migration.

The script removes Redshift-only dbt config keys while preserving the rest of a
model's SQL and Jinja. It intentionally uses only the Python standard library.
"""

from __future__ import annotations

import argparse
import re
import traceback
from pathlib import Path


DEFAULT_EXCLUDED_CONFIG_KEYS = [
    "dist",
    "dist_key",
    "distkey",
    "sort",
    "sort_key",
    "sortkey",
]

CONFIG_BLOCK_RE = re.compile(r"{{\s*config\((.*?)\)\s*}}", re.DOTALL)
INCREMENTAL_BLOCK_RE = re.compile(
    r"{%\s*if\s+is_incremental\(\)\s*%}.*?{%\s*endif\s*%}",
    re.DOTALL,
)


def split_top_level_args(config_body: str) -> list[str]:
    args: list[str] = []
    current: list[str] = []
    quote: str | None = None
    bracket_depth = 0
    paren_depth = 0

    for char in config_body:
        if quote:
            current.append(char)
            if char == quote:
                quote = None
            continue

        if char in {"'", '"'}:
            quote = char
            current.append(char)
            continue

        if char in "[{":
            bracket_depth += 1
        elif char in "]}":
            bracket_depth -= 1
        elif char == "(":
            paren_depth += 1
        elif char == ")":
            paren_depth -= 1

        if char == "," and bracket_depth == 0 and paren_depth == 0:
            value = "".join(current).strip()
            if value:
                args.append(value)
            current = []
        else:
            current.append(char)

    value = "".join(current).strip()
    if value:
        args.append(value)
    return args


def config_key(arg: str) -> str | None:
    if "=" not in arg:
        return None
    return arg.split("=", 1)[0].strip()


def format_config(args: list[str]) -> str:
    if not args:
        return ""
    if len(args) == 1:
        return f"{{{{ config({args[0]}) }}}}"

    body = ",\n    ".join(args)
    return "{{ config(\n    " + body + "\n) }}"


def clean_config_block(
    match: re.Match[str],
    excluded_config_keys: set[str],
    replacement_config: dict[str, str],
) -> str:
    args = split_top_level_args(match.group(1))
    kept_args: list[str] = []
    replaced_keys = set()

    for arg in args:
        key = config_key(arg)
        if key is None:
            kept_args.append(arg)
            continue
        if key in excluded_config_keys:
            continue
        if key in replacement_config:
            kept_args.append(f"{key}={replacement_config[key]!r}")
            replaced_keys.add(key)
            continue
        kept_args.append(arg)

    for key, value in replacement_config.items():
        if key not in replaced_keys and key not in {config_key(arg) for arg in kept_args}:
            kept_args.append(f"{key}={value!r}")

    return format_config(kept_args)


def clean_model_sql(
    sql: str,
    excluded_config_keys: list[str] | None = None,
    replacement_config: dict[str, str] | None = None,
    keep_incremental_blocks: bool = False,
) -> str:
    excluded = set(excluded_config_keys or DEFAULT_EXCLUDED_CONFIG_KEYS)
    replacements = replacement_config or {}

    sql = CONFIG_BLOCK_RE.sub(
        lambda match: clean_config_block(match, excluded, replacements),
        sql,
    )
    if not keep_incremental_blocks:
        sql = INCREMENTAL_BLOCK_RE.sub("", sql)
    return "\n".join(line.rstrip() for line in sql.splitlines())


def process_sql_files(
    models_dir: Path,
    excluded_config_keys: list[str],
    replacement_config: dict[str, str],
    keep_incremental_blocks: bool,
    dry_run: bool,
) -> tuple[list[Path], list[Path]]:
    processed_files: list[Path] = []
    failed_files: list[Path] = []
    error_log_path = models_dir / "error_log_jinja.txt"

    for filepath in sorted(models_dir.rglob("*.sql")):
        try:
            original = filepath.read_text()
            cleaned = clean_model_sql(
                original,
                excluded_config_keys=excluded_config_keys,
                replacement_config=replacement_config,
                keep_incremental_blocks=keep_incremental_blocks,
            )
            if not dry_run and cleaned != original:
                filepath.write_text(cleaned)
            processed_files.append(filepath)
        except Exception as exc:
            failed_files.append(filepath)
            error_message = f"Failed to process {filepath}: {exc}\n{traceback.format_exc()}"
            print(error_message)
            if not dry_run:
                with error_log_path.open("a") as error_log:
                    error_log.write(error_message + "\n")

    return processed_files, failed_files


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Remove Redshift-only dbt config from dbt model SQL files."
    )
    parser.add_argument("models_dir", type=Path, help="Path to a dbt models directory.")
    parser.add_argument(
        "--exclude-config",
        action="append",
        default=[],
        help="Additional config key to remove. Repeat for multiple keys.",
    )
    parser.add_argument(
        "--materialized",
        help="Set or add replacement materialization, such as 'view'.",
    )
    parser.add_argument(
        "--keep-incremental-blocks",
        action="store_true",
        help="Keep SQL inside is_incremental() blocks.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Process files without writing changes.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    excluded_config_keys = DEFAULT_EXCLUDED_CONFIG_KEYS + args.exclude_config
    replacement_config = {}
    if args.materialized:
        replacement_config["materialized"] = args.materialized

    processed_files, failed_files = process_sql_files(
        args.models_dir,
        excluded_config_keys=excluded_config_keys,
        replacement_config=replacement_config,
        keep_incremental_blocks=args.keep_incremental_blocks,
        dry_run=args.dry_run,
    )

    print(f"Processed files: {len(processed_files)}")
    print(f"Failed files: {len(failed_files)}")
    return 1 if failed_files else 0


if __name__ == "__main__":
    raise SystemExit(main())
