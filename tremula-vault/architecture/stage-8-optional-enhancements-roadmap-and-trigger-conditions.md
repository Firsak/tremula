---
depends_on:
- memory://tremula/architecture/stage-7-consolidation-splitting-self-organization
scope: shared
source: distilled
type: architecture
---

# Stage 8: Optional enhancements — roadmap and trigger conditions

Stages 1–7 complete a working system with FTS5-only retrieval. Stage 8 candidates are optional, gated by specific trigger conditions (when real-world use exposes limits).

## Candidates

**sqlite-vec semantic search:**  
Trigger: word-matching measurably misses (retrieval recall <80% on live vault). Adds vector embeddings alongside FTS5 for hybrid retrieval: "vector finds what you asked, graph finds what you forgot." Optional because FTS5 is effective for most use; semantic search is a complexity jump with diminishing returns if recall is already high.

**HTTP/Streamable daemon:**  
Trigger: SessionStart cold start becomes slow on large vaults. Replaces one-process-per-session model with long-lived warm server. Transport-independence is already baked in; this is a run-argument change. Optional because current polling scales fine until vault size makes startup dominate session latency.

**Rust indexer/watcher:**  
Trigger: Never (engineering pleasure, not necessity). Replaces mtime-polling `Index.refresh` with real file watcher. Optional because current polling (~1–2ms) is adequate at reasonable scales.

## Prerequisite measurements

Before committing to Stage 8 work, the source plan recommends measuring:
1. **Injection A/B:** index-only vs index + top-K by git status. Does git context improve LLM prompt quality?
2. **FTS5 quality baseline:** On a grown vault, what are precision, recall, latency? Is semantic search actually needed?
3. **Root node format:** After real multi-project federation use, is file-per-endpoint still the right granularity?
4. **Pre-publication audit:** PyPI/GitHub names, packaging, and docs ready for release.
