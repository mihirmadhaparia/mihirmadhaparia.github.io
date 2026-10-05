#!/usr/bin/env python3
"""Beyond page sync from a published Google Sheet (no Strava API needed).

A free automation (Zapier / Make / IFTTT) logs each new Strava activity as a row
in a Google Sheet; that Sheet is "published to the web" as CSV. This script reads
that CSV and writes:
  - assets/data/beyond.json              (18-week daily run miles + YTD stats + maps)
  - assets/images/strava/mapN.svg        (self-contained route-trace images)

No API keys, no secrets: the sheet is public-read and route maps are drawn locally
from each activity's Strava summary polyline. Stdlib only.

Env:
  BEYOND_SHEET_CSV   published Google Sheet CSV URL (…/pub?output=csv)
"""
import os, io, csv, json, math, datetime, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "assets", "data")
IMG_DIR = os.path.join(ROOT, "assets", "images", "strava")
WINDOW_DAYS = 126           # 18 weeks (matches the existing chart)
MAX_MAPS = 3
RUN_TYPES = {"run"}
MAP_TYPES = {"run", "trailrun", "hike", "walk"}
M2MI = 1.0 / 1609.344
M2FT = 3.28084
UA = {"User-Agent": "mihirmadhaparia.com-beyond-sync"}


# ---------- input ----------
def fetch_csv(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def find_col(headers, *needles):
    low = [h.strip().lower() for h in headers]
    for i, h in enumerate(low):
        if all(n in h for n in needles):
            return i
    return -1


def parse_date(s):
    s = (s or "").strip()
    if not s:
        return None
    # ISO first (2026-10-02T07:00:00Z or 2026-10-02)
    try:
        return datetime.date.fromisoformat(s[:10])
    except ValueError:
        pass
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d",
                "%B %d, %Y at %I:%M%p", "%b %d, %Y, %I:%M:%S %p"):
        try:
            return datetime.datetime.strptime(s[:40], fmt).date()
        except ValueError:
            continue
    # last resort: leading YYYY-MM-DD anywhere
    import re
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def to_float(x):
    try:
        return float(str(x).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


def read_rows(csv_text):
    rd = csv.reader(io.StringIO(csv_text))
    rows = [r for r in rd if any(c.strip() for c in r)]
    if not rows:
        return []
    headers = rows[0]
    ci = {
        "date": find_col(headers, "date"),
        "type": find_col(headers, "type"),
        "dist_mi": find_col(headers, "distance", "mi"),
        "dist_m": find_col(headers, "distance"),         # meters fallback
        "elev_ft": find_col(headers, "elev", "f"),       # feet
        "elev_m": find_col(headers, "elev"),             # meters fallback
        "poly": find_col(headers, "poly"),
        "mapurl": find_col(headers, "map"),
        "name": find_col(headers, "name"),
    }
    out = []
    for r in rows[1:]:
        def g(i):
            return r[i] if 0 <= i < len(r) else ""
        d = parse_date(g(ci["date"]))
        if not d:
            continue
        typ = (g(ci["type"]) or "").strip().lower().replace(" ", "")
        if ci["dist_mi"] >= 0 and "mi" in headers[ci["dist_mi"]].lower():
            miles = to_float(g(ci["dist_mi"]))
        else:
            miles = to_float(g(ci["dist_m"])) * M2MI
        if ci["elev_ft"] >= 0 and ("ft" in headers[ci["elev_ft"]].lower() or "feet" in headers[ci["elev_ft"]].lower()):
            feet = to_float(g(ci["elev_ft"]))
        else:
            feet = to_float(g(ci["elev_m"])) * M2FT
        out.append({
            "date": d, "type": typ, "miles": miles, "feet": feet,
            "poly": g(ci["poly"]).strip(), "mapurl": g(ci["mapurl"]).strip(),
            "name": (g(ci["name"]) or "Activity").strip(),
        })
    return out


# ---------- route map ----------
def decode_polyline(s):
    coords, i, lat, lng, n = [], 0, 0, 0, len(s)
    while i < n:
        for axis in (0, 1):
            shift, result = 0, 0
            while True:
                b = ord(s[i]) - 63
                i += 1
                result |= (b & 0x1f) << shift
                shift += 5
                if b < 0x20:
                    break
            d = ~(result >> 1) if (result & 1) else (result >> 1)
            if axis == 0:
                lat += d
            else:
                lng += d
        coords.append((lat * 1e-5, lng * 1e-5))
    return coords


def polyline_svg(poly):
    pts = decode_polyline(poly)
    if len(pts) < 2:
        return None
    lats = [p[0] for p in pts]
    lngs = [p[1] for p in pts]
    mlat = math.radians(sum(lats) / len(lats))
    xs = [lng * math.cos(mlat) for lng in lngs]
    ys = [-lat for lat in lats]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    w = maxx - minx or 1e-6
    h = maxy - miny or 1e-6
    VB = 400.0
    pad = 28.0
    scale = (VB - 2 * pad) / max(w, h)
    ox = (VB - w * scale) / 2
    oy = (VB - h * scale) / 2
    def px(x, y):
        return (ox + (x - minx) * scale, oy + (y - miny) * scale)
    d = ""
    for j, (x, y) in enumerate(zip(xs, ys)):
        X, Y = px(x, y)
        d += ("M" if j == 0 else "L") + "%.1f %.1f" % (X, Y)
    sX, sY = px(xs[0], ys[0])
    eX, eY = px(xs[-1], ys[-1])
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400" '
        'preserveAspectRatio="xMidYMid meet">'
        '<rect width="400" height="400" fill="#e9e7e1"/>'
        '<path d="%s" fill="none" stroke="#111111" stroke-width="4" '
        'stroke-linejoin="round" stroke-linecap="round"/>'
        '<circle cx="%.1f" cy="%.1f" r="7" fill="#111111"/>'
        '<circle cx="%.1f" cy="%.1f" r="7" fill="#ff3b1d"/>'
        '</svg>' % (d, sX, sY, eX, eY)
    )


def download(url, dest):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r, open(dest, "wb") as f:
        f.write(r.read())


# ---------- main ----------
def main():
    url = os.environ.get("BEYOND_SHEET_CSV", "").strip()
    if not url:
        raise SystemExit("Set BEYOND_SHEET_CSV to your published Google Sheet CSV URL.")
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(IMG_DIR, exist_ok=True)

    rows = read_rows(fetch_csv(url))
    today = datetime.date.today()
    start = today - datetime.timedelta(days=WINDOW_DAYS - 1)

    daily = [0.0] * WINDOW_DAYS
    ytd_mi = ytd_ft = 0.0
    for a in rows:
        if a["type"] not in RUN_TYPES:
            continue
        if start <= a["date"] <= today:
            daily[(a["date"] - start).days] += a["miles"]
        if a["date"].year == today.year:
            ytd_mi += a["miles"]
            ytd_ft += a["feet"]
    days = [round(x, 1) for x in daily]

    photos = []
    for a in sorted(rows, key=lambda r: r["date"], reverse=True):
        if len(photos) >= MAX_MAPS:
            break
        if a["type"] not in MAP_TYPES:
            continue
        idx = len(photos) + 1
        cap = "%s · %s" % (a["name"], a["date"].strftime("%b %d, %Y"))
        if a["poly"]:
            svg = polyline_svg(a["poly"])
            if not svg:
                continue
            fname = "map%d.svg" % idx
            with open(os.path.join(IMG_DIR, fname), "w", encoding="utf-8") as f:
                f.write(svg)
            photos.append({"file": "/assets/images/strava/" + fname, "cap": cap})
        elif a["mapurl"].startswith("http"):
            fname = "map%d.jpg" % idx
            try:
                download(a["mapurl"], os.path.join(IMG_DIR, fname))
            except Exception:
                continue
            photos.append({"file": "/assets/images/strava/" + fname, "cap": cap})

    out = {
        "updated": "%d/%d/%s" % (today.month, today.day, today.strftime("%y")),
        "updated_iso": today.isoformat(),
        "end": today.isoformat(),
        "days": days,
        "ytd_miles": int(round(ytd_mi)),
        "ytd_elev_ft": int(round(ytd_ft)),
        "photos": photos,
    }
    with open(os.path.join(DATA_DIR, "beyond.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print("Wrote beyond.json: %d days, YTD %d mi / %d ft, %d route maps" % (
        len(days), out["ytd_miles"], out["ytd_elev_ft"], len(photos)))


if __name__ == "__main__":
    main()
