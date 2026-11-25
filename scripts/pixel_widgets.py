"""Generate the Pixel Studio profile images. Requires Python 3.10+."""
import argparse
import base64
import calendar
import json
import os
import sys
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

LOGIN = "ProGencel"
DISPLAY_NAME = "Ahmet Efe Gençel"
DEFAULT_BIO = "Java developer. Working on Goblin-Quest right now."
OUTPUT = Path(__file__).resolve().parents[1] / "assets" / "pixel-widgets"
DAY = timedelta(days=1)
SANS = "-apple-system,BlinkMacSystemFont,'Segoe UI','Helvetica Neue',sans-serif"
MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
LEVELS = "NONE FIRST_QUARTILE SECOND_QUARTILE THIRD_QUARTILE FOURTH_QUARTILE".split()


@dataclass(frozen=True)
class Theme:
    panel: str
    border: str
    ink: str
    muted: str
    accent: str
    heat: tuple
    red_tile: str
    red: str
    green_tile: str
    green: str


THEMES = {
    "dark": Theme("#151b23", "#262c36", "#f0f6fc", "#9198a1", "#3fb950",
                  ("#1b222c", "#0e4429", "#006d32", "#26a641", "#39d353"),
                  "#4b282b", "#ff928c", "#193826", "#83cd7b"),
    "light": Theme("#f6f8fa", "#e4e8ec", "#1f2328", "#59636e", "#1a7f37",
                   ("#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"),
                   "#f5e3e0", "#ab3733", "#dcebdc", "#287342"),
}

# Original bitmap lettering and icons drawn for this project: CC0-1.0.
# https://creativecommons.org/publicdomain/zero/1.0/
# Seven rows per letter; the low five bits in each hex number are pixels.
LETTERS = {
    " ": "00 00 00 00 00 00 00", ">": "10 08 04 02 04 08 10",
    ".": "00 00 00 00 00 06 06", "A": "0e 11 11 1f 11 11 11",
    "B": "1e 11 11 1e 11 11 1e", "C": "0f 10 10 10 10 10 0f",
    "D": "1e 11 11 11 11 11 1e", "E": "1f 10 10 1e 10 10 1f",
    "F": "1f 10 10 1e 10 10 10", "G": "0f 10 10 17 11 11 0f",
    "H": "11 11 11 1f 11 11 11", "I": "0e 04 04 04 04 04 0e",
    "L": "10 10 10 10 10 10 1f", "N": "11 19 19 15 13 13 11",
    "O": "0e 11 11 11 11 11 0e", "P": "1e 11 11 1e 10 10 10",
    "R": "1e 11 11 1e 14 12 11", "T": "1f 04 04 04 04 04 04",
    "U": "11 11 11 11 11 11 0e", "X": "11 11 0a 04 0a 11 11",
}
# Social marks occupy twelve columns. A zero leaves the background visible.
ICONS = {
    "github": ("000111111000 001111111100 011011110110 110001100011 "
               "110000000011 110000000011 110000000011 111000000111 "
               "111100001111 101110011111 011000011110 001110011100"),
    "portfolio": ("111111111111 100000000001 101010000001 111111111111 "
                  "100000000001 100011000001 100110000001 100011000001 "
                  "100000111001 100000000001 111111111111"),
    "itch": ("001111111100 011111111110 111111111111 110110110011 "
             "010010010010 011111111110 011000000110 011011110110 "
             "011010010110 011010010110 011111111110"),
    "leetcode": ("000000011000 000000110000 000001100000 000011001100 "
                 "000110011000 001100110000 011001100000 011100011111 "
                 "001110000000 000111000110 000011111100"),
    "spring": ("00011111111000 00111111111100 00111100111100 01110100101110 "
               "01100100100110 11001100110011 11001111110011 11001111110011 "
               "01100111100110 01110000001110 00111111111100 00011111111000"),
}

QUERY = """query($login: String!) {
  user(login: $login) {
    login bio location company avatarUrl(size: 512) followers { totalCount }
    contributionsCollection {
      endedAt
      contributionCalendar { weeks { contributionDays {
        date weekday contributionCount contributionLevel
      } } }
    }
  }
}"""


def node(parent, tag, **attrs):
    return ET.SubElement(parent, tag, {k.replace("_", "-"): str(v) for k, v in attrs.items()})


def rect(root, x, y, w, h, fill, **attrs):
    return node(root, "rect", x=x, y=y, width=w, height=h, fill=fill, **attrs)


def text(root, x, y, value, size, color, font=SANS, **attrs):
    node(root, "text", x=x, y=y, font_family=font, font_size=size, fill=color, **attrs).text = value


def card(w, h, theme, title, radius):
    root = ET.Element("svg", {"xmlns": "http://www.w3.org/2000/svg", "width": str(w),
                      "height": str(h), "viewBox": f"0 0 {w} {h}", "role": "img",
                      "aria-labelledby": "title"})
    node(root, "title", id="title").text = title
    rect(root, .5, .5, w - 1, h - 1, theme.panel, rx=radius, stroke=theme.border)
    return root


def bitmap(root, rows, x, y, step, color):
    parts = []
    for row, bits in enumerate(rows):
        for col, bit in enumerate(bits):
            if bit == "1":
                parts.append(f"M{x+step*col} {y+step*row}h{step}v{step}h-{step}z")
    node(root, "path", d="".join(parts), fill=color, shape_rendering="crispEdges")


def pixel_text(root, value, x, y, step, color):
    letters = [LETTERS[c].split() for c in value.upper()]
    rows = ["0".join(f"{int(row, 16):05b}" for row in parts) for parts in zip(*letters)]
    bitmap(root, rows, x, y, step, color)


def social(key, theme):
    names = {"github": "GitHub", "portfolio": "Portfolio", "itch": "Itch.io", "leetcode": "LeetCode"}
    label = names[key]
    root = card(156, 38, theme, label, 8)
    x = (156 - (24 + 10 + 12 * len(label) - 2)) // 2
    bitmap(root, ICONS[key].split(), x, 8, 2, theme.accent)
    pixel_text(root, label, x + 34, 12, 2, theme.ink)
    return root


def tech(key, theme):
    game = key == "libgdx"
    label, detail = ("LibGDX", "Game development") if game else ("Spring Boot", "Backend development")
    root = card(216, 64, theme, label, 10)
    rect(root, 12, 10, 44, 44, theme.red_tile if game else theme.green_tile, rx=6)
    if game:
        pixel_text(root, "GDX", 17, 25, 2, theme.red)
    else:
        bitmap(root, ICONS["spring"].split(), 20, 20, 2, theme.green)
    text(root, 68, 29, label, 15, theme.ink, MONO, font_weight=700)
    text(root, 68, 47, detail, 12, theme.muted)
    return root


def one_line(value):
    clean = "".join(ch for ch in (value or "") if ch.isprintable() or ch.isspace())
    return " ".join(clean.split())


def profile_lines(value, size, mono=False):
    """Wrap the text left of the portrait. The SVG description keeps the full value."""
    lines = []
    while value and len(lines) < 2:
        width = 0
        for index, ch in enumerate(value):
            if unicodedata.east_asian_width(ch) in ("W", "F"):
                em = 1.12
            elif mono:
                em = .64
            elif ch in "WMmw@%&" or not ch.isascii():
                em = 1.1
            elif ch.islower() or ch.isspace():
                em = .66
            else:
                em = .78
            width += size * em
            if width > 644 - (size if lines else 0):
                break
        else:
            lines.append(value)
            break
        space = value.rfind(" ", 0, index + 1)
        cut = space if space > index // 2 else index
        lines.append(value[:cut].rstrip() + ("…" if lines else ""))
        value = value[cut:].lstrip()
    return lines


def about(user, avatar, theme):
    bio = one_line(user["bio"]) or DEFAULT_BIO
    followers = user["followers"]["totalCount"]
    if type(followers) is not int or followers < 0:
        raise ValueError("Invalid follower count.")
    followers_label = f"{followers:,} follower" + ("" if followers == 1 else "s")
    meta = "  ·  ".join(filter(None, [one_line(user["location"]), one_line(user["company"]), followers_label]))
    root = card(880, 230, theme, DISPLAY_NAME, 14)
    root.set("xmlns:xlink", "http://www.w3.org/1999/xlink")
    node(root, "desc").text = f"{bio} — {meta}"
    pixel_text(root, "> ABOUT", 36, 40, 2, theme.accent)
    text(root, 36, 104, DISPLAY_NAME, 30, theme.ink, font_weight=800, letter_spacing="-.02em")
    for i, line in enumerate(profile_lines(bio, 17)):
        text(root, 36, 140 + 21*i, line, 17, theme.ink, fill_opacity=".86")
    for i, line in enumerate(profile_lines(meta, 13, mono=True)):
        text(root, 36, 190 + 16*i, line, 13, theme.muted, MONO)
    rect(root, 726, 59, 124, 124, "none", stroke=theme.ink, stroke_width=3)
    node(root, "image", x=732, y=65, width=112, height=112, preserveAspectRatio="xMidYMid slice",
         **{"xlink:href": avatar})
    return root


@dataclass(frozen=True)
class Day:
    date: date
    weekday: int
    count: int
    level: int


def year_start(end):
    last_day = calendar.monthrange(end.year - 1, end.month)[1]
    return end.replace(year=end.year - 1, day=min(end.day, last_day)) + DAY


def calendar_days(collection, now):
    stamp = datetime.fromisoformat(collection["endedAt"].replace("Z", "+00:00"))
    if stamp.utcoffset() is None:
        raise ValueError("Calendar endpoint has no time zone.")
    end = min(stamp.astimezone(timezone.utc).date(), now.astimezone(timezone.utc).date())
    start = year_start(end)
    days = {}
    for week in collection["contributionCalendar"]["weeks"]:
        for item in week["contributionDays"]:
            d = date.fromisoformat(item["date"])
            if not start <= d <= end:
                continue
            weekday, count = item["weekday"], item["contributionCount"]
            level = LEVELS.index(item["contributionLevel"])
            if (d in days or type(weekday) is not int or weekday != d.isoweekday() % 7 or type(count) is not int
                    or count < 0 or (count == 0) != (level == 0)):
                raise ValueError("Invalid contribution day or level.")
            days[d] = Day(d, weekday, count, level)
    if len(days) != (end - start).days + 1:
        raise ValueError("Incomplete contribution calendar. Run again later.")
    return [days[d] for d in sorted(days)]


def statistics(days):
    run = longest = total = active = 0
    for d in days:
        run = run + 1 if d.count else 0
        longest = max(longest, run)
        total += d.count
        active += int(d.count > 0)
    tail = days if days[-1].count else days[:-1]
    current = 0
    for d in reversed(tail):
        if not d.count:
            break
        current += 1
    return current, bool(current and current == len(tail)), longest, total, active


def short_date(d):
    return f"{MONTHS[d.month-1]} {d.day}, {d.year}"


def activity(days, theme):
    current, capped, longest, total, active = statistics(days)
    start, end = days[0].date, days[-1].date
    period = f"{short_date(start)} – {short_date(end)}"
    root = card(880, 250, theme, f"Contributions · {period}", 14)
    node(root, "desc").text = (f"{total:,} contributions on {active} days. "
        f"Current streak: {'at least ' if capped else ''}{current} days. Longest in period: {longest} days.")
    pixel_text(root, "> CALENDAR", 36, 40, 2, theme.accent)
    text(root, 844, 52, period, 12, theme.muted, MONO, text_anchor="end")
    sunday = start - days[0].weekday * DAY

    def column(d):
        return 68 + ((d - sunday).days // 7) * 10

    months = [start] + [d.date for d in days if d.date.day == 1 and d.date != start]
    if len(months) > 1 and column(months[1]) - column(start) < 26:
        months.pop(0)
    for d in months:
        text(root, column(d), 88, MONTHS[d.month-1], 11, theme.muted, MONO)
    for row, label in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        text(root, 58, 107 + 10*row, label, 10, theme.muted, MONO, text_anchor="end")
    for d in days:
        square = rect(root, column(d.date), 100 + 10*d.weekday, 8, 8, theme.heat[d.level])
        node(square, "title").text = f"{d.date.isoformat()} · {d.count} contribution" + ("" if d.count == 1 else "s")
    text(root, 68, 208, f"{active:,} active days", 13, theme.muted, MONO)
    text(root, 464, 208, "Less", 11, theme.muted, MONO)
    for i, color in enumerate(theme.heat):
        rect(root, 498 + 12*i, 199, 9, 9, color)
    text(root, 563, 208, "More", 11, theme.muted, MONO)
    def duration(n, suffix=""):
        return f"{n}{suffix} day" + ("" if n == 1 else "s")
    metrics = [("CURRENT STREAK", duration(current, "+" if capped else "")),
               ("LONGEST IN PERIOD", duration(longest)), ("CONTRIBUTIONS", f"{total:,}")]
    for i, (label, value) in enumerate(metrics):
        y = 85 + i*55
        text(root, 654, y, label, 11.5, theme.muted, MONO, letter_spacing=".08em")
        text(root, 654, y + 26, value, 22, theme.ink, font_weight=800)
    return root


def read_url(request, limit):
    with urlopen(request, timeout=30) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Response exceeds the size limit.")
    return data


def fetch_profile(token):
    if not token:
        raise ValueError("PIXEL_TOKEN is missing.")
    body = json.dumps({"query": QUERY, "variables": {"login": LOGIN}}).encode()
    request = Request("https://api.github.com/graphql", data=body, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": "pixel-widgets"})
    result = json.loads(read_url(request, 2_000_000))
    if result.get("errors"):
        raise ValueError("GitHub GraphQL returned errors. Check token access and API rate limits.")
    user = result["data"]["user"]
    if not user or user["login"].casefold() != LOGIN.casefold():
        raise ValueError("GitHub did not return the requested profile.")
    return user


def fetch_avatar(url):
    parsed = urlsplit(url)
    if (parsed.scheme, parsed.hostname) != ("https", "avatars.githubusercontent.com"):
        raise ValueError("Unexpected GitHub avatar URL.")
    data = read_url(Request(url, headers={"User-Agent": "pixel-widgets"}), 3_000_000)
    if data.startswith(b"\x89PNG\r\n\x1a\n") and data[-8:-4] == b"IEND":
        mime = "image/png"
    elif data.startswith(b"\xff\xd8\xff") and data.endswith(b"\xff\xd9"):
        mime = "image/jpeg"
    elif data[:6] in (b"GIF87a", b"GIF89a") and data.endswith(b";"):
        mime = "image/gif"
    else:
        raise ValueError("Unsupported or incomplete GitHub avatar.")
    return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")


def build(output, refresh_static=False):
    user = fetch_profile(os.environ.get("PIXEL_TOKEN"))
    days = calendar_days(user["contributionsCollection"], datetime.now(timezone.utc))
    avatar = fetch_avatar(user["avatarUrl"])
    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output) as temp:
        stage = Path(temp)
        for mode, theme in THEMES.items():
            images = {"about": about(user, avatar, theme), "activity": activity(days, theme)}
            for key in ("github", "portfolio", "itch", "leetcode", "libgdx", "spring"):
                if refresh_static or not (output / f"{key}-{mode}.svg").is_file():
                    images[key] = tech(key, theme) if key in ("libgdx", "spring") else social(key, theme)
            for name, svg in images.items():
                path = stage / f"{name}-{mode}.svg"
                ET.ElementTree(svg).write(path, encoding="utf-8", xml_declaration=True)
                ET.parse(path)
        for path in sorted(stage.iterdir()):
            target = output / path.name
            if not target.exists() or target.read_bytes() != path.read_bytes():
                path.replace(target)


def self_test():
    """Run offline with synthetic dates only. Reads and writes no profile files."""
    for end, start in ((date(2024, 2, 29), date(2023, 3, 1)),
                       (date(2025, 2, 28), date(2024, 2, 29)),
                       (date(2025, 1, 1), date(2024, 1, 2))):
        assert year_start(end) == start
    # Istanbul is already on January 2, but the returned calendar ends on January 1 UTC.
    now = datetime.fromisoformat("2025-01-02T01:20:00+03:00")
    end = date(2025, 1, 1)
    start = year_start(end)
    rows = []
    for offset in range((end-start).days + 2):
        d = start + offset * DAY
        rows.append(dict(date=d.isoformat(), weekday=d.isoweekday() % 7,
                         contributionCount=0, contributionLevel="NONE"))
    coll = {"endedAt": now.isoformat(), "contributionCalendar": {"weeks": [{"contributionDays": rows[::-1]}]}}
    days = calendar_days(coll, now)
    assert days[0].date == start and days[-1].date == end and statistics(days) == (0, False, 0, 0, 0)
    for row in rows[-5:-2]:  # Three active days through yesterday.
        row.update(contributionCount=2, contributionLevel="FIRST_QUARTILE")
    assert statistics(calendar_days(coll, now)) == (3, False, 3, 6, 3)
    rows[-2].update(contributionCount=1, contributionLevel="FIRST_QUARTILE")
    assert statistics(calendar_days(coll, now)) == (4, False, 4, 7, 4)
    for row in rows:
        row.update(contributionCount=1, contributionLevel="FIRST_QUARTILE")
    days = calendar_days(coll, now)
    assert statistics(days) == (len(days), True, len(days), len(days), len(days))
    coll["contributionCalendar"]["weeks"] = []
    try:
        calendar_days(coll, now)
    except ValueError:
        pass
    else:
        raise AssertionError("An incomplete calendar was accepted.")
    assert profile_lines("W" * 400, 17)[-1].endswith("…")
    sample = {"bio": "A & B <demo>", "company": "Bursa", "location": None,
              "followers": {"totalCount": 1}, "repositories": ["PRIVATE_SENTINEL"]}
    for theme in THEMES.values():
        ET.fromstring(ET.tostring(activity(days, theme)))
        svg = ET.tostring(about(sample, "data:image/png;base64,", theme))
        assert b"PRIVATE_SENTINEL" not in svg and b"&lt;demo&gt;" in svg
        ET.fromstring(svg)
    print("Pixel widget checks passed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-static", action="store_true", help="Redraw existing buttons and tech cards.")
    parser.add_argument("--self-test", action="store_true", help="Run offline checks without writing SVGs.")
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
        else:
            build(OUTPUT, args.refresh_static)
    except HTTPError as error:
        sys.exit(f"HTTP {error.code}: check access, rate limits and GitHub status.")
    except (URLError, TimeoutError, OSError, ValueError, TypeError, KeyError, ET.ParseError) as error:
        sys.exit(f"Widget generation failed ({type(error).__name__}): {error}")
