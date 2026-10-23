# TMH · 睇咩好？

"What's good to watch?" A static one-page site showing what's hot in movies and TV, and whether each title can be watched at home yet.

- `index.html`: the whole app (HTML/CSS/JS, no build step, no external requests except JustWatch links).
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

### Services

The service filter knows: Netflix, Disney+, Prime Video, HBO Max, Apple TV, Peacock, Paramount+, Starz, MGM+. Use those exact spellings. To add one, add it to `SERVICES` in `index.html` and in `sync-fallback.py`.

### After editing

```bash
python3 sync-fallback.py
```

This checks the dates, services and patterns in `data.json` and stops if any are wrong. If they're fine, it refreshes the inline copy in `index.html`. On GitHub Pages the page always reads `data.json` itself, so the inline copy only matters for `file://`. Running the script is still the easiest way to catch typos.

## Sorting

- **Hot** (default): movies by worldwide gross; shows by chart rank, then latest premiere.
- **Newest**: movies by theatrical date; shows by premiere.
- **Recently came home / premiered**: movies by their latest home release so far; shows by premiere.
- In every "Coming soon" group, titles are listed soonest first. Movies still in cinemas with no home date come last.

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
