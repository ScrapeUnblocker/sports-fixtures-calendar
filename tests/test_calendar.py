"""Offline tests: real API answers (tests/data) through the calendar builder.
No API key and no network needed."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from fixtures_calendar import build, ics
from fixtures_calendar.api import ApiError

DATA = Path(__file__).parent / "data"
NOW = datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc)


def load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


class FakeClient:
    """Answers team/tournament lookups from tests/data, like the real client."""

    def __init__(self, answers):
        self.answers = answers
        self.calls = 0

    def team(self, team, *, sport=None, include=None):
        self.calls += 1
        if team not in self.answers:
            raise ApiError(404, f"SofaScore has no team '{team}'.")
        return self.answers[team]

    tournament = team


def unfold(text):
    return text.replace("\r\n ", "")


def test_finished_match_shows_the_score_and_upcoming_shows_vs():
    body = load("arsenal.json")
    done = body["last_matches"][0]
    upcoming = body["next_matches"][0]
    assert done["status"]["type"] == "finished"
    s = ics.summary(done)
    assert s.startswith("⚽ ") and f"{done['homeScore']['current']}-{done['awayScore']['current']}" in s
    assert " vs " in ics.summary(upcoming)
    assert ics.summary(upcoming, emoji=False)[0].isalpha()


def test_tennis_lists_the_sets():
    match = load("sinner.json")["last_matches"][0]
    assert match["sport"] == "tennis"
    desc = ics.description(match)
    assert "Sets: " in desc and desc.count("-") >= 3


def test_calendar_is_valid_rfc5545():
    body = load("arsenal.json")
    matches = body["last_matches"] + body["next_matches"]
    text = ics.calendar("Arsenal", matches, domain="example.github.io", alarm_minutes=30,
                        now=NOW)
    assert text.startswith("BEGIN:VCALENDAR\r\n") and text.endswith("END:VCALENDAR\r\n")
    assert all(len(line.encode()) <= 75 for line in text.split("\r\n"))
    flat = unfold(text)
    assert flat.count("BEGIN:VEVENT") == 4
    for m in matches:
        assert f"UID:match-{m['id']}@example.github.io" in flat
    # Reminders only for matches still to come.
    assert flat.count("BEGIN:VALARM") == 2
    assert "TRIGGER:-PT30M" in flat


def test_postponed_match_is_cancelled_in_the_calendar():
    m = dict(load("arsenal.json")["next_matches"][0])
    m["status"] = {"type": "postponed", "description": "Postponed"}
    text = unfold(ics.calendar("x", [m], domain="d", now=NOW))
    assert "STATUS:CANCELLED" in text and "SUMMARY:⚽ [Postponed]" in text


def test_text_is_escaped_and_folded_on_character_boundaries():
    assert ics.escape("a;b,c\nd\\e") == r"a\;b\,c\nd\\e"
    line = "SUMMARY:" + "⚽" * 40
    folded = ics.fold(line)
    assert all(len(p.encode()) <= 75 for p in folded.split("\r\n"))
    assert unfold(folded) == line


def test_build_writes_calendars_index_and_skips_unknown_teams(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "someone/sports-fixtures-calendar")
    monkeypatch.delenv("PAGES_URL", raising=False)
    cfg = tmp_path / "calendars.yml"
    cfg.write_text(
        "timezone: Europe/Vilnius\npast_days: 365\ncalendars:\n"
        "  - name: Mine\n    file: mine\n    teams:\n      - Arsenal\n"
        "      - team: Jannik Sinner\n        sport: tennis\n      - No Such FC\n",
        encoding="utf-8")
    client = FakeClient({"Arsenal": load("arsenal.json"),
                         "Jannik Sinner": load("sinner.json")})
    out = tmp_path / "site"
    cals = build.build(cfg, out, client=client, now=NOW, log=lambda *_: None)
    assert client.calls == 3
    assert len(cals[0].matches) == 6
    ics_text = (out / "mine.ics").read_text(encoding="utf-8")
    assert "X-WR-CALNAME:Mine" in ics_text
    assert "@someone.github.io" in ics_text
    page = (out / "index.html").read_text(encoding="utf-8")
    assert "webcal://someone.github.io/sports-fixtures-calendar/mine.ics" in page
    assert "calendar.google.com" in page and "No Such FC (not found)" in page
    resolved = json.loads((out / "resolved.json").read_text(encoding="utf-8"))
    assert [r.get("error") is None for r in resolved["mine"]] == [True, True, False]


def test_build_stops_when_nothing_in_a_calendar_resolves(tmp_path):
    cfg = tmp_path / "calendars.yml"
    cfg.write_text("calendars:\n  - name: X\n    teams: [Nobody]\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        build.build(cfg, tmp_path / "site", client=FakeClient({}), now=NOW,
                    log=lambda *_: None)


def test_config_errors_are_reported():
    with pytest.raises(ValueError):
        build._sources([["not", "a", "team"]], "team")
    assert build.slugify("My Teams 2026!") == "my-teams-2026"

def test_shootout_shows_the_match_score_and_the_penalties():
    m = load("arsenal.json")["last_matches"][1]
    assert m["homeScore"]["penalties"] is not None
    assert ics.summary(m, emoji=False) == "Fleetwood 1-1 (5-3 pens) Arsenal"
