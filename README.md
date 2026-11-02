# sports-fixtures-calendar

[![Tests](https://github.com/ScrapeUnblocker/sports-fixtures-calendar/actions/workflows/test.yml/badge.svg)](https://github.com/ScrapeUnblocker/sports-fixtures-calendar/actions/workflows/test.yml)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Your teams' fixtures in your own calendar, for any sport and any league, kept up to date for you.**

List the teams, players and competitions you follow in one small file. A scheduled
GitHub Action turns them into calendar feeds that you subscribe to once in Google
Calendar, Apple Calendar or Outlook. From then on new fixtures appear on their own,
moved kick-offs move, postponed matches are marked, and when a match ends its entry
changes from `Arsenal vs Chelsea` to `Arsenal 2-1 Chelsea`.

What the calendar shows (real entries from one build):

```
Sun 01 Nov 16:30   ⚽ Liverpool 0-1 Arsenal                 Premier League
Tue 27 Oct 20:00   ⚽ Fleetwood 1-1 (5-3 pens) Arsenal      EFL Cup
Wed 04 Nov 20:00   ⚽ Slavia Praha vs Arsenal               UEFA Champions League
Thu 08 Oct 19:45   🏀 Real Madrid 86-76 Partizan Mozzart    Euroleague
Sun 12 Jul 16:05   🎾 J. Sinner 3-1 A. Zverev               Wimbledon, Men
```

> Match data comes from SofaScore through the
> [ScrapeUnblocker SofaScore API](https://docs.scrapeunblocker.com/plugins/sofascore?utm_source=github&utm_medium=integration&utm_campaign=example-repos),
> so this repo stays a few hundred lines of plain Python with no scraping code to maintain.

## Why

Official fixture feeds are scattered: one club offers an `.ics`, the next only an app,
your second sport has nothing, and none of them puts the result in afterwards. If you
follow a football club, a basketball team and a tennis player, you end up with three
apps or none. This tool gives you one feed per calendar you define, across all of them:

- **26 sports**: football, basketball, tennis, ice hockey, American football, baseball,
  cricket, rugby, handball, volleyball, esports, darts, snooker, MMA and more.
- **Any team, player or competition** SofaScore covers, from the Champions League to a
  regional league, by plain name (`Arsenal`, `Jannik Sinner`, `NBA`), id or link.
- **Correct times everywhere**: events carry exact UTC times, so every calendar app shows
  them in your own time zone, including across daylight-saving changes.
- **Results filled in**: finished matches show the score (penalty shoot-outs included, and
  the sets in the event notes for tennis), and the last `past_days` of results stay in the calendar.
- **Updates in place**: each match keeps a stable id, so a rescheduled match moves instead
  of appearing twice, and a postponed or cancelled one is marked as cancelled.
- **Reminders** a set number of minutes before kick-off, if you want them.
- **A subscribe page**: GitHub Pages hosts the feeds plus an overview page with one-click
  "add to Google / Apple / Outlook" links and the next matches of every calendar.

## Set it up in five minutes

1. Click **Use this template** at the top of this page to create your own copy.
   Make it public, or private if your GitHub plan includes Pages for private
   repositories.
2. Get an API key at [scrapeunblocker.com](https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos)
   (the free trial needs no card), then add it in your repository under
   **Settings > Secrets and variables > Actions > New repository secret** with the name
   `SCRAPEUNBLOCKER_API_KEY`.
3. Turn on GitHub Pages: **Settings > Pages > Build and deployment > Source: GitHub Actions**.
4. Edit [`calendars.yml`](calendars.yml) with your teams and competitions and commit it.
   The commit starts the **Build calendars** workflow; you can also run it from the
   Actions tab.
5. Open `https://<your-user>.github.io/<your-repo>/` and click the subscribe link for
   your calendar app.

The workflow rebuilds the feeds every 6 hours. Your calendar app picks up changes the next
time it refreshes the subscription: Apple Calendar on the interval you choose for it,
Outlook every few hours, and Google Calendar on its own schedule, which can take up to a
day.

## Configuration

```yaml
timezone: Europe/London   # time zone of the overview page; the feeds use exact times
past_days: 30             # keep finished matches (with scores) this far back
refresh_hours: 6          # refresh hint for calendar apps; match the workflow schedule

calendars:
  - name: My teams
    file: my-teams           # published as my-teams.ics
    alarm_minutes: 30        # optional reminder before kick-off
    teams:
      - Arsenal                         # a name: the best SofaScore match
      - team: Real Madrid
        sport: basketball               # pick the sport when a name is ambiguous
      - team: Jannik Sinner             # tennis players, fighters and other
        sport: tennis                   # individual competitors are "teams" too
      - https://www.sofascore.com/football/team/inter-miami-cf/337602   # or a link / id

  - name: Champions League
    file: champions-league
    tournaments:
      - tournament: UEFA Champions League
        sport: football
```

Each build writes `resolved.json` next to the feeds, listing what every name matched
(name, sport and SofaScore link), and the overview page shows it too. If a name picks the
wrong team, use the team's sofascore.com link or id instead. A name that matches nothing
is reported and skipped; the rest of the calendar is still built.

Each team or competition gives you its last and next 30 matches (a competition: the last
and next 30 of the current season), from which the calendar keeps everything upcoming and
the finished matches of the last `past_days` days.

## Run it on your own machine

```bash
git clone https://github.com/ScrapeUnblocker/sports-fixtures-calendar
cd sports-fixtures-calendar
pip install -r requirements.txt
export SCRAPEUNBLOCKER_API_KEY=your_key      # Windows: set SCRAPEUNBLOCKER_API_KEY=...

# One file straight from the command line (add @sport to pick the sport):
python -m fixtures_calendar quick --team "Arsenal" --team "Lakers@basketball" \
    --tournament "Premier League" --alarm 15 --out fixtures.ics

# Or every calendar in calendars.yml into ./site:
python -m fixtures_calendar build --out site
```

Import the `.ics` file into any calendar app, or host the `site` folder anywhere that
serves static files and subscribe to its URL.

## What it costs

Each team or competition is one API request per build, whatever it returns. With five
entries and the default schedule of four builds a day that is 20 requests a day, about
600 a month; at pay-as-you-go prices that is well under a euro a month, and the free
trial covers the first 500 requests. Build less often (edit the `cron` line in
[`.github/workflows/build.yml`](.github/workflows/build.yml)) to use fewer.

## Privacy

GitHub Pages sites are public, even when the repository is private (access control for
Pages needs GitHub Enterprise Cloud): anyone who knows the URL can see which teams are in
your calendars. The feeds contain only public
fixture data and no personal information, but if you would rather keep your list to
yourself, run the tool locally or host the `site` folder somewhere private.

## How it works

`fixtures_calendar/api.py` calls two endpoints of the
[ScrapeUnblocker SofaScore API](https://docs.scrapeunblocker.com/plugins/sofascore?utm_source=github&utm_medium=integration&utm_campaign=example-repos):
`/sports/sofascore-team` and `/sports/sofascore-tournament`, each with
`include=last_matches,next_matches`. Both take a name, id or link and return matches as
clean JSON (teams, competition, round, status, start time, score per period, venue and a
match-centre link). `fixtures_calendar/ics.py` writes them as RFC 5545 events, and
`fixtures_calendar/build.py` reads the config, merges and de-duplicates the matches of each
calendar and writes the feeds and the overview page. The same API also has day lists, live
scores, full match statistics, lineups, standings and player season stats if you want to
build something bigger.

## Development

```bash
pip install -r requirements-dev.txt
pytest -q        # offline: real API answers are stored in tests/data, no key needed
```

## License

MIT. Not affiliated with or endorsed by SofaScore; match data is shown as SofaScore
publishes it.
