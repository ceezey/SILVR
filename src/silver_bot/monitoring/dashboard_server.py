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
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
}
CSS = """
:root{--canvas:#000000;--surface:#111827;--border:#374151;--ink:#F9FAFB;--muted:#9CA3AF;
--success:#10B981;--warning:#F59E0B;--danger:#EF4444}
*{box-sizing:border-box}
body{margin:0;background:var(--canvas);color:var(--ink);
font:14px/1.5 ui-monospace,"Cascadia Mono",Menlo,Consolas,monospace}
main{max-width:120ch;margin:0 auto;padding:1ch}
h1,caption{font-size:inherit;font-weight:bold;text-align:left}
h1{margin:0 0 1ch}
.row{display:flex;flex-wrap:wrap;gap:1ch;margin-bottom:1ch}
.banner{position:sticky;top:0;z-index:1;background:var(--canvas)}
section{flex:1 1 38ch;min-width:0;background:var(--surface);border:1px solid var(--border);padding:0 1ch}
table{width:100%;border-collapse:collapse}
th,td{padding:0 1ch 0 0;text-align:left;vertical-align:top;font-weight:normal}
thead th,th[scope=row],footer{color:var(--muted)}
td:last-child{overflow-wrap:anywhere}
td.ok,td.warn,td.err,td.off{white-space:nowrap}
.ok{color:var(--success)}.warn{color:var(--warning)}.err{color:var(--danger)}.off{color:var(--muted)}
"""
PAGE = string.Template(
    """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>silver-bot status</title>
<style>$css</style>
</head>
<body>
<main>
<h1>silver-bot status &middot; read-only &middot; 127.0.0.1</h1>
$panels
<footer>generated $generated_at &middot; read-only; reload to refresh</footer>
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
    return PAGE.substitute(css=CSS, panels="\n".join(groups), generated_at=html.escape(status["generated_at"]))


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
        if self.path != "/":
            self._send(404, "not found\n")
            return
        status = collect_status(self.server.root, load=self.server.load)
        self._send(200, render_page(status), content_type="text/html; charset=utf-8")

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
        body: str,
        *,
        content_type: str = "text/plain; charset=utf-8",
        headers: dict[str, str] | None = None,
    ) -> None:
        payload = body.encode("utf-8")
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
    print(f"silver-bot status: http://{BIND_HOST}:{server.server_address[1]}/ (read-only; Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
