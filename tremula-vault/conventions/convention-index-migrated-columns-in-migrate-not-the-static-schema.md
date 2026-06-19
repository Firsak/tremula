---
confirmation_count: 3
scope: backend
source: distilled
status: ratified
subject_paths:
- src/tremula/index.py
subject_symbols:
- tremula.index._migrate
type: convention
---

# Convention: index migrated columns in _migrate(), not the static schema

In `tremula.index`, the static `_SCHEMA` DDL runs on **every** connection — including pre-existing databases — and runs **before** `_migrate()`. So any `CREATE INDEX` over a column that `_migrate()` adds (e.g. the lifecycle `status` column) must live **inside `_migrate()`**, after the `ALTER TABLE ... ADD COLUMN`. Putting it in `_SCHEMA` crashes on any DB created before the column existed: `_SCHEMA` references a column that does not yet exist.

**Rule:** `_SCHEMA` = columns/tables present from the first build. `_migrate()` = every additive change — new columns AND their indexes — so old DBs upgrade cleanly.

**Test trap:** fresh-DB tests pass either way, so this class of bug only surfaces on a pre-existing DB. Cover it with a regression test that opens an old DB, then migrates. This exact ordering bug shipped (status index in `_SCHEMA`) and was caught only by an end-to-end `tremula verify` smoke, not by the unit suite.
