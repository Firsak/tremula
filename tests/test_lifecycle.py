"""Branch-aware memory scoping: note lifecycle + working-tree grounding.

Covers the acceptance criteria for branch-aware memory scoping — a provisional note is withheld
from proactive injection when its subject code is absent from the working tree,
ratified notes are always eligible, the confirmation counter is monotonic, and
nothing here ever mutates/deletes the vault except the explicit verify pass.
"""

from __future__ import annotations

import pytest
import yaml

from tremula import cli
from tremula.astmap import resolve_symbol
from tremula.config import Settings
from tremula.distiller import (
    _check_confirmation,
    _confirm_notes,
    apply_ops,
)
from tremula.index import Index, SearchHit, _decode_paths
from tremula.injection import _is_eligible, build_attachment, build_injection
from tremula.note import LifecycleStatus, load_note_in_vault
from tremula.vault import VaultService


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("TREMULA_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("TREMULA_HOOKS_DISABLED", raising=False)
    vault_dir = tmp_path / "proj" / "tremula-vault"
    vault_dir.mkdir(parents=True)
    (vault_dir / "_index.md").write_text(
        "---\ntype: index\nscope: shared\n---\n\n# Proj Index\n\nentry\n"
    )
    mounts = {"proj": vault_dir}
    index = Index(tmp_path / "home" / "index" / "proj.sqlite")
    index.rebuild(mounts)
    vault = VaultService(mounts, index, project="proj")
    return vault, index, mounts, vault_dir


# ---- Step 1: frontmatter + backward compat (AC1, AC2) --------------------------

def test_legacy_note_loads_as_ratified(setup):
    """A note with no lifecycle fields is grandfathered as ratified — the whole
    pre-feature vault stays injection-eligible."""
    _, _, _, vault_dir = setup
    (vault_dir / "modules").mkdir()
    (vault_dir / "modules" / "legacy.md").write_text(
        "---\ntype: module\nscope: shared\nsource: manual\n---\n\n# Legacy\n\nbody\n"
    )
    note = load_note_in_vault(vault_dir / "modules" / "legacy.md", vault_dir, "proj")
    assert note.frontmatter.status == LifecycleStatus.RATIFIED
    assert note.frontmatter.confirmation_count == 0
    assert note.frontmatter.subject_paths == []
    assert note.frontmatter.subject_symbols == []


def test_write_note_roundtrips_lifecycle(setup):
    vault, _, _, _ = setup
    uri = vault.write_note(
        title="Foo", content="body", type="function", source="distilled",
        status="provisional", confirmation_count=1,
        subject_paths=["src/foo.py"], subject_symbols=["foo.bar"],
    )
    note = vault.read_note(uri, track=False)
    assert note["status"] == "provisional"
    assert note["confirmation_count"] == 1
    assert note["subject_paths"] == ["src/foo.py"]
    assert note["subject_symbols"] == ["foo.bar"]


# ---- Step 2: index gate + ordering (AC3, AC4, AC5, AC6) ------------------------

def _seed_gate_notes(vault):
    vault.write_note("Ratified", "b", type="function", source="distilled",
                     status="ratified", confirmation_count=3, subject_paths=["src/gone.py"])
    vault.write_note("ProvPresent", "b", type="function", source="distilled",
                     status="provisional", confirmation_count=1, subject_paths=["src/here.py"])
    vault.write_note("ProvAbsent", "b", type="function", source="distilled",
                     status="provisional", confirmation_count=2, subject_paths=["src/miss.py"])


def test_eligible_gate(setup):
    vault, index, _, _ = setup
    _seed_gate_notes(vault)
    eligible = {r["uri"] for r in index.eligible_notes({"src/here.py"})}
    assert "memory://proj/functions/ratified" in eligible       # ratified always (AC5)
    assert "memory://proj/functions/provpresent" in eligible    # present (AC4)
    assert "memory://proj/functions/provabsent" not in eligible  # absent suppressed (AC3)


def test_eligible_provisional_empty_paths_falls_through(setup):
    vault, index, _, _ = setup
    vault.write_note("NoBind", "b", type="decision", source="distilled",
                     status="provisional", subject_paths=[])
    eligible = {r["uri"] for r in index.eligible_notes(set())}
    assert "memory://proj/decisions/nobind" in eligible  # no binding => eligible


def test_eligible_lifecycle_disabled_returns_all(setup):
    vault, index, _, _ = setup
    _seed_gate_notes(vault)
    eligible = index.eligible_notes(set(), lifecycle_enabled=False)
    uris = {r["uri"] for r in eligible}
    assert "memory://proj/functions/provabsent" in uris  # gate bypassed (AC13)


def test_all_notes_ordered_by_confirmation(setup):
    vault, index, _, _ = setup
    vault.write_note("Low", "b", type="function", source="distilled",
                     status="ratified", confirmation_count=1)
    vault.write_note("High", "b", type="function", source="distilled",
                     status="ratified", confirmation_count=9)
    ordered = [r["uri"] for r in index.all_notes() if "functions/" in r["uri"]]
    assert ordered.index("memory://proj/functions/high") < \
        ordered.index("memory://proj/functions/low")  # AC6


def test_searchhit_carries_lifecycle_columns(setup):
    vault, index, _, _ = setup
    vault.write_note("Searchme", "unique-token-xyz here", type="function",
                     source="distilled", status="provisional", subject_paths=["src/x.py"])
    hits = index.search_any(["xyz"])
    assert hits and hits[0].status == "provisional"
    assert _decode_paths(hits[0].subject_paths) == ["src/x.py"]


def test_index_migrates_preexisting_db(tmp_path):
    """Regression: opening an Index on a DB whose `notes` table predates the
    lifecycle columns must migrate cleanly. The status index is created only
    AFTER the column exists (else CREATE INDEX ON notes(status) raises)."""
    import sqlite3
    db = tmp_path / "home" / "old.sqlite"
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db))
    conn.executescript(
        "CREATE TABLE notes (uri TEXT PRIMARY KEY, project TEXT NOT NULL, "
        "type TEXT NOT NULL, scope TEXT NOT NULL, title TEXT NOT NULL, "
        "mtime REAL NOT NULL);"
    )
    conn.commit()
    conn.close()
    idx = Index(db)  # must not raise
    cols = {r["name"] for r in idx.conn.execute("PRAGMA table_info(notes)")}
    assert {"status", "confirmation_count", "subject_paths"} <= cols
    names = {r["name"] for r in idx.conn.execute("PRAGMA index_list(notes)")}
    assert "idx_notes_status" in names
    idx.close()


# ---- Step 3: injection gate at both surfaces (AC3, AC16, AC18) -----------------

def test_is_eligible_helper():
    ratified = SearchHit("u", "t", "function", "shared", "", 0.0, "ratified", "[]")
    prov_abs = SearchHit("u", "t", "function", "shared", "", 0.0, "provisional", '["src/a.py"]')
    prov_pre = SearchHit("u", "t", "function", "shared", "", 0.0, "provisional", '["src/a.py"]')
    assert _is_eligible(ratified, set())                       # ratified always
    assert not _is_eligible(prov_abs, {"src/b.py"})            # absent
    assert _is_eligible(prov_pre, {"src/a.py"})                # present
    assert _is_eligible(prov_abs, set(), lifecycle_enabled=False)  # toggle off


def test_build_injection_gate(setup):
    vault, index, mounts, _ = setup
    _seed_gate_notes(vault)
    block, uris = build_injection(mounts, "proj", index, Settings(),
                                  working_paths={"src/here.py"})
    assert "memory://proj/functions/ratified" in uris
    assert "memory://proj/functions/provpresent" in uris
    assert "memory://proj/functions/provabsent" not in uris


def test_build_attachment_gate_and_zero_extra_queries(setup, monkeypatch):
    vault, index, _, _ = setup
    vault.write_note("Gadget", "gizmo-token alpha", type="function", source="distilled",
                     status="provisional", subject_paths=["src/gadget.py"])
    # Per-hit metadata lookup must NOT be used (lifecycle is JOINed onto the hit).
    monkeypatch.setattr(index, "get_meta",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("get_meta called")))
    present, _ = build_attachment(vault, ["gizmo"], exclude=set(), settings=Settings(),
                                  working_paths={"src/gadget.py"})
    assert "gizmo-token" in present
    absent, attached = build_attachment(vault, ["gizmo"], exclude=set(), settings=Settings(),
                                        working_paths={"src/other.py"})
    assert attached == [] and absent == ""  # provisional + absent => withheld


def test_mcp_search_returns_suppressed_notes(setup):
    """Suppression is injection-scope only: the reactive search tool still finds
    a provisional-absent note (AC18)."""
    vault, _, _, _ = setup
    vault.write_note("Hidden", "needle-word body", type="function", source="distilled",
                     status="provisional", subject_paths=["src/absent.py"])
    results = vault.search("needle")
    assert any(r["uri"] == "memory://proj/functions/hidden" for r in results)


# ---- Step 4: distiller binding + confirmation (AC7, AC8, AC9, AC15, AC17) ------

def test_subject_paths_validated_against_session(setup):
    """LLM-emitted paths not actually touched this session are dropped; a born
    note is provisional with the validated binding (AC15 validation)."""
    vault, _, _, _ = setup
    ops = [{"action": "write", "title": "Bound", "type": "function", "scope": "shared",
            "content": "b", "subject_paths": ["src/real.py", "src/hallucinated.py"],
            "subject_symbols": ["real.fn"]}]
    apply_ops(vault, ops, provider=None, session_paths={"src/real.py"})
    note = vault.read_note("memory://proj/functions/bound", track=False)
    assert note["status"] == "provisional"
    assert note["subject_paths"] == ["src/real.py"]       # hallucinated dropped
    assert note["subject_symbols"] == ["real.fn"]


def _make_repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "foo.py").write_text("def bar():\n    return 1\n")
    return repo


def test_confirmation_increments_and_ratifies(setup, tmp_path):
    vault, index, _, _ = setup
    repo = _make_repo(tmp_path)
    vault.write_note("Foo", "b", type="function", source="distilled",
                     status="provisional", confirmation_count=1,
                     subject_paths=["src/foo.py"], subject_symbols=["foo.bar"])
    settings = Settings(confirmation_threshold=3)
    index.rebuild(vault.mounts)
    _confirm_notes(vault, repo, set(), settings)
    note = vault.read_note("memory://proj/functions/foo", track=False)
    assert note["confirmation_count"] == 2 and note["status"] == "provisional"
    index.rebuild(vault.mounts)
    _confirm_notes(vault, repo, set(), settings)  # 2 -> 3 => ratified
    note = vault.read_note("memory://proj/functions/foo", track=False)
    assert note["confirmation_count"] == 3 and note["status"] == "ratified"


def test_confirmation_monotonic_when_absent(setup, tmp_path):
    """Subject code absent (e.g. on another branch) must NOT lower the count (AC8)."""
    vault, index, _, _ = setup
    repo = _make_repo(tmp_path)
    vault.write_note("Gone", "b", type="function", source="distilled",
                     status="provisional", confirmation_count=2,
                     subject_paths=["src/missing.py"], subject_symbols=["missing.fn"])
    index.rebuild(vault.mounts)
    _confirm_notes(vault, repo, set(), Settings(confirmation_threshold=3))
    note = vault.read_note("memory://proj/functions/gone", track=False)
    assert note["confirmation_count"] == 2  # unchanged, never decremented


def test_confirmation_skips_manual_notes(setup, tmp_path):
    """Distiller-safety: the confirmation pass never touches human notes."""
    vault, index, _, _ = setup
    repo = _make_repo(tmp_path)
    # A manual note forced provisional — the pass must leave it alone.
    vault.write_note("Hand", "b", type="function", source="manual",
                     status="provisional", subject_paths=["src/foo.py"],
                     subject_symbols=["foo.bar"])
    index.rebuild(vault.mounts)
    log = _confirm_notes(vault, repo, set(), Settings())
    assert not any("hand" in line for line in log)
    note = vault.read_note("memory://proj/functions/hand", track=False)
    assert note["confirmation_count"] == 0  # untouched


def test_confirmation_batch_bound(setup, tmp_path):
    """At most confirmation_batch_size notes are processed per run (AC17)."""
    vault, index, _, _ = setup
    repo = _make_repo(tmp_path)
    for i in range(6):
        vault.write_note(f"N{i}", "b", type="function", source="distilled",
                         status="provisional", subject_paths=["src/foo.py"])
    index.rebuild(vault.mounts)
    log = _confirm_notes(vault, repo, set(), Settings(confirmation_batch_size=2))
    assert len(log) == 2  # only the batch size confirmed this run


def test_check_confirmation_per_type(setup, tmp_path):
    repo = _make_repo(tmp_path)
    # code note: symbol resolves
    assert _check_confirmation(
        {"type": "function", "subject_paths": ["src/foo.py"], "subject_symbols": ["bar"]},
        repo, set())
    # code note: file present, no symbols -> path-only confirm
    assert _check_confirmation(
        {"type": "module", "subject_paths": ["src/foo.py"], "subject_symbols": []}, repo, set())
    # code note: symbol absent
    assert not _check_confirmation(
        {"type": "function", "subject_paths": ["src/foo.py"], "subject_symbols": ["nope"]},
        repo, set())
    # decision: re-observation via session_paths
    assert _check_confirmation(
        {"type": "decision", "subject_paths": ["src/foo.py"], "subject_symbols": []},
        repo, {"src/foo.py"})
    assert not _check_confirmation(
        {"type": "decision", "subject_paths": ["src/foo.py"], "subject_symbols": []}, repo, set())


def test_resolve_symbol(tmp_path):
    repo = _make_repo(tmp_path)
    assert resolve_symbol(repo, "src/foo.py", "foo.bar")  # dotted, trailing match
    assert resolve_symbol(repo, "src/foo.py", "bar")
    assert not resolve_symbol(repo, "src/foo.py", "missing")
    assert not resolve_symbol(repo, "src/missing.py", "bar")  # missing file -> False


# ---- Step 7: verify command (AC11) ---------------------------------------------

def _register(tmp_path, monkeypatch, vault_dir):
    """Write a registry mapping project 'proj' to a real repo + vault, chdir in."""
    repo = tmp_path / "proj"
    (repo / "src").mkdir(parents=True, exist_ok=True)
    reg = tmp_path / "home" / "registry.yaml"
    reg.parent.mkdir(parents=True, exist_ok=True)
    reg.write_text(yaml.safe_dump(
        {"projects": {"proj": {"path": str(vault_dir), "repo": str(repo)}}}))
    monkeypatch.chdir(repo)
    return repo


def test_verify_lists_then_prunes_absent(setup, tmp_path, monkeypatch, capsys):
    vault, _, _, vault_dir = setup
    _register(tmp_path, monkeypatch, vault_dir)
    # provisional note whose subject file does NOT exist in the repo
    vault.write_note("Orphan", "b", type="function", source="distilled",
                     status="provisional", subject_paths=["src/deleted.py"])
    assert cli.main(["verify"]) == 0
    out = capsys.readouterr().out
    assert "memory://proj/functions/orphan" in out and "Re-run with --prune" in out
    # prune -> archived to attic, removed from active vault
    assert cli.main(["verify", "--prune"]) == 0
    assert (vault_dir / "attic" / "functions" / "orphan.md").exists()
    assert not (vault_dir / "functions" / "orphan.md").exists()


def test_verify_present_note_is_kept(setup, tmp_path, monkeypatch, capsys):
    vault, _, _, vault_dir = setup
    repo = _register(tmp_path, monkeypatch, vault_dir)
    (repo / "src" / "kept.py").write_text("x = 1\n")
    vault.write_note("Kept", "b", type="function", source="distilled",
                     status="provisional", subject_paths=["src/kept.py"])
    assert cli.main(["verify"]) == 0
    assert "no provisional notes with absent subject code" in capsys.readouterr().out


def test_verify_ratify_and_lower(setup, tmp_path, monkeypatch, capsys):
    vault, _, _, vault_dir = setup
    _register(tmp_path, monkeypatch, vault_dir)
    vault.write_note("Knob", "b", type="function", source="distilled",
                     status="provisional", subject_paths=["src/x.py"])
    assert cli.main(["verify", "--ratify", "memory://proj/functions/knob"]) == 0
    assert vault.read_note("memory://proj/functions/knob", track=False)["status"] == "ratified"
    assert cli.main(["verify", "--lower", "memory://proj/functions/knob"]) == 0
    note = vault.read_note("memory://proj/functions/knob", track=False)
    assert note["status"] == "provisional" and note["confirmation_count"] == 0
