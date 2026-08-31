"""Player photo ID matching and cached photo HTTP routes."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from src.player_normalizer import normalize_name
from src.player_photos import (
    load_overrides,
    match_directory,
    parse_directory_payload,
    upsert_photo_ids,
)


def test_parse_graphql_directory_and_accent_keys():
    payload = {
        "data": {
            "playerDirectory": {
                "players": [
                    {
                        "id": "52955",
                        "firstName": "Ludvig",
                        "lastName": "Åberg",
                        "country": "Sweden",
                        "countryFlag": "SWE",
                    },
                    {
                        "id": "46046",
                        "firstName": "Scottie",
                        "lastName": "Scheffler",
                        "countryFlag": "USA",
                    },
                ]
            }
        }
    }
    rows = parse_directory_payload(payload)
    keys = {row["player_key"]: row for row in rows}
    assert keys["ludvig_aberg"]["pga_id"] == "52955"
    assert keys["ludvig_aberg"]["country"] == "SWE"
    assert keys["scottie_scheffler"]["pga_id"] == "46046"


def test_match_skips_collisions_and_honors_overrides(tmp_path):
    directory = [
        {"player_key": "kim_si_woo", "pga_id": "1", "country": "KOR", "display": "Si Woo Kim"},
        {"player_key": "kim_si_woo", "pga_id": "2", "country": "KOR", "display": "Si Woo Kim"},
        {"player_key": "rory_mcilroy", "pga_id": "28237", "country": "NIR", "display": "Rory McIlroy"},
    ]
    overrides = {"ludvig_aberg": {"pga_id": "52955", "source": "override", "country": "SWE"}}
    matched = match_directory(
        directory,
        [
            ("kim_si_woo", "Si Woo Kim"),
            ("rory_mcilroy", "Rory McIlroy"),
            ("ludvig_aberg", "Ludvig Aberg"),
        ],
        overrides,
    )
    by_key = {row["player_key"]: row for row in matched}
    assert "kim_si_woo" not in by_key
    assert by_key["rory_mcilroy"]["pga_id"] == "28237"
    assert by_key["ludvig_aberg"]["source"] == "override"
    assert normalize_name("Åberg, Ludvig") == "ludvig_aberg"

    override_file = tmp_path / "overrides.json"
    override_file.write_text(json.dumps({"Collin Morikawa": "50525"}), encoding="utf-8")
    loaded = load_overrides(override_file)
    assert loaded["collin_morikawa"]["pga_id"] == "50525"


def test_photo_routes_serve_cache_and_skip_download(monkeypatch, tmp_path):
    from src import db
    from src import player_photos

    db_path = tmp_path / "photos.db"
    monkeypatch.setattr(db, "DB_PATH", str(db_path))
    db.init_db()
    photo_dir = tmp_path / "player_photos"
    monkeypatch.setattr(player_photos, "PHOTO_DIR", photo_dir)

    conn = db.get_conn()
    upsert_photo_ids(
        conn,
        [{"player_key": "collin_morikawa", "pga_id": "50525", "source": "pga_directory", "country": "USA"}],
    )
    conn.close()

    cached = photo_dir / "collin_morikawa.png"
    cached.parent.mkdir(parents=True)
    cached.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 3000)

    def _explode(*_args, **_kwargs):
        raise AssertionError("cached photos must not hit Cloudinary")

    monkeypatch.setattr(player_photos, "download_headshot", _explode)

    import app

    client = TestClient(app.app)
    index = client.get("/api/players/photo-index")
    assert index.status_code == 200
    assert index.json()["players"]["collin_morikawa"]["has_photo"] is True
    assert index.json()["players"]["collin_morikawa"]["country"] == "USA"

    photo = client.get("/api/players/collin_morikawa/photo")
    assert photo.status_code == 200
    assert photo.headers["content-type"].startswith("image/png")
    assert photo.content[:8] == b"\x89PNG\r\n\x1a\n"

    missing = client.get("/api/players/unknown_player/photo")
    assert missing.status_code == 404


def test_photo_download_is_cached_locally(monkeypatch, tmp_path):
    from src import db
    from src import player_photos

    db_path = tmp_path / "photos_dl.db"
    monkeypatch.setattr(db, "DB_PATH", str(db_path))
    db.init_db()
    photo_dir = tmp_path / "player_photos_dl"
    monkeypatch.setattr(player_photos, "PHOTO_DIR", photo_dir)

    conn = db.get_conn()
    upsert_photo_ids(
        conn,
        [{"player_key": "scottie_scheffler", "pga_id": "46046", "source": "pga_directory"}],
    )
    conn.close()

    body = b"\x89PNG\r\n\x1a\n" + b"s" * 3000
    monkeypatch.setattr(player_photos, "download_headshot", lambda pga_id: body if pga_id == "46046" else None)

    import app

    first = TestClient(app.app).get("/api/players/scottie_scheffler/photo")
    assert first.status_code == 200
    assert (photo_dir / "scottie_scheffler.png").read_bytes() == body
