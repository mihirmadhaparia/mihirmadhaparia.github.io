from __future__ import annotations

import html
import io
import json
import math
import textwrap
import zipfile
from copy import deepcopy
from datetime import date, datetime, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components


APP_TITLE = "AI Business Platform OS"
APP_TAGLINE = (
    "A portfolio-ready operating system for design, costing, contracts, procurement, "
    "approvals, execution, accounts, HR, health and safety, and handover."
)

COST_COLUMNS = ["category", "description", "qty", "unit", "unit_cost", "owner", "status"]
MILESTONE_COLUMNS = ["milestone", "trigger", "percent_due", "days_from_award", "owner"]
PROCUREMENT_COLUMNS = [
    "package",
    "primary_supplier",
    "primary_price",
    "primary_lead_days",
    "primary_terms_score",
    "alternate_supplier",
    "alternate_price",
    "alternate_lead_days",
    "alternate_terms_score",
    "approval_status",
    "approved_by",
]
DESIGN_COLUMNS = ["deliverable", "department", "owner", "due_week", "status", "consultant", "revision"]
APPROVAL_COLUMNS = ["submission", "authority", "due_week", "status", "comments"]
PHASE_COLUMNS = ["phase", "department", "owner", "start_week", "duration_weeks", "progress_pct", "quality_gate"]
MANPOWER_COLUMNS = ["role", "crew_count", "weeks", "weekly_rate", "deployment_stage"]
QUALITY_COLUMNS = ["checkpoint", "stage", "owner", "status", "evidence_required"]
LOGISTICS_COLUMNS = ["delivery", "material", "week", "site_zone", "status", "responsible_party"]
SITE_COLUMNS = ["zone", "material_package", "storage_method", "week", "status"]
INSTALLATION_COLUMNS = ["task", "crew", "duration_days", "status", "inspection_required"]
HANDOVER_COLUMNS = ["requirement", "owner", "status", "due_week", "evidence"]
ACCOUNTS_COLUMNS = ["period", "invoiced", "collected", "committed_cost", "paid_cost", "status"]
HR_COLUMNS = ["role", "current_headcount", "required_headcount", "training_hours", "recruitment_status"]
HSE_COLUMNS = ["risk", "severity", "mitigation", "owner", "incidents", "status"]

GOOD_STATUSES = {"approved", "signed off", "completed", "complete", "closed", "pass", "released", "done"}
WARNING_STATUSES = {"hold", "late", "overdue", "rejected", "open", "pending", "submitted", "in progress"}


DEFAULT_PROJECT_DATA = {
    "profile": {
        "company_name": "Mihir Business Systems",
        "project_name": "Preliminary Architectural Delivery Platform",
        "client_name": "Sample Client",
        "project_location": "Chicago, USA",
        "currency": "USD",
        "project_manager": "Project Director",
        "design_manager": "Design Lead",
        "procurement_lead": "Procurement Lead",
        "site_manager": "Site Manager",
        "contract_start": "2026-05-04",
        "target_handover": "2026-09-25",
        "business_model": "Design, procurement, fabrication, installation, and final handover",
        "scope_summary": (
            "End-to-end business control for pricing, contracts, materials, design, consultant "
            "approvals, execution, quality, logistics, installation, and closeout."
        ),
        "director_brief": (
            "AI app controlling design, costing, price finalization, project signing, material "
            "purchase, shop drawings, consultant sign-off, timelines, manpower, progress, "
            "quality, logistics, site planning, installation, and handover, plus accounts, HR, "
            "and health and safety."
        ),
    },
    "commercial": {
        "proposal_version": "P-001",
        "target_margin_pct": 18.0,
        "contingency_pct": 5.0,
        "overhead_pct": 8.0,
        "tax_pct": 5.0,
        "retention_pct": 5.0,
        "warranty_months": 12,
        "payment_terms": "30% advance, 30% after approved shop drawings, 30% on installation progress, 10% at handover",
        "contract_notes": (
            "Include change-order controls, consultant approval gates, material approval before "
            "fabrication, and handover documentation obligations."
        ),
        "scope_inclusions": (
            "Design coordination, cost build-up, procurement control, shop drawings, approvals, "
            "installation planning, QA/QC, closeout dossiers."
        ),
        "scope_exclusions": "Authority fees, unusual site shutdown costs, client-side utility upgrades.",
    },
    "cost_items": [
        {"category": "Design", "description": "Engineering and drafting package", "qty": 180, "unit": "hours", "unit_cost": 95, "owner": "Design", "status": "In progress"},
        {"category": "Materials", "description": "Primary material package", "qty": 1, "unit": "lot", "unit_cost": 128000, "owner": "Procurement", "status": "Budgeted"},
        {"category": "Fabrication", "description": "Workshop production and fit-up", "qty": 1, "unit": "lot", "unit_cost": 62000, "owner": "Operations", "status": "Budgeted"},
        {"category": "Installation", "description": "Site labor and supervision", "qty": 1, "unit": "lot", "unit_cost": 54000, "owner": "Site", "status": "Budgeted"},
        {"category": "Logistics", "description": "Deliveries, lifting, and site handling", "qty": 1, "unit": "lot", "unit_cost": 17500, "owner": "Logistics", "status": "Budgeted"},
        {"category": "QA / HSE", "description": "Inspection, testing, and safety compliance", "qty": 1, "unit": "lot", "unit_cost": 9800, "owner": "QA/HSE", "status": "Budgeted"},
    ],
    "contract_milestones": [
        {"milestone": "Award and mobilization", "trigger": "LOI / contract signature", "percent_due": 30, "days_from_award": 0, "owner": "Commercial"},
        {"milestone": "Approved shop drawings", "trigger": "Consultant sign-off", "percent_due": 20, "days_from_award": 21, "owner": "Design"},
        {"milestone": "Material release", "trigger": "Approved material submittals", "percent_due": 20, "days_from_award": 30, "owner": "Procurement"},
        {"milestone": "Installation progress", "trigger": "Measured work completed", "percent_due": 20, "days_from_award": 60, "owner": "Site"},
        {"milestone": "Final handover", "trigger": "Snag closeout and documents", "percent_due": 10, "days_from_award": 105, "owner": "PMO"},
    ],
    "procurement_items": [
        {
            "package": "Facade aluminum system",
            "primary_supplier": "Supplier A",
            "primary_price": 82000,
            "primary_lead_days": 21,
            "primary_terms_score": 7,
            "alternate_supplier": "Supplier B",
            "alternate_price": 79000,
            "alternate_lead_days": 28,
            "alternate_terms_score": 6,
            "approval_status": "Pending approval",
            "approved_by": "Director",
        },
        {
            "package": "Glass package",
            "primary_supplier": "Supplier C",
            "primary_price": 54000,
            "primary_lead_days": 18,
            "primary_terms_score": 8,
            "alternate_supplier": "Supplier D",
            "alternate_price": 56000,
            "alternate_lead_days": 14,
            "alternate_terms_score": 7,
            "approval_status": "Pending approval",
            "approved_by": "Procurement Lead",
        },
        {
            "package": "Fixings and brackets",
            "primary_supplier": "Supplier E",
            "primary_price": 12000,
            "primary_lead_days": 10,
            "primary_terms_score": 7,
            "alternate_supplier": "Supplier F",
            "alternate_price": 11100,
            "alternate_lead_days": 13,
            "alternate_terms_score": 8,
            "approval_status": "Approved",
            "approved_by": "Site Manager",
        },
        {
            "package": "Sealants and consumables",
            "primary_supplier": "Supplier G",
            "primary_price": 6900,
            "primary_lead_days": 7,
            "primary_terms_score": 6,
            "alternate_supplier": "Supplier H",
            "alternate_price": 7200,
            "alternate_lead_days": 5,
            "alternate_terms_score": 7,
            "approval_status": "Approved",
            "approved_by": "Procurement Lead",
        },
    ],
    "design_deliverables": [
        {"deliverable": "Concept design pack", "department": "Design", "owner": "Design Lead", "due_week": 1, "status": "Completed", "consultant": "Lead Consultant", "revision": "R1"},
        {"deliverable": "Shop drawings", "department": "Design", "owner": "Drafting Team", "due_week": 3, "status": "In progress", "consultant": "Lead Consultant", "revision": "R0"},
        {"deliverable": "Material submittal", "department": "Procurement", "owner": "Procurement Lead", "due_week": 3, "status": "Submitted", "consultant": "Lead Consultant", "revision": "R0"},
        {"deliverable": "Mock-up package", "department": "QA / Design", "owner": "QA Lead", "due_week": 5, "status": "Pending", "consultant": "Lead Consultant", "revision": "R0"},
        {"deliverable": "As-built drawings", "department": "Design", "owner": "Design Lead", "due_week": 14, "status": "Pending", "consultant": "Client Team", "revision": "R0"},
    ],
    "consultant_approvals": [
        {"submission": "Shop drawing set", "authority": "Lead Consultant", "due_week": 4, "status": "Pending", "comments": "Awaiting coordination comments"},
        {"submission": "Material finish board", "authority": "Lead Consultant", "due_week": 3, "status": "Submitted", "comments": "Color confirmation pending"},
        {"submission": "Mock-up sign-off", "authority": "Client / Consultant", "due_week": 6, "status": "Pending", "comments": "Needed before full release"},
        {"submission": "Inspection request - anchors", "authority": "QA / Consultant", "due_week": 8, "status": "Pending", "comments": "Dependent on site readiness"},
        {"submission": "Final completion and handover", "authority": "Client", "due_week": 15, "status": "Pending", "comments": "Requires documents and snag closeout"},
    ],
    "phases": [
        {"phase": "Award and mobilization", "department": "Commercial", "owner": "Project Director", "start_week": 1, "duration_weeks": 1, "progress_pct": 100, "quality_gate": "Contract executed"},
        {"phase": "Design development", "department": "Design", "owner": "Design Lead", "start_week": 1, "duration_weeks": 3, "progress_pct": 55, "quality_gate": "Drawings internally reviewed"},
        {"phase": "Procurement and approvals", "department": "Procurement", "owner": "Procurement Lead", "start_week": 2, "duration_weeks": 4, "progress_pct": 35, "quality_gate": "Approvals before release"},
        {"phase": "Fabrication", "department": "Operations", "owner": "Workshop Manager", "start_week": 5, "duration_weeks": 4, "progress_pct": 0, "quality_gate": "Factory QA inspections"},
        {"phase": "Site preparation", "department": "Site", "owner": "Site Manager", "start_week": 6, "duration_weeks": 2, "progress_pct": 10, "quality_gate": "Access and safety clear"},
        {"phase": "Installation", "department": "Site", "owner": "Site Manager", "start_week": 8, "duration_weeks": 5, "progress_pct": 0, "quality_gate": "Stage inspections complete"},
        {"phase": "Handover and closeout", "department": "PMO", "owner": "Project Manager", "start_week": 13, "duration_weeks": 2, "progress_pct": 0, "quality_gate": "Snags and documents closed"},
    ],
    "manpower_plan": [
        {"role": "Design engineers", "crew_count": 2, "weeks": 4, "weekly_rate": 2400, "deployment_stage": "Design development"},
        {"role": "Draftsmen", "crew_count": 3, "weeks": 6, "weekly_rate": 1800, "deployment_stage": "Shop drawings"},
        {"role": "Procurement coordinator", "crew_count": 1, "weeks": 5, "weekly_rate": 2200, "deployment_stage": "Procurement"},
        {"role": "QA / QC inspector", "crew_count": 1, "weeks": 8, "weekly_rate": 2100, "deployment_stage": "Production to handover"},
        {"role": "Site supervisors", "crew_count": 2, "weeks": 7, "weekly_rate": 1900, "deployment_stage": "Installation"},
        {"role": "Installers", "crew_count": 8, "weeks": 6, "weekly_rate": 1100, "deployment_stage": "Installation"},
        {"role": "HSE officer", "crew_count": 1, "weeks": 8, "weekly_rate": 1850, "deployment_stage": "Site execution"},
    ],
    "quality_checks": [
        {"checkpoint": "Internal drawing check", "stage": "Design", "owner": "Design Lead", "status": "Pass", "evidence_required": "Approved issue sheet"},
        {"checkpoint": "Incoming material inspection", "stage": "Procurement", "owner": "QA / QC", "status": "Pending", "evidence_required": "Delivery and inspection report"},
        {"checkpoint": "Mock-up approval", "stage": "Design / QA", "owner": "Project Manager", "status": "Pending", "evidence_required": "Signed mock-up report"},
        {"checkpoint": "Anchor layout verification", "stage": "Site", "owner": "Site Manager", "status": "Pending", "evidence_required": "Survey record"},
        {"checkpoint": "Installation plumb / line / level", "stage": "Installation", "owner": "QA / QC", "status": "Pending", "evidence_required": "Inspection checklist"},
        {"checkpoint": "Snag and final quality review", "stage": "Closeout", "owner": "Project Manager", "status": "Pending", "evidence_required": "Signed snag log"},
    ],
    "logistics_plan": [
        {"delivery": "Main profiles delivery", "material": "Facade aluminum system", "week": 5, "site_zone": "Zone A laydown", "status": "Planned", "responsible_party": "Logistics Lead"},
        {"delivery": "Glass delivery", "material": "Glass package", "week": 7, "site_zone": "Protected storage", "status": "Planned", "responsible_party": "Logistics Lead"},
        {"delivery": "Fixings delivery", "material": "Fixings and brackets", "week": 6, "site_zone": "Tool container", "status": "Released", "responsible_party": "Procurement Lead"},
    ],
    "site_placement": [
        {"zone": "Zone A", "material_package": "Frames and mullions", "storage_method": "Timber racks", "week": 5, "status": "Planned"},
        {"zone": "Zone B", "material_package": "Glass panels", "storage_method": "A-frame with cover", "week": 7, "status": "Planned"},
        {"zone": "Zone C", "material_package": "Fixings and sealants", "storage_method": "Secured container", "week": 6, "status": "Ready"},
    ],
    "installation_tasks": [
        {"task": "Set-out and survey", "crew": "Survey + supervisor", "duration_days": 2, "status": "Pending", "inspection_required": "Survey approval"},
        {"task": "Anchor installation", "crew": "Installation crew 1", "duration_days": 3, "status": "Pending", "inspection_required": "Anchor inspection"},
        {"task": "Frame erection", "crew": "Installation crew 1 and 2", "duration_days": 8, "status": "Pending", "inspection_required": "Line and level check"},
        {"task": "Glass / infill installation", "crew": "Glazing crew", "duration_days": 7, "status": "Pending", "inspection_required": "Visual and tolerance check"},
        {"task": "Sealant and finishing", "crew": "Finishing crew", "duration_days": 3, "status": "Pending", "inspection_required": "Final QA walk"},
    ],
    "handover_items": [
        {"requirement": "As-built drawings", "owner": "Design Lead", "status": "Pending", "due_week": 14, "evidence": "Approved as-built set"},
        {"requirement": "Operation and maintenance manuals", "owner": "QA / QC", "status": "Pending", "due_week": 14, "evidence": "O&M manual PDF"},
        {"requirement": "Warranty certificates", "owner": "Commercial", "status": "Pending", "due_week": 14, "evidence": "Warranty letters"},
        {"requirement": "Training and orientation", "owner": "Project Manager", "status": "Pending", "due_week": 15, "evidence": "Attendance record"},
        {"requirement": "Final account closure", "owner": "Accounts", "status": "Pending", "due_week": 15, "evidence": "Signed final statement"},
        {"requirement": "Client handover certificate", "owner": "Project Director", "status": "Pending", "due_week": 15, "evidence": "Signed certificate"},
    ],
    "accounts_entries": [
        {"period": "May 2026", "invoiced": 78000, "collected": 78000, "committed_cost": 65000, "paid_cost": 49000, "status": "Collected"},
        {"period": "June 2026", "invoiced": 42000, "collected": 21000, "committed_cost": 43000, "paid_cost": 26000, "status": "Partially collected"},
        {"period": "July 2026", "invoiced": 36000, "collected": 0, "committed_cost": 51000, "paid_cost": 12000, "status": "Pending"},
    ],
    "hr_plan": [
        {"role": "Design", "current_headcount": 4, "required_headcount": 5, "training_hours": 20, "recruitment_status": "Open"},
        {"role": "Procurement", "current_headcount": 2, "required_headcount": 2, "training_hours": 12, "recruitment_status": "Stable"},
        {"role": "Site", "current_headcount": 9, "required_headcount": 10, "training_hours": 18, "recruitment_status": "Open"},
        {"role": "QA / QC", "current_headcount": 1, "required_headcount": 2, "training_hours": 16, "recruitment_status": "Open"},
        {"role": "HSE", "current_headcount": 1, "required_headcount": 1, "training_hours": 24, "recruitment_status": "Stable"},
    ],
    "hse_register": [
        {"risk": "Working at height", "severity": "High", "mitigation": "Harness, permit, edge protection", "owner": "HSE Officer", "incidents": 0, "status": "Open"},
        {"risk": "Lifting operations", "severity": "High", "mitigation": "Lift plan and certified riggers", "owner": "Site Manager", "incidents": 0, "status": "Open"},
        {"risk": "Glass handling", "severity": "Medium", "mitigation": "Vacuum lifters and handling SOP", "owner": "QA / QC", "incidents": 1, "status": "Open"},
        {"risk": "Electrical tools", "severity": "Medium", "mitigation": "PAT checks and lockout procedure", "owner": "HSE Officer", "incidents": 0, "status": "Closed"},
        {"risk": "Housekeeping and access", "severity": "Low", "mitigation": "Daily cleanup and walkways", "owner": "Site Supervisor", "incidents": 0, "status": "Open"},
    ],
}


def clone_defaults() -> dict:
    return deepcopy(DEFAULT_PROJECT_DATA)


def to_float(value: object, default: float = 0.0) -> float:
    if value in ("", None):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def to_int(value: object, default: int = 0) -> int:
    if value in ("", None):
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def parse_date(value: str, fallback: date | None = None) -> date:
    if fallback is None:
        fallback = date.today()
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return fallback


def format_money(value: float, currency: str) -> str:
    return f"{currency} {value:,.0f}"


def format_pct(value: float) -> str:
    return f"{value:,.1f}%"


def safe_label(value: object) -> str:
    return str(value).strip() if value not in (None, "") else "Unassigned"


def status_text(value: object) -> str:
    return str(value).strip().lower()


def is_good_status(value: object) -> bool:
    text = status_text(value)
    return any(keyword in text for keyword in GOOD_STATUSES)


def is_warning_status(value: object) -> bool:
    text = status_text(value)
    return any(keyword in text for keyword in WARNING_STATUSES)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def dataframe_from_rows(rows: list[dict], columns: list[str]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    for column in columns:
        if column not in frame.columns:
            frame[column] = ""
    frame = frame[columns]
    return frame.fillna("")


def edited_records(key: str, rows: list[dict], columns: list[str], height: int = 250) -> list[dict]:
    frame = dataframe_from_rows(rows, columns)
    edited = st.data_editor(
        frame,
        key=key,
        hide_index=True,
        num_rows="dynamic",
        use_container_width=True,
        height=height,
    )
    cleaned = edited.fillna("")
    return cleaned.to_dict(orient="records")


def csv_bytes_from_frame(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False).encode("utf-8")


def init_state() -> None:
    if "platform_data" not in st.session_state:
        st.session_state.platform_data = clone_defaults()
    if "copilot_answer" not in st.session_state:
        st.session_state.copilot_answer = ""


def load_css() -> None:
    st.markdown(
        """
        <style>
            @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
            :root {
                --bg: #f9f9fb;
                --surface: rgba(255,255,255,0.84);
                --surface-strong: rgba(255,255,255,0.96);
                --text-primary: #1d1d1f;
                --text-secondary: #5f6672;
                --border: rgba(0,0,0,0.08);
                --border-strong: rgba(0,0,0,0.12);
                --accent: #0071e3;
                --accent-deep: #0058b0;
                --accent-soft: rgba(0,113,227,0.10);
                --shadow-sm: 0 12px 28px rgba(15, 23, 42, 0.06);
                --shadow-md: 0 22px 50px rgba(15, 23, 42, 0.08);
                --radius-xl: 28px;
                --radius-lg: 20px;
                --radius-md: 16px;
                --radius-sm: 12px;
            }
            #MainMenu, footer, [data-testid="stDecoration"], [data-testid="stStatusWidget"], .stDeployButton {
                display: none !important;
            }
            .stApp {
                background:
                    radial-gradient(circle at top left, rgba(0,113,227,0.12), transparent 24%),
                    radial-gradient(circle at top right, rgba(32, 164, 243, 0.08), transparent 22%),
                    linear-gradient(180deg, #f8f8fb 0%, #f3f4f7 58%, #eef1f5 100%);
                color: var(--text-primary) !important;
                font-family: "Plus Jakarta Sans", sans-serif;
            }
            [data-testid="stHeader"] {
                background: transparent !important;
            }
            [data-testid="stSidebar"] {
                background: rgba(255,255,255,0.78) !important;
                border-right: 1px solid var(--border);
                backdrop-filter: blur(18px);
            }
            .block-container {
                max-width: min(1440px, calc(100vw - 32px));
                padding-top: 1rem;
                padding-bottom: 3rem;
            }
            .stApp, .stMarkdown, .stMarkdown * {
                font-family: "Plus Jakarta Sans", sans-serif;
            }
            h1, h2, h3, h4 {
                color: var(--text-primary) !important;
                letter-spacing: -0.04em;
            }
            p, li, [data-testid="stCaptionContainer"], label {
                color: var(--text-secondary) !important;
            }
            .hero-shell {
                background: rgba(255,255,255,0.72);
                border: 1px solid var(--border);
                border-radius: var(--radius-xl);
                box-shadow: var(--shadow-md);
                padding: 28px 30px;
                backdrop-filter: blur(20px);
                margin-bottom: 18px;
            }
            .eyebrow {
                display: inline-flex;
                gap: 10px;
                align-items: center;
                font-family: "IBM Plex Mono", monospace !important;
                font-size: 0.76rem;
                font-weight: 700;
                letter-spacing: 0.14em;
                text-transform: uppercase;
                color: var(--accent) !important;
                margin-bottom: 12px;
            }
            .eyebrow::before {
                content: "";
                width: 28px;
                height: 1px;
                background: rgba(0,113,227,0.45);
            }
            .hero-title {
                font-size: clamp(2.5rem, 5vw, 4.6rem);
                line-height: 0.94;
                margin: 0;
            }
            .hero-copy {
                max-width: 880px;
                font-size: 1.02rem;
                line-height: 1.7;
                margin: 18px 0 0;
            }
            .chip-row {
                display: flex;
                flex-wrap: wrap;
                gap: 10px;
                margin-top: 22px;
            }
            .chip {
                display: inline-flex;
                align-items: center;
                padding: 7px 12px;
                border-radius: 999px;
                font-size: 0.78rem;
                font-family: "IBM Plex Mono", monospace !important;
                background: rgba(0,0,0,0.04);
                border: 1px solid rgba(0,0,0,0.06);
                color: var(--text-secondary) !important;
            }
            .section-card {
                background: rgba(255,255,255,0.76);
                border: 1px solid var(--border);
                border-radius: var(--radius-lg);
                box-shadow: var(--shadow-sm);
                padding: 20px 22px;
                backdrop-filter: blur(18px);
                margin-bottom: 16px;
            }
            .section-card h3 {
                margin-bottom: 0.35rem;
            }
            .section-copy {
                margin: 0;
                line-height: 1.65;
            }
            .brief-list {
                margin: 0;
                padding-left: 18px;
            }
            .brief-list li {
                margin-bottom: 8px;
                line-height: 1.62;
            }
            .notice {
                background: linear-gradient(180deg, rgba(0,113,227,0.06), rgba(255,255,255,0.85));
                border: 1px solid rgba(0,113,227,0.14);
                border-radius: var(--radius-lg);
                padding: 18px 20px;
                box-shadow: var(--shadow-sm);
            }
            .notice strong {
                color: var(--text-primary);
            }
            .stTextInput input, .stTextArea textarea, .stNumberInput input, div[data-baseweb="select"] > div {
                background: var(--surface-strong) !important;
                border: 1px solid var(--border) !important;
                border-radius: 14px !important;
                color: var(--text-primary) !important;
                box-shadow: none !important;
            }
            .stTextInput input:focus, .stTextArea textarea:focus, .stNumberInput input:focus {
                border-color: rgba(0,113,227,0.35) !important;
                box-shadow: 0 0 0 4px rgba(0,113,227,0.10) !important;
            }
            .stButton > button, .stDownloadButton > button {
                background: rgba(255,255,255,0.92) !important;
                border: 1px solid transparent !important;
                border-radius: 999px !important;
                box-shadow: 0 12px 28px rgba(15,23,42,0.06) !important;
                color: var(--text-primary) !important;
                font-weight: 600 !important;
                min-height: 44px !important;
            }
            .stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {
                background: linear-gradient(135deg, #0d4b96, var(--accent)) !important;
                color: #ffffff !important;
                box-shadow: 0 18px 32px rgba(0,113,227,0.18) !important;
            }
            [data-testid="stMetric"] {
                background: rgba(255,255,255,0.78);
                border: 1px solid var(--border);
                border-radius: var(--radius-lg);
                box-shadow: var(--shadow-sm);
                padding: 18px;
                backdrop-filter: blur(18px);
            }
            [data-testid="stTabs"] button {
                border-radius: 999px !important;
                padding: 10px 14px !important;
                font-weight: 600 !important;
                color: var(--text-secondary) !important;
            }
            [data-testid="stTabs"] button[aria-selected="true"] {
                background: rgba(0,0,0,0.05) !important;
                color: var(--text-primary) !important;
            }
            .streamlit-expanderHeader {
                font-weight: 700 !important;
            }
            [data-testid="stDataFrame"], [data-testid="stTable"] {
                border: 1px solid var(--border);
                border-radius: var(--radius-md);
                overflow: hidden;
            }
            code, pre {
                font-family: "IBM Plex Mono", monospace !important;
            }
            @media (max-width: 900px) {
                .hero-shell {
                    padding: 22px 20px;
                }
                .hero-title {
                    font-size: clamp(2.2rem, 10vw, 3.5rem);
                }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_hero(data: dict) -> None:
    profile = data["profile"]
    st.markdown(
        f"""
        <section class="hero-shell">
            <div class="eyebrow">Business Platform</div>
            <h1 class="hero-title">Run the full business lifecycle from quotation to handover.</h1>
            <p class="hero-copy">
                Styled to match <strong>mihirmadhaparia.com</strong>, this preliminary platform ties together
                design, costing, contract controls, procurement, shop drawings, consultant approvals,
                schedule, manpower, QA/QC, logistics, site planning, installation, closeout, accounts,
                HR, and health &amp; safety.
            </p>
            <div class="chip-row">
                <span class="chip">{html.escape(profile["project_name"])}</span>
                <span class="chip">{html.escape(profile["client_name"])}</span>
                <span class="chip">{html.escape(profile["project_location"])}</span>
                <span class="chip">Downloadable outputs</span>
                <span class="chip">Portfolio-matched UI</span>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def procurement_recommendations(rows: list[dict]) -> pd.DataFrame:
    frame = dataframe_from_rows(rows, PROCUREMENT_COLUMNS)

    def compute_row(row: pd.Series) -> pd.Series:
        primary_supplier = safe_label(row["primary_supplier"])
        alternate_supplier = str(row["alternate_supplier"]).strip()
        primary_price = to_float(row["primary_price"])
        primary_lead = to_float(row["primary_lead_days"])
        primary_terms = to_float(row["primary_terms_score"])
        alternate_price = to_float(row["alternate_price"], default=math.inf if alternate_supplier else 0.0)
        alternate_lead = to_float(row["alternate_lead_days"], default=math.inf if alternate_supplier else 0.0)
        alternate_terms = to_float(row["alternate_terms_score"])

        primary_score = primary_price + primary_lead * 250 - primary_terms * 1000
        alternate_score = math.inf
        if alternate_supplier and math.isfinite(alternate_price):
            alternate_score = alternate_price + alternate_lead * 250 - alternate_terms * 1000

        if alternate_score < primary_score:
            recommended_supplier = alternate_supplier
            recommended_price = alternate_price
            recommended_lead = alternate_lead
            selected_terms = alternate_terms
        else:
            recommended_supplier = primary_supplier
            recommended_price = primary_price
            recommended_lead = primary_lead
            selected_terms = primary_terms

        potential_saving = max(primary_price - recommended_price, 0.0)

        return pd.Series(
            {
                "recommended_supplier": recommended_supplier,
                "recommended_price": recommended_price,
                "recommended_lead_days": recommended_lead,
                "recommended_terms_score": selected_terms,
                "potential_saving": potential_saving,
            }
        )

    recommendations = frame.apply(compute_row, axis=1)
    combined = pd.concat([frame, recommendations], axis=1)
    return combined


def timeline_frame(rows: list[dict], start_date: date) -> pd.DataFrame:
    frame = dataframe_from_rows(rows, PHASE_COLUMNS)
    frame["start_week"] = frame["start_week"].apply(to_int)
    frame["duration_weeks"] = frame["duration_weeks"].apply(lambda value: max(to_int(value, 1), 1))
    frame["progress_pct"] = frame["progress_pct"].apply(lambda value: clamp(to_float(value), 0, 100))
    frame["start_date"] = frame["start_week"].apply(lambda week: start_date + timedelta(weeks=max(week - 1, 0)))
    frame["finish_date"] = frame.apply(
        lambda row: row["start_date"] + timedelta(days=max(int(row["duration_weeks"] * 7), 1)),
        axis=1,
    )
    return frame


def compute_metrics(data: dict) -> dict:
    profile = data["profile"]
    commercial = data["commercial"]
    currency = profile["currency"]

    cost_df = dataframe_from_rows(data["cost_items"], COST_COLUMNS)
    cost_df["qty"] = cost_df["qty"].apply(to_float)
    cost_df["unit_cost"] = cost_df["unit_cost"].apply(to_float)
    cost_df["line_total"] = cost_df["qty"] * cost_df["unit_cost"]

    direct_cost = float(cost_df["line_total"].sum())
    contingency_value = direct_cost * to_float(commercial["contingency_pct"]) / 100
    overhead_value = direct_cost * to_float(commercial["overhead_pct"]) / 100
    base_cost = direct_cost + contingency_value + overhead_value

    target_margin_pct = clamp(to_float(commercial["target_margin_pct"]), 0, 80)
    quote_before_tax = base_cost / max(1 - (target_margin_pct / 100), 0.05)
    tax_value = quote_before_tax * to_float(commercial["tax_pct"]) / 100
    final_contract_value = quote_before_tax + tax_value
    gross_profit = quote_before_tax - base_cost
    gross_margin_pct = (gross_profit / quote_before_tax * 100) if quote_before_tax else 0.0

    procurement_df = procurement_recommendations(data["procurement_items"])
    procurement_savings = float(procurement_df["potential_saving"].sum()) if not procurement_df.empty else 0.0
    pending_procurement = int((~procurement_df["approval_status"].apply(is_good_status)).sum()) if not procurement_df.empty else 0

    approvals_df = dataframe_from_rows(data["consultant_approvals"], APPROVAL_COLUMNS)
    approval_completion_pct = (
        approvals_df["status"].apply(is_good_status).mean() * 100 if len(approvals_df.index) else 0.0
    )
    pending_approvals = int((~approvals_df["status"].apply(is_good_status)).sum()) if not approvals_df.empty else 0

    phase_df = timeline_frame(data["phases"], parse_date(profile["contract_start"]))
    schedule_completion_pct = 0.0
    if not phase_df.empty:
        weighted_progress = (phase_df["progress_pct"] * phase_df["duration_weeks"]).sum()
        total_duration = phase_df["duration_weeks"].sum()
        schedule_completion_pct = float(weighted_progress / total_duration) if total_duration else 0.0
    total_project_weeks = int((phase_df["duration_weeks"] + phase_df["start_week"] - 1).max()) if not phase_df.empty else 0

    manpower_df = dataframe_from_rows(data["manpower_plan"], MANPOWER_COLUMNS)
    manpower_df["crew_count"] = manpower_df["crew_count"].apply(to_float)
    manpower_df["weeks"] = manpower_df["weeks"].apply(to_float)
    manpower_df["weekly_rate"] = manpower_df["weekly_rate"].apply(to_float)
    manpower_df["cost"] = manpower_df["crew_count"] * manpower_df["weeks"] * manpower_df["weekly_rate"]
    active_headcount = float(manpower_df["crew_count"].sum())

    quality_df = dataframe_from_rows(data["quality_checks"], QUALITY_COLUMNS)
    qa_ready_pct = quality_df["status"].apply(is_good_status).mean() * 100 if len(quality_df.index) else 0.0
    open_qa_items = int((~quality_df["status"].apply(is_good_status)).sum()) if not quality_df.empty else 0

    handover_df = dataframe_from_rows(data["handover_items"], HANDOVER_COLUMNS)
    handover_ready_pct = handover_df["status"].apply(is_good_status).mean() * 100 if len(handover_df.index) else 0.0
    pending_handover = int((~handover_df["status"].apply(is_good_status)).sum()) if not handover_df.empty else 0

    accounts_df = dataframe_from_rows(data["accounts_entries"], ACCOUNTS_COLUMNS)
    for column in ["invoiced", "collected", "committed_cost", "paid_cost"]:
        accounts_df[column] = accounts_df[column].apply(to_float)
    total_invoiced = float(accounts_df["invoiced"].sum())
    total_collected = float(accounts_df["collected"].sum())
    total_committed = float(accounts_df["committed_cost"].sum())
    total_paid = float(accounts_df["paid_cost"].sum())
    collection_rate_pct = (total_collected / total_invoiced * 100) if total_invoiced else 0.0
    net_cash_position = total_collected - total_paid

    hr_df = dataframe_from_rows(data["hr_plan"], HR_COLUMNS)
    hr_df["current_headcount"] = hr_df["current_headcount"].apply(to_float)
    hr_df["required_headcount"] = hr_df["required_headcount"].apply(to_float)
    hr_df["training_hours"] = hr_df["training_hours"].apply(to_float)
    hr_df["gap"] = hr_df["required_headcount"] - hr_df["current_headcount"]
    hiring_gap = float(hr_df["gap"].clip(lower=0).sum()) if not hr_df.empty else 0.0
    training_hours = float(hr_df["training_hours"].sum()) if not hr_df.empty else 0.0

    hse_df = dataframe_from_rows(data["hse_register"], HSE_COLUMNS)
    hse_df["incidents"] = hse_df["incidents"].apply(to_float)
    open_high = int(
        (
            hse_df["severity"].astype(str).str.lower().isin(["high", "critical"])
            & ~hse_df["status"].apply(is_good_status)
        ).sum()
    ) if not hse_df.empty else 0
    open_medium = int(
        (
            hse_df["severity"].astype(str).str.lower().isin(["medium"])
            & ~hse_df["status"].apply(is_good_status)
        ).sum()
    ) if not hse_df.empty else 0
    incidents = float(hse_df["incidents"].sum()) if not hse_df.empty else 0.0
    safety_score = clamp(100 - open_high * 12 - open_medium * 6 - incidents * 5, 0, 100)

    top_costs = cost_df.sort_values("line_total", ascending=False).head(3)
    top_cost_lines = [
        f"{row['description']} ({format_money(row['line_total'], currency)})"
        for _, row in top_costs.iterrows()
    ]

    return {
        "currency": currency,
        "direct_cost": direct_cost,
        "contingency_value": contingency_value,
        "overhead_value": overhead_value,
        "base_cost": base_cost,
        "quote_before_tax": quote_before_tax,
        "tax_value": tax_value,
        "final_contract_value": final_contract_value,
        "gross_profit": gross_profit,
        "gross_margin_pct": gross_margin_pct,
        "procurement_savings": procurement_savings,
        "pending_procurement": pending_procurement,
        "approval_completion_pct": approval_completion_pct,
        "pending_approvals": pending_approvals,
        "schedule_completion_pct": schedule_completion_pct,
        "total_project_weeks": total_project_weeks,
        "active_headcount": active_headcount,
        "qa_ready_pct": qa_ready_pct,
        "open_qa_items": open_qa_items,
        "handover_ready_pct": handover_ready_pct,
        "pending_handover": pending_handover,
        "total_invoiced": total_invoiced,
        "total_collected": total_collected,
        "total_committed": total_committed,
        "total_paid": total_paid,
        "collection_rate_pct": collection_rate_pct,
        "net_cash_position": net_cash_position,
        "hiring_gap": hiring_gap,
        "training_hours": training_hours,
        "safety_score": safety_score,
        "open_high_hse": open_high,
        "open_medium_hse": open_medium,
        "incidents": incidents,
        "cost_df": cost_df,
        "procurement_df": procurement_df,
        "approvals_df": approvals_df,
        "phase_df": phase_df,
        "manpower_df": manpower_df,
        "quality_df": quality_df,
        "handover_df": handover_df,
        "accounts_df": accounts_df,
        "hr_df": hr_df,
        "hse_df": hse_df,
        "top_cost_lines": top_cost_lines,
    }


def build_briefing(data: dict, metrics: dict) -> dict:
    currency = metrics["currency"]
    phase_df = metrics["phase_df"]
    procurement_df = metrics["procurement_df"]
    accounts_df = metrics["accounts_df"]

    critical_phase = "No phase defined"
    if not phase_df.empty:
        phase_df = phase_df.copy()
        phase_df["remaining_weight"] = (100 - phase_df["progress_pct"]) * phase_df["duration_weeks"]
        critical_phase = str(phase_df.sort_values("remaining_weight", ascending=False).iloc[0]["phase"])

    recommended_sources = []
    if not procurement_df.empty:
        for _, row in procurement_df.head(3).iterrows():
            recommended_sources.append(
                f"{row['package']}: use {row['recommended_supplier']} at {format_money(to_float(row['recommended_price']), currency)}"
            )

    overdue_accounts = []
    if not accounts_df.empty:
        for _, row in accounts_df.iterrows():
            if status_text(row["status"]) in {"pending", "overdue"}:
                overdue_accounts.append(
                    f"{row['period']} has {format_money(to_float(row['invoiced']) - to_float(row['collected']), currency)} still to collect"
                )

    highlights = [
        f"Recommended selling price is {format_money(metrics['final_contract_value'], currency)} including tax, with a modeled gross margin of {format_pct(metrics['gross_margin_pct'])}.",
        f"Procurement analysis shows up to {format_money(metrics['procurement_savings'], currency)} in achievable savings if alternates and terms are optimized.",
        f"Schedule completion is currently {format_pct(metrics['schedule_completion_pct'])} across an estimated {metrics['total_project_weeks']} week program.",
        f"Quality readiness is {format_pct(metrics['qa_ready_pct'])} and handover readiness is {format_pct(metrics['handover_ready_pct'])}.",
        f"Collection rate sits at {format_pct(metrics['collection_rate_pct'])}, with net cash position at {format_money(metrics['net_cash_position'], currency)}.",
    ]

    risks = []
    if metrics["pending_approvals"] > 0:
        risks.append(f"{metrics['pending_approvals']} consultant or client approvals are still open and can block release for fabrication or installation.")
    if metrics["pending_procurement"] > 0:
        risks.append(f"{metrics['pending_procurement']} procurement packages still require commercial or management approval before full release.")
    if metrics["open_high_hse"] > 0:
        risks.append(f"{metrics['open_high_hse']} high-severity HSE items are open and should stay visible before site mobilization expands.")
    if metrics["hiring_gap"] > 0:
        risks.append(f"HR still shows a staffing gap of {metrics['hiring_gap']:.0f} heads against the current required plan.")
    if metrics["open_qa_items"] > 0:
        risks.append(f"{metrics['open_qa_items']} QA/QC checkpoints remain open and should be tied to release gates.")
    if not risks:
        risks.append("No major modeled risks are blocking the platform right now, but approvals and safety need continuous review.")

    actions = [
        f"Lock pricing around the top cost drivers: {', '.join(metrics['top_cost_lines'])}.",
        f"Focus weekly control on the most exposed program phase: {critical_phase}.",
        "Tie material release to approved submittals, approved terms, and designated approvers in the procurement register.",
        "Use the outputs tab to issue a downloadable proposal, cost pack, procurement register, schedule, and handover dossier.",
    ]
    if recommended_sources:
        actions.append(f"Current best-buy recommendations: {'; '.join(recommended_sources[:2])}.")
    if overdue_accounts:
        actions.append(f"Collections follow-up: {overdue_accounts[0]}.")

    return {
        "headline": "Preliminary leadership briefing",
        "highlights": highlights,
        "risks": risks,
        "actions": actions,
    }


def build_copilot_response(question: str, data: dict, metrics: dict) -> str:
    q = question.lower().strip()
    currency = metrics["currency"]
    briefing = build_briefing(data, metrics)
    commercial = data["commercial"]
    procurement_df = metrics["procurement_df"]
    approvals_df = metrics["approvals_df"]
    phase_df = metrics["phase_df"]
    accounts_df = metrics["accounts_df"]
    hr_df = metrics["hr_df"]
    hse_df = metrics["hse_df"]

    if any(word in q for word in ["price", "quote", "cost", "margin"]):
        return textwrap.dedent(
            f"""
            Commercial recommendation:
            Recommended final selling price is {format_money(metrics['final_contract_value'], currency)} including tax.
            Base modeled cost is {format_money(metrics['base_cost'], currency)} and modeled gross profit is {format_money(metrics['gross_profit'], currency)}.
            Current commercial settings use {format_pct(to_float(commercial['target_margin_pct']))} target margin, {format_pct(to_float(commercial['contingency_pct']))} contingency, and {format_pct(to_float(commercial['overhead_pct']))} overhead.
            Top cost drivers are {', '.join(metrics['top_cost_lines'])}.
            """
        ).strip()

    if any(word in q for word in ["contract", "terms", "signing", "retention"]):
        milestones = dataframe_from_rows(data["contract_milestones"], MILESTONE_COLUMNS)
        lines = [
            f"- {row['milestone']}: {row['percent_due']}% against {row['trigger']}"
            for _, row in milestones.iterrows()
        ]
        return "\n".join(
            [
                "Contract guidance:",
                f"Retention is currently modeled at {format_pct(to_float(commercial['retention_pct']))} with a {to_int(commercial['warranty_months'])}-month warranty.",
                f"Payment structure: {commercial['payment_terms']}",
                "Suggested milestone structure:",
                *lines,
            ]
        )

    if any(word in q for word in ["procure", "purchase", "material", "supplier"]):
        if procurement_df.empty:
            return "No procurement rows are loaded yet."
        best_rows = procurement_df[["package", "recommended_supplier", "recommended_price", "potential_saving"]].head(4)
        lines = [
            f"- {row['package']}: {row['recommended_supplier']} at {format_money(to_float(row['recommended_price']), currency)}"
            + (
                f" with {format_money(to_float(row['potential_saving']), currency)} savings potential"
                if to_float(row["potential_saving"]) > 0
                else ""
            )
            for _, row in best_rows.iterrows()
        ]
        return "\n".join(
            [
                "Procurement guidance:",
                f"Modeled savings opportunity is {format_money(metrics['procurement_savings'], currency)}.",
                *lines,
                f"{metrics['pending_procurement']} packages still need management release or approval cleanup.",
            ]
        )

    if any(word in q for word in ["design", "drawing", "consultant", "approval"]):
        pending_rows = approvals_df[~approvals_df["status"].apply(is_good_status)]
        if pending_rows.empty:
            return "All modeled approvals are marked complete."
        lines = [
            f"- {row['submission']} due in week {to_int(row['due_week'])}: {row['status']}"
            for _, row in pending_rows.iterrows()
        ]
        return "\n".join(
            [
                "Design and approval guidance:",
                f"Approval completion is {format_pct(metrics['approval_completion_pct'])}.",
                *lines,
                "Keep fabrication and site release tied to signed shop drawings and approved material submittals.",
            ]
        )

    if any(word in q for word in ["timeline", "program", "manpower", "progress"]):
        if phase_df.empty:
            return "No program phases are loaded yet."
        lines = [
            f"- {row['phase']}: week {to_int(row['start_week'])} for {to_int(row['duration_weeks'])} weeks at {format_pct(to_float(row['progress_pct']))} progress"
            for _, row in phase_df.iterrows()
        ]
        return "\n".join(
            [
                "Program guidance:",
                f"Overall schedule completion is {format_pct(metrics['schedule_completion_pct'])} across {metrics['total_project_weeks']} weeks.",
                f"Active crew plan totals {metrics['active_headcount']:.0f} deployed heads.",
                *lines[:5],
            ]
        )

    if any(word in q for word in ["quality", "handover", "closeout", "qa", "qc"]):
        return "\n".join(
            [
                "Quality and closeout guidance:",
                f"QA readiness is {format_pct(metrics['qa_ready_pct'])} with {metrics['open_qa_items']} open checkpoints.",
                f"Handover readiness is {format_pct(metrics['handover_ready_pct'])} with {metrics['pending_handover']} pending handover requirements.",
                "Keep mock-up sign-off, installation inspections, snag closure, warranties, O&M manuals, and as-built drawings inside one release pack.",
            ]
        )

    if any(word in q for word in ["account", "cash", "invoice", "finance"]):
        pending = accounts_df[accounts_df["status"].astype(str).str.lower().isin(["pending", "overdue"])]
        lines = [
            f"- {row['period']}: outstanding {format_money(to_float(row['invoiced']) - to_float(row['collected']), currency)}"
            for _, row in pending.iterrows()
        ]
        return "\n".join(
            [
                "Accounts guidance:",
                f"Collection rate is {format_pct(metrics['collection_rate_pct'])} and net cash position is {format_money(metrics['net_cash_position'], currency)}.",
                *lines[:3],
                "Use milestone invoicing and retention visibility to keep final account closure aligned with handover.",
            ]
        )

    if any(word in q for word in ["hr", "people", "recruit", "training"]):
        open_roles = hr_df[hr_df["gap"] > 0]
        lines = [
            f"- {row['role']}: short by {row['gap']:.0f} heads"
            for _, row in open_roles.iterrows()
        ]
        return "\n".join(
            [
                "HR guidance:",
                f"Current hiring gap is {metrics['hiring_gap']:.0f} roles with {metrics['training_hours']:.0f} planned training hours.",
                *lines[:4],
                "Recruit early for site supervision and QA so approvals, inspections, and handover documents do not slip.",
            ]
        )

    if any(word in q for word in ["safety", "hse", "health"]):
        open_items = hse_df[~hse_df["status"].apply(is_good_status)]
        lines = [
            f"- {row['risk']} ({row['severity']}): {row['mitigation']}"
            for _, row in open_items.iterrows()
        ]
        return "\n".join(
            [
                "HSE guidance:",
                f"Safety score is {format_pct(metrics['safety_score'])} with {metrics['open_high_hse']} high-severity and {metrics['open_medium_hse']} medium-severity open items.",
                *lines[:4],
                "Treat work at height, lifting plans, and access control as hold points before full installation ramp-up.",
            ]
        )

    return "\n".join(
        [
            briefing["headline"],
            "",
            "Highlights:",
            *[f"- {item}" for item in briefing["highlights"]],
            "",
            "Risks:",
            *[f"- {item}" for item in briefing["risks"]],
            "",
            "Recommended actions:",
            *[f"- {item}" for item in briefing["actions"]],
        ]
    )


def render_briefing_card(title: str, items: list[str]) -> None:
    st.markdown(
        f"""
        <div class="section-card">
            <h3>{html.escape(title)}</h3>
            <ul class="brief-list">
                {''.join(f"<li>{html.escape(item)}</li>" for item in items)}
            </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar(data: dict, metrics: dict) -> dict:
    with st.sidebar:
        st.markdown("### Workspace")
        st.caption("Edit core project settings, load saved snapshots, and export the live dataset.")

        profile = data["profile"]
        profile["company_name"] = st.text_input("Company", value=profile["company_name"])
        profile["project_name"] = st.text_input("Project", value=profile["project_name"])
        profile["client_name"] = st.text_input("Client", value=profile["client_name"])
        profile["project_location"] = st.text_input("Location", value=profile["project_location"])
        profile["currency"] = st.text_input("Currency", value=profile["currency"])
        profile["project_manager"] = st.text_input("Project manager", value=profile["project_manager"])
        profile["contract_start"] = str(
            st.date_input("Contract start", value=parse_date(profile["contract_start"]), format="YYYY-MM-DD")
        )
        profile["target_handover"] = str(
            st.date_input("Target handover", value=parse_date(profile["target_handover"]), format="YYYY-MM-DD")
        )
        profile["scope_summary"] = st.text_area("Scope summary", value=profile["scope_summary"], height=110)
        profile["director_brief"] = st.text_area("Director brief", value=profile["director_brief"], height=140)

        st.divider()
        st.markdown("### Snapshot")
        snapshot_bytes = json.dumps(data, indent=2).encode("utf-8")
        st.download_button(
            "Download project snapshot",
            snapshot_bytes,
            file_name="business_platform_snapshot.json",
            mime="application/json",
            use_container_width=True,
        )

        uploaded = st.file_uploader("Upload snapshot JSON", type=["json"])
        if st.button("Load uploaded snapshot", use_container_width=True):
            if uploaded is None:
                st.warning("Upload a JSON snapshot first.")
            else:
                try:
                    loaded = json.loads(uploaded.getvalue().decode("utf-8"))
                    st.session_state.platform_data = loaded
                    st.success("Snapshot loaded.")
                    st.rerun()
                except json.JSONDecodeError:
                    st.error("That file is not valid JSON.")

        if st.button("Reset to starter template", use_container_width=True):
            st.session_state.platform_data = clone_defaults()
            st.session_state.copilot_answer = ""
            st.rerun()

        st.divider()
        st.markdown("### Live KPIs")
        st.caption(f"Modeled contract value: {format_money(metrics['final_contract_value'], metrics['currency'])}")
        st.caption(f"Gross margin: {format_pct(metrics['gross_margin_pct'])}")
        st.caption(f"Safety score: {format_pct(metrics['safety_score'])}")

    return data


def render_financial_chart(metrics: dict) -> None:
    chart = go.Figure(
        data=[
            go.Bar(
                x=["Direct cost", "Contingency", "Overhead", "Quote before tax", "Tax", "Final contract"],
                y=[
                    metrics["direct_cost"],
                    metrics["contingency_value"],
                    metrics["overhead_value"],
                    metrics["quote_before_tax"],
                    metrics["tax_value"],
                    metrics["final_contract_value"],
                ],
                marker_color=["#b6c2d9", "#8bb7ef", "#6ba4ea", "#0071e3", "#7bc7ff", "#0d4b96"],
            )
        ]
    )
    chart.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        height=320,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        yaxis_title="Modeled value",
    )
    st.plotly_chart(chart, use_container_width=True)


def render_schedule_chart(metrics: dict) -> None:
    frame = metrics["phase_df"]
    if frame.empty:
        st.info("Add project phases to view the master schedule.")
        return

    chart = px.timeline(
        frame,
        x_start="start_date",
        x_end="finish_date",
        y="phase",
        color="department",
        text="progress_pct",
        color_discrete_sequence=["#0071e3", "#64a5ff", "#0d4b96", "#7bc7ff", "#7b8797", "#4c6fa7"],
    )
    chart.update_yaxes(autorange="reversed")
    chart.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        height=360,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis_title="Schedule",
        yaxis_title="",
    )
    st.plotly_chart(chart, use_container_width=True)


def render_manpower_chart(metrics: dict) -> None:
    frame = metrics["manpower_df"]
    if frame.empty:
        st.info("Add manpower rows to view the labor plan.")
        return

    grouped = frame.groupby("role", as_index=False)["crew_count"].sum()
    chart = px.bar(
        grouped,
        x="role",
        y="crew_count",
        color="role",
        color_discrete_sequence=["#0071e3", "#4c8fe8", "#7bb3ff", "#8bc5ff", "#0d4b96", "#7b8797"],
    )
    chart.update_layout(
        showlegend=False,
        margin=dict(l=10, r=10, t=10, b=10),
        height=320,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis_title="",
        yaxis_title="Crew count",
    )
    st.plotly_chart(chart, use_container_width=True)


def render_accounts_chart(metrics: dict) -> None:
    frame = metrics["accounts_df"]
    if frame.empty:
        st.info("Add accounts rows to view the cash chart.")
        return
    grouped = frame.melt(
        id_vars=["period"],
        value_vars=["invoiced", "collected", "paid_cost"],
        var_name="metric",
        value_name="value",
    )
    chart = px.bar(
        grouped,
        x="period",
        y="value",
        color="metric",
        barmode="group",
        color_discrete_map={"invoiced": "#0d4b96", "collected": "#0071e3", "paid_cost": "#8bc5ff"},
    )
    chart.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        height=320,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis_title="",
        yaxis_title="Value",
        legend_title="",
    )
    st.plotly_chart(chart, use_container_width=True)


def render_command_center(data: dict, metrics: dict) -> None:
    briefing = build_briefing(data, metrics)

    left, right = st.columns([1.15, 0.85], gap="large")
    with left:
        st.markdown(
            """
            <div class="section-card">
                <h3>AI leadership briefing</h3>
                <p class="section-copy">
                    The platform uses your live project data to surface commercial, delivery, quality,
                    and operations signals from one place.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        render_briefing_card("Highlights", briefing["highlights"])
        render_briefing_card("Key risks", briefing["risks"])
        render_briefing_card("Recommended actions", briefing["actions"])

        st.markdown("### Ask The Copilot")
        prompt = st.text_area(
            "Ask the business copilot",
            value="What should I do next to keep this project commercially and operationally under control?",
            height=110,
            key="copilot_prompt",
        )
        if st.button("Generate business answer", type="primary"):
            st.session_state.copilot_answer = build_copilot_response(prompt, data, metrics)

        if st.session_state.copilot_answer:
            st.markdown(
                f"""
                <div class="notice">
                    <strong>Copilot response</strong>
                    <div style="margin-top:10px; white-space:pre-wrap; line-height:1.7;">{html.escape(st.session_state.copilot_answer)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with right:
        st.markdown(
            f"""
            <div class="section-card">
                <h3>Executive position</h3>
                <p class="section-copy">
                    Contract value: <strong>{format_money(metrics['final_contract_value'], metrics['currency'])}</strong><br>
                    Procurement savings opportunity: <strong>{format_money(metrics['procurement_savings'], metrics['currency'])}</strong><br>
                    Schedule completion: <strong>{format_pct(metrics['schedule_completion_pct'])}</strong><br>
                    Safety score: <strong>{format_pct(metrics['safety_score'])}</strong>
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.expander("Director brief captured", expanded=False):
            st.write(data["profile"]["director_brief"])
        with st.expander("Quick warnings", expanded=True):
            st.markdown(
                "\n".join(
                    [
                        f"- {metrics['pending_approvals']} approvals still open",
                        f"- {metrics['pending_procurement']} procurement packages not fully cleared",
                        f"- {metrics['open_qa_items']} QA items open",
                        f"- {metrics['pending_handover']} handover deliverables pending",
                        f"- Hiring gap: {metrics['hiring_gap']:.0f} roles",
                    ]
                )
            )

    chart_left, chart_right = st.columns(2, gap="large")
    with chart_left:
        st.markdown("### Commercial waterfall")
        render_financial_chart(metrics)
    with chart_right:
        st.markdown("### Master schedule")
        render_schedule_chart(metrics)


def render_commercial_tab(data: dict, metrics: dict) -> None:
    commercial = data["commercial"]

    intro_left, intro_right = st.columns([0.9, 1.1], gap="large")
    with intro_left:
        st.markdown(
            """
            <div class="section-card">
                <h3>Design, costing, quotation, and contract control</h3>
                <p class="section-copy">
                    This section handles pricing logic, cost build-up, payment structure,
                    contract conditions, and final commercial positioning.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        commercial["proposal_version"] = st.text_input("Proposal version", value=commercial["proposal_version"])
        commercial["target_margin_pct"] = st.number_input("Target margin %", value=float(commercial["target_margin_pct"]), step=1.0)
        commercial["contingency_pct"] = st.number_input("Contingency %", value=float(commercial["contingency_pct"]), step=1.0)
        commercial["overhead_pct"] = st.number_input("Overhead %", value=float(commercial["overhead_pct"]), step=1.0)
        commercial["tax_pct"] = st.number_input("Tax %", value=float(commercial["tax_pct"]), step=1.0)
        commercial["retention_pct"] = st.number_input("Retention %", value=float(commercial["retention_pct"]), step=1.0)
        commercial["warranty_months"] = st.number_input("Warranty months", value=int(commercial["warranty_months"]), step=1)
        commercial["payment_terms"] = st.text_area("Payment terms", value=commercial["payment_terms"], height=95)
        commercial["contract_notes"] = st.text_area("Contract controls", value=commercial["contract_notes"], height=110)
        commercial["scope_inclusions"] = st.text_area("Scope inclusions", value=commercial["scope_inclusions"], height=110)
        commercial["scope_exclusions"] = st.text_area("Scope exclusions", value=commercial["scope_exclusions"], height=95)

    with intro_right:
        st.markdown("### Quote summary")
        summary_cols = st.columns(2)
        summary_cols[0].metric("Base cost", format_money(metrics["base_cost"], metrics["currency"]))
        summary_cols[1].metric("Quote before tax", format_money(metrics["quote_before_tax"], metrics["currency"]))
        summary_cols[0].metric("Gross profit", format_money(metrics["gross_profit"], metrics["currency"]))
        summary_cols[1].metric("Gross margin", format_pct(metrics["gross_margin_pct"]))
        summary_cols[0].metric("Tax", format_money(metrics["tax_value"], metrics["currency"]))
        summary_cols[1].metric("Final contract value", format_money(metrics["final_contract_value"], metrics["currency"]))
        render_financial_chart(metrics)

    st.markdown("### Cost build-up")
    data["cost_items"] = edited_records("cost_items_editor", data["cost_items"], COST_COLUMNS, height=280)

    st.markdown("### Contract milestones and payment map")
    data["contract_milestones"] = edited_records("contract_milestones_editor", data["contract_milestones"], MILESTONE_COLUMNS, height=240)


def render_procurement_design_tab(data: dict, metrics: dict) -> None:
    top_left, top_right = st.columns([1.05, 0.95], gap="large")
    with top_left:
        st.markdown(
            """
            <div class="section-card">
                <h3>Material purchase and best-buy control</h3>
                <p class="section-copy">
                    Compare suppliers on price, lead time, and terms score. Use approval status to control
                    when materials are actually released.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.caption("Terms score is a simple 1-10 commercial rating where higher is more favorable.")
        data["procurement_items"] = edited_records("procurement_items_editor", data["procurement_items"], PROCUREMENT_COLUMNS, height=300)

    with top_right:
        st.markdown("### Procurement recommendations")
        procurement_df = metrics["procurement_df"][
            [
                "package",
                "recommended_supplier",
                "recommended_price",
                "recommended_lead_days",
                "potential_saving",
                "approval_status",
            ]
        ].copy()
        if not procurement_df.empty:
            procurement_df["recommended_price"] = procurement_df["recommended_price"].map(
                lambda value: format_money(to_float(value), metrics["currency"])
            )
            procurement_df["potential_saving"] = procurement_df["potential_saving"].map(
                lambda value: format_money(to_float(value), metrics["currency"])
            )
        st.dataframe(procurement_df, use_container_width=True, hide_index=True)
        st.metric("Modeled savings opportunity", format_money(metrics["procurement_savings"], metrics["currency"]))
        st.metric("Packages awaiting release", str(metrics["pending_procurement"]))

    design_left, design_right = st.columns(2, gap="large")
    with design_left:
        st.markdown("### Design and shop drawing register")
        data["design_deliverables"] = edited_records("design_deliverables_editor", data["design_deliverables"], DESIGN_COLUMNS, height=260)
    with design_right:
        st.markdown("### Consultant and client approvals")
        data["consultant_approvals"] = edited_records("consultant_approvals_editor", data["consultant_approvals"], APPROVAL_COLUMNS, height=260)
        st.metric("Approval completion", format_pct(metrics["approval_completion_pct"]))


def render_delivery_tab(data: dict, metrics: dict) -> None:
    phase_left, phase_right = st.columns([1.0, 1.0], gap="large")
    with phase_left:
        st.markdown("### Master timeline")
        data["phases"] = edited_records("phases_editor", data["phases"], PHASE_COLUMNS, height=280)
    with phase_right:
        st.markdown("### Program visualization")
        render_schedule_chart(metrics)

    manpower_left, manpower_right = st.columns([1.05, 0.95], gap="large")
    with manpower_left:
        st.markdown("### Manpower input plan")
        data["manpower_plan"] = edited_records("manpower_editor", data["manpower_plan"], MANPOWER_COLUMNS, height=260)
    with manpower_right:
        st.markdown("### Crew deployment")
        render_manpower_chart(metrics)

    with st.expander("QA / QC control", expanded=True):
        data["quality_checks"] = edited_records("quality_editor", data["quality_checks"], QUALITY_COLUMNS, height=250)
        qa_cols = st.columns(2)
        qa_cols[0].metric("QA readiness", format_pct(metrics["qa_ready_pct"]))
        qa_cols[1].metric("Open QA items", str(metrics["open_qa_items"]))

    with st.expander("Logistics and site placement", expanded=True):
        logistics_left, logistics_right = st.columns(2, gap="large")
        with logistics_left:
            data["logistics_plan"] = edited_records("logistics_editor", data["logistics_plan"], LOGISTICS_COLUMNS, height=220)
        with logistics_right:
            data["site_placement"] = edited_records("site_placement_editor", data["site_placement"], SITE_COLUMNS, height=220)

    with st.expander("Installation and handover", expanded=True):
        install_left, install_right = st.columns(2, gap="large")
        with install_left:
            data["installation_tasks"] = edited_records("installation_editor", data["installation_tasks"], INSTALLATION_COLUMNS, height=220)
        with install_right:
            data["handover_items"] = edited_records("handover_editor", data["handover_items"], HANDOVER_COLUMNS, height=220)
        handover_cols = st.columns(2)
        handover_cols[0].metric("Handover readiness", format_pct(metrics["handover_ready_pct"]))
        handover_cols[1].metric("Pending handover items", str(metrics["pending_handover"]))


def render_backoffice_tab(data: dict, metrics: dict) -> None:
    accounts_left, accounts_right = st.columns([1.0, 1.0], gap="large")
    with accounts_left:
        st.markdown("### Accounts reporting")
        data["accounts_entries"] = edited_records("accounts_editor", data["accounts_entries"], ACCOUNTS_COLUMNS, height=250)
    with accounts_right:
        st.markdown("### Collections and spend")
        render_accounts_chart(metrics)
        cash_cols = st.columns(2)
        cash_cols[0].metric("Collection rate", format_pct(metrics["collection_rate_pct"]))
        cash_cols[1].metric("Net cash position", format_money(metrics["net_cash_position"], metrics["currency"]))

    hr_left, hr_right = st.columns([1.0, 1.0], gap="large")
    with hr_left:
        st.markdown("### HR functionality")
        data["hr_plan"] = edited_records("hr_editor", data["hr_plan"], HR_COLUMNS, height=250)
    with hr_right:
        st.markdown(
            f"""
            <div class="section-card">
                <h3>People readiness</h3>
                <p class="section-copy">
                    Staffing gap: <strong>{metrics['hiring_gap']:.0f}</strong><br>
                    Planned training hours: <strong>{metrics['training_hours']:.0f}</strong><br>
                    Active project manpower: <strong>{metrics['active_headcount']:.0f}</strong>
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    hse_left, hse_right = st.columns([1.05, 0.95], gap="large")
    with hse_left:
        st.markdown("### Health and safety")
        data["hse_register"] = edited_records("hse_editor", data["hse_register"], HSE_COLUMNS, height=250)
    with hse_right:
        st.markdown(
            f"""
            <div class="section-card">
                <h3>Safety position</h3>
                <p class="section-copy">
                    Safety score: <strong>{format_pct(metrics['safety_score'])}</strong><br>
                    Open high-severity risks: <strong>{metrics['open_high_hse']}</strong><br>
                    Open medium-severity risks: <strong>{metrics['open_medium_hse']}</strong><br>
                    Recorded incidents: <strong>{metrics['incidents']:.0f}</strong>
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )


def build_dashboard_html(data: dict, metrics: dict, briefing: dict) -> bytes:
    currency = metrics["currency"]
    cards = [
        ("Contract value", format_money(metrics["final_contract_value"], currency)),
        ("Gross margin", format_pct(metrics["gross_margin_pct"])),
        ("Procurement savings", format_money(metrics["procurement_savings"], currency)),
        ("Approval completion", format_pct(metrics["approval_completion_pct"])),
        ("Schedule completion", format_pct(metrics["schedule_completion_pct"])),
        ("Safety score", format_pct(metrics["safety_score"])),
    ]

    html_report = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>{html.escape(data['profile']['project_name'])} Dashboard</title>
        <style>
            body {{
                margin: 0;
                font-family: Arial, sans-serif;
                color: #1d1d1f;
                background: linear-gradient(180deg, #f8f8fb 0%, #eef1f5 100%);
            }}
            .shell {{
                max-width: 1120px;
                margin: 0 auto;
                padding: 32px 20px 48px;
            }}
            .hero, .panel {{
                background: rgba(255,255,255,0.9);
                border: 1px solid rgba(0,0,0,0.08);
                border-radius: 22px;
                box-shadow: 0 14px 30px rgba(15,23,42,0.07);
                padding: 24px;
                margin-bottom: 18px;
            }}
            .eyebrow {{
                text-transform: uppercase;
                letter-spacing: 0.12em;
                font-size: 12px;
                color: #0071e3;
                margin-bottom: 10px;
            }}
            h1, h2 {{
                margin: 0 0 10px;
            }}
            .grid {{
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: 14px;
            }}
            .card {{
                background: #ffffff;
                border: 1px solid rgba(0,0,0,0.06);
                border-radius: 18px;
                padding: 18px;
            }}
            .label {{
                color: #5f6672;
                font-size: 13px;
                margin-bottom: 6px;
            }}
            .value {{
                font-size: 26px;
                font-weight: 700;
            }}
            ul {{
                margin: 0;
                padding-left: 18px;
                line-height: 1.7;
            }}
            @media (max-width: 800px) {{
                .grid {{
                    grid-template-columns: 1fr;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="shell">
            <section class="hero">
                <div class="eyebrow">Business Platform Snapshot</div>
                <h1>{html.escape(data['profile']['project_name'])}</h1>
                <p>{html.escape(data['profile']['scope_summary'])}</p>
            </section>
            <section class="panel">
                <h2>Headline metrics</h2>
                <div class="grid">
                    {''.join(f'<div class="card"><div class="label">{html.escape(label)}</div><div class="value">{html.escape(value)}</div></div>' for label, value in cards)}
                </div>
            </section>
            <section class="panel">
                <h2>{html.escape(briefing['headline'])}</h2>
                <h3>Highlights</h3>
                <ul>{''.join(f'<li>{html.escape(item)}</li>' for item in briefing['highlights'])}</ul>
                <h3>Risks</h3>
                <ul>{''.join(f'<li>{html.escape(item)}</li>' for item in briefing['risks'])}</ul>
                <h3>Actions</h3>
                <ul>{''.join(f'<li>{html.escape(item)}</li>' for item in briefing['actions'])}</ul>
            </section>
        </div>
    </body>
    </html>
    """
    return html_report.encode("utf-8")


def build_markdown_reports(data: dict, metrics: dict) -> dict[str, bytes]:
    currency = metrics["currency"]
    briefing = build_briefing(data, metrics)
    commercial = data["commercial"]

    executive = "\n".join(
        [
            f"# {data['profile']['project_name']} - Executive Summary",
            "",
            f"- Client: {data['profile']['client_name']}",
            f"- Location: {data['profile']['project_location']}",
            f"- Contract value: {format_money(metrics['final_contract_value'], currency)}",
            f"- Gross margin: {format_pct(metrics['gross_margin_pct'])}",
            f"- Procurement savings opportunity: {format_money(metrics['procurement_savings'], currency)}",
            f"- Schedule completion: {format_pct(metrics['schedule_completion_pct'])}",
            f"- Safety score: {format_pct(metrics['safety_score'])}",
            "",
            "## Highlights",
            *[f"- {item}" for item in briefing["highlights"]],
            "",
            "## Risks",
            *[f"- {item}" for item in briefing["risks"]],
            "",
            "## Recommended actions",
            *[f"- {item}" for item in briefing["actions"]],
        ]
    ).encode("utf-8")

    quotation = "\n".join(
        [
            f"# Quotation And Pricing - {data['profile']['project_name']}",
            "",
            f"- Proposal version: {commercial['proposal_version']}",
            f"- Base cost: {format_money(metrics['base_cost'], currency)}",
            f"- Quote before tax: {format_money(metrics['quote_before_tax'], currency)}",
            f"- Tax: {format_money(metrics['tax_value'], currency)}",
            f"- Final contract value: {format_money(metrics['final_contract_value'], currency)}",
            f"- Modeled gross profit: {format_money(metrics['gross_profit'], currency)}",
            "",
            "## Inclusions",
            commercial["scope_inclusions"],
            "",
            "## Exclusions",
            commercial["scope_exclusions"],
            "",
            "## Payment terms",
            commercial["payment_terms"],
        ]
    ).encode("utf-8")

    contract = "\n".join(
        [
            f"# Contract Strategy - {data['profile']['project_name']}",
            "",
            f"- Retention: {format_pct(to_float(commercial['retention_pct']))}",
            f"- Warranty: {to_int(commercial['warranty_months'])} months",
            "",
            "## Controls",
            commercial["contract_notes"],
            "",
            "## Payment structure",
            commercial["payment_terms"],
            "",
            "## Milestones",
            *[
                f"- {row['milestone']}: {row['percent_due']}% due on {row['trigger']}"
                for _, row in dataframe_from_rows(data["contract_milestones"], MILESTONE_COLUMNS).iterrows()
            ],
        ]
    ).encode("utf-8")

    handover = "\n".join(
        [
            f"# Handover Dossier - {data['profile']['project_name']}",
            "",
            f"- Handover readiness: {format_pct(metrics['handover_ready_pct'])}",
            f"- Pending handover items: {metrics['pending_handover']}",
            "",
            "## Required closeout items",
            *[
                f"- {row['requirement']} | owner: {row['owner']} | status: {row['status']} | evidence: {row['evidence']}"
                for _, row in dataframe_from_rows(data["handover_items"], HANDOVER_COLUMNS).iterrows()
            ],
        ]
    ).encode("utf-8")

    return {
        "00_executive_summary.md": executive,
        "01_quotation_and_pricing.md": quotation,
        "02_contract_strategy.md": contract,
        "11_handover_dossier.md": handover,
        "15_dashboard_snapshot.html": build_dashboard_html(data, metrics, briefing),
    }


def build_output_files(data: dict, metrics: dict) -> dict[str, bytes]:
    files = build_markdown_reports(data, metrics)
    files["03_cost_sheet.csv"] = csv_bytes_from_frame(metrics["cost_df"])
    files["04_procurement_register.csv"] = csv_bytes_from_frame(metrics["procurement_df"])
    files["05_design_register.csv"] = csv_bytes_from_frame(dataframe_from_rows(data["design_deliverables"], DESIGN_COLUMNS))
    files["06_consultant_approvals.csv"] = csv_bytes_from_frame(metrics["approvals_df"])
    files["07_master_schedule.csv"] = csv_bytes_from_frame(metrics["phase_df"])
    files["08_manpower_plan.csv"] = csv_bytes_from_frame(metrics["manpower_df"])
    files["09_quality_plan.csv"] = csv_bytes_from_frame(metrics["quality_df"])
    files["10_logistics_plan.csv"] = csv_bytes_from_frame(dataframe_from_rows(data["logistics_plan"], LOGISTICS_COLUMNS))
    files["10b_site_placement_plan.csv"] = csv_bytes_from_frame(dataframe_from_rows(data["site_placement"], SITE_COLUMNS))
    files["10c_installation_checklist.csv"] = csv_bytes_from_frame(dataframe_from_rows(data["installation_tasks"], INSTALLATION_COLUMNS))
    files["12_accounts_report.csv"] = csv_bytes_from_frame(metrics["accounts_df"])
    files["13_hr_plan.csv"] = csv_bytes_from_frame(metrics["hr_df"])
    files["14_hse_register.csv"] = csv_bytes_from_frame(metrics["hse_df"])
    files["16_project_snapshot.json"] = json.dumps(data, indent=2).encode("utf-8")
    return files


def build_zip_bundle(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    buffer.seek(0)
    return buffer.getvalue()


def preview_output_file(name: str, content: bytes) -> None:
    if name.endswith(".csv"):
        frame = pd.read_csv(io.BytesIO(content))
        st.dataframe(frame, use_container_width=True, hide_index=True)
        return
    if name.endswith(".html"):
        components.html(content.decode("utf-8"), height=720, scrolling=True)
        return
    if name.endswith(".json"):
        st.code(content.decode("utf-8"), language="json")
        return
    st.code(content.decode("utf-8"), language="markdown")


def mime_type_for_file(name: str) -> str:
    if name.endswith(".json"):
        return "application/json"
    if name.endswith(".csv"):
        return "text/csv"
    if name.endswith(".html"):
        return "text/html"
    if name.endswith(".md"):
        return "text/markdown"
    if name.endswith(".zip"):
        return "application/zip"
    return "application/octet-stream"


def render_outputs_tab(data: dict, metrics: dict) -> None:
    files = build_output_files(data, metrics)
    bundle = build_zip_bundle(files)

    st.markdown(
        """
        <div class="section-card">
            <h3>Downloadable control pack</h3>
            <p class="section-copy">
                All sections feed a packaged output set so you can collect input in the app and issue
                documents for quotation, procurement, design, execution, quality, accounts, HR, HSE,
                and handover.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    action_cols = st.columns([1.2, 1.2, 1.6])
    action_cols[0].download_button(
        "Download full project package",
        bundle,
        file_name="business_platform_control_pack.zip",
        mime="application/zip",
        use_container_width=True,
    )
    action_cols[1].download_button(
        "Download snapshot JSON",
        files["16_project_snapshot.json"],
        file_name="business_platform_snapshot.json",
        mime="application/json",
        use_container_width=True,
    )
    action_cols[2].caption("Preview any generated file below, then download it individually if needed.")

    file_names = list(files.keys())
    selected = st.selectbox("Preview generated file", options=file_names, index=0)
    preview_output_file(selected, files[selected])
    st.download_button(
        f"Download {selected}",
        files[selected],
        file_name=selected,
        mime=mime_type_for_file(selected),
        use_container_width=True,
    )


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, page_icon="MM", layout="wide", initial_sidebar_state="expanded")
    init_state()
    load_css()

    data = st.session_state.platform_data
    metrics = compute_metrics(data)
    render_sidebar(data, metrics)
    render_hero(data)

    metric_cols = st.columns(6)
    metric_cols[0].metric("Contract value", format_money(metrics["final_contract_value"], metrics["currency"]))
    metric_cols[1].metric("Gross margin", format_pct(metrics["gross_margin_pct"]))
    metric_cols[2].metric("Savings", format_money(metrics["procurement_savings"], metrics["currency"]))
    metric_cols[3].metric("Approvals", format_pct(metrics["approval_completion_pct"]))
    metric_cols[4].metric("Schedule", format_pct(metrics["schedule_completion_pct"]))
    metric_cols[5].metric("Safety", format_pct(metrics["safety_score"]))

    tabs = st.tabs(
        [
            "Command Center",
            "Commercial",
            "Procurement + Design",
            "Delivery + Handover",
            "Accounts / HR / HSE",
            "Outputs",
        ]
    )

    with tabs[0]:
        render_command_center(data, metrics)
    with tabs[1]:
        render_commercial_tab(data, metrics)
    with tabs[2]:
        render_procurement_design_tab(data, metrics)
    with tabs[3]:
        render_delivery_tab(data, metrics)
    with tabs[4]:
        render_backoffice_tab(data, metrics)
    with tabs[5]:
        render_outputs_tab(data, metrics)

    st.session_state.platform_data = data


if __name__ == "__main__":
    main()
