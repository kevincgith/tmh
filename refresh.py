#!/usr/bin/env python3
"""Daily data refresh for TMH. Run by .github/workflows/daily-refresh.yml, or by hand.

Uses only official, key-free sources, and only changes what it can match exactly:
  1. Netflix chart ranks from Netflix's official Top 10 (global weekly TV lists).
     Newer data wins: a rank is never replaced by an older week's.
  2. Netflix shows entering the official global weekly Top 5 (TV, English) are added with
     "source": "netflix-top10"; they are retired 21 days after they last charted.
  3. Chart ranks from other services are cleared once they are more than 21 days old.
  4. Missing posters are filled from TMDB when exactly one entry matches the title, the type,
     and the movie's year or the show's network.
Release dates and grosses are never touched; those stay manual.

It sets "autoUpdated" to today's Hong Kong date, writes a Markdown report and a commit message.

Usage: python3 refresh.py [--report report.md] [--commit-msg commit.txt] [--dry-run] [--no-tmdb]
"""
import argparse
import csv
import datetime as dt
import html
import io
import json
import pathlib
import re
import subprocess
import sys
import unicodedata
import urllib.parse
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent
NETFLIX_TSV = "https://www.netflix.com/tudum/top10/data/all-weeks-global.tsv"
NETFLIX_PAGES = ["https://www.netflix.com/tudum/top10/tv", "https://www.netflix.com/tudum/top10/tv-non-english"]
UA = "Mozilla/5.0 (compatible; TMH-refresh; +https://github.com/kevincgith/tmh)"
STALE_DAYS = 21
AUTO_ADD_TOP = 5
# TMDB network names accepted for each service when matching a show's poster.
NETWORKS = {
    "Netflix": {"Netflix"},
    "Disney+": {"Disney+"},
    "Prime Video": {"Prime Video", "Amazon Prime Video", "Amazon"},
    "HBO Max": {"HBO", "HBO Max", "Max"},
    "Apple TV": {"Apple TV", "Apple TV+"},
    "Peacock": {"Peacock"},
    "Paramount+": {"Paramount+", "Paramount+ with Showtime", "CBS", "Showtime"},
    "Starz": {"Starz", "STARZ"},
    "MGM+": {"MGM+", "EPIX"},
}


def today_hk():
    return dt.datetime.now(ZoneInfo("Asia/Hong_Kong")).date()


def days(iso):
    return dt.date.fromisoformat(iso)


def norm(s):
    s = unicodedata.normalize("NFKD", html.unescape(s)).lower().replace("&", "and")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def fetch(url, timeout=60):
    """curl rather than urllib: some sites reject Python's TLS fingerprint."""
    out = subprocess.run(["curl", "-sfL", "--max-time", str(timeout), "-A", UA, "-H", "Accept-Language: en-US", url],
                         capture_output=True)
    if out.returncode != 0:
        raise RuntimeError(f"fetch failed ({out.returncode}): {url}")
    return out.stdout


# ---------- data.json in its house style: one object per line ----------
def ser(v):
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{json.dumps(k, ensure_ascii=False)}: {ser(x)}" for k, x in v.items()) + " }"
    if isinstance(v, list):
        return "[" + ", ".join(ser(x) for x in v) + "]"
    return json.dumps(v, ensure_ascii=False)


def dump(data):
    lines = ["{"]
    top = [k for k in data if k not in ("movies", "shows")]
    for k in top:
        lines.append(f"  {json.dumps(k)}: {ser(data[k])},")
    for key in ("movies", "shows"):
        lines.append(f'  "{key}": [')
        items = data.get(key, [])
        for i, item in enumerate(items):
            lines.append("    " + ser(item) + ("," if i < len(items) - 1 else ""))
        lines.append("  ]" + ("," if key == "movies" else ""))
    lines.append("}")
    return "\n".join(lines) + "\n"


# ---------- Netflix official Top 10 ----------
def season_of(season_title):
    m = re.search(r"Season (\d+)", season_title or "")
    if m:
        return int(m.group(1))
    if "Limited Series" in (season_title or ""):
        return "Limited"
    return None


def season_compatible(ours, theirs):
    if ours is None or theirs is None:
        return True
    return ours == theirs


def js_unescape(s):
    """Decode the escapes of a single-quoted JavaScript string literal."""
    simple = {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f", "v": "\v", "0": "\0"}

    def sub(m):
        e = m.group(1)
        if e[0] in "xu":
            return chr(int(e[1:], 16))
        return simple.get(e, e)
    return re.sub(r"\\(x[0-9a-fA-F]{2}|u[0-9a-fA-F]{4}|.)", sub, s, flags=re.S)


def netflix_page_data(page):
    """Netflix embeds the page's data as netflix.reactContext.models.graphql = JSON.parse('...')."""
    m = re.search(r"models\.graphql\s*=\s*JSON\.parse\('((?:[^'\\]|\\.)*)'\)", page, re.S)
    if not m:
        raise ValueError("embedded page data not found")
    return json.loads(js_unescape(m.group(1)))["data"]


def netflix_page_rows(url):
    """Rows (same shape as the TSV) plus single-season premiere dates from a Netflix Top 10 web page.

    Netflix publishes the weekly lists on these pages before the downloadable TSV catches up.
    """
    data = netflix_page_data(fetch(url).decode("utf-8"))
    labels = {"ENGLISH_SERIES": "TV (English)", "NONENGLISH_SERIES": "TV (Non-English)"}
    rows, premieres = [], {}
    for key, obj in data.items():
        if not key.startswith("PulseTop10ItemEntity:") or not isinstance(obj, dict):
            continue
        t10, vid = obj.get("top10") or {}, obj.get("top10Video") or {}
        if t10.get("category") not in labels:
            continue
        show = ((vid.get("parentShow") or {}).get("title") or vid.get("title") or "").strip()
        rows.append({"week": t10["weekEndDate"], "category": labels[t10["category"]], "weekly_rank": str(t10["weeklyRank"]),
                     "show_title": show, "season_title": vid.get("title") or ""})
        # Series availability start = premiere only when the show has a single season.
        parent = ((obj.get("displayVideo") or {}).get("video") or {}).get("parentShow") or {}
        start = parent.get("availabilityStartTime")
        if start and (parent.get("seasons") or {}).get("totalCount") == 1:
            utc = dt.datetime.fromisoformat(start.replace("Z", "+00:00"))
            premieres[norm(show)] = utc.astimezone(ZoneInfo("America/Los_Angeles")).date().isoformat()
    return rows, premieres


def netflix_week(log, errors):
    """The newest official week across the TSV and the Top 10 pages, and single-season premiere dates."""
    rows, premieres, sources = [], {}, {}
    try:
        tsv = [r for r in csv.DictReader(io.StringIO(fetch(NETFLIX_TSV).decode("utf-8")), delimiter="\t")
               if r["category"].startswith("TV")]
        rows += tsv
        sources[NETFLIX_TSV] = max(r["week"] for r in tsv)
    except Exception as e:  # noqa: BLE001
        errors.append(f"Netflix TSV unavailable: {e}")
    for url in NETFLIX_PAGES:
        try:
            page_rows, page_premieres = netflix_page_rows(url)
            rows += page_rows
            premieres.update(page_premieres)
            if page_rows:
                sources[url] = max(r["week"] for r in page_rows)
        except Exception as e:  # noqa: BLE001
            errors.append(f"Netflix page unavailable ({url}): {e}")
    if not rows:
        raise RuntimeError("no Netflix Top 10 source could be read")
    latest = max(r["week"] for r in rows)
    week, seen = [], set()
    for r in rows:  # the same entry can come from both the TSV and a page
        k = (r["category"], r["weekly_rank"])
        if r["week"] == latest and k not in seen:
            seen.add(k)
            week.append(r)
    for src, wk in sources.items():
        log.append(f"Netflix source {src}: latest week ending {wk}.")
    return latest, week, premieres, [s for s, wk in sources.items() if wk == latest]


def apply_netflix(data, today, log, attention, errors):
    latest, week, premieres, srcs = netflix_week(log, errors)
    source = " / ".join(srcs)
    log.append(f"Netflix official Top 10: latest week ending {latest} ({len(week)} TV entries).")
    # Netflix publishes on Tuesdays for the week ending the previous Sunday, so data over 9 days old means a stall.
    if (today - days(latest)).days > 9:
        attention.append(f"Netflix's newest published week ends {latest}, over 9 days ago. Check whether the Top 10 sources moved.")
    shows = data["shows"]
    matched = set()
    for s in shows:
        if s.get("service") != "Netflix":
            continue
        hit = next((r for r in week if norm(r["show_title"]) == norm(s["title"])
                    and season_compatible(s.get("season"), season_of(r["season_title"]))), None)
        cur = s.get("chartRank")
        prem = premieres.get(norm(s["title"]))
        if prem and not s.get("premiere") and s.get("season") in (None, 1, "Limited"):
            s["premiere"] = prem
            log.append(f"{s['title']}: premiere {prem} (Netflix availability start, US Pacific date). Source: {source}")
        if hit:
            matched.add(id(hit))
            new = {"service": "Netflix", "rank": int(hit["weekly_rank"]), "asOf": latest,
                   "chart": "Official global weekly · " + hit["category"]}
            if s.get("source") == "netflix-top10":
                s["lastCharted"] = latest
            if cur and cur.get("asOf", "") > latest:
                continue  # existing rank is newer than Netflix's latest published week
            if cur != new:
                old = f"#{cur['rank']} as of {cur['asOf']}" if cur else "none"
                s["chartRank"] = new
                log.append(f"{s['title']}: Netflix rank {old} -> #{new['rank']} ({hit['category']}, week ending {latest}). "
                           f"Source: {source}")
        elif cur and cur.get("service") == "Netflix" and cur.get("asOf", "") < latest:
            s["chartRank"] = None
            log.append(f"{s['title']}: left Netflix's official Top 10 (week ending {latest}); rank cleared.")

    # Add new entries from the global weekly Top N, English TV.
    existing = {norm(s["title"]) for s in shows}
    for r in week:
        if id(r) in matched or r["category"] != "TV (English)" or int(r["weekly_rank"]) > AUTO_ADD_TOP:
            continue
        if norm(r["show_title"]) in existing:
            continue  # same title on another service, or a different season: leave for a human
        show = {
            "title": r["show_title"], "season": season_of(r["season_title"]), "service": "Netflix",
            "premiere": premieres.get(norm(r["show_title"])), "finale": None, "pattern": None, "episodes": None, "genre": None,
            "chartRank": {"service": "Netflix", "rank": int(r["weekly_rank"]), "asOf": latest,
                          "chart": "Official global weekly · " + r["category"]},
            "notes": "Added automatically from Netflix's official Top 10.",
            "source": "netflix-top10", "lastCharted": latest,
        }
        shows.append(show)
        existing.add(norm(r["show_title"]))
        log.append(f"Added {r['show_title']} (#{r['weekly_rank']} Netflix TV (English), week ending {latest}). "
                   f"Source: {source}")
        attention.append(f"{r['show_title']}: added from the Netflix chart; genre and pattern unknown"
                         + ("." if show["premiere"] else ", premiere date unknown."))

    # Retire auto-added shows that have been off the chart for 3 weeks.
    keep = []
    for s in shows:
        last = s.get("lastCharted")
        if s.get("source") == "netflix-top10" and last and (days(latest) - days(last)).days >= STALE_DAYS:
            log.append(f"Retired {s['title']} (auto-added; last in Netflix's Top 10 week ending {last}).")
            continue
        keep.append(s)
    data["shows"] = keep


def clear_stale_ranks(data, today, log):
    for s in data["shows"]:
        cr = s.get("chartRank")
        if cr and cr.get("service") != "Netflix" and (today - days(cr["asOf"])).days > STALE_DAYS:
            s["chartRank"] = None
            log.append(f"{s['title']}: {cr['service']} rank #{cr['rank']} as of {cr['asOf']} is over {STALE_DAYS} days old; cleared.")


# ---------- TMDB posters ----------
def tmdb_search(kind, title):
    page = fetch(f"https://www.themoviedb.org/search/{kind}?query={urllib.parse.quote(title)}").decode("utf-8")
    out = []
    for chunk in page.split("comp:media-card ")[1:]:
        mt = re.search(r'data-media-type="(\w+)"[^>]*href="(/(?:movie|tv)/[^"]+)"', chunk)
        t = re.search(r"<h2[^>]*><span>(.*?)</span>", chunk)
        d = re.search(r"</h2></a><span[^>]*>([^<]*)</span>", chunk)
        f = re.search(r"/t/p/w\d+_and_h\d+_face/([A-Za-z0-9]+\.(?:jpg|png))", chunk)
        if mt and t and mt.group(1) == kind:
            yr = re.search(r"(\d{4})", d.group(1)) if d else None
            out.append({"href": mt.group(2), "title": html.unescape(t.group(1)),
                        "year": int(yr.group(1)) if yr else None, "file": f.group(1) if f else None})
    return out


def tmdb_networks(href):
    page = fetch("https://www.themoviedb.org" + href).decode("utf-8")
    return {html.unescape(n) for n in re.findall(r'alt="See more TV shows from ([^"]+?)\.\.\."', page)}


def image_ok(url):
    out = subprocess.run(["curl", "-sI", "-o", "/dev/null", "-w", "%{http_code} %{content_type}", "--max-time", "30", url],
                         capture_output=True, text=True)
    return out.stdout.startswith("200 image/")


def fill_posters(data, log, attention):
    for kind, key in (("movie", "movies"), ("tv", "shows")):
        for item in data[key]:
            if item.get("poster"):
                continue
            title = item["title"]
            try:
                hits = [h for h in tmdb_search(kind, title) if norm(h["title"]) == norm(title) and h["file"]]
                if kind == "movie":
                    hits = [h for h in hits if h["year"] == item.get("year")]
                else:
                    want = NETWORKS.get(item.get("service"), set())
                    hits = [h for h in hits if tmdb_networks(h["href"]) & want]
            except RuntimeError as e:
                log.append(f"TMDB lookup skipped for {title}: {e}")
                continue
            if len(hits) != 1:
                attention.append(f"{title}: no poster ({len(hits)} TMDB matches on title, type and "
                                 f"{'year' if kind == 'movie' else 'network'}).")
                continue
            url = "https://image.tmdb.org/t/p/w342/" + hits[0]["file"]
            if not image_ok(url):
                attention.append(f"{title}: TMDB poster did not load ({url}).")
                continue
            item["poster"] = url
            log.append(f"{title}: poster added from TMDB https://www.themoviedb.org{hits[0]['href']}")


# ---------- things only a human can fix ----------
def review(data, today, attention):
    up = data.get("updated")
    if up and (today - days(up)).days > 7:
        attention.append(f"Release dates were last checked by hand on {up} ({(today - days(up)).days} days ago).")
    for m in data["movies"]:
        home = [m.get("digital"), m.get("physical")] + [s.get("date") for s in [m.get("streaming")] + (m.get("alsoStreaming") or []) if s]
        if m.get("theatrical") and not any(home) and (today - days(m["theatrical"])).days > 45:
            attention.append(f"{m['title']}: in cinemas since {m['theatrical']} with no home release dates; check for announcements.")
    for s in data["shows"]:
        if not s.get("premiere") and not s.get("chartRank") and s.get("source") != "netflix-top10":
            attention.append(f"{s['title']}: no premiere date and not charting.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", default=None)
    ap.add_argument("--commit-msg", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-tmdb", action="store_true")
    args = ap.parse_args()

    path = ROOT / "data.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    today = today_hk()
    log, attention, errors = [], [], []

    try:
        apply_netflix(data, today, log, attention, errors)
    except Exception as e:  # noqa: BLE001 - a failed source must not block the other steps
        errors.append(f"Netflix Top 10 step failed: {e}")
    clear_stale_ranks(data, today, log)
    if not args.no_tmdb:
        fill_posters(data, log, attention)
    review(data, today, attention)

    # Keep autoUpdated next to "updated" at the top of the file.
    ordered = {"updated": data.get("updated"), "autoUpdated": today.isoformat()}
    ordered.update({k: v for k, v in data.items() if k not in ordered})

    changes = [l for l in log if not l.startswith(("Netflix official Top 10:", "Netflix source ", "TMDB lookup skipped"))]
    report = [f"# TMH daily refresh {today.isoformat()}", "",
              "## Changes", *(f"- {c}" for c in changes or ["No listing changes."]), "",
              "## Notes", *(f"- {l}" for l in log if l not in changes), *(f"- ⚠️ {e}" for e in errors), "",
              "## Needs a human", *(f"- {a}" for a in attention or ["Nothing flagged."]), ""]
    msg = [f"Daily refresh {today.isoformat()}: " + (f"{len(changes)} change(s)" if changes else "no listing changes"),
           "", *changes, *([""] + errors if errors else [])]

    print("\n".join(report))
    if args.report:
        pathlib.Path(args.report).write_text("\n".join(report), encoding="utf-8")
    if args.commit_msg:
        pathlib.Path(args.commit_msg).write_text("\n".join(msg) + "\n", encoding="utf-8")
    if not args.dry_run:
        path.write_text(dump(ordered), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
