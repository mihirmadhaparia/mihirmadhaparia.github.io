# AI Business Platform OS

This project is a Streamlit-based business platform designed as a first strong preliminary version of the system described in your director's note. It covers the full working flow:

- Design and costing
- Price finalization and quotation
- Contract terms and project signing controls
- Material procurement with best-price / terms comparison and approval routing
- Shop drawings and design deliverables
- Consultant and client approvals
- Timeline, manpower, and progress control
- QA / QC checks
- Logistics and site placement planning
- Installation planning and control
- Handover / closeout
- Accounts reporting
- HR functionality
- Health and safety

The app is styled to align with the visual direction already used on `mihirmadhaparia.com`: light glass surfaces, blue accent color, compact typography, and portfolio-style spacing.

## What It Produces

The app is built around data input first, then downloadable output:

- Executive summary
- Pricing and contract notes
- Cost sheet CSV
- Procurement register CSV
- Design register CSV
- Consultant approvals CSV
- Master schedule CSV
- Manpower plan CSV
- Quality plan CSV
- Logistics and site placement CSVs
- Installation checklist CSV
- Handover dossier
- Accounts report CSV
- HR plan CSV
- HSE register CSV
- Dashboard HTML snapshot
- Full ZIP package containing the entire control pack

## Run Locally

If you are working with this app as a standalone folder, from this folder:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Then open the local URL shown in the terminal, usually:

```text
http://localhost:8501
```

If you are running it from inside the portfolio repository, use the repository root so local behavior matches Streamlit Community Cloud:

```powershell
cd C:\path\to\mihirmadhaparia.github.io
python -m streamlit run apps/ai-business-platform-os/app.py
```

## Hosting Online

Because your portfolio site is a static website, the practical path is:

1. Host this Streamlit app on Streamlit Community Cloud.
2. Link to that hosted app from the `Projects` page on your website.

If you want this app to live inside the same website repo structure as your existing Streamlit app, copy this folder into:

```text
apps/ai-business-platform-os
```

inside your `mihirmadhaparia.github.io` repository, then deploy with:

- Repository: `mihirmadhaparia/mihirmadhaparia.github.io`
- Branch: `main`
- Entrypoint: `apps/ai-business-platform-os/app.py`
- Suggested subdomain: `mihir-business-platform`

After the Streamlit app is created once, pushes to that repo will update the deployed app automatically.

Community Cloud supports apps whose entrypoint lives in a subdirectory. In that setup, the shared repository-level `.streamlit/config.toml` is the main config file used by deployed apps, while `apps/ai-business-platform-os/requirements.txt` can stay next to this app's entrypoint.

## Website Integration Note

Your website already uses a static portfolio page plus separately hosted Streamlit apps. This app is intentionally built to fit that pattern:

- Portfolio site provides the project card and launch button
- Streamlit hosts the live business platform
- The app UI mirrors your site's scheme so the transition feels consistent

## Next Recommended Upgrade

This version is designed to be useful immediately without requiring a backend database or paid AI service. The clean next steps are:

- Add persistent storage with Supabase, PostgreSQL, or Firebase
- Add user authentication
- Add file uploads for real drawings, contracts, and QA records
- Add real LLM-backed workflows for draft proposal writing, contract review, and automated risk summaries
- Add a multi-project database view and role-based dashboards
