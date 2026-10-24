# TMH · 睇咩好？

"What's good to watch?" A static one-page site showing what's hot in movies and TV, and whether each title can be watched at home yet.

- `index.html`: the whole app (HTML/CSS/JS, no build step). The only external requests are poster images you add and JustWatch links.
- `data.json`: all the data. Edit this to update the site.
- `sync-fallback.py`: optional helper that checks `data.json` and copies it into `index.html` so the page also works when opened straight from disk (`file://`).

Statuses ("Streaming", "Coming home", "Airing weekly", "NEW" etc.) are **never stored**. The page works them out from today's date each time it loads. To preview another day, add `?today=YYYY-MM-DD` to the URL.

## Updating data.json

Top level: `{ "updated": "YYYY-MM-DD", "movies": [...], "shows": [...] }`. Bump `updated` whenever you edit.

All dates are US release dates in `YYYY-MM-DD`. Use `null` for anything unknown. Don't guess; a missing date just shows as "TBA".

### Movie

```json
{
  "title": "Toy Story 5",
  "year": 2026,
  "theatrical": "2026-06-19",
  "worldwideGross": 1140000000,
  "genre": "Animation / Family",
  "digital": "2026-08-18",
  "physical": "2026-09-22",
  "streaming": { "service": "Disney+", "date": "2026-09-23" },
  "notes": ""
}
```

- `worldwideGross`: a plain USD number (`1140000000`, not `"$1.14B"`), or `null`.
- `streaming`: `null` if no streaming date has been announced.
- Optional `alsoStreaming`: `[{ "service": "MGM+", "date": "2026-06-18" }]` for a second streaming window. It counts for the "Streaming" status and the service filter.

How the status is chosen: Streaming (a streaming date has passed) → Digital → 4K/Blu-ray → "Coming home <date>" (only future dates known) → "In cinemas" (no home dates at all).

### Show

```json
{
  "title": "The Diplomat",
  "season": 4,
  "service": "Netflix",
  "premiere": "2026-10-15",
  "finale": null,
  "pattern": "binge",
  "episodes": 8,
  "genre": "Political thriller",
  "chartRank": { "service": "Netflix", "rank": 3, "asOf": "2026-10-22" },
  "notes": ""
}
```

- `season`: a number (shown as "S4"), `"Limited"`, another label such as `"Part 4"`, or `null`.
- `pattern`: `"binge"`, `"weekly"` or `null` (unknown).
- `chartRank`: `null` unless the show is on a streaming service's top-10 chart.

How the status is chosen:

- **All episodes out**: binge and the premiere has passed, or the finale has passed.
- **Airing weekly** / **Now airing**: premiered, not binge, and the finale is unknown or still ahead. "Airing weekly" only appears when `pattern` is `"weekly"`. With `pattern: null` the card says "Now airing · release pattern unknown" so it doesn't claim a schedule nobody gave it.
- **Coming <date>**: premiere is in the future.
- **Streaming now**: no premiere date, but it has a `chartRank`, so it must be out.
- **NEW** ribbon: premiered in the last 14 days.
- A "Next ep (est.)" hint shows only for weekly shows whose episode count or finale is known. It assumes one episode a week from the premiere.

### Posters (optional, movies and shows)

Add `"poster": "https://..."` to any movie or show to show a thumbnail on its card. It must be a direct link to an image file, and only `https://` URLs are used. Leave the field out or set it to `null` to keep the plain gradient card. If an image fails to load (wrong link, or the host blocks hotlinking), the card falls back to the gradient by itself.

To find a poster on TMDB, open the title's page, click the poster, and copy the image address. It looks like `https://image.tmdb.org/t/p/w342/<file>.jpg`; `w342` is a good size for the cards. Images are requested without a referrer.

### Services

The service filter knows: Netflix, Disney+, Prime Video, HBO Max, Apple TV, Peacock, Paramount+, Starz, MGM+. Use those exact spellings. To add one, add it to `SERVICES` in `index.html` and in `sync-fallback.py`.

### After editing

```bash
python3 sync-fallback.py
```

This checks the dates, services and patterns in `data.json` and stops if any are wrong. If they're fine, it refreshes the inline copy in `index.html`. On GitHub Pages the page always reads `data.json` itself, so the inline copy only matters for `file://`. Running the script is still the easiest way to catch typos.

## Layout

Each group ("Watch now", "Coming soon") is a row of poster tiles that scrolls sideways: swipe on phones, arrow buttons or trackpad on desktop. Tap a tile for the full details: badges, release timeline, notes and the JustWatch link. On phones this opens as a bottom sheet.

Tap **＋ Interested** on a title's detail panel, or on the featured title, to save it. Saved titles show a ✓ on their poster and appear in an **Interested** row at the top, newest first. That row follows the current tab, search and service filter. Picks are kept in the browser's `localStorage` (key `tmh-interested`). They stay on that device and browser only, and survive `data.json` updates because they're stored by title. If you rename a title in `data.json`, it drops out of the row. If the browser blocks storage (some private modes), the button still works for the visit but nothing is remembered.

Tap **Mark watched** to hide a title. It disappears from every row, the Interested row and the featured spot. It's parked in a collapsed **Watched** section at the bottom of the page; open that section and tap a title to un-mark it. Watched picks are stored the same way, under the key `tmh-watched`. A title can be both Interested and Watched. Un-marking it as watched puts it back in the Interested row.

When no search or filter is active (or only My services), a featured title sits at the top. It's the first "Watch now" title under the current sort: movies on the All and Movies tabs, shows on the Shows tab.

**New this week** lists movies that came home (digital, streaming or 4K/Blu-ray) and shows that premiered in the last 7 days, newest first. It's hidden while an availability chip is on.

**🎲 Surprise me** (top right) opens a random title you can watch at home today. It follows the current tab and service filter, skips anything marked watched, and never picks the same title twice in a row. With a service filter on, a movie only counts if it is streaming on that service today. Tap **Pick another** for a new pick.

**My services…** lets you tick the services you subscribe to (saved under `tmh-services`). Once set, the page opens filtered to "My services"; Clear filters shows everything.

**Calendar** tab: every dated release step (US cinemas, digital, streaming, 4K/Blu-ray, premieres, finales) from a week ago to 60 days ahead, grouped by day. **＋ Cal**, and **📅 Remind me** on a detail panel, download an all-day `.ics` file you open to add the date to your own calendar. "✓ Interested only" narrows the calendar to your picks.

**Sharing:** opening a title puts it in the URL (for example `#m/Toy%20Story%205`), so the link opens straight to that title. **Share** on the detail panel uses the phone's share sheet, or copies the link on desktop. Press `/` to jump to search.

## Daily refresh

- **In the page:** statuses are worked out from today's date. An open page re-renders by itself when the local day rolls over. It also re-checks `data.json` hourly and whenever you switch back to the tab, then shows a "New listings loaded" notice if anything changed. The header shows how old the data is; after 3 days it turns amber.
- **The data:** a GitHub Actions workflow in this repo (`.github/workflows/daily-refresh.yml`) runs `refresh.py` every day at 06:30 Hong Kong time, then validates and commits. Release dates and grosses stay manual (see "Updating data.json" above). Open pages pick up any change within the hour.

### What the daily workflow changes

`refresh.py` uses only official sources that need no API key, and changes only what it can match exactly:

1. **Netflix chart ranks** come from Netflix's official Top 10 file (`all-weeks-global.tsv`, the global weekly TV lists, published on Tuesdays for the week ending Sunday). Newer data always wins: a rank you entered with a later `asOf` date is not replaced by an older Netflix week. A show that drops out of the official list has its rank cleared. Ranks record which chart they came from in `chartRank.chart`.
2. **New Netflix hits:** shows that enter the official global weekly top 5 (English TV) and aren't already listed are added with `"source": "netflix-top10"`. Fields Netflix doesn't publish (premiere date, genre, pattern) are left `null`. These auto-added shows are removed 21 days after they were last in the chart (`lastCharted`). Shows you add by hand are never removed automatically.
3. **Other services' ranks** (Prime Video etc.) are cleared once their `asOf` is more than 21 days old, since there is no official feed to refresh them from.
4. **Missing posters** are filled from TMDB only when exactly one entry matches the exact title and type, plus the year (movies) or the network (shows), and the image loads.
5. It sets `autoUpdated` to the day it ran. The page shows this as "charts checked …", while `updated` remains the date you last checked release dates by hand.

Every run writes a report to the workflow's summary page (Actions tab → Daily data refresh → a run). The report lists what changed and a **Needs a human** list: films in cinemas for over 45 days with no home dates, shows with no premiere date, missing posters, and release dates not hand-checked for over a week. Each commit (`Daily refresh YYYY-MM-DD: …`) lists every change with its source. Revert a commit to undo a day.

To run it now: Actions tab → **Daily data refresh** → **Run workflow**. Locally: `python3 refresh.py --dry-run` shows what it would change without writing anything.

GitHub pauses scheduled workflows in a public repo after 60 days without activity. The workflow commits every day (at least the `autoUpdated` date), which counts as activity, so this shouldn't happen. If it ever stops, re-enable it in the Actions tab.

## Sorting

- **Hot** (default): movies by worldwide gross; shows by chart rank, then latest premiere.
- **Newest**: movies by theatrical date; shows by premiere.
- **Recently released** (labelled "Recently came home" on the Movies tab and "Recently premiered" on the Shows tab): movies by their latest home release so far; shows by premiere.
- In every "Coming soon" row, titles are listed soonest first. Movies still in cinemas with no home date come last.

## Running locally

```bash
python3 -m http.server 8000
```

Then open http://localhost:8000. You can also double-click `index.html`; it falls back to the inline copy.

## Deploying to GitHub Pages

1. Create a GitHub repo and push `index.html`, `data.json` and `README.md` to the `main` branch, at the repo root.
2. In the repo, go to **Settings → Pages → Build and deployment**, set **Source: Deploy from a branch**, then pick **Branch: `main`**, folder **`/ (root)`**, and save.
3. After a minute the site is live at `https://<user>.github.io/<repo>/`.
4. To update, edit `data.json` (the GitHub web editor works), commit, and Pages redeploys. The page fetches `data.json` with `no-cache`, so a normal refresh shows the new data.

Any other static host (Netlify, Cloudflare Pages, S3) works the same way: upload the files as they are.
