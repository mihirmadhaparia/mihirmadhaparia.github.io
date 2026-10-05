# Beyond page auto-sync — setup (no Strava API)

Since Strava's API isn't open to you, we pull data a different way: a free
automation service logs each new Strava activity into a **Google Sheet**, and a
weekly GitHub Action reads that (public) sheet and updates the Beyond page.
No API keys, no subscription, no secrets.

Flow:  **Strava → (Zapier / Make / IFTTT) → Google Sheet → GitHub Action → site**

The Action (`.github/workflows/strava-sync.yml` → `tools/strava_sync.py`) computes
the 18‑week daily mileage + YTD stats and draws route‑map traces from each run's
Strava polyline. The chart itself is unchanged; if the sheet is ever unreachable,
the page falls back to the values baked into `beyond.html`.

---

## 1. Make the Google Sheet
1. Create a new Google Sheet. In row 1, add these **exact-ish** headers
   (matching is fuzzy/case-insensitive, but these are safest):

   | date | type | distance_m | elevation_m | polyline | name |
   |------|------|-----------|-------------|----------|------|

   - `distance_m` / `elevation_m` are **meters** (what Zapier/Make give). If your
     tool only gives miles/feet, name the columns `distance_mi` / `elevation_ft`
     instead — the script detects the unit from the header.
   - `polyline` is the activity's **map summary polyline** (used to draw the route
     trace). Leave blank for treadmill runs.

## 2. Connect Strava with a free automation
Pick whichever has Strava on its free plan (Make and Zapier both do):

**Make.com (recommended):** New scenario → **Strava › Watch Activities** →
**Google Sheets › Add a Row**. Map fields:
- Start Date → `date`
- Type → `type`
- Distance → `distance_m`
- Total Elevation Gain → `elevation_m`
- Map: Summary Polyline → `polyline`
- Name → `name`

**Zapier:** Trigger **Strava › New Activity** → Action **Google Sheets › Create
Spreadsheet Row**, same mapping (Zapier's Distance / Total Elevation Gain are in
meters; use **Map Summary Polyline** for `polyline`).

**IFTTT:** Strava "New activity by you" → Google Sheets "Add row". IFTTT gives
miles (use `distance_mi`) and generally **no polyline**, so route maps won't draw —
prefer Make or Zapier if you want the route traces.

> Tip: run one activity (or re-save an old one) so a test row appears.

## 3. Publish the sheet to the web (read-only CSV)
In the Sheet: **File → Share → Publish to web → Link → (whole document) → CSV →
Publish**. Copy the URL (ends in `/pub?output=csv`).

## 4. Add the URL as a repo variable
GitHub repo → **Settings → Secrets and variables → Actions → Variables tab →
New repository variable**:
- Name: `BEYOND_SHEET_CSV`
- Value: the published CSV URL from step 3

(It's a *variable*, not a secret — the sheet is public-read.)

## 5. Test
Repo → **Actions → "Beyond sync (Strava via Google Sheet)" → Run workflow**.
Check the run log and that `assets/data/beyond.json` updated. After that it runs
every Monday automatically.

---

## Notes
- **Schedule:** weekly (Mondays 09:00 UTC). Edit the `cron` to change it.
- **Route maps:** the 3 most recent run/hike/walk activities with a polyline are
  drawn as self-contained SVG traces (`assets/images/strava/mapN.svg`), overwritten
  each run so the repo doesn't grow. No maps API / key needed.
- **Attribution:** keep the "Powered by Strava" link on the page (Strava's terms).
- **Privacy:** only the columns you map leave Strava; the sheet is read-only public.
  Don't add anything to it you don't want public.
