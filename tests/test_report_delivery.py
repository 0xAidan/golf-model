"""The direct FastAPI host serves public reports without SPA fallbacks."""

from fastapi.testclient import TestClient
import pytest


@pytest.fixture
def report_host(monkeypatch, tmp_path):
    import app

    dist = tmp_path / "dist"
    reports = dist / "reports"
    reports.mkdir(parents=True)
    shell = "<!doctype html><html><body><div id='root'>Report test shell</div></body></html>"
    (dist / "index.html").write_text(shell, encoding="utf-8")
    (reports / "performance-2026.json").write_text('{"schema_version":1,"default_scope":"pre_event"}', encoding="utf-8")
    (reports / "decisions.csv").write_text("player,market\nPlayer A,top10\n", encoding="utf-8")
    private = tmp_path / "private.json"
    private.write_text('{"private":"never public"}', encoding="utf-8")
    (reports / "outside.json").symlink_to(private)
    mount = next(route for route in app.app.routes if route.name == "frontend-reports")
    monkeypatch.setattr(mount.app, "directory", str(reports))
    monkeypatch.setattr(mount.app, "all_directories", [str(reports)])
    monkeypatch.setattr(mount.app, "config_checked", False)
    monkeypatch.setattr(app, "FRONTEND_DIST_DIR", dist)
    monkeypatch.setattr(app, "FRONTEND_DIST_INDEX", dist / "index.html")
    monkeypatch.setattr(app, "get_conn", lambda: pytest.fail("Static report requests must not open the prediction database"))
    return TestClient(app.app), reports, shell


def test_public_json_report_is_json_instead_of_the_spa(report_host):
    client, _, _ = report_host
    response = client.get("/reports/performance-2026.json")
    assert response.status_code == 200
    assert response.headers["content-type"].split(";")[0] == "application/json"
    assert response.json() == {"schema_version": 1, "default_scope": "pre_event"}


def test_public_csv_report_has_csv_mime_and_exact_contents(report_host):
    client, _, _ = report_host
    response = client.get("/reports/decisions.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].split(";")[0] == "text/csv"
    assert response.text == "player,market\nPlayer A,top10\n"


@pytest.mark.parametrize("url", [
    "/reports/missing.json", "/reports/", "/reports/outside.json",
    "/reports/%2e%2e/private.json", "/reports/%2e%2e/%2e%2e/private.json",
    "/reports/%2e%2e%2f%2e%2e%2fprivate.json", "/reports/data/golf.db",
    "/reports/output/private.json",
])
def test_absent_and_unsafe_reports_return_404_without_spa_or_private_content(report_host, url):
    client, _, shell = report_host
    response = client.get(url)
    assert response.status_code == 404
    assert shell not in response.text
    assert "never public" not in response.text


def test_missing_report_directory_is_404_even_before_a_build(report_host):
    client, reports, shell = report_host
    for path in reports.iterdir():
        path.unlink()
    reports.rmdir()
    response = client.get("/reports/performance-2026.json")
    assert response.status_code == 404
    assert shell not in response.text


@pytest.mark.parametrize("url", ["/", "/rankings", "/markets", "/performance", "/models", "/research/legacy"])
def test_normal_client_routes_still_receive_the_spa(report_host, url):
    client, _, shell = report_host
    response = client.get(url)
    assert response.status_code == 200
    assert response.headers["content-type"].split(";")[0] == "text/html"
    assert response.text == shell


def test_report_head_and_mutation_methods_stay_static(report_host):
    client, _, _ = report_host
    head = client.head("/reports/performance-2026.json")
    assert head.status_code == 200
    assert head.headers["content-type"].split(";")[0] == "application/json"
    assert head.content == b""
    assert client.post("/reports/performance-2026.json").status_code == 405
