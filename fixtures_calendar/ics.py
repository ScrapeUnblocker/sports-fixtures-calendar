"""iCalendar (RFC 5545) output for a list of matches.

Matches keep a stable UID (the match id), so a calendar app updates an event in
place when a kick-off moves, a match is postponed or the final score comes in,
instead of adding a duplicate.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional

# How long to block in the calendar for a match of each sport, in minutes.
# Matches have no fixed end, so these are typical durations including breaks.
SPORT_MINUTES: Dict[str, int] = {
    "football": 115, "futsal": 90, "minifootball": 90, "basketball": 150,
    "tennis": 150, "padel": 120, "badminton": 60, "table-tennis": 45,
    "ice-hockey": 150, "bandy": 120, "floorball": 120, "american-football": 200,
    "baseball": 190, "cricket": 480, "rugby": 100, "aussie-rules": 150,
    "handball": 90, "volleyball": 120, "beach-volley": 60, "waterpolo": 75,
    "darts": 120, "snooker": 240, "esports": 120, "mma": 180,
}
DEFAULT_MINUTES = 120

SPORT_EMOJI: Dict[str, str] = {
    "football": "⚽", "futsal": "⚽", "minifootball": "⚽", "basketball": "🏀",
    "tennis": "🎾", "padel": "🎾", "badminton": "🏸", "table-tennis": "🏓",
    "ice-hockey": "🏒", "bandy": "🏒", "floorball": "🏑", "american-football": "🏈",
    "baseball": "⚾", "cricket": "🏏", "rugby": "🏉", "aussie-rules": "🏉",
    "handball": "🤾", "volleyball": "🏐", "beach-volley": "🏐", "waterpolo": "🤽",
    "darts": "🎯", "snooker": "🎱", "esports": "🎮", "mma": "🥊",
}

CANCELLED = {"canceled", "postponed", "abandoned"}
SET_SPORTS = {"tennis", "padel", "badminton", "table-tennis", "volleyball", "beach-volley"}


def escape(text: str) -> str:
    return (text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n"))


def fold(line: str) -> str:
    """Splits a content line into 75-octet pieces, as RFC 5545 requires."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    parts, start = [], 0
    limit = 75
    while start < len(raw):
        end = min(start + limit, len(raw))
        # Never cut a multi-byte character in half.
        while end < len(raw) and (raw[end] & 0xC0) == 0x80:
            end -= 1
        parts.append(raw[start:end].decode("utf-8"))
        start = end
        limit = 74  # continuation lines start with a space
    return "\r\n ".join(parts)


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _team_name(team: Optional[dict]) -> str:
    team = team or {}
    return team.get("shortName") or team.get("name") or "TBD"


def score_line(match: dict) -> Optional[str]:
    """'2-1', with penalties or sets when there are any; None before a result."""
    home, away = match.get("homeScore") or {}, match.get("awayScore") or {}
    # `display` is the score as shown; after a shoot-out `current` also counts
    # the penalties (6-4 for a 1-1 won 5-3), and `display` is left out when the
    # two agree.
    h = home.get("display", home.get("current"))
    a = away.get("display", away.get("current"))
    if h is None or a is None:
        return None
    text = f"{h}-{a}"
    if home.get("penalties") is not None and away.get("penalties") is not None:
        text += f" ({home['penalties']}-{away['penalties']} pens)"
    return text


def set_scores(match: dict) -> Optional[str]:
    home, away = match.get("homeScore") or {}, match.get("awayScore") or {}
    sets = []
    for n in range(1, 8):
        h, a = home.get(f"period{n}"), away.get(f"period{n}")
        if h is None or a is None:
            break
        sets.append(f"{h}-{a}")
    return ", ".join(sets) or None


def summary(match: dict, emoji: bool = True) -> str:
    home, away = _team_name(match.get("homeTeam")), _team_name(match.get("awayTeam"))
    status = (match.get("status") or {}).get("type")
    score = score_line(match)
    if status == "finished" and score:
        title = f"{home} {score} {away}"
    else:
        title = f"{home} vs {away}"
    if status in CANCELLED:
        title = f"[{status.capitalize()}] {title}"
    icon = SPORT_EMOJI.get(match.get("sport") or "") if emoji else None
    return f"{icon} {title}" if icon else title


def description(match: dict) -> str:
    tour = match.get("tournament") or {}
    lines = []
    name = tour.get("name")
    if name:
        country = (tour.get("category") or {}).get("name")
        lines.append(f"{name}" + (f" ({country})" if country and country not in name else ""))
    if match.get("roundName") or match.get("round"):
        lines.append(f"Round: {match.get('roundName') or match.get('round')}")
    status = (match.get("status") or {}).get("description")
    if status:
        lines.append(f"Status: {status}")
    if match.get("sport") in SET_SPORTS and set_scores(match):
        lines.append(f"Sets: {set_scores(match)}")
    if match.get("url"):
        lines.append(f"Match centre: {match['url']}")
    return "\n".join(lines)


def location(match: dict) -> Optional[str]:
    venue = match.get("venue") or {}
    parts = [venue.get("name"), venue.get("city"), venue.get("country")]
    seen: List[str] = []
    for p in parts:
        if p and p not in seen:
            seen.append(p)
    return ", ".join(seen) or None


def vevent(match: dict, *, domain: str, now: datetime, alarm_minutes: Optional[int],
           emoji: bool = True) -> List[str]:
    start = datetime.fromtimestamp(match["startTimestamp"], tz=timezone.utc)
    minutes = SPORT_MINUTES.get(match.get("sport") or "", DEFAULT_MINUTES)
    status = (match.get("status") or {}).get("type")
    lines = [
        "BEGIN:VEVENT",
        f"UID:match-{match['id']}@{domain}",
        f"DTSTAMP:{_stamp(now)}",
        f"DTSTART:{_stamp(start)}",
        f"DTEND:{_stamp(start + timedelta(minutes=minutes))}",
        f"SUMMARY:{escape(summary(match, emoji))}",
        f"DESCRIPTION:{escape(description(match))}",
    ]
    where = location(match)
    if where:
        lines.append(f"LOCATION:{escape(where)}")
    if match.get("url"):
        lines.append(f"URL:{match['url']}")
    lines.append("STATUS:CANCELLED" if status in CANCELLED else "STATUS:CONFIRMED")
    # Free, not busy: a fixture is something to watch, not a meeting.
    lines.append("TRANSP:TRANSPARENT")
    if alarm_minutes and status == "notstarted":
        lines += ["BEGIN:VALARM", "ACTION:DISPLAY",
                  f"DESCRIPTION:{escape(summary(match, emoji))}",
                  f"TRIGGER:-PT{int(alarm_minutes)}M", "END:VALARM"]
    lines.append("END:VEVENT")
    return lines


def calendar(name: str, matches: Iterable[dict], *, domain: str,
             timezone_name: str = "UTC", alarm_minutes: Optional[int] = None,
             refresh_hours: int = 6, emoji: bool = True,
             now: Optional[datetime] = None) -> str:
    now = now or datetime.now(timezone.utc)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//ScrapeUnblocker//sports-fixtures-calendar//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{escape(name)}",
        f"X-WR-TIMEZONE:{timezone_name}",
        f"REFRESH-INTERVAL;VALUE=DURATION:PT{int(refresh_hours)}H",
        f"X-PUBLISHED-TTL:PT{int(refresh_hours)}H",
    ]
    for match in matches:
        if match.get("startTimestamp") and match.get("id"):
            lines += vevent(match, domain=domain, now=now, alarm_minutes=alarm_minutes,
                            emoji=emoji)
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(line) for line in lines) + "\r\n"
