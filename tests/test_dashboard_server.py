import hashlib
import http.client
import json
import socket
import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest

from silver_bot.config import AppConfig
from silver_bot.monitoring.dashboard_server import BIND_HOST, SECURITY_HEADERS, DashboardServer, main, render_page
from silver_bot.monitoring.status import PANEL_TITLES, collect_status
from silver_bot.storage.sqlite import SQLiteStorage

NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
SECRETS = {
    "api_key": "SENTINEL-KEY",
    "api_secret": "SENTINEL-SECRET",
    "telegram_bot_token": "SENTINEL-TOKEN",
    "telegram_chat_id": "SENTINEL-CHAT",
}


def make_config(root: Path, **overrides) -> AppConfig:
    values = {"database_path": root / "data" / "silver_bot.sqlite3"}
    values.update(overrides)
    return AppConfig(**values)


def write_audit(root: Path, *events: dict) -> None:
    path = root / "logs" / "audit.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(event, sort_keys=True) + "\n" for event in events), encoding="utf-8")


def page_for(root: Path, config: AppConfig | None = None) -> str:
    chosen = config or make_config(root)
    return render_page(collect_status(root, load=lambda: chosen, now=NOW))


def test_page_shows_six_panels_in_layout_order_with_banner_first(tmp_path):
    page = page_for(tmp_path)

    positions = [page.index(f"<caption>{title.replace('&', '&amp;')}</caption>") for title in PANEL_TITLES]
    assert positions == sorted(positions)
    assert page.index('class="row banner"') < positions[1]
    assert "<script" not in page
    assert "generated 2026-10-09 12:00 UTC" in page


def test_state_tags_carry_glyph_word_and_class(tmp_path):
    page = page_for(tmp_path)

    assert '<td class="off">[ OFF ]</td><td>OFF</td>' in page
    assert '<td class="ok">[ OK ]</td><td>ON</td>' in page
    assert '<td class="err">[ ERR ]</td><td>missing</td>' in page


def test_markup_in_sources_is_escaped(tmp_path):
    write_audit(
        tmp_path,
        {
            "context": {},
            "created_at": "2026-10-09T11:00:00+00:00",
            "event_type": "error",
            "level": "ERROR",
            "message": "<script>alert(1)</script>",
        },
    )

    page = page_for(tmp_path)

    assert "<script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page


def test_secrets_never_reach_the_page(tmp_path):
    write_audit(
        tmp_path,
        {
            "context": {"api_key": "SENTINEL-KEY", "telegram_bot_token": "SENTINEL-TOKEN"},
            "created_at": "2026-10-09T11:00:00+00:00",
            "event_type": "bot_started",
            "level": "INFO",
            "message": "started",
        },
    )

    page = page_for(tmp_path, make_config(tmp_path, **SECRETS))

    for secret in SECRETS.values():
        assert secret not in page


@pytest.fixture
def server(tmp_path):
    config = make_config(tmp_path)
    instance = DashboardServer(0, root=tmp_path, load=lambda: config)
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    yield instance
    instance.shutdown()
    instance.server_close()


def call(server, method: str = "GET", path: str = "/", host: str | None = None):
    port = server.server_address[1]
    connection = http.client.HTTPConnection(BIND_HOST, port, timeout=5)
    connection.request(method, path, headers={"Host": host or f"127.0.0.1:{port}"})
    response = connection.getresponse()
    body = response.read().decode("utf-8")
    connection.close()
    return response, body


def test_get_root_returns_page_with_security_headers(server):
    response, body = call(server)

    assert response.status == 200
    assert response.getheader("Content-Type") == "text/html; charset=utf-8"
    assert response.getheader("Content-Security-Policy") == "default-src 'none'; style-src 'unsafe-inline'"
    assert response.getheader("X-Content-Type-Options") == "nosniff"
    assert response.getheader("Cache-Control") == "no-store"
    assert response.getheader("Referrer-Policy") == "no-referrer"
    assert "<caption>MODE &amp; SAFETY</caption>" in body


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def test_other_methods_get_405(server, method):
    response, _ = call(server, method)

    assert response.status == 405
    assert response.getheader("Allow") == "GET"
    assert response.getheader("Content-Security-Policy") == "default-src 'none'; style-src 'unsafe-inline'"


@pytest.mark.parametrize("path", ["/x", "/?a=1", "/favicon.ico"])
def test_unknown_paths_get_404(server, path):
    response, _ = call(server, path=path)

    assert response.status == 404


def test_foreign_host_header_gets_400(server):
    response, _ = call(server, host=f"evil.example:{server.server_address[1]}")

    assert response.status == 400


def test_localhost_host_header_is_accepted(server):
    response, _ = call(server, host=f"localhost:{server.server_address[1]}")

    assert response.status == 200


def test_server_binds_loopback_only(server):
    assert server.server_address[0] == "127.0.0.1"


def test_serving_changes_no_source_file(server, tmp_path):
    database = tmp_path / "data" / "silver_bot.sqlite3"
    SQLiteStorage(database).initialize()
    report = tmp_path / "reports" / "backtest_report.json"
    report.parent.mkdir()
    report.write_text("{}")
    write_audit(tmp_path, {"context": {}, "created_at": "2026-10-09T11:00:00+00:00",
                           "event_type": "bot_started", "level": "INFO", "message": "m"})
    tracked = [database, report, tmp_path / "logs" / "audit.jsonl"]
    before = {path: (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns) for path in tracked}
    files_before = {path for path in tmp_path.rglob("*")}

    for method in ("GET", "POST", "DELETE"):
        call(server, method)

    after = {path: (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns) for path in tracked}
    assert after == before
    new_files = {path.name for path in tmp_path.rglob("*")} - {path.name for path in files_before}
    assert new_files <= {database.name + "-wal", database.name + "-shm"}


def test_main_exits_2_when_port_is_taken(capsys):
    with socket.socket() as blocker:
        blocker.bind((BIND_HOST, 0))
        blocker.listen()
        port = blocker.getsockname()[1]

        assert main(["--port", str(port)]) == 2

    assert f"cannot listen on 127.0.0.1:{port}" in capsys.readouterr().err


def test_ok_response_carries_each_security_header_once(server):
    response, _ = call(server)

    for name in SECURITY_HEADERS:
        assert len(response.msg.get_all(name)) == 1


def test_malformed_request_gets_400_with_security_headers_once(server):
    with socket.create_connection((BIND_HOST, server.server_address[1]), timeout=5) as sock:
        sock.sendall(b"GARBAGE\r\n\r\n")
        data = b""
        while chunk := sock.recv(4096):
            data += chunk
    head = data.split(b"\r\n\r\n", 1)[0].decode("latin-1")
    status_line, *header_lines = head.split("\r\n")

    assert "400" in status_line
    names = [line.split(":", 1)[0].lower() for line in header_lines]
    for name in SECURITY_HEADERS:
        assert names.count(name.lower()) == 1


@pytest.mark.parametrize("port", ["70000", "-1"])
def test_main_exits_2_on_out_of_range_port(port, capsys):
    assert main(["--port", port]) == 2
    assert f"invalid port: {port}" in capsys.readouterr().err
