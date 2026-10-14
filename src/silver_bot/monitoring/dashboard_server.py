"""Read-only operator dashboard on 127.0.0.1 (PRD-F13, silverbot-cr-001).

Run with ``python -m silver_bot.monitoring.dashboard_server [--port N]`` from the
project root. The page has no controls and the server answers GET only.
"""

from __future__ import annotations

import argparse
import html
import string
import sys
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import Any

from silver_bot.config import AppConfig, load_config
from silver_bot.monitoring.status import collect_status

BIND_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
TAGS = {"ok": "[ OK ]", "warn": "[ WRN ]", "err": "[ ERR ]", "off": "[ OFF ]", "plain": ""}
# DSD section 3.2: banner; readiness | evidence; risk budget; positions | alerts.
LAYOUT: tuple[tuple[int, ...], ...] = ((0,), (1, 2), (3,), (4, 5))
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; font-src 'self'",
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
}
HTML_TYPE = "text/html; charset=utf-8"
FONTS = {
    "/fonts/IBMPlexMono-Regular.woff2": "IBMPlexMono-Regular.woff2",
    "/fonts/IBMPlexMono-Bold.woff2": "IBMPlexMono-Bold.woff2",
}
CSS = """
@font-face{font-family:"IBM Plex Mono";src:url("/fonts/IBMPlexMono-Regular.woff2") format("woff2");
font-weight:400;font-style:normal;font-display:swap}
@font-face{font-family:"IBM Plex Mono";src:url("/fonts/IBMPlexMono-Bold.woff2") format("woff2");
font-weight:700;font-style:normal;font-display:swap}
:root{--canvas:#0B0D10;--surface:#13161B;--border:#2A2F38;--ink:#E8EAED;--muted:#9AA1AC;
--brand:#C3C9D2;--accent:#7AA2F7;--success:#3FB68B;--warning:#E3B341;--danger:#F0616D}
*{box-sizing:border-box}
body{margin:0;background:var(--canvas);color:var(--ink);
font:12px/24px "IBM Plex Mono",ui-monospace,"Cascadia Mono",Menlo,Consolas,monospace}
main{max-width:120ch;margin:0 auto;padding:0 24px}
a{color:var(--accent)}
header{display:flex;align-items:center;gap:16px;height:48px}
.wordmark{font-size:14px;font-weight:700;color:var(--brand)}
.meta{color:var(--muted)}
.m-brand{fill:var(--brand)}.m-head{fill:var(--surface);stroke:var(--brand);stroke-width:3}
.m-canvas{fill:var(--canvas)}.m-ink{fill:var(--ink);opacity:.75}
.m-ok{fill:var(--success);opacity:.28}.m-err{fill:var(--danger);opacity:.38}
caption,.label{font-size:10px;font-weight:700;text-transform:uppercase;text-align:left}
.row{display:flex;flex-wrap:wrap;gap:16px;margin-bottom:16px}
.banner{position:sticky;top:0;z-index:1;background:var(--canvas)}
section{flex:1 1 38ch;min-width:0;background:var(--surface);border:1px solid var(--border);
border-radius:4px;padding:0 16px}
table{width:100%;border-collapse:collapse}
th,td{padding:0 1ch 0 0;text-align:left;vertical-align:top;font-weight:normal}
thead th,th[scope=row],footer{color:var(--muted)}
thead th,td:last-child{font-size:11px}
td:last-child{overflow-wrap:anywhere}
td.ok,td.warn,td.err,td.off{white-space:nowrap}
.ladder ol{display:flex;flex-wrap:wrap;gap:8px;list-style:none;margin:0;padding:0 0 16px}
.step{flex:1 1 18ch;background:var(--canvas);border:1px solid var(--border);border-radius:3px;padding:0 8px}
.step.next{border-color:var(--accent);outline:1px solid var(--accent)}
.step strong{font-size:10px;color:var(--accent)}
.degraded,.next-strip{margin:0 0 16px}
.next-strip{color:var(--accent)}
.ok{color:var(--success)}.warn{color:var(--warning)}.err{color:var(--danger)}.off{color:var(--muted)}
@media (max-width:1279px){main{padding:0 16px}}
@media (max-width:959px){.row{flex-direction:column}section{flex:1 1 auto;width:100%}}
"""
# One header for every HTML page: the S-tier mark (DSD 2.4), wordmark and context.
HEADER = (
    '<header><svg viewBox="0 0 160 160" width="28" height="28" role="img" aria-label="Silverbot mark">'
    '<rect class="m-brand" x="40" y="0" width="5" height="16" rx="2"/>'
    '<rect class="m-brand" x="115" y="0" width="5" height="16" rx="2"/>'
    '<rect class="m-head" x="1.5" y="15.5" width="157" height="141" rx="12"/>'
    '<rect class="m-canvas" x="14" y="28" width="132" height="76" rx="6"/>'
    '<rect class="m-ok" x="84" y="39" width="56" height="36"/>'
    '<rect class="m-err" x="84" y="77" width="56" height="12"/>'
    '<rect class="m-ink" x="20" y="75" width="120" height="2"/>'
    "</svg>"
    '<span class="wordmark">Silverbot</span>'
    '<span class="meta">status &middot; read-only &middot; 127.0.0.1</span></header>'
)
NOT_FOUND_PAGE = string.Template(
    """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Silverbot &middot; not found</title>
<style>$css</style>
</head>
<body>
<main>
$header
<p>not found</p>
<p><a href="/">back to the status page</a></p>
</main>
</body>
</html>
"""
)
PAGE = string.Template(
    """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Silverbot status</title>
<style>$css</style>
</head>
<body>
<main>
$header
$banner
$degraded$ladder
$strip$panels
<footer>generated $generated_at &middot; read-only; reading $root &middot; reload to refresh</footer>
</main>
</body>
</html>
"""
)


def render_page(status: dict[str, Any]) -> str:
    """Render the status dict as one self-contained, escaped HTML page."""

    panels = status["panels"]
    groups = []
    for group in LAYOUT:
        css_class = "row banner" if group == LAYOUT[0] else "row"
        sections = "".join(_render_panel(panels[index]) for index in group)
        groups.append(f'<div class="{css_class}">{sections}</div>')
    count = int(status.get("degraded", 0))
    degraded = ""
    if count > 0:
        noun = "panel" if count == 1 else "panels"
        degraded = (
            f'<p class="degraded"><span class="warn">{TAGS["warn"]}</span> '
            f"degraded: {count} {noun} unreadable</p>\n"
        )
    ladder = status["ladder"]
    next_text = ladder["next_text"]
    strip = f'<p class="next-strip">{html.escape(next_text)}</p>\n' if next_text else ""
    return PAGE.substitute(
        css=CSS,
        header=HEADER,
        banner=groups[0],
        degraded=degraded,
        ladder=_render_ladder(ladder),
        strip=strip,
        panels="\n".join(groups[1:]),
        generated_at=html.escape(status["generated_at"]),
        root=html.escape(status["root"]),
    )


def render_not_found() -> str:
    """Render the branded 404 page: no status data and no collection."""

    return NOT_FOUND_PAGE.substitute(css=CSS, header=HEADER)


def _render_ladder(ladder: dict[str, Any]) -> str:
    cards = []
    for index, step in enumerate(ladder["steps"]):
        is_next = ladder["next"] == index
        marker = " <strong>NEXT</strong>" if is_next else ""
        cards.append(
            f'<li class="step{" next" if is_next else ""}">{index + 1} '
            f'<span class="label">{html.escape(step["label"])}</span> <span class="{step["state"]}">{TAGS[step["state"]]}</span> '
            f'{html.escape(step["text"])}{marker}</li>'
        )
    return (
        '<section class="ladder"><div class="label">EVIDENCE LADDER</div>'
        f"<ol>{''.join(cards)}</ol></section>"
    )


def _render_panel(panel: dict[str, Any]) -> str:
    body = "".join(
        f'<tr><th scope="row">{html.escape(item["label"])}</th>'
        f'<td class="{item["state"]}">{TAGS[item["state"]]}</td>'
        f'<td>{html.escape(item["text"])}</td></tr>'
        for item in panel["rows"]
    )
    return (
        f'<section><table><caption>{html.escape(panel["title"])}</caption>'
        '<thead><tr><th scope="col">item</th><th scope="col">state</th><th scope="col">detail</th></tr></thead>'
        f"<tbody>{body}</tbody></table></section>"
    )


class DashboardServer(ThreadingHTTPServer):
    """HTTP server fixed to 127.0.0.1 that serves the status page."""

    daemon_threads = True
    # On Windows SO_REUSEADDR lets a second socket share a busy port; refuse that.
    allow_reuse_address = sys.platform != "win32"

    def __init__(self, port: int, *, root: Path, load: Callable[[], AppConfig] = load_config) -> None:
        self.root = Path(root)
        self.load = load
        super().__init__((BIND_HOST, port), DashboardHandler)


class DashboardHandler(BaseHTTPRequestHandler):
    """Answer GET / with the page; refuse every other method, path and host."""

    server: DashboardServer
    server_version = "silver-bot-dashboard"
    sys_version = ""
    # Not HTTP/0.9: that mode drops the status line and headers from error replies.
    default_request_version = "HTTP/1.0"

    def parse_request(self) -> bool:
        if not super().parse_request():
            return False
        if self.command != "GET":
            self._send(405, "method not allowed\n", headers={"Allow": "GET"})
            return False
        return True

    def do_GET(self) -> None:
        if not self._host_allowed():
            self._send(400, "bad host\n")
            return
        if self.path == "/":
            status = collect_status(self.server.root, load=self.server.load)
            self._send(200, render_page(status), content_type=HTML_TYPE)
        elif self.path in FONTS:
            font = files("silver_bot.monitoring").joinpath("fonts", FONTS[self.path]).read_bytes()
            self._send(200, font, content_type="font/woff2")
        else:
            self._send(404, render_not_found(), content_type=HTML_TYPE)

    def end_headers(self) -> None:
        # Every response, including send_error ones, carries the security headers.
        for name, value in SECURITY_HEADERS.items():
            self.send_header(name, value)
        super().end_headers()

    def _host_allowed(self) -> bool:
        port = self.server.server_address[1]
        names = {"127.0.0.1", "localhost"}
        allowed = {f"{name}:{port}" for name in names} | (names if port == 80 else set())
        return self.headers.get("Host", "") in allowed

    def _send(
        self,
        code: int,
        body: bytes | str,
        *,
        content_type: str = "text/plain; charset=utf-8",
        headers: dict[str, str] | None = None,
    ) -> None:
        payload = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        for name, value in {
            "Content-Type": content_type,
            "Content-Length": str(len(payload)),
            **(headers or {}),
        }.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(payload)


def main(argv: list[str] | None = None) -> int:
    """Serve the read-only status page until interrupted."""

    parser = argparse.ArgumentParser(
        prog="python -m silver_bot.monitoring.dashboard_server",
        description="Read-only Silver Bot status page on 127.0.0.1.",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"port on 127.0.0.1 (default {DEFAULT_PORT})")
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        print(f"invalid port: {args.port}", file=sys.stderr)
        return 2
    try:
        server = DashboardServer(args.port, root=Path.cwd())
    except OSError as exc:
        print(f"cannot listen on {BIND_HOST}:{args.port}: {exc.strerror or exc}", file=sys.stderr)
        return 2
    print(
        f"silver-bot status: http://{BIND_HOST}:{server.server_address[1]}/ "
        f"(read-only; reading {server.root}; Ctrl+C to stop)"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
