# Tableau Migration Tracker

This folder contains the public-safe version of the migration control plane
shown in the deck. The tracker compares the known Redshift/dbt object inventory
against the target Iceberg catalog so cutover status can be reviewed by schema,
folder, owner, and required-for-cutover flag.

## Files

- [Migration tracker.png](<Migration tracker.png>) - screenshot of the Tableau
  tracker used to monitor migration progress.
- [Shift Left - High Level Overview.png](<Shift Left - High Level Overview.png>)
  - larger tracker view with schema-level progress and object detail.
- [migration_tracker.sql](migration_tracker.sql) - dbt model pattern that
  classifies source objects as migrated, required but not migrated, or optional.

## What It Shows

- object-level migration status,
- schema and folder progress,
- owner-level follow-up,
- `on_hold` or optional exceptions handled explicitly,
- readiness reporting before the hot-swap cutover.
