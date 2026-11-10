"""Read-only operator dashboard (PRD-F13, silvr-cr-001 to silvr-cr-004).

Run with ``python -m silvr.monitoring.dashboard_server [--port N]`` from the
project root. It binds 127.0.0.1 by default. The page has no controls and the
server answers GET only.

Hosted mode (owner decision 2026-10-24): ``--host 0.0.0.0
--allowed-host <public domain>`` with the ``DASHBOARD_PASSWORD`` environment
variable set. The server speaks plain HTTP, so only expose it behind HTTPS. A
non-loopback bind without a password is refused, and every GET then needs HTTP
Basic auth.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hmac
import html
import ipaddress
import os
import string
import sys
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import Any

from silvr.config import AppConfig, load_config
from silvr.monitoring.status import ALL_GATES_PASS, STRATEGY_REPORTS, collect_status

BIND_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
PASSWORD_ENV = "DASHBOARD_PASSWORD"
AUTH_CHALLENGE = 'Basic realm="silvr", charset="UTF-8"'
TAGS = {"ok": "[ OK ]", "warn": "[ WRN ]", "err": "[ ERR ]", "off": "[ OFF ]", "plain": ""}
# DSD section 3.2: banner; readiness | evidence; risk budget; positions | alerts.
LAYOUT: tuple[tuple[int, ...], ...] = ((0,), (1, 2), (3,), (4, 5))
# Panel number and data source shown in each panel title row (silvr-cr-004); 01 is the ladder, 07 the host.
PANEL_META: tuple[tuple[int, str], ...] = (
    (0, ".env"),
    (2, "*_readiness_report.json"),
    (3, "reports/"),
    (4, "risk_state"),
    (5, "paper_trades · paper_events"),
    (6, "logs/audit.jsonl"),
)
ROW_CLASSES = {(1, 2): "row fix-first", (4, 5): "row fix-last"}
RISK_LABELS = ("day", "daily realized pnl", "trades today", "consecutive losses", "open positions", "updated")
PAPER_LINE = "Simulated fills only. No real order exists."
# Detail line under each ladder card: the report that feeds the step.
STEP_DETAILS = (*STRATEGY_REPORTS, "demo_readiness_report", "PRD-F12 · stays closed")
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
body{margin:0;background-color:var(--canvas);
background-image:linear-gradient(to right,rgba(42,47,56,.18) 1px,transparent 1px),
linear-gradient(to bottom,rgba(42,47,56,.18) 1px,transparent 1px);background-size:48px 48px;
color:var(--ink);font:12px/24px "IBM Plex Mono",ui-monospace,"Cascadia Mono",Menlo,Consolas,monospace}
main{padding:16px 24px 0}
a{color:var(--accent)}
header{position:sticky;top:0;z-index:3;display:flex;align-items:center;gap:16px;height:48px;padding:0 24px;
background:var(--surface);border-bottom:1px solid var(--border)}
.wordmark{font-size:14px;font-weight:700;color:var(--brand)}
.meta{color:var(--muted)}
.tele{display:flex;align-items:center;margin-left:auto;line-height:16px}
.tele>span+span{margin-left:16px;padding-left:16px;border-left:1px solid var(--border)}
.tele .label{margin-right:8px}
.m-brand{fill:var(--brand)}.m-head{fill:var(--surface);stroke:var(--brand);stroke-width:3}
.m-canvas{fill:var(--canvas)}.m-ink{fill:var(--ink);opacity:.75}
.m-ok{fill:var(--success);opacity:.28}.m-err{fill:var(--danger);opacity:.38}
.label,thead th{font-size:10px;font-weight:700;text-transform:uppercase;text-align:left}
.muted{color:var(--muted)}
.row{display:flex;flex-wrap:wrap;gap:16px;margin-bottom:16px}
section{position:relative;flex:1 1 38ch;min-width:0;background:var(--surface);border:1px solid var(--border);
border-radius:4px;padding:16px}
section::before{content:"";position:absolute;inset:0;pointer-events:none;background-repeat:no-repeat;
background-image:linear-gradient(var(--muted),var(--muted)),linear-gradient(var(--muted),var(--muted)),
linear-gradient(var(--muted),var(--muted)),linear-gradient(var(--muted),var(--muted)),
linear-gradient(var(--muted),var(--muted)),linear-gradient(var(--muted),var(--muted)),
linear-gradient(var(--muted),var(--muted)),linear-gradient(var(--muted),var(--muted));
background-position:left top,left top,right top,right top,left bottom,left bottom,right bottom,right bottom;
background-size:10px 1.5px,1.5px 10px,10px 1.5px,1.5px 10px,10px 1.5px,1.5px 10px,10px 1.5px,1.5px 10px}
.ptitle{display:flex;align-items:center;gap:8px;margin:0 0 8px;font-size:10px;font-weight:700;
text-transform:uppercase;letter-spacing:.08em;line-height:24px}
.ptitle .idx,.ptitle .src{color:var(--muted)}
.ptitle .src{font-weight:400;letter-spacing:0;text-transform:none;white-space:nowrap}
.ptitle .rule{flex:1 1 auto;height:1px;background:var(--border)}
.hair{height:1px;margin:8px 0;background:var(--border)}
table{width:100%;border-collapse:collapse}
th,td{padding:0 1ch 0 0;text-align:left;vertical-align:top;font-weight:normal}
thead th,th[scope=row],footer{color:var(--muted)}
thead th{border-bottom:1px solid var(--border)}
td:last-child{font-size:11px;overflow-wrap:anywhere}
td.ok,td.warn,td.err,td.off,th[scope=row]{white-space:nowrap}
.readout>span{display:block}
.mode{font-size:40px;font-weight:700;line-height:48px}
.top{display:flex;flex-wrap:wrap;gap:8px 32px;align-items:flex-start;margin:0 0 16px}
.top>div{min-width:0}
.top .status{flex:1 1 24ch}
.top .label,.top p{display:block;margin:0}
.big{font-size:40px;font-weight:700;line-height:48px}
.denom{font-size:22px;font-weight:700;color:var(--muted)}
.rail{display:flex;gap:4px;margin:0 0 8px}
.rail span{flex:1 1 0;height:4px;background:var(--border)}
.rail .s-ok{background:var(--success)}.rail .s-next{background:var(--accent)}
.rail .s-live{height:0;margin-top:2px;background:none;border-top:1px dashed var(--muted)}
.ladder{margin-bottom:16px}
.ladder ol{display:flex;flex-wrap:wrap;gap:8px;list-style:none;margin:0 0 16px;padding:0}
.step{flex:1 1 18ch;min-width:0;background:var(--canvas);border:1px solid var(--border);border-radius:3px;padding:8px}
.step.next{border-color:var(--accent)}
.step.live{border-style:dashed}
.step>span{display:block;overflow-wrap:anywhere}
.step .head{display:flex;align-items:center;gap:8px}
.step .idx{font-size:10px;font-weight:700;color:var(--muted)}
.step strong{margin-left:auto;font-size:10px;color:var(--accent)}
.step .detail{font-size:11px;color:var(--muted)}
.mk{display:inline-block;width:8px;height:8px}
.mk.s-ok{background:var(--success)}.mk.s-next{border:1px solid var(--accent)}.mk.s-todo{border:1px solid var(--muted)}
.next-strip{margin:0;padding:0 8px;border:1px solid var(--accent);border-radius:3px;color:var(--accent)}
.restraint{display:flex;flex-wrap:wrap;align-items:baseline;gap:0 16px;margin:0 0 8px;padding:0 8px;
background:var(--canvas);border:1px solid var(--border);border-radius:3px}
.cluster{display:flex;flex-wrap:wrap;margin:0 0 8px}
.cell{flex:1 1 auto;min-width:0;padding:0 16px;border-left:1px solid var(--border)}
.cell:first-child{padding-left:0;border-left:0}
.cell>span{display:block;overflow-wrap:anywhere}
.cell .val{font-size:22px;font-weight:700;line-height:32px}
.cell .detail{font-size:11px}
.limits{padding-top:8px;border-top:1px solid var(--border);font-size:11px;color:var(--muted)}
.log{list-style:none;margin:0;padding:0}
.log li{display:flex;gap:8px;align-items:baseline}
.log .ts,.log .ev{font-size:11px;color:var(--muted)}
.log .ts{flex:0 0 auto;white-space:nowrap}
.log .text{flex:1 1 0;min-width:0;overflow-wrap:anywhere}
.sim{flex:0 0 auto;padding:0 4px;border:1px solid var(--muted);border-radius:3px;font-size:10px;font-weight:700;
line-height:14px;color:var(--muted)}
.tagline{margin-top:16px}
.tagline p{margin:0}
.tagline .name{font-weight:700}
.tagline .line{font-size:11px;color:var(--muted)}
.note{margin:0;margin-top:auto;color:var(--muted);font-size:11px;overflow-wrap:anywhere}
.degraded{margin:0 0 16px}
.ok{color:var(--success)}.warn{color:var(--warning)}.err{color:var(--danger)}.off{color:var(--muted)}
@media (min-width:960px){.fix-first>section:first-child{flex:0 0 400px}
.fix-last>section:last-child{flex:0 0 440px}}
@media (min-width:1280px){.layout{display:grid;grid-template-columns:clamp(38ch,24vw,44ch) minmax(0,1fr);
gap:16px;align-items:start}
.sidebar{position:sticky;top:64px;align-self:start;height:calc(100vh - 80px);overflow-y:auto;
display:flex;flex-direction:column}
.sidebar .row{flex:0 0 auto;flex-direction:column;margin-bottom:0}
.sidebar section{flex:0 0 auto;display:flex;flex-direction:column}}
@media (max-width:1279px){main{padding:16px 16px 0}header{padding:0 16px}
.sidebar{position:sticky;top:48px;z-index:2;background:var(--canvas)}
.sidebar .host,.sidebar .tagline,.tele .feed{display:none}}
@media (max-width:959px){.row{flex-direction:column}section{flex:1 1 auto;width:100%}
.big,.mode{font-size:32px}}
@media (max-width:639px){.tele .host,.meta{display:none}}
"""
# One sticky navbar for every HTML page: the S-tier mark (DSD 2.4), wordmark and context.
HEADER_START = (
    '<header><svg viewBox="0 0 160 160" width="28" height="28" role="img" aria-label="SILVR mark">'
    '<rect class="m-brand" x="40" y="0" width="5" height="16" rx="2"/>'
    '<rect class="m-brand" x="115" y="0" width="5" height="16" rx="2"/>'
    '<rect class="m-head" x="1.5" y="15.5" width="157" height="141" rx="12"/>'
    '<rect class="m-canvas" x="14" y="28" width="132" height="76" rx="6"/>'
    '<rect class="m-ok" x="84" y="39" width="56" height="36"/>'
    '<rect class="m-err" x="84" y="77" width="56" height="12"/>'
    '<rect class="m-ink" x="20" y="75" width="120" height="2"/>'
    "</svg>"
    '<span class="wordmark">SILVR</span>'
    '<span class="meta">status &middot; read-only</span>'
)
HEADER = HEADER_START + "</header>"
NOT_FOUND_PAGE = string.Template(
    """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SILVR &middot; not found</title>
<style>$css</style>
</head>
<body>
$header
<main>
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
<title>SILVR status</title>
<style>$css</style>
</head>
<body>
$header
<main>
<div class="layout">
<aside class="sidebar">
$banner
</aside>
<div class="content">
$degraded$ladder
$panels
</div>
</div>
<footer>generated $generated_at &middot; read-only; reading $root &middot; reload to refresh</footer>
</main>
</body>
</html>
"""
)


def render_page(status: dict[str, Any], *, bind: tuple[str, int | None] | None = None) -> str:
    """Render the status dict as one self-contained, escaped HTML page.

    ``bind`` is the (host, port) the server is bound to; without it the navbar names the default host only.
    """

    host, port = bind or (BIND_HOST, None)
    panels = status["panels"]
    restraint = status["restraint"]
    rendered = [_render_status_panel(index, panel, restraint) for index, panel in enumerate(panels)]
    groups = []
    for group in LAYOUT:
        css_class = "row banner" if group == LAYOUT[0] else ROW_CLASSES.get(group, "row")
        sections = "".join(rendered[index] for index in group)
        if group == LAYOUT[0]:
            sections += _render_host(status, host)
        groups.append(f'<div class="{css_class}">{sections}</div>')
    count = int(status.get("degraded", 0))
    degraded = ""
    if count > 0:
        noun = "panel" if count == 1 else "panels"
        degraded = (
            f'<p class="degraded"><span class="warn">{TAGS["warn"]}</span> '
            f"degraded: {count} {noun} unreadable</p>\n"
        )
    return PAGE.substitute(
        css=CSS,
        header=_header(_telemetry(status["generated_at"], host, port)),
        banner=groups[0] + _TAGLINE,
        degraded=degraded,
        ladder=_render_ladder(status["ladder"]),
        panels="\n".join(groups[1:]),
        generated_at=html.escape(status["generated_at"]),
        root=html.escape(status["root"]),
    )


def render_not_found() -> str:
    """Render the branded 404 page: no status data and no collection."""

    return NOT_FOUND_PAGE.substitute(css=CSS, header=HEADER)


def is_loopback_host(host: str) -> bool:
    """True for "localhost" and loopback IPs; anything unparsable counts as non-loopback."""

    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


_TAGLINE = (
    '<div class="tagline"><p class="name">Discipline over id.</p>'
    '<p class="line">Rules, not impulse, decide every trade.</p></div>'
)


def _header(telemetry: str = "") -> str:
    return HEADER_START + telemetry + "</header>"


def _telemetry(generated_at: str, host: str, port: int | None) -> str:
    """Plain-text strip on the right of the navbar: bound host, data feeds, read time (UTC)."""

    shown = f"[{host}]" if ":" in host else host
    address = shown if port is None else f"{shown}:{port}"
    moment = generated_at.removesuffix(" UTC")
    return (
        '<div class="tele">'
        f'<span class="host"><span class="label muted">HOST</span>{html.escape(address)}</span>'
        '<span class="feed"><span class="label muted">FEED</span>'
        "reports &middot; risk_state &middot; audit.jsonl</span>"
        f'<span class="utc"><span class="label muted">UTC</span>{html.escape(moment)}</span>'
        "</div>"
    )


def _title(number: int | None, title: str, source: str = "") -> str:
    """Panel title row: muted index, bold title, a hairline, then the data source at the far right."""

    index = f'<span class="idx">{number:02d}</span>' if number is not None else ""
    origin = f'<span class="src">{html.escape(source)}</span>' if source else ""
    return (
        f'<h2 class="ptitle">{index}<span class="ttl">{html.escape(title)}</span>'
        f'<span class="rule"></span>{origin}</h2>'
    )


def _render_host(status: dict[str, Any], host: str) -> str:
    """Panel 07: where the page is served from and what it read (all values already known to the server)."""

    loopback = is_loopback_host(host)
    rows = (
        ("BIND", f"{host} only" if loopback else host),
        ("ROOT", status["root"]),
        ("READ", status["generated_at"]),
        ("REFRESH", "reload the page"),
    )
    body = "".join(f'<tr><th scope="row">{key}</th><td>{html.escape(value)}</td></tr>' for key, value in rows)
    source = "loopback" if loopback else "bound host"
    return f'<section class="host">{_title(7, "HOST", source)}<table><tbody>{body}</tbody></table></section>'


def _render_ladder(ladder: dict[str, Any]) -> str:
    """Panel 01: gates clear, status line, destination, progress rail, five step cards and the Next strip."""

    steps = ladder["steps"]
    full = len(steps) == len(STEP_DETAILS)
    next_index = ladder["next"]
    count = ladder.get("gates_clear")
    if count is None:
        gates = '<span class="off">[ OFF ]</span> not available: ladder unreadable'
        status_column = ""
        rail = ""
    else:
        gates = f'<span class="big">{int(count)}</span><span class="denom"> / 4</span>'
        line = ALL_GATES_PASS if next_index is None else (
            f"{int(count)} of 4 evidence gates clear. Next gate: {steps[next_index]['label']}."
        )
        status_column = f'<div class="status"><span class="label muted">STATUS</span><p>{html.escape(line)}</p></div>'
        rail = _render_rail(steps, next_index) if full else ""
    top = (
        '<div class="top">'
        f'<div><span class="label muted">EVIDENCE GATES CLEAR</span><p>{gates}</p></div>'
        f"{status_column}"
        '<div><span class="label muted">DESTINATION</span>'
        '<p class="muted">LIVE &middot; blocked (PRD-F12)</p></div>'
        "</div>"
    )
    cards = "".join(_render_card(index, step, next_index, full) for index, step in enumerate(steps))
    next_text = ladder["next_text"]
    strip = ""
    if next_text:
        # The fixed DSD 4.5.5 text, with its leading "Next: " drawn as the label instead of printed twice.
        label = '<span class="label">NEXT ▸</span> ' if next_text.startswith("Next: ") else ""
        body = next_text.removeprefix("Next: ")
        strip = f'<p class="next-strip">{label}{html.escape(body)}</p>'
    return (
        f'<section class="ladder">{_title(1, "EVIDENCE LADDER · MISSION TRACK", "reports/")}'
        f"{top}{rail}<ol>{cards}</ol>{strip}</section>"
    )


def _render_rail(steps: list[dict[str, str]], next_index: int | None) -> str:
    """The V-5 rail: decorative only (aria-hidden); each segment's glyph and word sit in its card below."""

    segments = []
    for index, step in enumerate(steps):
        if index == len(steps) - 1:
            kind = "s-live"  # Live is a dashed line and is never filled, whatever any report says
        elif step["state"] == "ok":
            kind = "s-ok"
        elif index == next_index:
            kind = "s-next"
        else:
            kind = "s-todo"
        segments.append(f'<span class="{kind}"></span>')
    return f'<div class="rail" aria-hidden="true">{"".join(segments)}</div>'


def _render_card(index: int, step: dict[str, str], next_index: int | None, full: bool) -> str:
    is_next = next_index == index
    live = full and index == len(STEP_DETAILS) - 1
    classes = "step" + (" next" if is_next else "") + (" live" if live else "")
    if live:
        marker = "s-todo"
    elif step["state"] == "ok":
        marker = "s-ok"
    else:
        marker = "s-next" if is_next else "s-todo"
    flag = "<strong>NEXT</strong>" if is_next else ""
    detail = f'<span class="detail">{html.escape(STEP_DETAILS[index])}</span>' if full else ""
    return (
        f'<li class="{classes}"><div class="head"><span class="mk {marker}"></span>'
        f'<span class="idx">{index + 1:02d}</span>{flag}</div>'
        f'<span class="label">{html.escape(step["label"])}</span>'
        f'<span class="status"><span class="{step["state"]}">{TAGS[step["state"]]}</span> '
        f'{html.escape(step["text"])}</span>{detail}</li>'
    )


def _render_status_panel(index: int, panel: dict[str, Any], restraint: dict[str, Any]) -> str:
    number, source = PANEL_META[index]
    if index == 0:
        lead, rows = _readout(panel["rows"])
        return _render_panel({**panel, "rows": rows}, note_last=True, number=number, source=source, lead=lead)
    if index == 3:
        return _render_risk(panel, number, source)
    if index == 4:
        return _render_positions(panel, restraint, number, source)
    headers = ("TIME", "STATE", "EVENT") if index == 5 else ("ITEM", "STATE", "DETAIL")
    return _render_panel(panel, number=number, source=source, headers=headers)


def _readout(rows: list[dict[str, str]]) -> tuple[str, list[dict[str, str]]]:
    """The operating-mode readout (V-1) and the banner rows without the MODE row it replaces."""

    mode = next((item for item in rows if item["label"] == "MODE"), None)
    if mode is None:
        return "", rows
    text = mode["text"]
    line = f'<span class="muted">{PAPER_LINE}</span>' if text.upper() == "PAPER" else ""
    readout = (
        '<div class="readout"><span class="label muted">OPERATING MODE</span>'
        f'<span class="mode">{html.escape(text)}</span>{line}</div><div class="hair"></div>'
    )
    return readout, [item for item in rows if item is not mode]


def _row_html(item: dict[str, str]) -> str:
    return (
        f'<tr><th scope="row">{html.escape(item["label"])}</th>'
        f'<td class="{item["state"]}">{TAGS[item["state"]]}</td>'
        f'<td>{html.escape(item["text"])}</td></tr>'
    )


def _render_panel(
    panel: dict[str, Any],
    *,
    note_last: bool = False,
    number: int | None = None,
    source: str = "",
    headers: tuple[str, str, str] = ("ITEM", "STATE", "DETAIL"),
    lead: str = "",
) -> str:
    """Render one panel; with ``note_last`` its NOTE rows follow the table as <p class="note">."""

    rows = panel["rows"]
    notes = [item for item in rows if note_last and item["label"] == "NOTE"]
    body = "".join(_row_html(item) for item in rows if item not in notes)
    tail = "".join(
        f'<p class="note"><span class="label">{html.escape(item["label"])}</span> {html.escape(item["text"])}</p>'
        for item in notes
    )
    head = "".join(f'<th scope="col">{html.escape(name)}</th>' for name in headers)
    return (
        f'<section>{_title(number, panel["title"], source)}{lead}<table>'
        f"<thead><tr>{head}</tr></thead>"
        f"<tbody>{body}</tbody></table>{tail}</section>"
    )


def _render_risk(panel: dict[str, Any], number: int, source: str) -> str:
    """Panel 04 (V-4): the six risk_state values as one instrument cluster, limits below.

    Any other shape (the empty and unavailable states) falls back to the plain table.
    """

    rows = panel["rows"]
    if [item["label"] for item in rows[: len(RISK_LABELS)]] != list(RISK_LABELS):
        return _render_panel(panel, number=number, source=source)
    cells = []
    for item in rows[: len(RISK_LABELS)]:
        value, note = item["text"], ""
        if item["state"] != "plain":  # e.g. a stale day: value on top, its state cell below
            value, _, reason = item["text"].partition("; ")
            note = f'<span class="detail"><span class="{item["state"]}">{TAGS[item["state"]]}</span> {html.escape(reason)}</span>'
        cells.append(
            f'<div class="cell"><span class="label muted">{html.escape(item["label"])}</span>'
            f'<span class="val">{html.escape(value)}</span>{note}</div>'
        )
    limits = " &middot; ".join(html.escape(f'{item["label"]} {item["text"]}') for item in rows[len(RISK_LABELS) :])
    footer = f'<div class="limits"><span class="label">LIMITS</span> {limits}</div>' if limits else ""
    return f'<section>{_title(number, panel["title"], source)}<div class="cluster">{"".join(cells)}</div>{footer}</section>'


def _render_restraint(restraint: dict[str, Any]) -> str:
    """The V-3b strip: a real count of today's risk-engine holds, or why it is not available."""

    state = restraint.get("state", "off")
    word = " held" if state == "ok" else ""
    return (
        '<div class="restraint"><span class="label muted">RESTRAINT</span>'
        f'<span><span class="{state}">{TAGS[state]}</span>{word}</span>'
        f'<span>{html.escape(str(restraint.get("text", "")))}</span></div>'
    )


def _render_positions(panel: dict[str, Any], restraint: dict[str, Any], number: int, source: str) -> str:
    """Panel 05: restraint strip, open positions, then closed trades and events as log rows with SIM tags."""

    rows = panel["rows"]
    logs = [item for item in rows if item["label"].startswith("SIM ")]
    others = [item for item in rows if item not in logs]
    table = f"<table><tbody>{''.join(_row_html(item) for item in others)}</tbody></table>" if others else ""
    entries = []
    for item in logs:
        kind = f'<span class="ev">{html.escape(item["event"])}</span> ' if item.get("event") else ""
        entries.append(
            f'<li><span class="ts">{html.escape(item["label"][4:])}</span><span class="sim">SIM</span>'
            f'<span class="text">{kind}{html.escape(item["text"])}</span></li>'
        )
    log = f'<ul class="log">{"".join(entries)}</ul>' if entries else ""
    return f'<section>{_title(number, panel["title"], source)}{_render_restraint(restraint)}{table}{log}</section>'


class DashboardServer(ThreadingHTTPServer):
    """HTTP server for the status page; loopback unless a password is set.

    Binds ``host`` (default 127.0.0.1). A non-loopback ``host`` fails closed: it
    needs ``password``, which then gates every GET with HTTP Basic auth.
    ``allowed_host`` is one extra public Host header value to accept.
    """

    daemon_threads = True
    # On Windows SO_REUSEADDR lets a second socket share a busy port; refuse that.
    allow_reuse_address = sys.platform != "win32"

    def __init__(
        self,
        port: int,
        *,
        root: Path,
        load: Callable[[], AppConfig] = load_config,
        host: str = BIND_HOST,
        allowed_host: str | None = None,
        password: str | None = None,
    ) -> None:
        if not password and not is_loopback_host(host):
            raise ValueError(f"refusing to bind {host}: a non-loopback host needs {PASSWORD_ENV}")
        self.root = Path(root)
        self.load = load
        self.allowed_host = allowed_host.strip().lower() if allowed_host and allowed_host.strip() else None
        self.password = password.encode("utf-8") if password else None
        super().__init__((host, port), DashboardHandler)


class DashboardHandler(BaseHTTPRequestHandler):
    """Answer GET / with the page; refuse every other method, path, host and (if gated) anonymous caller."""

    server: DashboardServer
    server_version = "silvr-dashboard"
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
        if not self._authorized():
            self._send(401, "authentication required\n", headers={"WWW-Authenticate": AUTH_CHALLENGE})
            return
        if self.path == "/":
            status = collect_status(self.server.root, load=self.server.load)
            host, port = self.server.server_address[:2]
            self._send(200, render_page(status, bind=(str(host), int(port))), content_type=HTML_TYPE)
        elif self.path in FONTS:
            font = files("silvr.monitoring").joinpath("fonts", FONTS[self.path]).read_bytes()
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
        host = self.headers.get("Host", "")
        if host in allowed:
            return True
        # The platform edge sends the bare public domain, so the port is optional.
        public = self.server.allowed_host
        return public is not None and host.lower() in {public, f"{public}:{port}"}

    def _authorized(self) -> bool:
        """True when no password is set, or the Basic credentials carry it (user name ignored)."""

        expected = self.server.password
        if expected is None:
            return True
        scheme, _, token = self.headers.get("Authorization", "").partition(" ")
        if scheme.lower() != "basic":
            return False
        try:
            decoded = base64.b64decode(token.strip(), validate=True)
        except (binascii.Error, ValueError):
            return False
        _, colon, supplied = decoded.partition(b":")
        return bool(colon) and hmac.compare_digest(supplied, expected)

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
        prog="python -m silvr.monitoring.dashboard_server",
        description=(
            f"Read-only SILVR status page (default {BIND_HOST}). A non-loopback --host "
            f"needs the {PASSWORD_ENV} environment variable and serves behind HTTP Basic auth."
        ),
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"port to listen on (default {DEFAULT_PORT})")
    parser.add_argument("--host", default=BIND_HOST, help=f"address to bind (default {BIND_HOST})")
    parser.add_argument("--allowed-host", default=None, help="extra Host header to accept, e.g. the public domain")
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        print(f"invalid port: {args.port}", file=sys.stderr)
        return 2
    # Environment only, never a flag: a flag would show in the process list.
    password = (os.environ.get(PASSWORD_ENV) or "").strip() or None
    try:
        server = DashboardServer(
            args.port, root=Path.cwd(), host=args.host, allowed_host=args.allowed_host, password=password
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"cannot listen on {args.host}:{args.port}: {exc.strerror or exc}", file=sys.stderr)
        return 2
    gate = "; password required" if password else ""
    print(
        f"silvr status: http://{args.host}:{server.server_address[1]}/ "
        f"(read-only{gate}; reading {server.root}; Ctrl+C to stop)"
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
