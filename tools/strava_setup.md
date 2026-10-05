# Updating the Beyond page from Strava (manual, one step)

Strava locked down its API (and the automation tools that relied on it), so the
Beyond page updates from a **Strava data export** instead — no API, no account
connection, and it includes your **real posted photos** and full GPS.

Do this whenever you want to refresh the page (every few weeks is plenty):

## 1. Request your Strava archive
1. On Strava (web): **Settings → My Account →** scroll to **"Download or Delete
   Your Account" → Get Started**.
2. Under **"Download Request (optional)"**, click **Request Your Archive**.
3. Strava emails you a download link (can take a few minutes up to a few hours).
   Download the `.zip` (named like `export_1234567.zip`).

## 2. Update the page (one command)
From the repo folder, run:

```
python tools/beyond_from_export.py  path/to/export_1234567.zip
```

(You can drag the zip into the terminal to paste its path.) It reads the export,
recomputes the last-18-week daily mileage + YTD stats, copies your 3 most recent
activity photos into `assets/images/strava/`, and writes `assets/data/beyond.json`.
You'll see a summary like `Updated beyond.json: 126 days, YTD 158 mi / 4,927 ft, 3 photos`.

## 3. Publish
```
git add -A
git commit -m "Update Beyond from Strava"
git push
```
GitHub Pages redeploys in ~1 minute and the page reflects the new data. The chart
is unchanged — only its numbers, the stats, the "updated" date, and the photos refresh.

---

### Even easier
If you'd rather not run anything: just **send me the export zip** and I'll process
it, update the page, and hand it back for you to push. (That's what we did before.)

### Notes
- Only **Run** activities count toward the mileage/stats; treadmill runs count for
  distance but produce no map.
- Photos come straight from your Strava uploads in the export's `media/` folder.
- If the page ever can't load `beyond.json`, it falls back to the values baked into
  `beyond.html`, so it never breaks.
- Keep the "Powered by Strava" link on the page (Strava's terms).
