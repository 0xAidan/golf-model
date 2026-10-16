"""Generation controls preserve stored history and the incumbent model math."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import stat
from threading import Barrier

from fastapi.testclient import TestClient
import pytest

from src import market_generation_policy as policy


@pytest.fixture(autouse=True)
def isolated_policy(monkeypatch, tmp_path):
    root = tmp_path / "policy"
    monkeypatch.setenv("GOLF_MARKET_GENERATION_POLICY_DIR", str(root))
    monkeypatch.delenv("DASHBOARD_API_KEY", raising=False)
    monkeypatch.delenv("MARKET_GENERATION_API_KEY", raising=False)
    return root


def save(markets, revision="unconfigured"):
    return policy.update_market_generation_policy(enabled_markets=markets, expected_revision=revision)


def test_unconfigured_read_keeps_legacy_allowlist_without_creating_files(isolated_policy):
    result = policy.get_market_generation_policy()
    assert result["revision"] == "unconfigured"
    assert result["configured"] is False
    assert result["enabled_markets"] == list(policy.SUPPORTED_IDS)
    assert result["editing_available"] is False
    assert not isolated_policy.exists()
    assert {m["id"] for m in result["supported_markets"] if not m["supported"]} == {"make_cut", "miss_cut", "top15"}


def test_explicit_empty_disables_all_and_retains_immutable_revision_chain(isolated_policy):
    first = save([])
    first_file = isolated_policy / "revisions" / f"{first['revision']}.json"
    original_bytes = first_file.read_bytes()
    assert first["enabled_markets"] == []
    assert all(not policy.market_enabled(m) for m in policy.SUPPORTED_IDS)
    second = save(["top10", "72h"], first["revision"])
    assert second["enabled_markets"] == ["72h", "top10"]
    assert first_file.read_bytes() == original_bytes
    assert len(list((isolated_policy / "revisions").glob("*.json"))) == 2
    current_file = isolated_policy / "revisions" / f"{second['revision']}.json"
    assert json.loads(current_file.read_bytes())["previous_revision"] == first["revision"]
    assert hashlib.sha256(current_file.read_bytes()).hexdigest() == second["revision"]
    assert policy.get_market_generation_policy() == second


@pytest.mark.parametrize("markets", [None, "top10", {}, [1], ["top10", "top10"], ["make_cut"], ["miss_cut"], ["top15"], ["all"], ["Top10"]])
def test_rejects_invalid_allowlists_without_creating_files(markets, isolated_policy):
    with pytest.raises(policy.PolicyValidationError):
        save(markets)
    assert not isolated_policy.exists()


@pytest.mark.parametrize("revision", [None, "", 1, []])
def test_revision_is_required(revision, isolated_policy):
    with pytest.raises(policy.PolicyValidationError):
        save([], revision)
    assert not isolated_policy.exists()


def test_simultaneous_writers_cannot_silently_overwrite_each_other(isolated_policy):
    barrier = Barrier(2)

    def update(markets):
        barrier.wait()
        try:
            return save(markets)
        except policy.PolicyRevisionConflict as exc:
            return exc.current

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(update, [["72h"], []]))
    assert results[0] == results[1] == policy.get_market_generation_policy()
    assert len(list((isolated_policy / "revisions").glob("*.json"))) == 1


@pytest.mark.parametrize("damage", ["missing_pointer", "missing_revision", "tampered_revision", "bad_pointer", "oversized_pointer"])
def test_corrupt_or_missing_config_fails_closed_without_overwriting_history(damage, isolated_policy):
    saved = save([])
    revision_file = isolated_policy / "revisions" / f"{saved['revision']}.json"
    pointer = isolated_policy / "current.json"
    if damage == "missing_pointer":
        pointer.unlink()
    elif damage == "missing_revision":
        revision_file.unlink()
    elif damage == "tampered_revision":
        revision_file.write_text('{"enabled_markets":["72h"]}')
    elif damage == "oversized_pointer":
        pointer.write_text(" " * 2048)
    else:
        pointer.write_text('{"revision":"../../secret"}')
    before = {str(p): p.read_bytes() for p in isolated_policy.rglob("*.json")}
    read = policy.get_market_generation_policy()
    assert read["state"] == "unavailable"
    assert read["enabled_markets"] == []
    assert read["editing_available"] is False
    with pytest.raises(policy.PolicyUnavailableError):
        save(["72h"])
    assert {str(p): p.read_bytes() for p in isolated_policy.rglob("*.json")} == before


def test_revision_directory_is_durable_before_current_pointer(monkeypatch):
    events = []
    original_sync = policy.os.fsync
    original_pointer = policy._atomic_pointer

    def sync(descriptor):
        events.append("directory_sync" if stat.S_ISDIR(policy.os.fstat(descriptor).st_mode) else "file_sync")
        original_sync(descriptor)

    def pointer(root, revision):
        events.append("pointer")
        assert events[-3:] == ["file_sync", "directory_sync", "pointer"]
        original_pointer(root, revision)

    monkeypatch.setattr(policy.os, "fsync", sync)
    monkeypatch.setattr(policy, "_atomic_pointer", pointer)
    save([])


def test_first_save_durably_creates_every_ancestor_before_publishing(monkeypatch, tmp_path):
    root = tmp_path / "new-data" / "nested" / "policy"
    monkeypatch.setenv("GOLF_MARKET_GENERATION_POLICY_DIR", str(root))
    existing_mode = stat.S_IMODE(tmp_path.stat().st_mode)
    events = []
    original_mkdir = Path.mkdir
    original_sync = policy._sync_directory
    original_pointer = policy._atomic_pointer

    def mkdir(path, *args, **kwargs):
        original_mkdir(path, *args, **kwargs)
        events.append(("mkdir", path))

    def sync(path):
        original_sync(path)
        events.append(("sync", path))

    def pointer(path, revision):
        events.append(("publish", path))
        original_pointer(path, revision)

    monkeypatch.setattr(Path, "mkdir", mkdir)
    monkeypatch.setattr(policy, "_sync_directory", sync)
    monkeypatch.setattr(policy, "_atomic_pointer", pointer)
    result = save([])
    created = [tmp_path / "new-data", tmp_path / "new-data/nested", root, root / "revisions"]
    publish_index = events.index(("publish", root))
    for index, directory in enumerate(created):
        mkdir_index = events.index(("mkdir", directory))
        durable_index = events.index(("sync", directory.parent), mkdir_index)
        assert mkdir_index < durable_index < publish_index
        if index + 1 < len(created):
            assert durable_index < events.index(("mkdir", created[index + 1]))
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert stat.S_IMODE(tmp_path.stat().st_mode) == existing_mode
    assert result["enabled_markets"] == []
    get_current = policy.get_market_generation_policy()
    assert get_current["revision"] == result["revision"]


def test_concurrent_directory_creator_is_synced_before_acknowledging(monkeypatch, isolated_policy):
    events = []
    original_mkdir = Path.mkdir
    original_sync = policy._sync_directory

    def mkdir(path, *args, **kwargs):
        if path == isolated_policy:
            # Simulate a second process winning mkdir after our existence check.
            original_mkdir(path, mode=0o750)
            path.chmod(0o750)
            events.append(("competing_mkdir", path))
            raise FileExistsError(str(path))
        original_mkdir(path, *args, **kwargs)

    def sync(path):
        original_sync(path)
        events.append(("sync", path))

    monkeypatch.setattr(Path, "mkdir", mkdir)
    monkeypatch.setattr(policy, "_sync_directory", sync)
    saved = save([])
    won = events.index(("competing_mkdir", isolated_policy))
    assert events.index(("sync", isolated_policy.parent), won) > won
    assert stat.S_IMODE(isolated_policy.stat().st_mode) == 0o750
    assert policy.get_market_generation_policy()["revision"] == saved["revision"]


def test_policy_changes_do_not_open_or_change_prediction_history(tmp_db, monkeypatch):
    tid = tmp_db.get_or_create_tournament("Preserved Open", year=2025)
    conn = tmp_db.get_conn()
    conn.execute("INSERT INTO picks(tournament_id, bet_type, player_key, player_display) VALUES (?, 'outright', 'old_player', 'Old Player')", (tid,))
    conn.commit()
    conn.close()
    before = Path(tmp_db.DB_PATH).read_bytes()
    monkeypatch.setattr(tmp_db, "get_conn", lambda: pytest.fail("Policy must not open the prediction database"))
    first = save([])
    save(["group", "top20"], first["revision"])
    assert policy.get_market_generation_policy()["enabled_markets"] == ["group", "top20"]
    assert Path(tmp_db.DB_PATH).read_bytes() == before


@pytest.fixture
def client():
    import app

    return TestClient(app.app)


def test_api_public_read_and_missing_auth_write(client, isolated_policy):
    assert client.get("/api/market-generation-policy").json()["auth_configured"] is False
    response = client.patch("/api/market-generation-policy", json={"enabled_markets": [], "expected_revision": "unconfigured"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "write_auth_unconfigured"
    assert not isolated_policy.exists()


@pytest.mark.parametrize("header", [{}, {"x-api-key": "wrong"}, {"authorization": "Bearer wrong"}, {"x-api-key": b"\xc3\xa9"}])
def test_unauthorized_write_is_401_without_mutation(client, monkeypatch, isolated_policy, header):
    monkeypatch.setenv("MARKET_GENERATION_API_KEY", "scoped-test-secret")
    response = client.patch("/api/market-generation-policy", json={"enabled_markets": [], "expected_revision": "unconfigured"}, headers=header)
    assert response.status_code == 401
    assert not isolated_policy.exists()


@pytest.mark.parametrize("key_env", ["MARKET_GENERATION_API_KEY", "DASHBOARD_API_KEY"])
def test_authenticated_write_and_conflict_return_verified_readback(client, monkeypatch, key_env):
    monkeypatch.setenv(key_env, "test-secret")
    headers = {"authorization": "Bearer test-secret"}
    response = client.patch("/api/market-generation-policy", json={"enabled_markets": [], "expected_revision": "unconfigured"}, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["enabled_markets"] == []
    assert body["auth_configured"] is body["editing_available"] is True
    assert "test-secret" not in response.text
    assert client.get("/api/market-generation-policy").json() == body
    conflict = client.patch("/api/market-generation-policy", json={"enabled_markets": ["72h"], "expected_revision": "unconfigured"}, headers=headers)
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["current"] == body


def test_dedicated_key_is_scoped_and_has_precedence(client, monkeypatch):
    monkeypatch.setenv("MARKET_GENERATION_API_KEY", "market-secret")
    monkeypatch.setenv("DASHBOARD_API_KEY", "dashboard-secret")
    payload = {"enabled_markets": [], "expected_revision": "unconfigured"}
    assert client.patch("/api/market-generation-policy", json=payload, headers={"x-api-key": "dashboard-secret"}).status_code == 401
    assert client.patch("/api/market-generation-policy", json=payload, headers={"x-api-key": "market-secret"}).status_code == 200
    # The scoped credential does not unlock unrelated mutating routes.
    assert client.post("/api/simple/upcoming-prediction", json={}, headers={"x-api-key": "market-secret"}).status_code == 401


@pytest.mark.parametrize("payload", [
    {}, {"enabled_markets": []}, {"enabled_markets": [], "expected_revision": "unconfigured", "extra": True},
    {"enabled_markets": ["make_cut"], "expected_revision": "unconfigured"},
])
def test_api_rejects_invalid_policy(client, monkeypatch, payload, isolated_policy):
    monkeypatch.setenv("MARKET_GENERATION_API_KEY", "key")
    response = client.patch("/api/market-generation-policy", json=payload, headers={"x-api-key": "key"})
    assert response.status_code == 422
    assert not isolated_policy.exists()


def test_pinned_original_sources_remain_exact():
    root = Path(__file__).resolve().parents[1]
    baseline = json.loads((root / "config/model-baselines/original-453f49ec24f0e48a.json").read_text())
    assert len(baseline["source_hashes"]) == 8
    for relative, expected in baseline["source_hashes"].items():
        assert hashlib.sha256((root / relative).read_bytes()).hexdigest() == expected, relative
