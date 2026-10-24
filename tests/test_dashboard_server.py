import base64
import hashlib
import html
import http.client
import json
import os
import socket
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from silver_bot.config import AppConfig
from silver_bot.monitoring.dashboard_server import (
    BIND_HOST,
    SECURITY_HEADERS,
    DashboardServer,
    is_loopback_host,
    main,
    render_page,
)
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
    banner = page.index('class="row banner"')
    ladder = page.index('class="ladder"')
    strip = page.index('class="next-strip"')
    assert banner < ladder < strip < positions[1]
    assert "<script" not in page
    assert "generated 2026-10-09 12:00 UTC" in page


ROOT_TOKENS = {
    "--canvas": "#0B0D10",
    "--surface": "#13161B",
    "--border": "#2A2F38",
    "--ink": "#E8EAED",
    "--muted": "#9AA1AC",
    "--brand": "#C3C9D2",
    "--accent": "#7AA2F7",
    "--success": "#3FB68B",
    "--warning": "#E3B341",
    "--danger": "#F0616D",
}


def write_report(root: Path, stem: str, content: str, mtime: float | None = None) -> None:
    path = root / "reports" / f"{stem}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if mtime is not None:
        os.utime(path, (mtime, mtime))


def today_shape(root: Path) -> None:
    old = (NOW - timedelta(hours=40)).timestamp()
    for stem in ("backtest_report", "out_of_sample_validation_report", "paper_trading_report"):
        write_report(root, stem, "")
    generated = (NOW - timedelta(hours=30)).isoformat()
    write_report(root, "demo_readiness_report", json.dumps({"ready": True, "generated_at": generated, "checks": []}), old)
    write_report(root, "live_readiness_report", json.dumps({"ready": False, "generated_at": generated, "checks": []}), old)


def test_title_header_and_mark(tmp_path):
    page = page_for(tmp_path)
    header = page[page.index("<header>") : page.index("</header>")]

    assert "<title>Silverbot status</title>" in page
    assert "<svg" in header and "Silverbot" in header
    assert "xmlns" not in page
    assert "status &middot; read-only &middot; 127.0.0.1" in header


def test_root_block_holds_exactly_the_ten_tokens():
    from silver_bot.monitoring.dashboard_server import CSS

    block = CSS[CSS.index(":root{") + 6 : CSS.index("}", CSS.index(":root{"))]
    tokens = dict(item.split(":", 1) for item in block.replace("\n", "").split(";") if item.strip())

    assert tokens == ROOT_TOKENS
    for name in ROOT_TOKENS:
        assert f"var({name})" in CSS


def test_pages_carry_no_url(tmp_path):
    from silver_bot.monitoring.dashboard_server import render_not_found

    for page in (page_for(tmp_path), render_not_found()):
        assert "http:" not in page and "https:" not in page
        assert "<form" not in page and "<button" not in page and "<input" not in page


def test_ladder_with_todays_data_shows_backtest_next(tmp_path):
    today_shape(tmp_path)

    page = page_for(tmp_path)

    assert page.count('<li class="step') == 5
    assert '<li class="step next">' in page
    first = page[page.index('<li class="step next">') :]
    assert "Backtest" in first[:200] and '<span class="err">[ ERR ]</span>' in first[:300]
    assert "0 B" in first[:300] and "<strong>NEXT</strong>" in first[:300]
    assert '<p class="next-strip">Next: run a backtest (runbook-backtest.md steps 5 and 6)</p>' in page
    assert "READY · stale" in page
    assert "blocked (PRD-F12)" in page


def test_degraded_line_only_when_a_source_fails(tmp_path):
    assert 'class="degraded"' not in page_for(tmp_path)

    (tmp_path / "logs" / "audit.jsonl").mkdir(parents=True)
    page = page_for(tmp_path)

    assert page.count('class="degraded"') == 1
    assert '<p class="degraded"><span class="warn">[ WRN ]</span> degraded: 1 panel unreadable</p>' in page


def test_degraded_line_pluralises(tmp_path):
    status = collect_status(tmp_path, load=lambda: make_config(tmp_path), now=NOW)
    status["degraded"] = 2

    assert "degraded: 2 panels unreadable" in render_page(status)


def test_unreadable_ladder_renders_one_step_and_no_strip(tmp_path):
    status = collect_status(tmp_path, load=lambda: make_config(tmp_path), now=NOW)
    status["ladder"] = {"steps": [{"state": "err", "label": "unreadable", "text": "KeyError"}], "next": None, "next_text": ""}

    page = render_page(status)

    assert page.count('<li class="step') == 1
    card = page.split('<li class="step', 1)[1].split("</li>", 1)[0]
    assert '<span class="label">unreadable</span>' in card
    assert "[ ERR ]" in card and "KeyError" in card
    assert "next-strip" not in page.split("</style>", 1)[1]
    assert "<strong>NEXT</strong>" not in page


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


def call(server, method: str = "GET", path: str = "/", host: str | None = None, auth: str | None = None):
    port = server.server_address[1]
    connection = http.client.HTTPConnection(BIND_HOST, port, timeout=5)
    headers = {"Host": host or f"127.0.0.1:{port}"}
    if auth is not None:
        headers["Authorization"] = auth
    connection.request(method, path, headers=headers)
    response = connection.getresponse()
    body = response.read().decode("utf-8")
    connection.close()
    return response, body


def call_raw(server, path: str, auth: str | None = None):
    port = server.server_address[1]
    connection = http.client.HTTPConnection(BIND_HOST, port, timeout=5)
    headers = {"Host": f"127.0.0.1:{port}"}
    if auth is not None:
        headers["Authorization"] = auth
    connection.request("GET", path, headers=headers)
    response = connection.getresponse()
    body = response.read()
    connection.close()
    return response, body


CSP = "default-src 'none'; style-src 'unsafe-inline'; font-src 'self'"
FONT_SHA256 = {
    "/fonts/IBMPlexMono-Regular.woff2": "49ce58b41a0e1cb921c0f58d9a5b8b96a2cc21437c7066f3ba4f24873076d131",
    "/fonts/IBMPlexMono-Bold.woff2": "5788454f0ba4bd6300752c474215c4dd926682fa173ae1c6252d57828b6a235d",
}


def test_csp_literal_is_pinned():
    assert SECURITY_HEADERS["Content-Security-Policy"] == CSP


@pytest.mark.parametrize("path", sorted(FONT_SHA256))
def test_fonts_are_served_with_headers_and_exact_bytes(server, path):
    response, body = call_raw(server, path)

    assert response.status == 200
    assert response.getheader("Content-Type") == "font/woff2"
    for name, value in SECURITY_HEADERS.items():
        assert response.getheader(name) == value
    assert hashlib.sha256(body).hexdigest() == FONT_SHA256[path]


@pytest.mark.parametrize(
    "path",
    [
        "/fonts/x.woff2",
        "/fonts/../status.py",
        "/fonts/%2e%2e/x",
        "/fonts/",
        "/fonts/IBMPlexMono-Regular.woff2?v=1",
    ],
)
def test_font_lookalike_paths_get_404(server, path):
    response, body = call_raw(server, path)

    assert response.status == 404
    assert body.startswith(b"<!doctype html>")


def test_404_is_branded_html_without_status_data(server):
    response, body = call(server, path="/nope")

    assert response.status == 404
    assert response.getheader("Content-Type") == "text/html; charset=utf-8"
    assert 'href="/"' in body
    assert "not found" in body
    assert "MODE &amp; SAFETY" not in body
    assert "generated " not in body


def test_csp_is_exact_on_200_404_405_and_400(server):
    port = server.server_address[1]
    for response in (
        call(server)[0],
        call(server, path="/nope")[0],
        call(server, "POST")[0],
        call(server, host=f"evil.example:{port}")[0],
    ):
        assert response.getheader("Content-Security-Policy") == SECURITY_HEADERS["Content-Security-Policy"]


def test_get_root_returns_page_with_security_headers(server):
    response, body = call(server)

    assert response.status == 200
    assert response.getheader("Content-Type") == "text/html; charset=utf-8"
    assert response.getheader("Content-Security-Policy") == SECURITY_HEADERS["Content-Security-Policy"]
    assert response.getheader("X-Content-Type-Options") == "nosniff"
    assert response.getheader("Cache-Control") == "no-store"
    assert response.getheader("Referrer-Policy") == "no-referrer"
    assert "<caption>MODE &amp; SAFETY</caption>" in body


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def test_other_methods_get_405(server, method):
    response, _ = call(server, method)

    assert response.status == 405
    assert response.getheader("Allow") == "GET"
    assert response.getheader("Content-Security-Policy") == SECURITY_HEADERS["Content-Security-Policy"]


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


def test_page_footer_shows_the_escaped_root(tmp_path):
    root = tmp_path / "a&b dir"
    root.mkdir()

    page = page_for(root)

    assert f"reading {html.escape(str(root))}" in page
    assert "a&amp;b dir" in page


PUBLIC_HOST = "bot.up.railway.app"


def basic(password: str, user: str = "anyone") -> str:
    return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()


@pytest.fixture
def gated(tmp_path):
    """Loopback-bound server with a password and a public Host, like Railway behind its edge."""

    config = make_config(tmp_path)
    instance = DashboardServer(0, root=tmp_path, load=lambda: config, allowed_host=PUBLIC_HOST, password="pw")
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    yield instance
    instance.shutdown()
    instance.server_close()


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.5", "example.com", "", "::"])
def test_non_loopback_host_without_password_is_refused(tmp_path, host):
    for password in (None, ""):
        with pytest.raises(ValueError, match="DASHBOARD_PASSWORD"):
            DashboardServer(0, root=tmp_path, host=host, password=password)


@pytest.mark.parametrize("host", ["127.0.0.1", "127.0.0.2", "localhost", "LOCALHOST", "::1"])
def test_is_loopback_host_accepts_loopback_names(host):
    assert is_loopback_host(host)


@pytest.mark.parametrize("host", ["0.0.0.0", "10.0.0.1", "bot.up.railway.app", "not an ip", ""])
def test_is_loopback_host_rejects_everything_else(host):
    assert not is_loopback_host(host)


def test_non_loopback_host_with_password_may_bind(tmp_path):
    instance = DashboardServer(0, root=tmp_path, host="0.0.0.0", password="pw")
    try:
        assert instance.server_address[0] == "0.0.0.0"
    finally:
        instance.server_close()


def test_main_exits_2_for_non_loopback_host_without_password(monkeypatch, capsys):
    monkeypatch.delenv("DASHBOARD_PASSWORD", raising=False)

    assert main(["--host", "0.0.0.0", "--port", "0"]) == 2
    assert "DASHBOARD_PASSWORD" in capsys.readouterr().err


def test_main_treats_a_blank_password_as_unset(monkeypatch, capsys):
    monkeypatch.setenv("DASHBOARD_PASSWORD", "   ")

    assert main(["--host", "0.0.0.0", "--port", "0"]) == 2
    assert "DASHBOARD_PASSWORD" in capsys.readouterr().err


def test_main_reads_the_password_from_the_environment_only(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DASHBOARD_PASSWORD", "SENTINEL-PW")
    seen = []

    def stop(self):
        seen.append(self.password)
        raise KeyboardInterrupt

    monkeypatch.setattr(DashboardServer, "serve_forever", stop)

    assert main(["--host", "0.0.0.0", "--port", "0", "--allowed-host", PUBLIC_HOST]) == 0

    assert seen == [b"SENTINEL-PW"]
    out = capsys.readouterr()
    assert "password required" in out.out
    assert "SENTINEL-PW" not in out.out + out.err


def test_unauthenticated_get_gets_401_with_challenge_and_security_headers(gated):
    for path in ("/", "/nope", "/fonts/IBMPlexMono-Regular.woff2"):
        response, body = call(gated, path=path)

        assert response.status == 401
        assert response.getheader("WWW-Authenticate") == 'Basic realm="silverbot", charset="UTF-8"'
        assert "caption" not in body and "generated" not in body
        for name, value in SECURITY_HEADERS.items():
            assert response.getheader(name) == value
            assert len(response.msg.get_all(name)) == 1


@pytest.mark.parametrize(
    "header",
    [
        basic("wrong"),
        basic(""),
        basic("pw ", user="u"),
        "Basic !!!",
        "Basic ",
        "Basic",
        "Bearer x",
        "Bearer " + base64.b64encode(b"u:pw").decode(),
        "Basic " + base64.b64encode(b"nocolon").decode(),
        "Basic " + base64.b64encode(b"\xff\xfe").decode(),
    ],
)
def test_wrong_or_malformed_credentials_get_401(gated, header):
    response, _ = call(gated, auth=header)

    assert response.status == 401
    assert response.getheader("WWW-Authenticate") is not None


def test_correct_password_gets_the_page_with_any_user_name(gated):
    for user in ("anyone", "", "admin"):
        response, body = call(gated, auth=basic("pw", user=user))

        assert response.status == 200
        assert "<caption>MODE &amp; SAFETY</caption>" in body
        assert response.getheader("Content-Security-Policy") == SECURITY_HEADERS["Content-Security-Policy"]


def test_password_with_a_colon_and_non_ascii_round_trips(tmp_path):
    config = make_config(tmp_path)
    instance = DashboardServer(0, root=tmp_path, load=lambda: config, password="p:\u00e9w")
    threading.Thread(target=instance.serve_forever, daemon=True).start()
    try:
        assert call(instance, auth=basic("p:\u00e9w"))[0].status == 200
        assert call(instance, auth=basic("p"))[0].status == 401
    finally:
        instance.shutdown()
        instance.server_close()


def test_fonts_and_404_need_auth_and_then_work(gated):
    font, body = call_raw(gated, "/fonts/IBMPlexMono-Bold.woff2", auth=basic("pw"))
    missing, _ = call(gated, path="/nope", auth=basic("pw"))

    assert font.status == 200 and hashlib.sha256(body).hexdigest() == FONT_SHA256["/fonts/IBMPlexMono-Bold.woff2"]
    assert missing.status == 404
    assert call_raw(gated, "/fonts/IBMPlexMono-Bold.woff2")[0].status == 401


@pytest.mark.parametrize("host", [PUBLIC_HOST, "BOT.UP.RAILWAY.APP", "Bot.Up.Railway.App"])
def test_public_host_is_accepted_with_or_without_port(gated, host):
    port = gated.server_address[1]

    for value in (host, f"{host}:{port}"):
        response, _ = call(gated, host=value, auth=basic("pw"))

        assert response.status == 200


@pytest.mark.parametrize("host", ["evil.example", "bot.up.railway.app.evil.example", "xbot.up.railway.app"])
def test_foreign_host_gets_400_even_with_correct_auth(gated, host):
    assert call(gated, host=host, auth=basic("pw"))[0].status == 400
    assert call(gated, host=host)[0].status == 400


def test_wrong_port_on_the_public_host_gets_400(gated):
    other = gated.server_address[1] + 1

    assert call(gated, host=f"{PUBLIC_HOST}:{other}", auth=basic("pw"))[0].status == 400


def test_loopback_host_headers_still_work_when_gated(gated):
    port = gated.server_address[1]

    assert call(gated, host=f"localhost:{port}", auth=basic("pw"))[0].status == 200
    assert call(gated, host=f"localhost:{port}")[0].status == 401


def test_public_host_is_rejected_when_no_allowed_host_is_set(server):
    assert call(server, host=PUBLIC_HOST)[0].status == 400


def test_post_to_a_gated_server_is_still_405(gated):
    response, _ = call(gated, "POST", auth=basic("pw"))

    assert response.status == 405
    assert response.getheader("Allow") == "GET"


def test_loopback_without_password_needs_no_auth(server):
    assert server.password is None
    assert call(server)[0].status == 200
    assert call_raw(server, "/fonts/IBMPlexMono-Regular.woff2")[0].status == 200
    assert call(server, auth="Bearer garbage")[0].status == 200


def test_page_header_shows_the_bound_host(tmp_path):
    status = collect_status(tmp_path, load=lambda: make_config(tmp_path), now=NOW)

    page = render_page(status, host="0.0.0.0")
    header = page[page.index("<header>") : page.index("</header>")]

    assert "status &middot; read-only &middot; 0.0.0.0" in header
    assert "127.0.0.1" not in header


def test_page_header_escapes_the_host(tmp_path):
    from silver_bot.monitoring.dashboard_server import render_not_found

    status = collect_status(tmp_path, load=lambda: make_config(tmp_path), now=NOW)

    for page in (render_page(status, host="<b>&"), render_not_found("<b>&")):
        assert "&lt;b&gt;&amp;" in page
        assert "<b>" not in page


def test_served_page_header_shows_the_bound_host(tmp_path):
    config = make_config(tmp_path)
    instance = DashboardServer(0, root=tmp_path, load=lambda: config, host="localhost")
    threading.Thread(target=instance.serve_forever, daemon=True).start()
    try:
        _, body = call(instance, host=f"localhost:{instance.server_address[1]}")
        _, missing = call(instance, path="/nope", host=f"localhost:{instance.server_address[1]}")
    finally:
        instance.shutdown()
        instance.server_close()

    assert "read-only &middot; localhost</span>" in body
    assert "read-only &middot; localhost</span>" in missing


def test_main_startup_line_names_the_directory(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    started = []

    def stop(self):
        started.append(True)
        raise KeyboardInterrupt

    monkeypatch.setattr(DashboardServer, "serve_forever", stop)

    assert main(["--port", "0"]) == 0

    assert f"reading {Path.cwd()};" in capsys.readouterr().out
