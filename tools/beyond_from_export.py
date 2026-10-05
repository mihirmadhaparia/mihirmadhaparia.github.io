#!/usr/bin/env python3
"""Update the Beyond page from a Strava bulk export (no API needed).

Strava: Settings -> My Account -> "Download or Delete Your Account" -> Get Started
-> Request your archive. Strava emails a .zip. Run:

    python tools/beyond_from_export.py  path/to/export_XXXX.zip

(You can also pass an already-unzipped folder.) It reads activities.csv, computes
the last-18-week daily run mileage + YTD stats (same format the chart uses), copies
your most recent posted photos into assets/images/strava/, and writes
assets/data/beyond.json. Then commit + push. Stdlib only.
"""
import os, sys, csv, json, io, zipfile, shutil, datetime, tempfile, re, hashlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "assets", "data")
IMG_DIR = os.path.join(ROOT, "assets", "images", "strava")
WINDOW_DAYS = 126
MAX_PHOTOS = 3
RUN_TYPES = {"Run"}
PHOTO_TYPES = {"Run", "Trail Run", "Hike", "Walk"}
M2MI = 1.0 / 1609.344
M2FT = 3.28084
IMG_EXT = (".jpg", ".jpeg", ".png", ".webp", ".heic")
# Specific photos to never use (e.g. the sweaty-arm shot), by media filename.
SKIP_MEDIA = {"F381FC56-F2FA-4891-9DB0-42290068AA76.jpg"}


def resolve_export(path):
    """Return a directory containing activities.csv (unzips to temp if needed)."""
    if os.path.isdir(path):
        return path, None
    if zipfile.is_zipfile(path):
        tmp = tempfile.mkdtemp()
        with zipfile.ZipFile(path) as z:
            z.extractall(tmp)
        return tmp, tmp
    raise SystemExit("Not a folder or zip: %s" % path)


def col(headers, name):
    """Last exact (case-insensitive) match — picks the raw-meters Distance col."""
    idx = -1
    for i, h in enumerate(headers):
        if h.strip().lower() == name.lower():
            idx = i
    return idx


def parse_date(s):
    s = (s or "").strip()
    for fmt in ("%b %d, %Y, %I:%M:%S %p", "%b %d, %Y, %I:%M:%S%p", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(s[:40], fmt)
        except ValueError:
            continue
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    return datetime.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def num(x):
    try:
        return float(str(x).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


def load_media_map(exp):
    """activity_id -> [media relative paths], from media.csv if present."""
    mp = {}
    path = os.path.join(exp, "media.csv")
    if not os.path.exists(path):
        return mp
    rows = list(csv.reader(open(path, encoding="utf-8", errors="replace")))
    if not rows:
        return mp
    hdr = rows[0]
    aid = next((i for i, h in enumerate(hdr) if "activity" in h.lower()), -1)
    fil = next((i for i, h in enumerate(hdr) if any(k in h.lower() for k in ("filename", "media", "name", "path"))), -1)
    for r in rows[1:]:
        if aid >= 0 and fil >= 0 and aid < len(r) and fil < len(r):
            mp.setdefault(r[aid].strip(), []).append(r[fil].strip())
    return mp


def find_file(exp, rel):
    rel = rel.strip().lstrip("/").replace("\\", "/")
    for cand in (os.path.join(exp, rel), os.path.join(exp, "media", os.path.basename(rel)),
                 os.path.join(exp, os.path.basename(rel))):
        if os.path.isfile(cand):
            return cand
    return None


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python tools/beyond_from_export.py <export.zip or folder>")
    exp, cleanup = resolve_export(sys.argv[1])
    acts_csv = os.path.join(exp, "activities.csv")
    if not os.path.exists(acts_csv):
        raise SystemExit("activities.csv not found in the export.")
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(IMG_DIR, exist_ok=True)

    rows = list(csv.reader(open(acts_csv, encoding="utf-8", errors="replace")))
    hdr = rows[0]
    I_ID = col(hdr, "Activity ID")
    I_DATE = col(hdr, "Activity Date")
    I_TYPE = col(hdr, "Activity Type")
    I_DIST = col(hdr, "Distance")           # last exact match = raw meters
    I_ELEV = col(hdr, "Elevation Gain")
    I_MEDIA = col(hdr, "Media")
    I_NAME = col(hdr, "Activity Name")

    media_map = load_media_map(exp)
    today = datetime.date.today()
    start = today - datetime.timedelta(days=WINDOW_DAYS - 1)

    daily = [0.0] * WINDOW_DAYS
    ytd_mi = ytd_ft = 0.0
    acts = []
    for r in rows[1:]:
        if I_DATE < 0 or I_DATE >= len(r):
            continue
        dt = parse_date(r[I_DATE])
        if not dt:
            continue
        typ = r[I_TYPE].strip() if 0 <= I_TYPE < len(r) else ""
        dist_m = num(r[I_DIST]) if 0 <= I_DIST < len(r) else 0.0
        elev_m = num(r[I_ELEV]) if 0 <= I_ELEV < len(r) else 0.0
        d = dt.date()
        if typ in RUN_TYPES:
            if start <= d <= today:
                daily[(d - start).days] += dist_m * M2MI
            if d.year == today.year:
                ytd_mi += dist_m * M2MI
                ytd_ft += elev_m * M2FT
        acts.append({
            "id": r[I_ID].strip() if 0 <= I_ID < len(r) else "",
            "date": d, "type": typ,
            "name": (r[I_NAME].strip() if 0 <= I_NAME < len(r) else ""),
            "media_raw": r[I_MEDIA].strip() if (0 <= I_MEDIA < len(r)) else "",
        })
    days = [round(x, 1) for x in daily]

    # --- photos: most recent run/hike/walk activities that have media ---
    photos = []
    for a in sorted(acts, key=lambda x: x["date"], reverse=True):
        if len(photos) >= MAX_PHOTOS:
            break
        if a["type"] not in PHOTO_TYPES:
            continue
        cands = []
        if a["media_raw"]:
            cands += re.split(r"[|,\s]+", a["media_raw"])
        cands += media_map.get(a["id"], [])
        cands = [c for c in cands if c and c.lower().endswith(IMG_EXT) and os.path.basename(c) not in SKIP_MEDIA]
        src = next((find_file(exp, c) for c in cands if find_file(exp, c)), None)
        if not src:
            continue
        ext = os.path.splitext(src)[1].lower()
        dest = os.path.join(IMG_DIR, "photo%d%s" % (len(photos) + 1, ext))
        try:
            shutil.copyfile(src, dest)
        except Exception:
            continue
        name = a["name"] or a["type"]
        ver = hashlib.md5(open(dest, "rb").read()).hexdigest()[:8]
        photos.append({
            "file": "/assets/images/strava/" + os.path.basename(dest) + "?v=" + ver,
            "cap": "%s · %s" % (name, a["date"].strftime("%b %d, %Y")),
        })

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
    # regenerate the multi-city route-map module in beyond.html
    try:
        import build_route_maps
        build_route_maps.inject(exp)
    except Exception as e:
        print("Route-map build skipped:", e)
    if cleanup:
        shutil.rmtree(cleanup, ignore_errors=True)
    print("Updated beyond.json: %d days, YTD %d mi / %d ft, %d photos" % (
        len(days), out["ytd_miles"], out["ytd_elev_ft"], len(photos)))
    print("Now commit and push:  git add -A && git commit -m \"Update Beyond from Strava\" && git push")


if __name__ == "__main__":
    main()
