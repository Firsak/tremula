"""Stage 3 acceptance: index, vault service, capture, injection, distiller."""


import pytest

from tremula.capture import append_event, read_session, session_file
from tremula.config import Settings
from tremula.distiller import build_prompt, distill, parse_ops
from tremula.index import Index
from tremula.injection import build_injection
from tremula.memory_uri import MemoryURIError
from tremula.vault import VaultService


@pytest.fixture
def vault_setup(tmp_path, monkeypatch):
    """A single-project mount set with an index, under a temp TREMULA_HOME."""
    monkeypatch.setenv("TREMULA_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("TREMULA_HOOKS_DISABLED", raising=False)
    vault_dir = tmp_path / "proj" / "tremula-vault"
    vault_dir.mkdir(parents=True)
    (vault_dir / "_index.md").write_text(
        "---\ntype: index\nscope: shared\n---\n\n# Proj Index\n\nentry point\n"
    )
    mounts = {"proj": vault_dir}
    index = Index(tmp_path / "home" / "index" / "proj.sqlite")
    index.rebuild(mounts)
    return VaultService(mounts, index, project="proj"), index, mounts


# ---- index -----------------------------------------------------------------

def test_index_search_and_neighbors(vault_setup):
    vault, index, _ = vault_setup
    a = vault.write_note("Auth module", "Handles login via JWT.", type="module")
    b = vault.write_note("Token store", "Stores refresh tokens.", type="module",
                         links={"depends_on": [a]})
    hits = index.search("JWT login")
    assert any(h.uri == a for h in hits)
    # b depends_on a -> they are neighbors (traversal is bidirectional)
    assert a in index.neighbors(b, depth=1)
    assert b in index.neighbors(a, depth=1)


def test_search_scope_filter(vault_setup):
    vault, index, _ = vault_setup
    vault.write_note("Frontend widget", "renders the dashboard", type="module", scope="frontend")
    vault.write_note("Backend worker", "renders nothing", type="module", scope="backend")
    fe = index.search("renders", scope="frontend")
    assert all(h.scope == "frontend" for h in fe)
    assert any("widget" in h.title.lower() for h in fe)


# ---- vault service ---------------------------------------------------------

def test_write_creates_markdown_and_indexes(vault_setup):
    vault, index, mounts = vault_setup
    uri = vault.write_note("Cache layer", "SQLite FTS5 cache.", type="architecture")
    assert uri == "memory://proj/architecture/cache-layer"
    path = mounts["proj"] / "architecture" / "cache-layer.md"
    assert path.exists()
    assert "type: architecture" in path.read_text()
    assert index.get_meta(uri) is not None


def test_read_outside_mount_set_raises(vault_setup):
    vault, _, _ = vault_setup
    with pytest.raises(MemoryURIError, match="not in the mount set"):
        vault.read_note("memory://other/modules/secret")


def test_link_notes_adds_edge(vault_setup):
    vault, index, _ = vault_setup
    a = vault.write_note("Service A", "calls B", type="module")
    b = vault.write_note("Service B", "is called", type="module")
    vault.link_notes(a, b, "depends_on")
    note = vault.read_note(a)
    assert b in note["links"]["depends_on"]
    assert b in index.neighbors(a, depth=1)


def test_split_note(vault_setup):
    vault, _, mounts = vault_setup
    big = vault.write_note(
        "Big doc",
        "# Big doc\n\nintro\n\n## Section one\n\nbody one\n\n## Section two\n\nbody two\n",
        type="architecture",
    )
    children = vault.split_note(big)
    assert len(children) == 2
    parent_body = vault.read_note(big)["body"]
    assert "index" in parent_body.lower()
    # children carry part_of back to the parent
    assert vault.read_note(children[0])["links"]["part_of"] == [big]


def test_get_context_graph_expansion(vault_setup):
    vault, _, _ = vault_setup
    a = vault.write_note("Payment flow", "charges a card via Stripe", type="architecture")
    b = vault.write_note("Stripe webhook", "receives events", type="module",
                         links={"implements": [a]})
    result = vault.get_context("Stripe card charge", depth=1)
    assert a in result.seeds
    assert b in result.neighbors  # graph found what the query didn't name
    assert "Stripe webhook" in result.content


# ---- capture ---------------------------------------------------------------

def test_capture_append_and_read(vault_setup):
    append_event("proj", "sess1", "UserPromptSubmit", {"text": "hello"})
    events = read_session(session_file("proj", "sess1"))
    assert len(events) == 1
    assert events[0]["event"] == "UserPromptSubmit"
    assert events[0]["payload"]["text"] == "hello"


def test_capture_disabled(monkeypatch, vault_setup):
    monkeypatch.setenv("TREMULA_HOOKS_DISABLED", "1")
    assert append_event("proj", "sess2", "Stop", {}) is False
    assert not session_file("proj", "sess2").exists()


# ---- injection -------------------------------------------------------------

def test_injection_has_index_and_hot_notes(vault_setup):
    vault, index, mounts = vault_setup
    uri = vault.write_note("Hot note", "freshly written knowledge", type="convention")
    block, uris = build_injection(mounts, "proj", index, Settings())
    assert "Proj Index" in block          # _index.md content
    assert "Recently updated memory" in block
    assert "Hot note" in block
    assert "memory://proj/_index" in uris and uri in uris  # dedupe bookkeeping


# ---- distiller (injected fake provider, no live LLM) -----------------------

class FakeProvider:
    def __init__(self, response: str):
        self.response = response
        self.seen_prompt: str | None = None

    def complete(self, prompt: str) -> str:
        self.seen_prompt = prompt
        return prompt and self.response


def test_distiller_applies_ops(vault_setup):
    vault, _, mounts = vault_setup
    provider = FakeProvider(
        '{"ops": [{"action": "write", "title": "Use stdio", "type": "decision", '
        '"scope": "shared", "content": "We chose stdio transport."}]}'
    )
    events = [{"event": "UserPromptSubmit", "payload": {"text": "let us use stdio"}}]
    applied = distill(events, vault, provider)
    assert applied == ["write memory://proj/decisions/use-stdio"]
    assert (mounts["proj"] / "decisions" / "use-stdio.md").exists()
    # hygiene prompt was used and contained the session events
    assert "DURABLE" in provider.seen_prompt
    assert "let us use stdio" in provider.seen_prompt


def test_distiller_empty_session_is_noop(vault_setup):
    vault, _, _ = vault_setup
    provider = FakeProvider('{"ops": []}')
    assert distill([], vault, provider) == []
    assert provider.seen_prompt is None  # provider never called on empty input


def test_distiller_tolerates_prose_around_json(vault_setup):
    vault, _, _ = vault_setup
    ops = parse_ops('Sure! Here you go:\n{"ops": [{"action": "link", '
                    '"src": "memory://proj/a", "dst": "memory://proj/b", '
                    '"relation": "depends_on"}]}\nDone.')
    assert ops[0]["action"] == "link"


def test_build_prompt_contains_hygiene_rules():
    prompt = build_prompt([{"event": "Stop", "payload": {}}])
    assert "DROP" in prompt and "KEEP" in prompt
