# Architecture-option validation reference

## Case study

When a project has both a local transactional control plane and agent memory, evaluate them separately:

- **Operational state:** tasks, scheduler jobs, conversations, mission plans, approvals, runs, events, locks.
- **Semantic memory/index:** Obsidian-derived facts, episodes, embeddings, recall and persona summaries.

For the the agent bridge, the evidence favored SQLite WAL for operational state because it is single-host/local, already integrated with `aiosqlite`, uses short transactions plus `BEGIN IMMEDIATE`, and passed backup/restore and concurrent-transition tests. PostgreSQL remains a future trigger-based option, not a default migration target.

## Required gates before declaring an embedded store safe

1. Use SQLite Online Backup API (or equivalent consistent snapshot), not a blind live-file copy while WAL is active.
2. Restore into a new file and run `PRAGMA integrity_check` plus schema/data smoke tests.
3. Race two transitions against the same record; assert one winner, one state mismatch, and exactly one durable event.
4. Verify restart/reopen behavior and document the single-host/no-network-filesystem boundary.
5. Add a startup test proving optional PostgreSQL integration is not a hidden dependency of local persistence.

## Memory-system adoption rule

If adding TencentDB Agent Memory, a vector store, or another brain/index, keep Obsidian as the human-readable canonical source. Run capture/index in shadow mode, keep recall non-authoritative, preserve source IDs/hashes/provenance, and define export/deletion/backup controls before enabling production recall. A search index must be rebuildable; it must not silently become a second source of truth.

## Practical candidate sequence

- Operational: SQLite WAL now; PostgreSQL only after explicit triggers such as multi-host writes, sustained lock contention, remote access, PITR/HA, or cross-service transactions.
- Semantic: SQLite FTS5 baseline, then sqlite-vec or an embedded vector alternative benchmark; use PostgreSQL+pgvector or Qdrant only when measured workload needs justify service complexity.
- Do not choose DuckDB for transactional mission state; analytics and operational workloads have different semantics.
