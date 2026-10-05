#!/usr/bin/env python3
"""Strava -> Beyond page sync (runs in GitHub Actions, weekly).

Refreshes the Strava token, pulls activities + recent photos, and writes:
  - assets/data/beyond.json   (stats + 18-week daily run mileage + photo manifest)
  - assets/images/strava/photoN.jpg  (downloaded recent activity photos)

The Beyond page reads beyond.json at load time; the chart itself is unchanged.
Stdlib only (no pip installs needed).

Env vars (set as GitHub repo secrets):
  STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_REFRESH_TOKEN
"""
import os, json, time, datetime, urllib.request, urllib.parse, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "assets", "data")
IMG_DIR = os.path.join(ROOT, "assets", "images", "strava")
WINDOW_DAYS = 126          # 18 weeks (matches the existing chart)
MAX_PHOTOS = 3             # recent activity photos to show
PHOTO_TYPES = {"Run", "TrailRun", "Hike", "Walk"}
M2MI = 1.0 / 1609.344
M2FT = 3.28084
UA = {"User-Agent": "mihirmadhaparia.com-strava-sync"}


def _req(url, data=None, headers=None):
    h = dict(UA)
    if headers:
        h.update(headers)
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=h)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def refresh_token():
    cid = os.environ["STRAVA_CLIENT_ID"]
    secret = os.environ["STRAVA_CLIENT_SECRET"]
    refresh = os.environ["STRAVA_REFRESH_TOKEN"]
    tok = _req("https://www.strava.com/oauth/token", data={
        "client_id": cid, "client_secret": secret,
        "grant_type": "refresh_token", "refresh_token": refresh,
    })
    return tok["access_token"]


def get_activities(access_token, after_epoch):
    hdr = {"Authorization": "Bearer " + access_token}
    out, page = [], 1
    while True:
        q = urllib.parse.urlencode({"after": after_epoch, "per_page": 200, "page": page})
        batch = _req("https://www.strava.com/api/v3/athlete/activities?" + q, headers=hdr)
        if not batch:
            break
        out.extend(batch)
        if len(batch) < 200:
            break
        page += 1
        if page > 10:
            break
    return out


def get_primary_photo_url(access_token, activity_id):
    hdr = {"Authorization": "Bearer " + access_token}
    q = urllib.parse.urlencode({"size": 1024, "photo_sources": "true"})
    try:
        photos = _req("https://www.strava.com/api/v3/activities/%d/photos?%s" % (activity_id, q), headers=hdr)
    except urllib.error.HTTPError:
        return None
    for p in photos or []:
        urls = p.get("urls") or {}
        # prefer the largest available size
        for key in sorted(urls.keys(), key=lambda k: int(k) if str(k).isdigit() else 0, reverse=True):
            if urls[key]:
                return urls[key]
    return None


def download(url, dest):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r, open(dest, "wb") as f:
        f.write(r.read())


def parse_dt(a):
    s = a.get("start_date_local") or a.get("start_date")
    return datetime.datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(IMG_DIR, exist_ok=True)

    access = refresh_token()
    today = datetime.date.today()
    start_window = today - datetime.timedelta(days=WINDOW_DAYS - 1)
    year_start = datetime.date(today.year, 1, 1)
    after = int(time.mktime(min(start_window, year_start).timetuple())) - 86400
    acts = get_activities(access, after)

    # --- 18-week daily run mileage (oldest first), matches the chart's format ---
    daily = [0.0] * WINDOW_DAYS
    ytd_mi = ytd_ft = 0.0
    for a in acts:
        if a.get("type") != "Run" and a.get("sport_type") != "Run":
            continue
        d = parse_dt(a).date()
        dist_m = float(a.get("distance") or 0)
        elev_m = float(a.get("total_elevation_gain") or 0)
        if start_window <= d <= today:
            daily[(d - start_window).days] += dist_m * M2MI
        if d.year == today.year:
            ytd_mi += dist_m * M2MI
            ytd_ft += elev_m * M2FT
    days = [round(x, 1) for x in daily]

    # --- recent activity photos ---
    photos = []
    for a in sorted(acts, key=parse_dt, reverse=True):
        if len(photos) >= MAX_PHOTOS:
            break
        if (a.get("type") in PHOTO_TYPES or a.get("sport_type") in PHOTO_TYPES) and (a.get("total_photo_count") or 0) > 0:
            url = get_primary_photo_url(access, a["id"])
            if not url:
                continue
            idx = len(photos) + 1
            fname = "photo%d.jpg" % idx
            try:
                download(url, os.path.join(IMG_DIR, fname))
            except Exception:
                continue
            d = parse_dt(a).date()
            photos.append({
                "file": "/assets/images/strava/" + fname,
                "cap": "%s · %s" % (a.get("name", "Activity"), d.strftime("%b %d, %Y")),
            })

    out = {
        "updated": today.strftime("%-m/%-d/%y") if os.name != "nt" else today.strftime("%m/%d/%y"),
        "updated_iso": today.isoformat(),
        "end": today.isoformat(),
        "days": days,
        "ytd_miles": int(round(ytd_mi)),
        "ytd_elev_ft": int(round(ytd_ft)),
        "photos": photos,
    }
    with open(os.path.join(DATA_DIR, "beyond.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print("Wrote beyond.json: %d days, YTD %d mi / %d ft, %d photos" % (
        len(days), out["ytd_miles"], out["ytd_elev_ft"], len(photos)))


if __name__ == "__main__":
    main()
