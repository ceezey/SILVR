"""Read-only operator dashboard on 127.0.0.1 (PRD-F13, silverbot-cr-001).

Run with ``python -m silver_bot.monitoring.dashboard_server [--port N]`` from the
project root. The page has no controls and the server answers GET only.
"""

from __future__ import annotations

import html
import string
from typing import Any

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
