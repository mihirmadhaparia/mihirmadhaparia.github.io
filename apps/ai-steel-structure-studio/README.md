# AI Steel Structure Studio

This app is mirrored inside the portfolio repository so it can live alongside the website and be deployed from the same GitHub project.

## Deploy From The Portfolio Repo

Deploy this app on Streamlit Community Cloud with:

- Repository: `mihirmadhaparia/mihirmadhaparia.github.io`
- Branch: `main`
- Entrypoint file: `apps/ai-steel-structure-studio/app.py`
- Suggested custom subdomain: `mihir-ai-steel-studios`

The portfolio site links its **Launch App** button to:

```text
https://mihir-ai-steel-studios.streamlit.app
```

After the app is created once in Streamlit Community Cloud, future pushes to this repo will update the deployed app automatically.

A Streamlit MVP for turning a plain-English building prompt into a conceptual steel structure package:

- 3D browser preview with opaque section-aware primary frames, rafters, purlins, girts, bracing, cladding surfaces, visible connection plates, clips, gussets, bolts, and slab
- Downloadable STL and OBJ mesh exports for 3D viewing
- Downloadable DXF and SVG conceptual drawings
- Downloadable BOM CSV and project JSON
- Free built-in prompt parser with optional Ollama, OpenAI, and Gemini extraction backends
- Section-aware 3D visualization using extensive `steel_sections.csv`, `purlin_sections.csv`, and `brace_connection_catalog.csv` catalogs
- Roof and wall cladding takeoffs using `roofing_options.csv`, including corrugated, ribbed, standing seam, trapezoidal, insulated, deck, and translucent sheet options
- One active project at a time with a chat-style prompt page for follow-up requests

This is a concept generator, not an engineered design tool. A licensed structural engineer must verify loads, member sizing, connections, foundations, code compliance, and permit drawings before construction.

## Quick Start

From this folder:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

If PowerShell blocks venv activation, run this once in the current terminal:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Then open the local Streamlit URL shown in the terminal, usually:

```text
http://localhost:8501
```

## How To Use The App

1. Open the **Prompt** tab.
2. Use the chat box to describe the building, for example:

```text
Design a 60m x 24m x 9m steel factory with a gable roof, 10 bays, wall girts, purlins, and cross bracing.
```

3. Continue in the same chat with follow-ups like `make it 5m wider`, `remove wall girts`, or `switch to a mono-slope roof`.
4. Fine-tune dimensions, roof style, bay count, and member display sizes in the sidebar.
5. Review the **3D Preview** and **Drawings + BOM** tabs. In **3D Preview**, enable the large visualizer and use its **Full screen** button for easier orbiting and inspection.
6. Download STL, OBJ, DXF, SVG, BOM CSV, or JSON from the **Exports** tab.

To keep refining the same project, keep chatting in the **Prompt** tab. Example follow-ups:

```text
Make it 70m long and switch to a mono-slope roof.
Remove wall girts and add cross bracing.
Make it 5m wider and increase the bay count to 12.
Use standing seam roof sheets and insulated wall panels.
```

The app intentionally keeps one active project in session. Use **Reset Project** when you want to start over.

## Steel And Connection Catalogs

The app loads section data from `steel_sections.csv` and falls back to an embedded starter catalog if the CSV is missing. The current generated catalog includes thousands of AISC-style W, M, S, HP, C, MC, HSS, pipe, tee, and angle entries plus cold-formed purlin families.

`purlin_sections.csv` contains generated common Z, lapped Z, C, sigma, hat, and eave-strut style purlins/girts. `brace_connection_catalog.csv` contains angle-based conceptual brace, bolt, weld, and plate rules. `roofing_options.csv` contains roof and wall sheet/deck/cladding families used for takeoff rows and cladding fastener notes.

The app uses member angles to select conceptual brace plates/bolts and adds connection hardware rows to the BOM. The 3D preview also shows visible base plates, primary frame plates, purlin clips, girt clips, brace gussets, and bolt/anchor markers so the connection concept can be inspected visually.

The catalog can be regenerated with:

```powershell
python .\tools\build_catalogs.py
```

The best production source for U.S. shapes is the official AISC Shapes Database v16.0. The current generated values are for visual/detailing prototypes only; verify all dimensions, weights, and design properties before engineering use.

The Drawings + BOM tab also includes conceptual bolt, weld, bracket, and plate schedules. These details are placeholders for conversations and engineer handoff, not fabrication instructions.

## AI Integration Options

The app is designed so AI only extracts structured parameters. The CAD generation is deterministic Python, which makes the output more predictable and keeps API costs low.

### Option 1: Free Built-In Parser

Use **Free local parser** in the app. It costs nothing, runs offline, and understands common prompts like:

- `40m x 20m x 10m warehouse`
- `60 meters long, 25 meters wide, 12 meters tall`
- `8 bay gable roof factory with bracing`

This is the best place to start.

### Option 2: Free Local AI With Ollama

Install Ollama, then pull a local model:

```powershell
ollama pull llama3.2:1b
```

In the app, go to **AI Setup**:

- Extraction engine: `Ollama Local`
- Host: `http://localhost:11434`
- Model: `llama3.2:1b`

Use the **Test Ollama Connection** button in the **AI Setup** tab to verify that Ollama is running and that at least one model is available. On Windows, Ollama usually runs in the background after installation. If it is not reachable, open the Ollama app or run:

```powershell
ollama serve
```

Good alternatives to try locally are `llama3.1`, `qwen2.5`, `mistral`, or a newer small instruct model that fits your computer.

### Option 3: Paid OpenAI API

Set environment variables before launching Streamlit:

```powershell
$env:OPENAI_API_KEY="your_api_key_here"
$env:OPENAI_MODEL="gpt-5.4-mini"
python -m streamlit run app.py
```

In the app, choose **OpenAI**. This is useful when customer prompts are vague, messy, or include many requirements in one paragraph.

### Option 4: Paid Google Gemini API

Set environment variables before launching Streamlit:

```powershell
$env:GEMINI_API_KEY="your_api_key_here"
$env:GEMINI_MODEL="gemini-2.5-flash"
python -m streamlit run app.py
```

In the app, choose **Google Gemini**. This is another practical low-cost extraction option.

## Recommended Agent Roadmap

Start with one extraction agent only. Do not let the AI directly write CAD geometry until you have a strong validation layer.

1. **Prompt extraction agent:** Converts user text into length, width, height, roof type, bay count, and options.
2. **Structural checklist agent:** Flags missing location, snow load, wind speed, seismic category, occupancy, crane loads, mezzanine loads, and fire rating.
3. **Costing agent:** Converts the BOM into a rough material and erection estimate.
4. **Proposal agent:** Turns the generated package into a customer-facing summary for your website.
5. **Engineer handoff agent:** Produces a clean design brief for a licensed structural engineer.

## Future Website Path

Streamlit is excellent for this prototype. For your website, the clean migration path is:

- Move `BuildingSpec`, parsing, model generation, and export functions into a backend package.
- Wrap the backend with FastAPI endpoints:
  - `POST /extract`
  - `POST /generate`
  - `GET /download/{file_id}`
- Build the public UI in React, Next.js, or your existing website stack.
- Store generated packages in object storage such as S3, Cloudflare R2, or Supabase Storage.
- Add a job queue for large CAD exports once you add FreeCAD, CadQuery, or another CAD kernel.

## Adding STEP Or Native CAD Later

This MVP intentionally exports STL, OBJ, DXF, SVG, CSV, and JSON without a heavy CAD kernel. That makes it easy to run on Python 3.13.

For STEP files later, use one of these approaches:

- **CadQuery/OpenCascade service:** Good Python API, but may require Python 3.10 or 3.11 depending on available wheels.
- **FreeCAD worker:** Strong STEP export path, good for server-side jobs, heavier install.
- **Commercial CAD API:** Best for production reliability, but usually paid.

Keep native CAD generation in a backend worker, not directly in the website frontend.

## Project Files

- `app.py`: Streamlit app, parser, AI provider calls, geometry generation, previews, and exports
- `requirements.txt`: Python dependencies
- `.env.example`: Optional AI environment variable template
- `steel_sections.csv`: Extensive editable section catalog for visual member profiles and BOM grouping
- `purlin_sections.csv`: Generated purlin/girt/eave-strut catalog
- `brace_connection_catalog.csv`: Angle-based conceptual brace, bolt, weld, and plate rules
- `roofing_options.csv`: Roof/wall cladding, deck, corrugated sheet, insulated panel, and translucent sheet catalog
- `tools/build_catalogs.py`: Regenerates the section, purlin, and brace/connection catalogs
