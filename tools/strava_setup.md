# Strava auto-sync — one-time setup

The Beyond page auto-updates from Strava via a weekly GitHub Action
(`.github/workflows/strava-sync.yml` → `tools/strava_sync.py`). The Action
refreshes your Strava token, recomputes the 18-week daily mileage + YTD stats,
pulls your most recent activity photos, and commits the result to
`assets/data/beyond.json` and `assets/images/strava/`. The page reads that file;
the chart itself is unchanged.

You only need to do the following **once** (≈10 minutes). I can't do these —
they require your Strava login and your GitHub repo settings.

## 1. Create a Strava API application
1. Go to https://www.strava.com/settings/api
2. Create an app (any name; "Authorization Callback Domain" = `localhost`).
3. Note your **Client ID** and **Client Secret**.

## 2. Authorize once to get a refresh token
1. In a browser, visit this URL (replace `YOUR_CLIENT_ID`):
   ```
   https://www.strava.com/oauth/authorize?client_id=YOUR_CLIENT_ID&response_type=code&redirect_uri=http://localhost&approval_prompt=force&scope=activity:read_all
   ```
2. Click **Authorize**. The browser redirects to a `localhost` URL that won't
   load — that's fine. Copy the `code=...` value from the address bar.
3. Exchange that code for tokens (run in any terminal with `curl`):
   ```
   curl -X POST https://www.strava.com/oauth/token \
     -d client_id=YOUR_CLIENT_ID \
     -d client_secret=YOUR_CLIENT_SECRET \
     -d code=THE_CODE_FROM_STEP_2 \
     -d grant_type=authorization_code
   ```
4. From the JSON response, copy the **`refresh_token`** value.

## 3. Add three repo secrets on GitHub
Repo → **Settings → Secrets and variables → Actions → New repository secret**.
Add each of these:
- `STRAVA_CLIENT_ID`
- `STRAVA_CLIENT_SECRET`
- `STRAVA_REFRESH_TOKEN`

## 4. Test it
Repo → **Actions → "Strava sync (Beyond page)" → Run workflow**. After it runs,
check that `assets/data/beyond.json` updated and the Beyond page reflects it.
After that it runs automatically every Monday.

## Notes
- **Schedule:** weekly (Mondays 09:00 UTC). Change the `cron` in the workflow to adjust.
- **Photos:** the 3 most recent run/hike/walk activity photos are downloaded into
  `assets/images/strava/` (overwritten each run, so the repo doesn't grow).
- **Attribution:** a "Powered by Strava" link is shown on the Beyond page, per
  Strava's API agreement. Keep it.
- **Fallback:** if `beyond.json` is ever missing, the page falls back to the
  values currently inlined in `beyond.html`, so it never breaks.
- **Token:** Strava refresh tokens are normally stable. If a sync ever fails with
  an auth error, redo steps 2–3 to refresh `STRAVA_REFRESH_TOKEN`.
