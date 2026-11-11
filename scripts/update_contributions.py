#!/usr/bin/env python3
"""Refresh the terminal-style contribution trace and profile telemetry.

The GitHub profile page exposes the contribution calendar as an HTML fragment.
This script reads that fragment, keeps the same 53 week grid, and writes a
self-contained SVG that matches the rest of the profile assets.

Standard library only. Run from the repository root or let the workflow do it.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import re
import sys
import urllib.request
from pathlib import Path

USERNAME = "imran407704"
ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "assets" / "contributions.svg"
UA = "imran407704-profile-recon/1.0"

LEVEL_COLORS = {
    0: "#0b1f16",
    1: "#0e3b27",
    2: "#0a6b45",
    3: "#00b36b",
    4: "#00ff9c",
}
LEVEL_LABELS = [0, 1, 2, 3, 4]
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def fetch(url: str, *, ajax: bool = False) -> str:
    headers = {"User-Agent": UA, "Accept": "text/html,application/json"}
    if ajax:
        headers["X-Requested-With"] = "XMLHttpRequest"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch_json(url: str) -> dict:
    return json.loads(fetch(url))


def contribution_days() -> dict[dt.date, int]:
    page = fetch(f"https://github.com/{USERNAME}")
    match = re.search(r'src="([^"]*controller=profiles[^"]*tab=contributions[^"]*)"', page)
    if not match:
        raise RuntimeError("contribution fragment not found on the profile page")

    fragment_url = html.unescape(match.group(1))
    if fragment_url.startswith("/"):
        fragment_url = "https://github.com" + fragment_url
    fragment = fetch(fragment_url, ajax=True)

    days: dict[dt.date, int] = {}
    for tag in re.findall(r"<td\b[^>]*ContributionCalendar-day[^>]*>", fragment):
        date_match = re.search(r'data-date="(\d{4}-\d{2}-\d{2})"', tag)
        level_match = re.search(r'data-level="([0-4])"', tag)
        if date_match and level_match:
            days[dt.date.fromisoformat(date_match.group(1))] = int(level_match.group(1))
    if not days:
        raise RuntimeError("no contribution cells found in the fragment")
    return days


def telemetry() -> dict[str, int]:
    user = fetch_json(f"https://api.github.com/users/{USERNAME}")
    repos = fetch_json(f"https://api.github.com/users/{USERNAME}/repos?per_page=100&type=owner")
    stars = sum(int(repo.get("stargazers_count", 0)) for repo in repos if not repo.get("fork"))
    return {
        "repos": int(user.get("public_repos", 0)),
        "followers": int(user.get("followers", 0)),
        "stars": stars,
    }


def build_svg(days: dict[dt.date, int], stats: dict[str, int]) -> str:
    last = max(days)
    start = last - dt.timedelta(days=364)
    # GitHub weeks start on Sunday. The final week may be partial.
    start -= dt.timedelta(days=(start.weekday() + 1) % 7)
    weeks = (last - start).days // 7 + 1
    cell, gap = 12, 3
    step = cell + gap
    chart_x, chart_y = 96, 88
    chart_w = weeks * step - gap
    chart_h = 7 * step - gap

    cells: list[str] = []
    month_marks: list[tuple[int, str]] = []
    seen_months: set[tuple[int, int]] = set()
    day_labels = [(1, "MON"), (3, "WED"), (5, "FRI")]

    for week in range(weeks):
        for weekday in range(7):
            date = start + dt.timedelta(days=week * 7 + weekday)
            if date > last:
                continue
            level = days.get(date, 0)
            x = chart_x + week * step
            y = chart_y + weekday * step
            cells.append(
                f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" '
                f'fill="{LEVEL_COLORS[level]}"><title>{date.isoformat()} · level {level}</title></rect>'
            )
            if weekday == 0:
                key = (date.year, date.month)
                if key not in seen_months:
                    seen_months.add(key)
                    month_marks.append((week, MONTHS[date.month - 1]))

    month_text = "".join(
        f'<text x="{chart_x + week * step}" y="72" font-family="\'Fira Code\',Menlo,Consolas,monospace" '
        f'font-size="8" letter-spacing="1" fill="#4a6b5d">{name}</text>'
        for week, name in month_marks
    )
    day_text = "".join(
        f'<text x="{chart_x - 12}" y="{chart_y + weekday * step + 9}" text-anchor="end" '
        f'font-family="\'Fira Code\',Menlo,Consolas,monospace" font-size="8" fill="#4a6b5d">{label}</text>'
        for weekday, label in day_labels
    )
    legend_x = chart_x + 34
    legend = "".join(
        f'<rect x="{legend_x + index * 18}" y="{chart_y + chart_h + 18}" width="12" height="12" rx="2" '
        f'fill="{LEVEL_COLORS[level]}"/>'
        for index, level in enumerate(LEVEL_LABELS)
    )

    stat_blocks = [
        ("REPOS", stats["repos"]),
        ("FOLLOWERS", stats["followers"]),
        ("STARS", stats["stars"]),
    ]
    stat_y = 96
    stat_svg = []
    for index, (label, value) in enumerate(stat_blocks):
        y = stat_y + index * 48
        stat_svg.append(
            f'<text x="962" y="{y}" font-family="\'Fira Code\',Menlo,Consolas,monospace" '
            f'font-size="8" letter-spacing="1.8" fill="#4a6b5d">{label}</text>'
            f'<text x="962" y="{y + 25}" font-family="\'Fira Code\',Menlo,Consolas,monospace" '
            f'font-size="26" font-weight="700" fill="#00ff9c">{value}</text>'
        )
        if index < len(stat_blocks) - 1:
            stat_svg.append(
                f'<line x1="962" y1="{y + 34}" x2="1150" y2="{y + 34}" stroke="#123b2a"/>'
            )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="248" viewBox="0 0 1200 248" role="img" aria-labelledby="ct ctDesc">
  <title id="ct">Contribution trace for {USERNAME}</title>
  <desc id="ctDesc">A terminal styled contribution calendar for the last year, with repository, follower and star counts.</desc>
  <defs>
    <linearGradient id="cpanel" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#08140e"/>
      <stop offset="1" stop-color="#040806"/>
    </linearGradient>
    <pattern id="cscan" width="4" height="4" patternUnits="userSpaceOnUse">
      <rect width="4" height="1" fill="#000000" opacity=".18"/>
    </pattern>
  </defs>
  <rect x="24" y="16" width="1152" height="216" rx="12" fill="url(#cpanel)" stroke="#123b2a" stroke-width="1.5"/>
  <path d="M42 42V28h24" fill="none" stroke="#00ff9c" stroke-opacity=".35" stroke-width="2"/>
  <path d="M1158 42V28h-24" fill="none" stroke="#00ff9c" stroke-opacity=".35" stroke-width="2"/>
  <rect x="52" y="36" width="6" height="6" fill="#00ff9c"/>
  <text x="68" y="43" font-family="'Fira Code',Menlo,Consolas,monospace" font-size="10" letter-spacing="2" fill="#00ff9c">CONTRIBUTION_TRACE</text>
  <text x="1148" y="43" text-anchor="end" font-family="'Fira Code',Menlo,Consolas,monospace" font-size="9" letter-spacing="1.4" fill="#4a6b5d">LAST 365 DAYS // 0x407704</text>
  <line x1="52" y1="56" x2="1148" y2="56" stroke="#123b2a"/>
  {month_text}
  {day_text}
  {''.join(cells)}
  <text x="{chart_x}" y="{chart_y + chart_h + 27}" font-family="'Fira Code',Menlo,Consolas,monospace" font-size="8" letter-spacing="1" fill="#4a6b5d">LESS</text>
  {legend}
  <text x="{legend_x + 5 * 18 + 8}" y="{chart_y + chart_h + 27}" font-family="'Fira Code',Menlo,Consolas,monospace" font-size="8" letter-spacing="1" fill="#4a6b5d">MORE</text>
  <line x1="930" y1="76" x2="930" y2="202" stroke="#123b2a"/>
  {''.join(stat_svg)}
  <text x="1156" y="228" text-anchor="end" font-family="'Fira Code',Menlo,Consolas,monospace" font-size="8" letter-spacing="1" fill="#3f5c50">SYNC {last.isoformat()}</text>
  <rect x="24" y="16" width="1152" height="216" rx="12" fill="url(#cscan)" opacity=".5"/>
</svg>
'''


def main() -> int:
    try:
        days = contribution_days()
        stats = telemetry()
    except Exception as error:  # keep the last good SVG when GitHub rate limits us
        print(f"update skipped: {error}", file=sys.stderr)
        return 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(build_svg(days, stats), encoding="utf-8")
    print(f"wrote {OUTPUT} ({len(days)} days, {stats})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
