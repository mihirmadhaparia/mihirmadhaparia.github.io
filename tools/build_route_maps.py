#!/usr/bin/env python3
"""Build the multi-city route-map module for the Beyond page from a Strava export.

Parses run GPS tracks (FIT), clusters them by nearest city, and renders a
brutalist route "tapestry" SVG per city (faded single-color territory-glow
backdrop + crisp route lines, recent runs in red). Injects a tabbed module into
beyond.html between <!--MAPS_START--> and <!--MAPS_END-->. Stdlib only.

Used by tools/beyond_from_export.py; can also be run standalone:
    python tools/build_route_maps.py <export.zip or folder>
"""
import os, sys, csv, gzip, struct, math, datetime, zipfile, tempfile, shutil, html

sys.setrecursionlimit(100000)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BEYOND = os.path.join(ROOT, "beyond.html")
MIN_RUNS = 2           # minimum runs for a city to get a tab
RECENT_RED = 4         # most-recent runs per city drawn in red
VBW, VBH = 760.0, 460.0

CITY_ANCHORS = [
    (44.98, -93.27, "Minneapolis, MN"), (43.07, -89.40, "Madison, WI"),
    (41.88, -87.63, "Chicago, IL"), (40.71, -74.01, "New York, NY"),
    (42.36, -71.06, "Boston, MA"), (38.90, -77.04, "Washington, DC"),
    (39.74, -104.99, "Denver, CO"), (30.27, -97.74, "Austin, TX"),
    (29.76, -95.37, "Houston, TX"), (25.76, -80.19, "Miami, FL"),
    (33.75, -84.39, "Atlanta, GA"), (37.77, -122.42, "San Francisco, CA"),
    (34.05, -118.24, "Los Angeles, CA"), (32.72, -117.16, "San Diego, CA"),
    (47.61, -122.33, "Seattle, WA"), (45.52, -122.68, "Portland, OR"),
    (51.51, -0.13, "London, UK"), (48.86, 2.35, "Paris, FR"),
    (-1.29, 36.82, "Nairobi, KE"), (19.08, 72.88, "Mumbai, IN"),
]
ANCHOR_KM = 90.0


# ---------------- FIT ----------------
def parse_fit(data):
    hs = data[0]; ds = struct.unpack_from('<I', data, 4)[0]
    pos = hs; end = min(len(data), hs + ds); defs = {}; pts = []
    def rd(pos, d):
        vals = {}
        for (fnum, size) in d['fields']:
            raw = data[pos:pos + size]; pos += size
            if d['gnum'] == 20 and fnum in (0, 1) and size == 4:
                vals[fnum] = struct.unpack(d['endian'] + 'i', raw)[0]
        for size in d['dev']:
            pos += size
        if d['gnum'] == 20 and 0 in vals and 1 in vals:
            la, lo = vals[0], vals[1]
            if la != 0x7fffffff and lo != 0x7fffffff:
                pts.append((la * (180 / 2 ** 31), lo * (180 / 2 ** 31)))
        return pos
    while pos < end:
        rh = data[pos]; pos += 1
        if rh & 0x80:
            d = defs.get((rh >> 5) & 0x3)
            if not d:
                break
            pos = rd(pos, d); continue
        local = rh & 0x0f
        if rh & 0x40:
            pos += 1; arch = data[pos]; pos += 1
            endian = '>' if arch == 1 else '<'
            gnum = struct.unpack_from(endian + 'H', data, pos)[0]; pos += 2
            nf = data[pos]; pos += 1; fields = []
            for _ in range(nf):
                fields.append((data[pos], data[pos + 1])); pos += 3
            dev = []
            if rh & 0x20:
                nd = data[pos]; pos += 1
                for _ in range(nd):
                    dev.append(data[pos + 1]); pos += 3
            defs[local] = {'endian': endian, 'gnum': gnum, 'fields': fields, 'dev': dev}
        else:
            d = defs.get(local)
            if not d:
                break
            pos = rd(pos, d)
    return pts


# ---------------- geometry ----------------
def haversine(a, b):
    R = 6371.0
    la1, lo1, la2, lo2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))

def perp(p, a, b):
    cl = math.cos(math.radians(a[0]))
    ax, ay = a[1] * cl, a[0]; bx, by = b[1] * cl, b[0]; px, py = p[1] * cl, p[0]
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))

def rdp(pts, eps):
    if len(pts) < 3:
        return pts
    a, b = pts[0], pts[-1]; dm = 0; idx = 0
    for i in range(1, len(pts) - 1):
        d = perp(pts[i], a, b)
        if d > dm:
            dm = d; idx = i
    if dm > eps:
        return rdp(pts[:idx + 1], eps)[:-1] + rdp(pts[idx:], eps)
    return [a, b]

def centroid(r):
    return (sum(p[0] for p in r) / len(r), sum(p[1] for p in r) / len(r))

def pct(vals, p):
    v = sorted(vals); return v[int(p * (len(v) - 1))]


# ---------------- extraction + clustering ----------------
def resolve_export(path):
    if os.path.isdir(path):
        return path, None
    tmp = tempfile.mkdtemp()
    with zipfile.ZipFile(path) as z:
        z.extractall(tmp)
    return tmp, tmp

def extract_runs(exp):
    acts_csv = os.path.join(exp, "activities.csv")
    rows = list(csv.reader(open(acts_csv, encoding="utf-8", errors="replace")))
    hdr = rows[0]
    def col(n):
        idx = -1
        for i, h in enumerate(hdr):
            if h.strip().lower() == n.lower():
                idx = i
        return idx
    I_TYPE, I_FN, I_DATE = col("Activity Type"), col("Filename"), col("Activity Date")
    runs = []
    for r in rows[1:]:
        if len(r) <= max(I_TYPE, I_FN, I_DATE):
            continue
        if r[I_TYPE].strip() != "Run":
            continue
        fn = r[I_FN].strip()
        p = os.path.join(exp, fn)
        if not fn.endswith(".fit.gz") or not os.path.exists(p):
            continue
        try:
            pts = parse_fit(gzip.open(p, "rb").read())
        except Exception:
            continue
        if len(pts) < 10:
            continue
        pts = pts[::3]
        simp = rdp(pts, 0.00018)
        try:
            dt = datetime.datetime.strptime(r[I_DATE].strip()[:40], "%b %d, %Y, %I:%M:%S %p")
        except ValueError:
            dt = datetime.datetime(1970, 1, 1)
        runs.append({"date": dt, "pts": simp})
    return runs

def city_for(c):
    best, bestd = None, 1e9
    for la, lo, name in CITY_ANCHORS:
        d = haversine(c, (la, lo))
        if d < bestd:
            bestd, best = d, name
    if bestd <= ANCHOR_KM:
        return best
    return "%.1f, %.1f" % (round(c[0], 1), round(c[1], 1))

def cluster(runs):
    cities = {}
    for run in runs:
        name = city_for(centroid(run["pts"]))
        cities.setdefault(name, []).append(run)
    # keep cities with enough runs, sorted by run count desc
    keep = [(n, rs) for n, rs in cities.items() if len(rs) >= MIN_RUNS]
    keep.sort(key=lambda x: -len(x[1]))
    return keep


# ---------------- render ----------------
def render_svg(runs):
    runs = sorted(runs, key=lambda r: r["date"])  # oldest..newest
    pts = [p for r in runs for p in r["pts"]]
    las = [p[0] for p in pts]; los = [p[1] for p in pts]
    latlo, lathi = pct(las, .03), pct(las, .97)
    lnglo, lnghi = pct(los, .03), pct(los, .97)
    mlat = math.radians((latlo + lathi) / 2)
    def proj(la, lo):
        return (lo * math.cos(mlat), -la)
    xs = [proj(latlo, lnglo)[0], proj(latlo, lnghi)[0]]
    ys = [proj(lathi, lnglo)[1], proj(latlo, lnglo)[1]]
    minx, maxx = min(xs), max(xs); miny, maxy = min(ys), max(ys)
    w = maxx - minx or 1e-6; h = maxy - miny or 1e-6
    pad = 22.0
    sc = min((VBW - 2 * pad) / w, (VBH - 2 * pad) / h)
    ox = (VBW - w * sc) / 2; oy = (VBH - h * sc) / 2
    def px(la, lo):
        x, y = proj(la, lo); return (ox + (x - minx) * sc, oy + (y - miny) * sc)
    def dstr(r):
        return "".join(("M" if j == 0 else "L") + "%.1f %.1f" % px(p[0], p[1]) for j, p in enumerate(r["pts"]))
    back, fore = [], []
    n = len(runs)
    for i, r in enumerate(runs):
        d = dstr(r)
        back.append('<path d="%s" fill="none" stroke="#6b6660" stroke-width="11" opacity="0.06"/>' % d)
        recent = i >= n - RECENT_RED
        fore.append('<path d="%s" fill="none" stroke="%s" stroke-width="%s" opacity="%.2f" stroke-linejoin="round" stroke-linecap="round"/>'
                    % (d, "#ff3b1d" if recent else "#1a1a1a", "2" if recent else "1.2", 0.9 if recent else 0.4))
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 460" '
            'preserveAspectRatio="xMidYMid meet" class="routemap__svg">'
            '<rect width="760" height="460" fill="#e9e7e1"/>'
            '<defs><filter id="rmblur" x="-5%" y="-5%" width="110%" height="110%">'
            '<feGaussianBlur stdDeviation="3.4"/></filter></defs>'
            '<g filter="url(#rmblur)" stroke-linejoin="round" stroke-linecap="round">' + "".join(back) + '</g>'
            + "".join(fore) + '</svg>')


def build_inner(export):
    exp, cleanup = resolve_export(export)
    try:
        runs = extract_runs(exp)
        cities = cluster(runs)
    finally:
        if cleanup:
            shutil.rmtree(cleanup, ignore_errors=True)
    if not cities:
        return None, 0
    import json
    data = {"cities": []}
    for name, rs in cities:
        rs = sorted(rs, key=lambda r: r["date"])  # oldest..newest
        routes = [[[round(p[0], 5), round(p[1], 5)] for p in r["pts"]] for r in rs]
        data["cities"].append({
            "name": name, "runs": len(rs),
            "recent": min(RECENT_RED, len(rs)), "routes": routes,
        })
    js = json.dumps(data, separators=(',', ':'))
    inner = ('\n            <div class="routemap__tabs" id="routemap-tabs"></div>'
             '\n            <div id="routemap-canvas" class="routemap__canvas"></div>'
             '\n            <script type="application/json" id="routemap-data">' + js + '</script>\n            ')
    return inner, len(cities)


def inject(export):
    inner, ncities = build_inner(export)
    s = open(BEYOND, encoding="utf-8").read()
    start = s.find("<!--MAPS_START-->")
    end = s.find("<!--MAPS_END-->")
    if start < 0 or end < 0:
        raise SystemExit("MAPS markers not found in beyond.html")
    if inner is None:
        print("No GPS runs found; leaving map placeholder.")
        return 0
    s = s[:start + len("<!--MAPS_START-->")] + inner + s[end:]
    open(BEYOND, "w", encoding="utf-8").write(s)
    print("Injected route maps for %d cities into beyond.html" % ncities)
    return ncities


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python tools/build_route_maps.py <export.zip or folder>")
    inject(sys.argv[1])
