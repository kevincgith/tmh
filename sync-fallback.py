#!/usr/bin/env python3
"""Check data.json and copy it into index.html's inline fallback (used when opened via file://).

Usage: python3 sync-fallback.py
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SERVICES = {"Netflix", "Disney+", "Prime Video", "HBO Max", "Apple TV", "Peacock", "Paramount+", "Starz", "MGM+"}


def check(data):
    problems = []

    def date(where, v):
        if v is not None and not (isinstance(v, str) and ISO.match(v)):
            problems.append(f"{where}: bad date {v!r} (use YYYY-MM-DD or null)")

    def service(where, v):
        if v not in SERVICES:
            problems.append(f"{where}: service {v!r} is not one of the filter services")

    def poster(where, v):
        if v is not None and not (isinstance(v, str) and v.startswith("https://")):
            problems.append(f"{where}: poster must be an https:// image URL or null")

    date("updated", data.get("updated"))
    date("autoUpdated", data.get("autoUpdated"))
    for item in data.get("movies", []) + data.get("shows", []):
        poster(f"{item.get('title', '?')}.poster", item.get("poster"))
    for m in data.get("movies", []):
        t = m.get("title", "?")
        for k in ("theatrical", "digital", "physical"):
            date(f"{t}.{k}", m.get(k))
        g = m.get("worldwideGross")
        if g is not None and not isinstance(g, (int, float)):
            problems.append(f"{t}.worldwideGross: must be a number or null")
        for s in [m.get("streaming")] + (m.get("alsoStreaming") or []):
            if s is not None:
                service(f"{t}.streaming", s.get("service"))
                date(f"{t}.streaming.date", s.get("date"))
    for s in data.get("shows", []):
        t = s.get("title", "?")
        for k in ("premiere", "finale"):
            date(f"{t}.{k}", s.get(k))
        service(f"{t}.service", s.get("service"))
        if s.get("pattern") not in ("binge", "weekly", None):
            problems.append(f"{t}.pattern: must be \"binge\", \"weekly\" or null")
        cr = s.get("chartRank")
        if cr is not None:
            date(f"{t}.chartRank.asOf", cr.get("asOf"))
            if not isinstance(cr.get("rank"), int):
                problems.append(f"{t}.chartRank.rank: must be an integer")
            if "chart" in cr and not isinstance(cr["chart"], str):
                problems.append(f"{t}.chartRank.chart: must be text")
        date(f"{t}.lastCharted", s.get("lastCharted"))
        if s.get("source") not in (None, "netflix-top10"):
            problems.append(f"{t}.source: unknown value {s.get('source')!r}")
    return problems


def main():
    data = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))
    problems = check(data)
    if problems:
        print("data.json problems:\n  " + "\n  ".join(problems))
        sys.exit(1)
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html_path = ROOT / "index.html"
    html = html_path.read_text(encoding="utf-8")
    new, n = re.subn(
        r'(<script id="tmh-fallback" type="application/json">).*?(</script>)',
        lambda mo: mo.group(1) + blob + mo.group(2),
        html,
        flags=re.S,
    )
    if n != 1:
        sys.exit("Could not find the tmh-fallback block in index.html")
    html_path.write_text(new, encoding="utf-8")
    print(f"OK: {len(data['movies'])} movies, {len(data['shows'])} shows synced into index.html")


if __name__ == "__main__":
    main()
