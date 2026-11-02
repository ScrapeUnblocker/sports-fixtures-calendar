"""Reads calendars.yml, fetches each team's and competition's matches, and
writes one .ics file per calendar plus an index.html to subscribe from."""

from __future__ import annotations

import html
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlparse
from zoneinfo import ZoneInfo

import yaml

from . import ics
from .api import ApiError, SofaScore

SITE = ("https://scrapeunblocker.com/?utm_source=github&utm_medium=integration"
        "&utm_campaign=example-repos")
DOCS = ("https://docs.scrapeunblocker.com/plugins/sofascore?utm_source=github"
        "&utm_medium=integration&utm_campaign=example-repos")


@dataclass
class Source:
    kind: str  # "team" or "tournament"
    value: str
    sport: Optional[str] = None


@dataclass
class Calendar:
    name: str
    file: str
    sources: List[Source]
    alarm_minutes: Optional[int] = None
    matches: List[dict] = field(default_factory=list)
    resolved: List[dict] = field(default_factory=list)


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "calendar"


def _sources(entries: Any, kind: str) -> List[Source]:
    out = []
    for entry in entries or []:
        if isinstance(entry, (str, int)):
            out.append(Source(kind, str(entry)))
        elif isinstance(entry, dict) and (entry.get(kind) or entry.get("name")):
            out.append(Source(kind, str(entry.get(kind) or entry.get("name")),
                              entry.get("sport")))
        else:
            raise ValueError(f"Cannot read {kind} entry: {entry!r}")
    return out


def load_config(path: Path) -> Dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    calendars = []
    for raw in data.get("calendars") or []:
        name = raw.get("name") or "Fixtures"
        sources = _sources(raw.get("teams"), "team") + _sources(raw.get("tournaments"),
                                                                 "tournament")
        if not sources:
            raise ValueError(f"Calendar '{name}' lists no teams or tournaments.")
        calendars.append(Calendar(name=name, file=slugify(raw.get("file") or name),
                                  sources=sources, alarm_minutes=raw.get("alarm_minutes")))
    if not calendars:
        raise ValueError("calendars.yml has no calendars.")
    return {
        "calendars": calendars,
        "timezone": data.get("timezone") or "UTC",
        "past_days": int(data.get("past_days", 30)),
        "refresh_hours": int(data.get("refresh_hours", 6)),
        "emoji": bool(data.get("emoji", True)),
    }


def fetch(client: SofaScore, source: Source) -> Dict[str, Any]:
    if source.kind == "team":
        body = client.team(source.value, sport=source.sport)
        entity = body.get("team") or {}
    else:
        body = client.tournament(source.value, sport=source.sport)
        entity = body.get("tournament") or {}
    matches = (body.get("last_matches") or []) + (body.get("next_matches") or [])
    return {"entity": entity, "matches": matches}


def collect(client: SofaScore, cal: Calendar, *, past_days: int,
            now: datetime, log=print) -> None:
    oldest = (now - timedelta(days=past_days)).timestamp()
    by_id: Dict[int, dict] = {}
    for source in cal.sources:
        try:
            got = fetch(client, source)
        except ApiError as exc:
            if exc.status == 401:
                raise
            log(f"  ! {source.kind} '{source.value}': {exc.message}")
            cal.resolved.append({"input": source.value, "kind": source.kind,
                                 "error": exc.message})
            continue
        ent = got["entity"]
        cal.resolved.append({"input": source.value, "kind": source.kind,
                             "id": ent.get("id"), "name": ent.get("name"),
                             "sport": ent.get("sport"), "url": ent.get("url")})
        log(f"  {source.kind} '{source.value}' -> {ent.get('name')} "
            f"({ent.get('sport')}), {len(got['matches'])} matches")
        for m in got["matches"]:
            if m.get("id") and (m.get("startTimestamp") or 0) >= oldest:
                by_id[m["id"]] = m
    cal.matches = sorted(by_id.values(), key=lambda m: m["startTimestamp"])


def pages_url() -> Optional[str]:
    explicit = os.environ.get("PAGES_URL")
    if explicit:
        return explicit.rstrip("/") + "/"
    repo = os.environ.get("GITHUB_REPOSITORY")
    if repo and "/" in repo:
        owner, name = repo.split("/", 1)
        if name.lower() == f"{owner.lower()}.github.io":
            return f"https://{owner.lower()}.github.io/"
        return f"https://{owner.lower()}.github.io/{name}/"
    return None


def _when(ts: int, tz: ZoneInfo) -> str:
    return datetime.fromtimestamp(ts, tz=tz).strftime("%a %d %b %H:%M")


def index_html(cals: List[Calendar], *, base: Optional[str], tz_name: str,
               now: datetime) -> str:
    tz = ZoneInfo(tz_name)
    esc = html.escape
    blocks = []
    for cal in cals:
        rel = f"{cal.file}.ics"
        links = [f'<a href="{rel}">Download .ics</a>']
        if base:
            https_url = base + rel
            webcal = "webcal://" + https_url.split("://", 1)[1]
            links = [
                f'<a href="{esc(webcal)}">Apple / any calendar app</a>',
                f'<a href="https://calendar.google.com/calendar/r?cid={quote(webcal, safe="")}">'
                "Google Calendar</a>",
                f'<a href="https://outlook.live.com/calendar/0/addfromweb?url='
                f'{quote(https_url, safe="")}&name={quote(cal.name)}">Outlook</a>',
            ] + links
        upcoming = [m for m in cal.matches if m["startTimestamp"] >= now.timestamp()][:8]
        rows = "".join(
            f"<tr><td>{esc(_when(m['startTimestamp'], tz))}</td>"
            f"<td>{esc(ics.summary(m, emoji=True))}</td>"
            f"<td>{esc((m.get('tournament') or {}).get('name') or '')}</td></tr>"
            for m in upcoming) or '<tr><td colspan="3">No upcoming matches yet.</td></tr>'
        who = ", ".join(
            (f'<a href="{esc(r["url"])}">{esc(r["name"])}</a>' if r.get("url")
             else esc(r.get("name") or r["input"])) if not r.get("error")
            else f'<span class="err">{esc(r["input"])} (not found)</span>'
            for r in cal.resolved)
        blocks.append(f"""
<section>
  <h2>{esc(cal.name)}</h2>
  <p class="links">Subscribe: {' · '.join(links)}</p>
  <p class="who">Following: {who}</p>
  <table><thead><tr><th>Kick-off ({esc(tz_name)})</th><th>Match</th><th>Competition</th></tr></thead>
  <tbody>{rows}</tbody></table>
</section>""")
    updated = now.astimezone(tz).strftime("%Y-%m-%d %H:%M")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sports fixtures calendars</title>
<style>
body {{ font: 15px/1.5 system-ui, sans-serif; max-width: 860px; margin: 2rem auto; padding: 0 16px; color: #0f172a; }}
h1 {{ font-size: 1.6rem; }} h2 {{ margin-top: 2rem; }}
table {{ border-collapse: collapse; width: 100%; }} th, td {{ text-align: left; padding: 6px 8px; border-bottom: 1px solid #e2e8f0; }}
.links a {{ font-weight: 600; }} .who, footer {{ color: #475569; }} .err {{ color: #b91c1c; }}
</style></head><body>
<h1>Sports fixtures calendars</h1>
<p>Subscribe once and your calendar app keeps the fixtures up to date: new matches, moved kick-offs and final scores.
Times are shown in your own time zone by your calendar app. Updated {esc(updated)} ({esc(tz_name)}).</p>
{''.join(blocks)}
<footer><p>Built with <a href="https://github.com/ScrapeUnblocker/sports-fixtures-calendar">sports-fixtures-calendar</a>.
Match data from SofaScore via <a href="{SITE}">ScrapeUnblocker</a>'s <a href="{DOCS}">SofaScore API</a>.</p></footer>
</body></html>
"""


def write_ics(path: Path, text: str) -> None:
    # newline="" keeps the CRLF line ends RFC 5545 asks for on every platform.
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def build(config_path: Path, out_dir: Path, *, client: Optional[SofaScore] = None,
          now: Optional[datetime] = None, log=print) -> List[Calendar]:
    cfg = load_config(config_path)
    now = now or datetime.now(timezone.utc)
    client = client or SofaScore()
    base = pages_url()
    domain = urlparse(base).hostname if base else "sports-fixtures-calendar"
    out_dir.mkdir(parents=True, exist_ok=True)
    for cal in cfg["calendars"]:
        log(f"{cal.name}:")
        collect(client, cal, past_days=cfg["past_days"], now=now, log=log)
        if not any(not r.get("error") for r in cal.resolved):
            raise SystemExit(f"Calendar '{cal.name}': none of its teams or tournaments "
                             "were found - check calendars.yml.")
        write_ics(out_dir / f"{cal.file}.ics",
                  ics.calendar(cal.name, cal.matches, domain=domain,
                               timezone_name=cfg["timezone"],
                               alarm_minutes=cal.alarm_minutes,
                               refresh_hours=cfg["refresh_hours"], emoji=cfg["emoji"],
                               now=now))
        log(f"  -> {cal.file}.ics ({len(cal.matches)} matches)")
    (out_dir / "index.html").write_text(
        index_html(cfg["calendars"], base=base, tz_name=cfg["timezone"], now=now),
        encoding="utf-8")
    (out_dir / "resolved.json").write_text(json.dumps(
        {c.file: c.resolved for c in cfg["calendars"]}, indent=2), encoding="utf-8")
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    log(f"Done: {len(cfg['calendars'])} calendar(s), {client.calls} API call(s).")
    return cfg["calendars"]


def quick(teams: List[str], tournaments: List[str], out: Path, *, name: str,
          alarm_minutes: Optional[int], client: Optional[SofaScore] = None,
          log=print) -> Calendar:
    """One calendar straight from the command line, no config file."""
    def parse(raw: str, kind: str) -> Source:
        value, _, sport = raw.partition("@")
        return Source(kind, value.strip(), sport.strip() or None)
    cal = Calendar(name=name, file=slugify(out.stem),
                   sources=[parse(t, "team") for t in teams]
                   + [parse(t, "tournament") for t in tournaments],
                   alarm_minutes=alarm_minutes)
    client = client or SofaScore()
    now = datetime.now(timezone.utc)
    collect(client, cal, past_days=30, now=now, log=log)
    write_ics(out, ics.calendar(cal.name, cal.matches, domain="sports-fixtures-calendar",
                                alarm_minutes=alarm_minutes, now=now))
    log(f"Wrote {out} ({len(cal.matches)} matches, {client.calls} API call(s)).")
    return cal


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="python -m fixtures_calendar",
                                description="Sports fixtures as subscribable calendars.")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="Build every calendar in calendars.yml.")
    b.add_argument("--config", default="calendars.yml")
    b.add_argument("--out", default="site")
    q = sub.add_parser("quick", help="One .ics file from the command line.")
    q.add_argument("--team", action="append", default=[],
                   help="Team or player name, id or SofaScore link; add @sport to "
                        "pick the sport, e.g. 'Real Madrid@basketball'. Repeatable.")
    q.add_argument("--tournament", action="append", default=[],
                   help="Competition name, id or link, e.g. 'Premier League'. Repeatable.")
    q.add_argument("--name", default="My fixtures")
    q.add_argument("--alarm", type=int, default=None, help="Reminder, minutes before.")
    q.add_argument("--out", default="fixtures.ics")
    args = p.parse_args(argv)
    try:
        if args.cmd == "build":
            build(Path(args.config), Path(args.out))
        else:
            if not args.team and not args.tournament:
                p.error("give at least one --team or --tournament")
            quick(args.team, args.tournament, Path(args.out), name=args.name,
                  alarm_minutes=args.alarm)
    except ApiError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0
