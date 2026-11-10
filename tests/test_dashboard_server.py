import base64
import hashlib
import html
import http.client
import json
import os
import re
import socket
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from silvr.config import AppConfig
from silvr.monitoring.dashboard_server import (
    BIND_HOST,
    SECURITY_HEADERS,
    DashboardServer,
    is_loopback_host,
    main,
    render_page,
)
from silvr.monitoring.status import PANEL_TITLES, collect_status

NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
SECRETS = {
    "api_key": "SENTINEL-KEY",
    "api_secret": "SENTINEL-SECRET",
    "telegram_bot_token": "SENTINEL-TOKEN",
    "telegram_chat_id": "SENTINEL-CHAT",
}


def make_config(root: Path, **overrides) -> AppConfig:
    return AppConfig(**overrides)


def write_audit(root: Path, *events: dict) -> None:
    path = root / "logs" / "audit.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(event, sort_keys=True) + "\n" for event in events), encoding="utf-8")


def page_for(root: Path, config: AppConfig | None = None) -> str:
    chosen = config or make_config(root)
    return render_page(collect_status(root, load=lambda: chosen, now=NOW))


def ttl(title: str) -> str:
    """The title span of a panel title row (silvr-cr-004 replaced the table <caption>)."""

    return f'<span class="ttl">{html.escape(title)}</span>'


def test_page_shows_seven_panels_in_layout_order_with_banner_first(tmp_path):
    page = page_for(tmp_path)

    # LAYOUT puts FORWARD TEST (index 6) after EVIDENCE REPORTS and before RISK BUDGET.
    order = (*PANEL_TITLES[:3], PANEL_TITLES[6], *PANEL_TITLES[3:6])
    assert len(PANEL_TITLES) == 7
    positions = [page.index(ttl(title)) for title in order]
    assert positions == sorted(positions)
    positions = [page.index(ttl(title)) for title in PANEL_TITLES[:3]]
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

    assert "<title>SILVR status</title>" in page
    assert "<svg" in header and 'aria-label="SILVR mark"' in header
    assert '<span class="wordmark">SILVR</span>' in header
    assert "Silverbot" not in page
    assert "xmlns" not in page
    assert "status &middot; read-only</span>" in header
    assert "<a " not in header and "<button" not in header


def css_rule(selector: str) -> str:
    from silvr.monitoring.dashboard_server import CSS

    found = re.search(r"(?:^|[}\n])" + re.escape(selector) + r"\{([^}]*)\}", CSS)
    assert found, f"no CSS rule for {selector}"
    return found.group(1).replace("\n", "")


def test_navbar_is_a_sticky_full_width_bar_outside_main(tmp_path):
    rule = css_rule("header")

    assert "position:sticky" in rule and "top:0" in rule and "z-index:" in rule
    assert "height:48px" in rule
    assert "background:var(--surface)" in rule and "border-bottom:1px solid var(--border)" in rule
    page = page_for(tmp_path)
    assert page.index("</header>") < page.index("<main>")


def test_content_spans_the_window_with_gutters():
    from silvr.monitoring.dashboard_server import CSS

    assert "max-width:120ch" not in CSS
    assert "padding:16px 24px 0" in css_rule("main")
    assert "@media (max-width:1279px){main{padding:16px 16px 0}" in CSS


def test_mode_and_safety_is_first_and_inside_the_sidebar(tmp_path):
    page = page_for(tmp_path)

    start = page.index('<aside class="sidebar">')
    end = page.index("</aside>")
    mode = page.index(ttl("MODE & SAFETY"))
    assert start < mode < end
    # Panels 00 to 08: nine title rows, two (00 MODE & SAFETY and 07 HOST) in the sidebar.
    assert page.count('class="ttl"') == 9
    assert page[start:end].count('class="ttl"') == 2
    assert end < page.index('class="ladder"') < page.index('class="next-strip"')
    for title in PANEL_TITLES[1:]:
        other = page.index(ttl(title))
        assert mode < other and end < other


def test_sidebar_is_sticky_below_the_navbar_on_wide_screens():
    from silvr.monitoring.dashboard_server import CSS

    rule = css_rule(".sidebar")

    assert "position:sticky" in rule and "align-self:start" in rule
    assert "top:64px" in rule
    wide = CSS[CSS.index("@media (min-width:1280px)") : CSS.index("@media (max-width:1279px)")]
    assert ".sidebar{position:sticky" in wide.replace("\n", "") and "display:grid" in wide
    assert "clamp(38ch,24vw,44ch)" in wide
    narrow = CSS[CSS.index("@media (max-width:1279px)") : CSS.index("@media (max-width:959px)")].replace("\n", "")
    assert ".sidebar{position:sticky;top:48px;z-index:2;background:var(--canvas)}" in narrow


def test_wide_sidebar_fills_the_height_below_the_navbar():
    from silvr.monitoring.dashboard_server import CSS

    rule = css_rule(".sidebar")
    wide = CSS[CSS.index("@media (min-width:1280px)") : CSS.index("@media (max-width:1279px)")].replace("\n", "")
    narrow = CSS[CSS.index("@media (max-width:1279px)") : CSS.index("@media (max-width:959px)")].replace("\n", "")

    assert "height:calc(100vh - 80px)" in rule and "max-height" not in rule
    assert "overflow-y:auto" in rule
    assert "display:flex" in rule and "flex-direction:column" in rule
    # silvr-cr-004 V-8: the panels hug their content so 07 HOST and the tagline sit right below 00.
    assert ".sidebar .row{flex:0 0 auto;flex-direction:column" in wide
    assert ".sidebar section{flex:0 0 auto;display:flex;flex-direction:column}" in wide
    assert "height:" not in narrow and "display:flex" not in narrow


def test_note_is_a_paragraph_after_the_banner_table_inside_the_sidebar(tmp_path):
    page = page_for(tmp_path)
    text = "settings as loaded by this page, not the state of a running bot (G-3)"
    start = page.index('<aside class="sidebar">')
    end = page.index("</aside>")
    sidebar = page[start:end]

    assert page.count(text) == 1 and text in sidebar
    note = '<p class="note"><span class="label">NOTE</span> ' + html.escape(text) + "</p>"
    assert sidebar.count(note) == 1
    assert sidebar.index("</table>") < sidebar.index(note) < sidebar.index("</section>")
    assert '<th scope="row">NOTE</th>' not in page
    assert "NOTE" not in page[end:]


def test_only_the_banner_panel_gets_the_separate_note():
    from silvr.monitoring.dashboard_server import _render_panel

    panel = {
        "title": "OTHER",
        "rows": [{"label": "NOTE", "state": "plain", "text": "<b>x</b>"}],
    }

    assert 'class="note"' not in _render_panel(panel)
    assert '<th scope="row">NOTE</th>' in _render_panel(panel)
    split = _render_panel(panel, note_last=True)
    assert '<th scope="row">NOTE</th>' not in split
    assert '<p class="note"><span class="label">NOTE</span> &lt;b&gt;x&lt;/b&gt;</p></section>' in split


def test_note_sits_at_the_bottom_of_the_flex_column():
    rule = css_rule(".note")

    assert "margin-top:auto" in rule


def test_root_block_holds_exactly_the_ten_tokens():
    from silvr.monitoring.dashboard_server import CSS

    block = CSS[CSS.index(":root{") + 6 : CSS.index("}", CSS.index(":root{"))]
    tokens = dict(item.split(":", 1) for item in block.replace("\n", "").split(";") if item.strip())

    assert tokens == ROOT_TOKENS
    for name in ROOT_TOKENS:
        assert f"var({name})" in CSS


def test_pages_carry_no_url(tmp_path):
    from silvr.monitoring.dashboard_server import render_not_found

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
    assert (
        '<p class="next-strip"><span class="label">NEXT ▸</span> '
        "run a backtest (runbook-backtest.md steps 5 and 6)</p>"
    ) in page
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
    assert "<title>SILVR &middot; not found</title>" in body
    assert "Silverbot" not in body
    assert body.index("<header>") < body.index("<main>")
    assert '<span class="wordmark">SILVR</span>' in body
    assert "status &middot; read-only</span>" in body


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
    assert ttl("MODE & SAFETY") in body


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
    report = tmp_path / "reports" / "backtest_report.json"
    report.parent.mkdir()
    report.write_text("{}")
    write_audit(tmp_path, {"context": {}, "created_at": "2026-10-09T11:00:00+00:00",
                           "event_type": "bot_started", "level": "INFO", "message": "m"})
    tracked = [report, tmp_path / "logs" / "audit.jsonl"]
    before = {path: (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns) for path in tracked}
    files_before = {path for path in tmp_path.rglob("*")}

    for method in ("GET", "POST", "DELETE"):
        call(server, method)

    after = {path: (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns) for path in tracked}
    assert after == before
    new_files = {path.name for path in tmp_path.rglob("*")} - {path.name for path in files_before}
    assert new_files == set()


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
        assert response.getheader("WWW-Authenticate") == 'Basic realm="silvr", charset="UTF-8"'
        assert 'class="ttl"' not in body and "generated" not in body
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
        assert ttl("MODE & SAFETY") in body
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


def test_main_startup_line_names_the_directory(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    started = []

    def stop(self):
        started.append(True)
        raise KeyboardInterrupt

    monkeypatch.setattr(DashboardServer, "serve_forever", stop)

    assert main(["--port", "0"]) == 0

    assert f"reading {Path.cwd()};" in capsys.readouterr().out


# ---- silvr-cr-004: mission control ---------------------------------------------------------------

STEP_STEMS = ("backtest_report", "out_of_sample_validation_report", "paper_trading_report")
STEP_NAMES = ("Backtest", "Out-of-sample", "Paper", "Demo")


def status_for(root: Path) -> dict:
    config = make_config(root)
    return collect_status(root, load=lambda: config, now=NOW)


def clear_gates(root: Path, count: int) -> None:
    """Make the first ``count`` of the four evidence gates [ OK ], in ladder order."""

    old = (NOW - timedelta(hours=40)).timestamp()
    for stem in STEP_STEMS[: min(count, 3)]:
        write_report(root, stem, "{}", old)
    if count == 4:
        fresh = {"ready": True, "generated_at": (NOW - timedelta(hours=1)).isoformat(), "checks": []}
        write_report(root, "demo_readiness_report", json.dumps(fresh), old)


def rail_kinds(page: str) -> list[str]:
    rail = re.search(r'<div class="rail" aria-hidden="true">(.*?)</div>', page).group(1)
    return re.findall(r'<span class="(s-[a-z]+)"></span>', rail)


@pytest.mark.parametrize("count", [0, 1, 2, 3, 4])
def test_gates_clear_count_line_and_rail(tmp_path, count):
    clear_gates(tmp_path, count)

    page = render_page(status_for(tmp_path))

    assert f'<span class="big">{count}</span><span class="denom"> / 4</span>' in page
    assert '<span class="label muted">EVIDENCE GATES CLEAR</span>' in page
    if count == 4:
        line = "All evidence gates pass. Live trading stays blocked (PRD-F12)."
    else:
        line = f"{count} of 4 evidence gates clear. Next gate: {STEP_NAMES[count]}."
    assert f'<span class="label muted">STATUS</span><p>{line}</p>' in page
    expected = ["s-ok"] * count + (["s-next"] if count < 4 else []) + ["s-todo"] * (3 - count) + ["s-live"]
    assert rail_kinds(page) == expected
    assert "LIVE &middot; blocked (PRD-F12)" in page


def test_live_is_never_counted_or_filled_whatever_a_report_says(tmp_path):
    live = {"ready": True, "generated_at": (NOW - timedelta(hours=1)).isoformat(), "checks": []}
    write_report(tmp_path, "live_readiness_report", json.dumps(live))
    status = status_for(tmp_path)

    page = render_page(status)

    assert '<span class="big">0</span>' in page
    assert rail_kinds(page)[-1] == "s-live" and "s-ok" not in rail_kinds(page)
    status["ladder"]["steps"][4]["state"] = "ok"  # even a forged ok state must not fill or count it
    forged = render_page(status)
    assert rail_kinds(forged)[-1] == "s-live" and '<span class="big">0</span>' in forged
    live_card = re.search(r'<li class="step live">.*?</li>', page).group(0)
    assert "PRD-F12 · stays closed" in live_card and "blocked (PRD-F12)" in live_card
    clear_gates(tmp_path, 4)
    assert '<span class="big">4</span>' in render_page(status_for(tmp_path))


def test_rail_is_decorative_and_cards_carry_the_state(tmp_path):
    clear_gates(tmp_path, 2)

    page = render_page(status_for(tmp_path))

    assert page.count('aria-hidden="true"') == 1
    assert '<div class="rail" aria-hidden="true">' in page
    cards = re.findall(r'<li class="step[^"]*">.*?</li>', page)
    assert len(cards) == 5
    for index, card in enumerate(cards):
        assert f'<span class="idx">{index + 1:02d}</span>' in card
        assert re.search(r"\[ (OK|WRN|ERR|OFF) \]", card)
    assert '<span class="ok">[ OK ]</span>' in cards[0]
    assert "<strong>NEXT</strong>" in cards[2] and cards[2].startswith('<li class="step next">')
    assert page.count("<strong>NEXT</strong>") == 1
    assert "backtest_report" in cards[0] and "demo_readiness_report" in cards[3]


def test_title_rows_run_00_to_08_with_mode_and_safety_first(tmp_path):
    page = page_for(tmp_path)

    titles = re.findall(r'<span class="idx">(\d\d)</span><span class="ttl">(.*?)</span>', page)
    assert titles == [
        ("00", "MODE &amp; SAFETY"),
        ("07", "HOST"),
        ("01", "EVIDENCE LADDER · MISSION TRACK"),
        ("02", "READINESS"),
        ("03", "EVIDENCE REPORTS"),
        ("08", "FORWARD TEST"),
        ("04", "RISK BUDGET"),
        ("05", "POSITIONS / TRADES"),
        ("06", "ALERTS"),
    ]
    sources = re.findall(r'<span class="rule"></span><span class="src">(.*?)</span>', page)
    assert sources == [
        ".env",
        "loopback",
        "reports/",
        "*_readiness_report.json",
        "reports/",
        "reports/trend_ensemble_forward/",
        "risk_state",
        "paper_trades · paper_events",
        "logs/audit.jsonl",
    ]


def test_row_classes_give_readiness_and_alerts_their_fixed_widths(tmp_path):
    from silvr.monitoring.dashboard_server import CSS

    page = page_for(tmp_path)

    assert page.count('<div class="row fix-first">') == 1 and page.count('<div class="row fix-last">') == 1
    wide = CSS[CSS.index("@media (min-width:960px)") : CSS.index("@media (min-width:1280px)")]
    assert ".fix-first>section:first-child{flex:0 0 400px}" in wide
    assert ".fix-last>section:last-child{flex:0 0 440px}" in wide
    stacked = CSS[CSS.index("@media (max-width:959px)") :]
    assert "flex-direction:column" in stacked and "400px" not in stacked and "440px" not in stacked


def test_navbar_telemetry_names_the_bound_host_feeds_and_utc_time(tmp_path):
    status = status_for(tmp_path)

    page = render_page(status, bind=("127.0.0.1", 8765))

    header = page[page.index("<header>") : page.index("</header>")]
    assert '<span class="label muted">HOST</span>127.0.0.1:8765' in header
    assert "reports &middot; risk_state &middot; audit.jsonl" in header
    assert '<span class="label muted">UTC</span>2026-10-09 12:00<' in header
    assert "<a " not in header and "<button" not in header
    assert "HOST</span>127.0.0.1<" in render_page(status)  # no port known: the host only
    assert "[::1]:9" in render_page(status, bind=("::1", 9))


def test_served_page_names_the_actual_port(server):
    port = server.server_address[1]

    _, body = call(server)

    assert f'<span class="label muted">HOST</span>127.0.0.1:{port}' in body
    assert "<td>127.0.0.1 only</td>" in body


def test_host_panel_rows_and_non_loopback_bind(tmp_path):
    status = status_for(tmp_path)

    page = render_page(status, bind=("127.0.0.1", 1))
    host = page[page.index('<section class="host">') : page.index("</section>", page.index('<section class="host">'))]

    for key, value in (
        ("BIND", "127.0.0.1 only"),
        ("ROOT", html.escape(str(tmp_path))),
        ("READ", "2026-10-09 12:00 UTC"),
        ("REFRESH", "reload the page"),
    ):
        assert f'<th scope="row">{key}</th><td>{value}</td>' in host
    hosted = render_page(status, bind=("0.0.0.0", 80))
    assert "<td>0.0.0.0</td>" in hosted and "0.0.0.0 only" not in hosted
    assert '<span class="src">bound host</span>' in hosted


def test_sidebar_holds_mode_readout_host_and_tagline(tmp_path):
    page = page_for(tmp_path)
    sidebar = page[page.index('<aside class="sidebar">') : page.index("</aside>")]

    assert '<span class="label muted">OPERATING MODE</span><span class="mode">PAPER</span>' in sidebar
    assert '<span class="muted">Simulated fills only. No real order exists.</span>' in sidebar
    assert '<th scope="row">MODE</th>' not in sidebar  # the readout replaces the table row
    for key in ("LIVE", "PAPER", "DEMO", "KILL"):
        assert f'<th scope="row">{key}</th>' in sidebar
    assert sidebar.index("OPERATING MODE") < sidebar.index('<th scope="row">LIVE</th>') < sidebar.index("HOST")
    assert '<p class="name">Discipline over id.</p>' in sidebar
    assert '<p class="line">Rules, not impulse, decide every trade.</p>' in sidebar
    assert sidebar.index("Discipline over id.") > sidebar.index("REFRESH")


def test_simulated_line_only_in_paper_mode(tmp_path):
    status = status_for(tmp_path)
    status["panels"][0]["rows"][0]["text"] = "DEMO"

    page = render_page(status)

    assert '<span class="mode">DEMO</span>' in page
    assert "Simulated fills only" not in page


def test_invalid_config_shows_no_mode_readout(tmp_path):
    from silvr.config import ConfigError

    def reject() -> AppConfig:
        raise ConfigError("bad")

    page = render_page(collect_status(tmp_path, load=reject, now=NOW))

    assert "OPERATING MODE" not in page and 'class="mode"' not in page
    assert "config invalid: bad" in page


def restraint_page(tmp_path, restraint: dict) -> str:
    status = status_for(tmp_path)
    status["restraint"] = restraint
    return render_page(status)


def test_restraint_strip_shows_count_reason_and_status_cell(tmp_path):
    text = "Risk engine held 3 setups today. Reason: Max daily loss limit reached."

    page = restraint_page(tmp_path, {"state": "ok", "count": 3, "text": text})

    assert '<span class="label muted">RESTRAINT</span><span><span class="ok">[ OK ]</span> held</span>' in page
    assert f"<span>{text}</span>" in page
    assert page.index('class="restraint"') > page.index(ttl("POSITIONS / TRADES"))


def test_restraint_strip_empty_and_unavailable_states(tmp_path):
    empty = restraint_page(tmp_path, {"state": "ok", "count": 0, "text": "No setups held today."})
    assert "<span>No setups held today.</span>" in empty and "[ OK ]</span> held" in empty

    off = restraint_page(tmp_path, {"state": "off", "count": None, "text": "not available: no database configured (G-3)"})
    assert '<span><span class="off">[ OFF ]</span></span><span>not available: no database configured (G-3)</span>' in off
    assert "held</span>" not in off.split('class="restraint"', 1)[1].split("</div>", 1)[0]


def test_default_page_without_database_shows_restraint_unavailable(tmp_path):
    page = page_for(tmp_path)

    assert "not available: no database configured (G-3)" in page


def test_restraint_text_is_escaped(tmp_path):
    page = restraint_page(tmp_path, {"state": "ok", "count": 1, "text": "<b>x</b> & y"})

    assert "<b>x</b>" not in page and "&lt;b&gt;x&lt;/b&gt; &amp; y" in page


def positions_page(tmp_path, rows: list[dict]) -> str:
    status = status_for(tmp_path)
    status["panels"][4]["rows"] = rows
    return render_page(status)


def test_events_render_as_log_rows_with_sim_tag_and_muted_event_type(tmp_path):
    rows = [
        {"state": "plain", "label": "open positions", "text": "1"},
        {"state": "plain", "label": "SIM 2026-10-09 10:30 UTC", "text": "BTCUSDT long 60000 to 60300, pnl 3.00, take_profit", "event": "closed trade"},
        {
            "state": "plain",
            "label": "SIM 2026-10-09 10:00 UTC",
            "text": "Risk engine held. Setup declined: Max daily loss limit reached.",
            "event": "risk_rejected",
        },
        {"state": "plain", "label": "SIM 2026-10-09 09:00 UTC", "text": "<i>x</i>", "event": "paper_trade_opened"},
    ]

    page = positions_page(tmp_path, rows)

    assert '<th scope="row">open positions</th><td class="plain"></td><td>1</td>' in page
    assert (
        '<li><span class="ts">2026-10-09 10:00 UTC</span><span class="sim">SIM</span>'
        '<span class="text"><span class="ev">risk_rejected</span> '
        "Risk engine held. Setup declined: Max daily loss limit reached.</span></li>"
    ) in page
    assert '<span class="ev">closed trade</span> BTCUSDT long 60000 to 60300' in page
    assert page.count('<span class="sim">SIM</span>') == 3
    assert "<i>x</i>" not in page and "&lt;i&gt;x&lt;/i&gt;" in page
    assert page.index("open positions") < page.index('<ul class="log">')


def test_positions_empty_state_has_no_log_list(tmp_path):
    page = page_for(tmp_path)

    assert "none recorded (no paper run, G-3)" in page
    assert '<ul class="log">' not in page


def risk_rows(day_state: str = "plain", day_text: str = "2026-10-09") -> list[dict]:
    return [
        {"state": day_state, "label": "day", "text": day_text},
        {"state": "plain", "label": "daily realized pnl", "text": "-12.50"},
        {"state": "plain", "label": "trades today", "text": "3"},
        {"state": "plain", "label": "consecutive losses", "text": "2"},
        {"state": "plain", "label": "open positions", "text": "1"},
        {"state": "plain", "label": "updated", "text": "2026-10-09 11:59 UTC"},
        {"state": "plain", "label": "max daily loss", "text": "0.02 of equity"},
        {"state": "plain", "label": "max risk per trade", "text": "0.005 of equity"},
    ]


def risk_page(tmp_path, rows: list[dict]) -> str:
    status = status_for(tmp_path)
    status["panels"][3]["rows"] = rows
    return render_page(status)


def test_risk_budget_is_one_cluster_of_six_readouts_with_limits_below(tmp_path):
    page = risk_page(tmp_path, risk_rows())

    cluster = page[page.index('<div class="cluster">') : page.index('<div class="limits">')]
    labels = re.findall(r'<span class="label muted">(.*?)</span><span class="val">(.*?)</span>', cluster)
    assert labels == [
        ("day", "2026-10-09"),
        ("daily realized pnl", "-12.50"),
        ("trades today", "3"),
        ("consecutive losses", "2"),
        ("open positions", "1"),
        ("updated", "2026-10-09 11:59 UTC"),
    ]
    assert cluster.count('<div class="cell">') == 6
    for state in ("ok", "warn", "err"):
        assert f'class="{state}"' not in cluster  # pnl is never coloured as a score
    limits = page[page.index('<div class="limits">') :].split("</div>", 1)[0]
    assert "LIMITS" in limits and "max daily loss 0.02 of equity" in limits
    assert "max risk per trade 0.005 of equity" in limits
    assert "<table" not in page[page.index(ttl("RISK BUDGET")) : page.index('<div class="limits">')]


def test_stale_risk_day_keeps_its_glyph_and_word_in_the_cell(tmp_path):
    page = risk_page(tmp_path, risk_rows("warn", "2026-10-08; stale: not today (2026-10-09 UTC)"))

    assert '<span class="val">2026-10-08</span>' in page
    assert '<span class="warn">[ WRN ]</span> stale: not today (2026-10-09 UTC)' in page


def test_risk_unavailable_state_replaces_the_cluster(tmp_path):
    page = page_for(tmp_path)

    assert 'class="cluster"' not in page and 'class="limits"' not in page
    assert '<td class="off">[ OFF ]</td><td>not available: risk_state empty, no running bot (G-3)</td>' in page


def test_pages_have_no_external_reference_or_script(tmp_path):
    from silvr.monitoring.dashboard_server import CSS

    page = page_for(tmp_path)

    for needle in ("http", "//", "<script", "<link", "<img", "@import", "<iframe", "<form", "<button"):
        assert needle not in page.replace("</", "")  # closing tags carry "/", never "//"
    assert re.findall(r'url\("([^"]+)"\)', CSS) == list(FONT_SHA256)


def test_css_grid_brackets_and_type_sizes_follow_the_record():
    from silvr.monitoring.dashboard_server import CSS

    assert "linear-gradient(to right,rgba(42,47,56,.18) 1px,transparent 1px)" in CSS
    assert "linear-gradient(to bottom,rgba(42,47,56,.18) 1px,transparent 1px)" in CSS
    assert "background-size:48px 48px" in CSS
    section = css_rule("section")
    assert "background:var(--surface)" in section and "border:1px solid var(--border)" in section
    assert "border-radius:4px" in section and "padding:16px" in section
    brackets = css_rule("section::before")
    assert brackets.count("linear-gradient(var(--muted),var(--muted))") == 8
    assert "10px 1.5px" in brackets and "1.5px 10px" in brackets
    sizes = {int(size) for size in re.findall(r"font-size:(\d+)px", CSS)}
    assert sizes <= {10, 11, 12, 14, 22, 32, 40}
    assert {10, 11, 22, 40} <= sizes
    for forbidden in ("transition", "animation", "@keyframes", "box-shadow", "blur(", "radial-gradient", "backdrop"):
        assert forbidden not in CSS
    assert css_rule(".mode").count("font-size:40px") == 1 and css_rule(".big").count("font-size:40px") == 1


def test_stacked_layout_keeps_the_cr_003_rules_and_shrinks_the_readouts():
    from silvr.monitoring.dashboard_server import CSS

    narrow = CSS[CSS.index("@media (max-width:1279px)") : CSS.index("@media (max-width:959px)")].replace("\n", "")
    stacked = CSS[CSS.index("@media (max-width:959px)") : CSS.index("@media (max-width:639px)")].replace("\n", "")

    assert ".sidebar{position:sticky;top:48px;z-index:2;background:var(--canvas)}" in narrow
    assert "height:" not in narrow  # the pinned strip keeps its natural height
    assert ".row{flex-direction:column}section{flex:1 1 auto;width:100%}" in stacked
    assert ".big,.mode{font-size:32px}" in stacked


def test_new_markup_never_adds_a_control_or_state_changing_route(server):
    port = server.server_address[1]
    response, body = call(server)

    assert response.status == 200
    assert "<form" not in body and "<input" not in body and "<button" not in body and "<a " not in body
    assert call(server, "POST")[0].status == 405
    assert call(server, path="/mission")[0].status == 404
    assert response.getheader("Content-Security-Policy") == SECURITY_HEADERS["Content-Security-Policy"]
    assert f":{port}" in body


FORWARD_NOTE = "Progress only. No verdict until 2027-11-10. Do not change the strategy because of this number."


def write_progress(root: Path, **overrides) -> Path:
    data = {
        "kind": "forward_progress",
        "status": "running",
        "reason": None,
        "through": "2026-11-30T23:59:00+00:00",
        "days_done": 20,
        "net": 123.4,
        "max_drawdown": 45.5,
        "weekly_average": 41.25,
        "weekly_target": 50.0,
        "losing_week_share": 0.25,
        "trades": 12,
        "kill_switch_trips": 0,
        "data_gaps": [],
        "note": FORWARD_NOTE,
        **overrides,
    }
    path = root / "reports" / "trend_ensemble_forward" / "forward_progress.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def forward_section(page: str) -> str:
    start = page.index(ttl("FORWARD TEST"))
    return page[page.rindex("<section>", 0, start) : page.index("</section>", start)]


def test_forward_test_panel_renders_after_evidence_and_before_risk(tmp_path):
    write_progress(tmp_path)

    page = page_for(tmp_path)

    evidence = page.index(ttl("EVIDENCE REPORTS"))
    forward = page.index(ttl("FORWARD TEST"))
    risk = page.index(ttl("RISK BUDGET"))
    assert evidence < forward < risk
    # its own full-width row: one section, between the evidence row and the risk row
    row_start = page.rindex('<div class="row">', 0, forward)
    assert page.count("<section", row_start, forward) == 1
    assert evidence < row_start < forward < risk


def test_forward_test_panel_markup_and_values(tmp_path):
    write_progress(tmp_path)

    section = forward_section(page_for(tmp_path))

    assert '<span class="idx">08</span>' in section
    assert '<span class="src">reports/trend_ensemble_forward/</span>' in section
    assert '<th scope="col">ITEM</th><th scope="col">STATE</th><th scope="col">DETAIL</th>' in section
    assert '<th scope="row">status</th><td class="ok">[ OK ]</td><td>running</td>' in section
    assert "<td>2026-11-11 to 2026-11-30, 20 / 365 days</td>" in section
    assert "<td>$41.25 vs $50 target</td>" in section
    assert f'<p class="note"><span class="label">NOTE</span> {FORWARD_NOTE}</p>' in section
    assert '<th scope="row">NOTE</th>' not in section  # the note follows the table, not inside it


def test_forward_test_panel_states_carry_glyph_and_word(tmp_path):
    write_progress(tmp_path, status="verdict FAIL")
    failed = forward_section(page_for(tmp_path))
    write_progress(tmp_path, status="incomplete data")
    gap = forward_section(page_for(tmp_path))

    assert '<td class="err">[ ERR ]</td><td>verdict FAIL</td>' in failed
    assert '<td class="warn">[ WRN ]</td><td>incomplete data</td>' in gap


def test_forward_test_panel_before_the_first_run_says_not_started(tmp_path):
    section = forward_section(page_for(tmp_path))

    assert '<td class="off">[ OFF ]</td>' in section
    assert "not started: no forward_progress.json yet" in section
    assert "No verdict until" not in section


def test_forward_test_note_reads_the_stored_status_once_decided(tmp_path):
    write_progress(tmp_path, status="verdict PASS")

    section = forward_section(page_for(tmp_path))

    assert '<p class="note"><span class="label">NOTE</span> verdict PASS</p>' in section
    assert "No verdict until" not in section


def test_forward_test_panel_unreadable_file_does_not_blank_the_page(tmp_path):
    (tmp_path / "reports" / "trend_ensemble_forward" / "forward_progress.json").mkdir(parents=True)

    page = page_for(tmp_path)

    assert "degraded: 1 panel unreadable" in page
    for title in PANEL_TITLES:
        assert ttl(title) in page
    assert "[ ERR ]" in forward_section(page)
    assert page.count('<li class="step') == 5


def test_forward_test_panel_escapes_stored_text(tmp_path):
    write_progress(tmp_path, status="error", reason="<script>alert(1)</script>", note="<b>n</b>", data_gaps=["<i>x</i>"])

    page = page_for(tmp_path)

    assert "<script" not in page and "<b>n</b>" not in page and "<i>x</i>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in forward_section(page)
    assert "&lt;i&gt;x&lt;/i&gt;" in forward_section(page)


def test_forward_test_panel_adds_no_route_control_or_script(server, tmp_path):
    write_progress(tmp_path)

    response, body = call(server)

    assert response.status == 200
    section = forward_section(body)
    assert "<script" not in body and "<form" not in section and "<button" not in section and "<a " not in section
    assert call(server, "POST")[0].status == 405
    assert call(server, path="/reports/trend_ensemble_forward/forward_progress.json")[0].status == 404
