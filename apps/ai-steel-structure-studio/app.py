from __future__ import annotations

import csv
import html
import io
import json
import math
import os
import re
import traceback
import textwrap
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Iterable

import streamlit as st
import streamlit.components.v1 as components

try:
    import plotly.graph_objects as go
except Exception:  # pragma: no cover - handled in the UI
    go = None


APP_VERSION = "0.2.0"
STEEL_DENSITY_KG_M3 = 7850
DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "llama3.2:1b"
APP_DIR = Path(__file__).resolve().parent


def resolve_app_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return APP_DIR / candidate


@dataclass
class BuildingSpec:
    project_name: str = "Concept Warehouse"
    building_type: str = "Warehouse"
    length_m: float = 40.0
    width_m: float = 20.0
    eave_height_m: float = 10.0
    bay_count: int = 8
    roof_style: str = "Gable"
    roof_pitch_deg: float = 10.0
    frame_section_m: float = 0.45
    secondary_section_m: float = 0.18
    slab_thickness_m: float = 0.18
    include_bracing: bool = True
    include_wall_girts: bool = True
    include_roof_purlins: bool = True
    roof_sheet_option: str = "CORRUGATED_GALV"
    wall_sheet_option: str = "CORRUGATED_GALV"
    design_notes: str = ""


@dataclass(frozen=True)
class SteelSection:
    section_id: str
    family: str
    depth_m: float
    flange_width_m: float
    web_thickness_m: float
    flange_thickness_m: float
    weight_kg_m: float
    wall_thickness_m: float = 0.0
    lip_m: float = 0.0
    source_note: str = "Starter visual catalog. Verify against manufacturer/AISC data before design use."


@dataclass(frozen=True)
class BraceConnectionRule:
    rule_id: str
    brace_family: str
    min_angle_deg: float
    max_angle_deg: float
    preferred_section: str
    connection_plate: str
    bolt_spec: str
    bolts_per_end: int
    bolt_diameter_mm: float
    weld_detail: str
    use_case: str
    status: str = "Concept placeholder - engineer before fabrication"


@dataclass(frozen=True)
class CladdingOption:
    option_id: str
    display_name: str
    panel_type: str
    material: str
    thickness_mm: float
    rib_height_mm: float
    coverage_width_m: float
    min_pitch_deg: float
    weight_kg_m2: float
    fastening_pattern: str
    notes: str = "Conceptual cladding option. Verify manufacturer span tables, fasteners, and code requirements."


@dataclass
class Member:
    name: str
    role: str
    start: tuple[float, float, float]
    end: tuple[float, float, float]
    size_m: float
    section_id: str = "W12X26"

    @property
    def length_m(self) -> float:
        return distance(self.start, self.end)

    @property
    def steel_weight_kg(self) -> float:
        section = get_section(self.section_id)
        if section:
            return self.length_m * section.weight_kg_m
        return self.length_m * (self.size_m**2) * STEEL_DENSITY_KG_M3

    @property
    def section(self) -> SteelSection | None:
        return get_section(self.section_id)


@dataclass
class ModelPackage:
    spec: BuildingSpec
    members: list[Member]
    vertices: list[tuple[float, float, float]]
    faces: list[tuple[int, int, int]]
    bom_rows: list[dict[str, object]]
    connection_rows: list[dict[str, object]]
    warnings: list[str]


SECTION_CATALOG: dict[str, SteelSection] = {
    "W8X10": SteelSection("W8X10", "W", 0.200, 0.100, 0.0043, 0.0052, 14.9),
    "W10X12": SteelSection("W10X12", "W", 0.251, 0.101, 0.0048, 0.0053, 17.9),
    "W12X26": SteelSection("W12X26", "W", 0.310, 0.165, 0.0058, 0.0097, 38.7),
    "W14X30": SteelSection("W14X30", "W", 0.351, 0.171, 0.0069, 0.0098, 44.6),
    "W16X36": SteelSection("W16X36", "W", 0.403, 0.178, 0.0075, 0.0109, 53.6),
    "W18X35": SteelSection("W18X35", "W", 0.450, 0.152, 0.0076, 0.0108, 52.1),
    "W21X44": SteelSection("W21X44", "W", 0.525, 0.165, 0.0089, 0.0114, 65.5),
    "W24X55": SteelSection("W24X55", "W", 0.599, 0.178, 0.0100, 0.0128, 81.9),
    "Z200X2.5": SteelSection("Z200X2.5", "Z", 0.200, 0.065, 0.0025, 0.0025, 5.7, wall_thickness_m=0.0025, lip_m=0.018),
    "C200X2.5": SteelSection("C200X2.5", "C", 0.200, 0.065, 0.0025, 0.0025, 5.7, wall_thickness_m=0.0025, lip_m=0.018),
    "HSS100X100X6": SteelSection("HSS100X100X6", "HSS", 0.100, 0.100, 0.0060, 0.0060, 17.7, wall_thickness_m=0.0060),
    "ROD20": SteelSection("ROD20", "ROD", 0.020, 0.020, 0.020, 0.020, 2.47),
}


def load_section_catalog_from_csv(path: str = "steel_sections.csv") -> dict[str, SteelSection]:
    csv_path = resolve_app_path(path)
    if not csv_path.exists():
        return {}

    loaded: dict[str, SteelSection] = {}
    with csv_path.open(newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            try:
                section = SteelSection(
                    section_id=row["section_id"],
                    family=row["family"],
                    depth_m=float(row["depth_m"]),
                    flange_width_m=float(row["flange_width_m"]),
                    web_thickness_m=float(row["web_thickness_m"]),
                    flange_thickness_m=float(row["flange_thickness_m"]),
                    weight_kg_m=float(row["weight_kg_m"]),
                    wall_thickness_m=float(row.get("wall_thickness_m") or 0.0),
                    lip_m=float(row.get("lip_m") or 0.0),
                    source_note=row.get("source_note") or "Loaded from steel_sections.csv",
                )
                loaded[section.section_id] = section
            except (KeyError, TypeError, ValueError):
                continue
    return loaded


SECTION_CATALOG.update(load_section_catalog_from_csv())


def load_brace_connection_catalog(path: str = "brace_connection_catalog.csv") -> list[BraceConnectionRule]:
    csv_path = resolve_app_path(path)
    if not csv_path.exists():
        return [
            BraceConnectionRule(
                "ROD_X_BRACE_STD",
                "Cross bracing",
                35,
                55,
                "ROD20",
                "8mm gusset plate",
                "M20 class 8.8 bolts",
                1,
                20,
                "6mm fillet shop weld to frame where engineered",
                "Typical tension rod cross brace",
            )
        ]

    rules: list[BraceConnectionRule] = []
    with csv_path.open(newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            try:
                rules.append(
                    BraceConnectionRule(
                        rule_id=row["rule_id"],
                        brace_family=row["brace_family"],
                        min_angle_deg=float(row["min_angle_deg"]),
                        max_angle_deg=float(row["max_angle_deg"]),
                        preferred_section=row["preferred_section"],
                        connection_plate=row["connection_plate"],
                        bolt_spec=row["bolt_spec"],
                        bolts_per_end=int(float(row["bolts_per_end"])),
                        bolt_diameter_mm=float(row["bolt_diameter_mm"]),
                        weld_detail=row["weld_detail"],
                        use_case=row["use_case"],
                        status=row.get("status") or "Concept placeholder - engineer before fabrication",
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
    return rules


BRACE_CONNECTION_CATALOG = load_brace_connection_catalog()


CLADDING_CATALOG: dict[str, CladdingOption] = {
    "CORRUGATED_GALV": CladdingOption(
        "CORRUGATED_GALV",
        "Corrugated galvanized steel",
        "Corrugated",
        "Galvanized steel",
        0.55,
        18,
        0.762,
        5,
        5.2,
        "Crest fasteners at supports with side-lap stitching as specified.",
    )
}


def load_cladding_catalog(path: str = "roofing_options.csv") -> dict[str, CladdingOption]:
    csv_path = resolve_app_path(path)
    if not csv_path.exists():
        return {}

    loaded: dict[str, CladdingOption] = {}
    with csv_path.open(newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            try:
                option = CladdingOption(
                    option_id=row["option_id"],
                    display_name=row["display_name"],
                    panel_type=row["panel_type"],
                    material=row["material"],
                    thickness_mm=float(row["thickness_mm"]),
                    rib_height_mm=float(row["rib_height_mm"]),
                    coverage_width_m=float(row["coverage_width_m"]),
                    min_pitch_deg=float(row["min_pitch_deg"]),
                    weight_kg_m2=float(row["weight_kg_m2"]),
                    fastening_pattern=row["fastening_pattern"],
                    notes=row.get("notes") or "Loaded from roofing_options.csv",
                )
                loaded[option.option_id] = option
            except (KeyError, TypeError, ValueError):
                continue
    return loaded


CLADDING_CATALOG.update(load_cladding_catalog())


DEFAULT_PROMPT = (
    "Design a steel warehouse that is 40 meters long, 20 meters wide, and "
    "10 meters tall. Use a gable roof, 8 bays, roof purlins, wall girts, and "
    "cross bracing. Keep it simple for a conceptual factory building."
)
NAV_PAGES = ["Prompt", "3D Preview", "Drawings + BOM", "Exports", "AI Setup"]
VISUALIZER_LAYERS = [
    "Primary steel",
    "Secondary steel",
    "Bracing",
    "Connections",
    "Bolts",
    "Cladding",
    "Panel seams",
    "Centerlines",
    "Member labels",
    "Slab",
]
DEFAULT_VISUALIZER_LAYERS = [
    "Primary steel",
    "Secondary steel",
    "Bracing",
    "Connections",
    "Bolts",
    "Cladding",
    "Panel seams",
    "Slab",
]
VIEW_PRESETS = ["Isometric", "Top plan", "Front elevation", "End frame", "Low perspective"]


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def vec_sub(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def vec_add(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def vec_mul(a: tuple[float, float, float], scalar: float) -> tuple[float, float, float]:
    return (a[0] * scalar, a[1] * scalar, a[2] * scalar)


def vec_dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def vec_cross(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def vec_norm(a: tuple[float, float, float]) -> tuple[float, float, float]:
    length = math.sqrt(vec_dot(a, a))
    if length == 0:
        return (0.0, 0.0, 0.0)
    return (a[0] / length, a[1] / length, a[2] / length)


def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", name.strip()).strip("_")
    return cleaned or "steel_structure"


def get_section(section_id: str) -> SteelSection | None:
    return SECTION_CATALOG.get(section_id)


def choose_primary_section(spec: BuildingSpec) -> str:
    span = spec.width_m
    height = spec.eave_height_m
    if span >= 40 or height >= 14:
        return "W24X55"
    if span >= 32 or height >= 12:
        return "W21X44"
    if span >= 26 or height >= 10:
        return "W18X35"
    if span >= 20 or height >= 8:
        return "W16X36"
    if span >= 14:
        return "W14X30"
    return "W12X26"


def section_depth(section_id: str, fallback: float) -> float:
    section = get_section(section_id)
    return section.depth_m if section else fallback


def first_catalog_section(prefix: str, fallback: str) -> str:
    for key in SECTION_CATALOG:
        if key.startswith(prefix):
            return key
    return fallback


def choose_purlin_section(spec: BuildingSpec, role: str = "roof") -> str:
    if role == "eave":
        target_prefix = "EAVE250" if spec.width_m >= 24 else "EAVE200"
    elif role == "girt":
        target_prefix = "C200" if spec.eave_height_m >= 8 else "C150"
    else:
        target_prefix = "Z250" if spec.width_m >= 24 else "Z200"

    preferred = f"{target_prefix}X2P5"
    if preferred in SECTION_CATALOG:
        return preferred
    return first_catalog_section(target_prefix, "Z200X2P5" if role == "roof" else "C200X2P5")


def get_cladding_option(option_id: str) -> CladdingOption:
    return CLADDING_CATALOG.get(option_id) or CLADDING_CATALOG["CORRUGATED_GALV"]


def cladding_label(option_id: str) -> str:
    option = get_cladding_option(option_id)
    return f"{option.display_name} ({option.option_id})"


def cladding_options_for_ui() -> list[str]:
    return [option_id for option_id in sorted(CLADDING_CATALOG)]


def select_cladding_from_label(label: str) -> str:
    match = re.search(r"\(([A-Z0-9_]+)\)\s*$", label)
    if match and match.group(1) in CLADDING_CATALOG:
        return match.group(1)
    for option_id, option in CLADDING_CATALOG.items():
        if option.display_name == label:
            return option_id
    return "CORRUGATED_GALV"


def detect_cladding_options(prompt: str) -> dict[str, str]:
    normalized = prompt.lower()
    rules = [
        (("standing seam", "concealed fastener"), "STANDING_SEAM_24GA"),
        (("22 gauge standing", "22ga standing", "heavy standing"), "STANDING_SEAM_22GA"),
        (("pbr", "pbr-panel", "purlin bearing"), "PBR_PANEL_26GA"),
        (("r-panel", "r panel", "ribbed panel"), "R_PANEL_26GA"),
        (("24 gauge r", "24ga r", "heavy r-panel"), "R_PANEL_24GA"),
        (("trapezoidal", "32mm rib"), "TRAPEZOIDAL_32MM"),
        (("trapezoidal 45", "45mm rib", "deep rib"), "TRAPEZOIDAL_45MM"),
        (("insulated", "sandwich", "pir panel"), "INSULATED_PIR_50"),
        (("100mm insulated", "100 mm insulated", "cold storage"), "INSULATED_PIR_100"),
        (("b-deck", "b deck", "roof deck"), "METAL_DECK_B_22GA"),
        (("n-deck", "n deck", "deep deck"), "METAL_DECK_N_20GA"),
        (("polycarbonate", "skylight", "rooflight"), "POLYCARB_SKYLIGHT"),
        (("frp", "fiberglass translucent"), "FRP_TRANSLUCENT"),
        (("corrugated", "corrugated sheet", "corrugated sheets"), "CORRUGATED_GALV"),
        (("pvc corrugated", "plastic corrugated"), "PVC_CORRUGATED"),
        (("aluminum corrugated", "aluminium corrugated"), "CORRUGATED_ALUM"),
    ]
    roof_words = ("roof", "roofing", "top", "ceiling")
    wall_words = ("wall", "walls", "siding", "facade", "cladding")
    selections: dict[str, str] = {}

    def nearest_scope(start: int, end: int) -> str:
        before = normalized[max(0, start - 40) : start]
        after = normalized[end : min(len(normalized), end + 40)]
        roof_pattern = r"\b(?:roof|roofing|top|ceiling)\b"
        wall_pattern = r"\b(?:wall|walls|siding|facade|cladding)\b"
        both_pattern = rf"(?:{roof_pattern}.{{0,18}}{wall_pattern}|{wall_pattern}.{{0,18}}{roof_pattern})"
        if re.search(both_pattern, before) or re.search(both_pattern, after):
            return "both"
        if re.search(rf"^\W*(?:on|for|as|with|to)?\W*(?:the)?\W*{roof_pattern}", after):
            return "roof"
        if re.search(rf"^\W*(?:on|for|as|with|to)?\W*(?:the)?\W*{wall_pattern}", after):
            return "wall"
        if re.search(rf"{roof_pattern}\W*(?:with|using|as|in)?\W*$", before):
            return "roof"
        if re.search(rf"{wall_pattern}\W*(?:with|using|as|in)?\W*$", before):
            return "wall"

        window_start = max(0, start - 56)
        window_end = min(len(normalized), end + 56)
        window = normalized[window_start:window_end]
        keyword_center = (start + end) / 2 - window_start

        def nearest_distance(words: tuple[str, ...]) -> float | None:
            distances: list[float] = []
            for word in words:
                for match in re.finditer(re.escape(word), window):
                    center = (match.start() + match.end()) / 2
                    distances.append(abs(center - keyword_center))
            return min(distances) if distances else None

        roof_distance = nearest_distance(roof_words)
        wall_distance = nearest_distance(wall_words)
        if roof_distance is None and wall_distance is None:
            return "both"
        if roof_distance is not None and wall_distance is not None and abs(roof_distance - wall_distance) <= 2:
            return "both"
        if wall_distance is None or (roof_distance is not None and roof_distance < wall_distance):
            return "roof"
        return "wall"

    for keywords, option_id in rules:
        for keyword in keywords:
            for match in re.finditer(re.escape(keyword), normalized):
                scope = nearest_scope(match.start(), match.end())
                if scope in {"roof", "both"}:
                    selections["roof_sheet_option"] = option_id
                if scope in {"wall", "both"}:
                    selections["wall_sheet_option"] = option_id
    return selections


def spec_to_dict(spec: BuildingSpec) -> dict[str, object]:
    return asdict(spec)


def spec_from_dict(data: dict[str, object]) -> BuildingSpec:
    defaults = spec_to_dict(BuildingSpec())
    defaults.update({key: value for key, value in data.items() if key in defaults})
    defaults["length_m"] = float(defaults["length_m"])
    defaults["width_m"] = float(defaults["width_m"])
    defaults["eave_height_m"] = float(defaults["eave_height_m"])
    defaults["bay_count"] = int(defaults["bay_count"])
    defaults["roof_pitch_deg"] = float(defaults["roof_pitch_deg"])
    defaults["frame_section_m"] = float(defaults["frame_section_m"])
    defaults["secondary_section_m"] = float(defaults["secondary_section_m"])
    defaults["slab_thickness_m"] = float(defaults["slab_thickness_m"])
    defaults["include_bracing"] = bool(defaults["include_bracing"])
    defaults["include_wall_girts"] = bool(defaults["include_wall_girts"])
    defaults["include_roof_purlins"] = bool(defaults["include_roof_purlins"])
    return BuildingSpec(**defaults)


def feet_to_meters(value: float) -> float:
    return value * 0.3048


def number_unit_to_meters(value: str, unit: str | None) -> float:
    parsed = float(value.replace(",", ""))
    if unit and unit.lower() in {"ft", "foot", "feet", "'"}:
        return feet_to_meters(parsed)
    return parsed


def parse_dimension_triplet(prompt: str) -> tuple[float, float, float] | None:
    pattern = re.compile(
        r"(?P<a>\d+(?:\.\d+)?)\s*(?P<unit_a>m|meter|meters|ft|foot|feet)?\s*[xX]\s*"
        r"(?P<b>\d+(?:\.\d+)?)\s*(?P<unit_b>m|meter|meters|ft|foot|feet)?\s*[xX]\s*"
        r"(?P<c>\d+(?:\.\d+)?)\s*(?P<unit_c>m|meter|meters|ft|foot|feet)?"
    )
    match = pattern.search(prompt)
    if not match:
        return None

    unit = match.group("unit_c") or match.group("unit_b") or match.group("unit_a")
    return (
        number_unit_to_meters(match.group("a"), match.group("unit_a") or unit),
        number_unit_to_meters(match.group("b"), match.group("unit_b") or unit),
        number_unit_to_meters(match.group("c"), match.group("unit_c") or unit),
    )


def find_labeled_dimension(prompt: str, labels: Iterable[str]) -> float | None:
    label_group = "|".join(re.escape(label) for label in labels)
    number = r"(?P<value>\d+(?:,\d{3})*(?:\.\d+)?)"
    unit = r"(?P<unit>m|meter|meters|metre|metres|ft|foot|feet|')?"

    after_label = re.compile(
        rf"(?:{label_group})\D{{0,24}}{number}\s*{unit}",
        re.IGNORECASE,
    )
    before_label = re.compile(
        rf"{number}\s*{unit}\D{{0,18}}(?:{label_group})",
        re.IGNORECASE,
    )

    for pattern in (before_label, after_label):
        match = pattern.search(prompt)
        if match:
            return number_unit_to_meters(match.group("value"), match.group("unit"))
    return None


def extract_with_local_parser(prompt: str) -> BuildingSpec:
    text = prompt.strip()
    normalized = text.lower().replace("metres", "meters").replace("metre", "meter")
    spec = BuildingSpec(design_notes="Parsed with the built-in free rule-based extractor.")

    triplet = parse_dimension_triplet(normalized)
    if triplet:
        spec.length_m, spec.width_m, spec.eave_height_m = triplet

    length = find_labeled_dimension(normalized, ["length", "long", "deep"])
    width = find_labeled_dimension(normalized, ["width", "wide", "span"])
    height = find_labeled_dimension(normalized, ["height", "tall", "eave", "ceiling"])

    if length:
        spec.length_m = length
    if width:
        spec.width_m = width
    if height:
        spec.eave_height_m = height

    bay_match = re.search(r"(\d+)\s*(?:bay|bays)", normalized)
    if bay_match:
        spec.bay_count = int(bay_match.group(1))
    else:
        spec.bay_count = int(clamp(round(spec.length_m / 5), 3, 24))

    pitch_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:degree|deg)\s*(?:roof\s*)?pitch", normalized)
    if pitch_match:
        spec.roof_pitch_deg = float(pitch_match.group(1))

    if "factory" in normalized:
        spec.building_type = "Factory"
    elif "workshop" in normalized:
        spec.building_type = "Workshop"
    elif "hangar" in normalized:
        spec.building_type = "Aircraft Hangar"
    elif "warehouse" in normalized:
        spec.building_type = "Warehouse"

    if "flat roof" in normalized or "low slope" in normalized:
        spec.roof_style = "Flat"
        spec.roof_pitch_deg = 2.0
    elif "mono" in normalized or "single slope" in normalized or "shed roof" in normalized:
        spec.roof_style = "Mono-slope"
    else:
        spec.roof_style = "Gable"

    if "no bracing" in normalized or "without bracing" in normalized:
        spec.include_bracing = False
    if "no girts" in normalized or "without girts" in normalized:
        spec.include_wall_girts = False
    if "no purlins" in normalized or "without purlins" in normalized:
        spec.include_roof_purlins = False

    cladding_choices = detect_cladding_options(normalized)
    if "roof_sheet_option" in cladding_choices:
        spec.roof_sheet_option = cladding_choices["roof_sheet_option"]
    if "wall_sheet_option" in cladding_choices:
        spec.wall_sheet_option = cladding_choices["wall_sheet_option"]

    name_match = re.search(r"(?:called|named|project name is)\s+([a-zA-Z0-9 _-]{3,40})", text, re.IGNORECASE)
    if name_match:
        spec.project_name = name_match.group(1).strip()

    return validate_spec(spec)


AI_JSON_SCHEMA = {
    "project_name": "Concept Warehouse",
    "building_type": "Warehouse | Factory | Workshop | Aircraft Hangar",
    "length_m": 40,
    "width_m": 20,
    "eave_height_m": 10,
    "bay_count": 8,
    "roof_style": "Gable | Flat | Mono-slope",
    "roof_pitch_deg": 10,
    "include_bracing": True,
    "include_wall_girts": True,
    "include_roof_purlins": True,
    "roof_sheet_option": "CORRUGATED_GALV | R_PANEL_26GA | PBR_PANEL_26GA | STANDING_SEAM_24GA | TRAPEZOIDAL_32MM | INSULATED_PIR_50",
    "wall_sheet_option": "CORRUGATED_GALV | R_PANEL_26GA | PBR_PANEL_26GA | TRAPEZOIDAL_32MM | INSULATED_PIR_50 | POLYCARB_SKYLIGHT",
    "design_notes": "brief assumptions",
}


def explicit_prompt_overrides(prompt: str) -> dict[str, object]:
    text = prompt.strip()
    normalized = text.lower().replace("metres", "meters").replace("metre", "meter")
    overrides: dict[str, object] = {}

    triplet = parse_dimension_triplet(normalized)
    if triplet:
        overrides["length_m"], overrides["width_m"], overrides["eave_height_m"] = triplet

    length = find_labeled_dimension(normalized, ["length", "long", "deep"])
    width = find_labeled_dimension(normalized, ["width", "wide", "span"])
    height = find_labeled_dimension(normalized, ["height", "tall", "eave", "ceiling"])
    if length:
        overrides["length_m"] = length
    if width:
        overrides["width_m"] = width
    if height:
        overrides["eave_height_m"] = height

    bay_match = re.search(r"(\d+)\s*(?:bay|bays)", normalized)
    if bay_match:
        overrides["bay_count"] = int(bay_match.group(1))

    pitch_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:degree|deg)\s*(?:roof\s*)?pitch", normalized)
    if pitch_match:
        overrides["roof_pitch_deg"] = float(pitch_match.group(1))

    if "factory" in normalized:
        overrides["building_type"] = "Factory"
    elif "workshop" in normalized:
        overrides["building_type"] = "Workshop"
    elif "hangar" in normalized:
        overrides["building_type"] = "Aircraft Hangar"
    elif "warehouse" in normalized:
        overrides["building_type"] = "Warehouse"

    if "flat roof" in normalized or "low slope" in normalized:
        overrides["roof_style"] = "Flat"
        overrides.setdefault("roof_pitch_deg", 2.0)
    elif "mono" in normalized or "single slope" in normalized or "shed roof" in normalized:
        overrides["roof_style"] = "Mono-slope"
    elif "gable" in normalized:
        overrides["roof_style"] = "Gable"

    if "no bracing" in normalized or "without bracing" in normalized:
        overrides["include_bracing"] = False
    if "no girts" in normalized or "without girts" in normalized:
        overrides["include_wall_girts"] = False
    if "no purlins" in normalized or "without purlins" in normalized:
        overrides["include_roof_purlins"] = False

    overrides.update(detect_cladding_options(normalized))

    name_match = re.search(r"(?:called|named|project name is)\s+([a-zA-Z0-9 _-]{3,40})", text, re.IGNORECASE)
    if name_match:
        overrides["project_name"] = name_match.group(1).strip()

    return overrides


def merge_ai_with_explicit_prompt(prompt: str, ai_spec: BuildingSpec) -> BuildingSpec:
    data = spec_to_dict(ai_spec)
    if str(data.get("project_name", "")).strip().lower() in {"short project name", "project name"}:
        data["project_name"] = BuildingSpec().project_name
    data.update(explicit_prompt_overrides(prompt))
    return validate_spec(spec_from_dict(data))


def apply_relative_followup(current: BuildingSpec, request: str, data: dict[str, object]) -> None:
    normalized = request.lower()
    relative_patterns = [
        ("length_m", ["longer", "length", "long"]),
        ("width_m", ["wider", "width", "wide", "span"]),
        ("eave_height_m", ["taller", "higher", "height", "tall"]),
    ]
    for field, labels in relative_patterns:
        label_group = "|".join(re.escape(label) for label in labels)
        inc = re.search(rf"(?:increase|add|make).*?(?:{label_group}).*?by\s+(\d+(?:\.\d+)?)\s*(m|meter|meters|ft|foot|feet)?", normalized)
        dec = re.search(rf"(?:decrease|reduce|make).*?(?:{label_group}).*?by\s+(\d+(?:\.\d+)?)\s*(m|meter|meters|ft|foot|feet)?", normalized)
        number_before_inc = re.search(rf"(\d+(?:\.\d+)?)\s*(m|meter|meters|ft|foot|feet)?\s+(?:{label_group})", normalized)
        if inc:
            data[field] = float(getattr(current, field)) + number_unit_to_meters(inc.group(1), inc.group(2))
        if number_before_inc and any(word in normalized for word in ["longer", "wider", "taller", "higher"]):
            data[field] = float(getattr(current, field)) + number_unit_to_meters(number_before_inc.group(1), number_before_inc.group(2))
        if dec:
            data[field] = float(getattr(current, field)) - number_unit_to_meters(dec.group(1), dec.group(2))

    if "add bracing" in normalized or "include bracing" in normalized:
        data["include_bracing"] = True
    if "remove bracing" in normalized or "no bracing" in normalized or "without bracing" in normalized:
        data["include_bracing"] = False
    if "add purlins" in normalized or "add roof purlins" in normalized or "include purlins" in normalized or "include roof purlins" in normalized:
        data["include_roof_purlins"] = True
    if "remove purlins" in normalized or "remove roof purlins" in normalized or "no purlins" in normalized or "without purlins" in normalized:
        data["include_roof_purlins"] = False
    if "add girts" in normalized or "add wall girts" in normalized or "include girts" in normalized or "include wall girts" in normalized:
        data["include_wall_girts"] = True
    if "remove girts" in normalized or "remove wall girts" in normalized or "no girts" in normalized or "without girts" in normalized:
        data["include_wall_girts"] = False


def apply_followup_local(current: BuildingSpec, request: str) -> BuildingSpec:
    data = spec_to_dict(current)
    data.update(explicit_prompt_overrides(request))
    apply_relative_followup(current, request, data)
    notes = data.get("design_notes", "")
    data["design_notes"] = f"{notes}\nFollow-up applied: {request}".strip()
    return validate_spec(spec_from_dict(data))


def followup_prompt(current: BuildingSpec, request: str) -> str:
    return (
        "Update the current steel building project. Keep existing values unless the user asks to change them. "
        "Return the complete updated JSON object using the required schema, not a partial patch.\n\n"
        f"Current project JSON:\n{json.dumps(spec_to_dict(current), indent=2)}\n\n"
        f"User follow-up request:\n{request}"
    )


def merge_followup_ai_result(current: BuildingSpec, request: str, ai_spec: BuildingSpec) -> BuildingSpec:
    data = spec_to_dict(current)
    normalized = request.lower()

    if any(word in normalized for word in ["roof", "slope", "pitch", "gable", "mono", "flat"]):
        data["roof_style"] = ai_spec.roof_style
        data["roof_pitch_deg"] = ai_spec.roof_pitch_deg
    if "bay" in normalized:
        data["bay_count"] = ai_spec.bay_count
    if any(word in normalized for word in ["warehouse", "factory", "workshop", "hangar"]):
        data["building_type"] = ai_spec.building_type
    if "bracing" in normalized:
        data["include_bracing"] = ai_spec.include_bracing
    if "purlin" in normalized:
        data["include_roof_purlins"] = ai_spec.include_roof_purlins
    if "girt" in normalized:
        data["include_wall_girts"] = ai_spec.include_wall_girts
    if any(word in normalized for word in ["roof sheet", "roofing", "roof panel", "standing seam", "corrugated", "r-panel", "pbr", "trapezoidal", "deck", "skylight"]):
        data["roof_sheet_option"] = ai_spec.roof_sheet_option
    if any(word in normalized for word in ["wall sheet", "wall panel", "siding", "cladding", "corrugated", "r-panel", "pbr", "trapezoidal", "insulated"]):
        data["wall_sheet_option"] = ai_spec.wall_sheet_option

    data.update(explicit_prompt_overrides(request))
    apply_relative_followup(current, request, data)
    if ai_spec.design_notes:
        data["design_notes"] = f"{current.design_notes}\nAI follow-up notes: {ai_spec.design_notes}".strip()
    return validate_spec(spec_from_dict(data))


def apply_followup_with_provider(
    current: BuildingSpec,
    request: str,
    provider: str,
    api_key: str,
    model: str,
    ollama_host: str,
) -> tuple[BuildingSpec, str]:
    if provider == "OpenAI":
        if not api_key:
            raise ValueError("OpenAI selected, but no API key was provided.")
        updated = extract_with_openai(followup_prompt(current, request), api_key, model)
        return merge_followup_ai_result(current, request, updated), "OpenAI"
    if provider == "Google Gemini":
        if not api_key:
            raise ValueError("Google Gemini selected, but no API key was provided.")
        updated = extract_with_gemini(followup_prompt(current, request), api_key, model)
        return merge_followup_ai_result(current, request, updated), "Google Gemini"
    if provider == "Ollama Local":
        updated = extract_with_ollama(followup_prompt(current, request), model, ollama_host)
        return merge_followup_ai_result(current, request, updated), "Ollama Local"
    return apply_followup_local(current, request), "Local parser"


def building_spec_json_schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "project_name": {"type": "string"},
            "building_type": {"type": "string", "enum": ["Warehouse", "Factory", "Workshop", "Aircraft Hangar"]},
            "length_m": {"type": "number"},
            "width_m": {"type": "number"},
            "eave_height_m": {"type": "number"},
            "bay_count": {"type": "integer"},
            "roof_style": {"type": "string", "enum": ["Gable", "Flat", "Mono-slope"]},
            "roof_pitch_deg": {"type": "number"},
            "include_bracing": {"type": "boolean"},
            "include_wall_girts": {"type": "boolean"},
            "include_roof_purlins": {"type": "boolean"},
            "roof_sheet_option": {"type": "string", "enum": sorted(CLADDING_CATALOG.keys())},
            "wall_sheet_option": {"type": "string", "enum": sorted(CLADDING_CATALOG.keys())},
            "design_notes": {"type": "string"},
        },
        "required": [
            "project_name",
            "building_type",
            "length_m",
            "width_m",
            "eave_height_m",
            "bay_count",
            "roof_style",
            "roof_pitch_deg",
            "include_bracing",
            "include_wall_girts",
            "include_roof_purlins",
            "roof_sheet_option",
            "wall_sheet_option",
            "design_notes",
        ],
    }


def ai_system_prompt() -> str:
    return (
        "You extract conceptual steel building parameters from a user's prompt. "
        "Return only valid JSON. Use meters. If a value is missing, make a practical "
        "conceptual default and explain it briefly in design_notes. Do not include "
        "engineering certification or code-compliance claims. JSON shape: "
        f"{json.dumps(AI_JSON_SCHEMA)}"
    )


def parse_json_from_text(text: str) -> dict[str, object]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("AI response did not include a JSON object.")
    return json.loads(text[start : end + 1])


def post_json(url: str, payload: dict[str, object], headers: dict[str, str], timeout: int = 45) -> dict[str, object]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def get_json(url: str, timeout: int = 5) -> dict[str, object]:
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def check_ollama_status(host: str) -> tuple[bool, str]:
    base = host.rstrip("/")
    try:
        version_data = get_json(f"{base}/api/version", timeout=3)
        tags_data = get_json(f"{base}/api/tags", timeout=5)
        models = [model.get("name", "") for model in tags_data.get("models", []) if isinstance(model, dict)]
        model_summary = ", ".join(models[:5]) if models else "no models pulled yet"
        version = version_data.get("version", "unknown")
        return True, f"Ollama is running at {base}. Version: {version}. Local models: {model_summary}."
    except Exception as exc:
        return False, f"Ollama is not reachable at {base}. Start Ollama and pull a model first. Details: {exc}"


def extract_with_openai(prompt: str, api_key: str, model: str) -> BuildingSpec:
    payload = {
        "model": model,
        "input": [
            {"role": "system", "content": ai_system_prompt()},
            {"role": "user", "content": prompt},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "building_spec",
                "strict": True,
                "schema": building_spec_json_schema(),
            }
        },
    }
    data = post_json(
        "https://api.openai.com/v1/responses",
        payload,
        {"Authorization": f"Bearer {api_key}"},
    )
    chunks: list[str] = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"}:
                chunks.append(content.get("text", ""))
    if not chunks and "output_text" in data:
        chunks.append(str(data["output_text"]))
    return validate_spec(spec_from_dict(parse_json_from_text("\n".join(chunks))))


def extract_with_gemini(prompt: str, api_key: str, model: str) -> BuildingSpec:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": f"{ai_system_prompt()}\n\nUser prompt:\n{prompt}"}],
            }
        ],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    data = post_json(url, payload, {})
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    return validate_spec(spec_from_dict(parse_json_from_text(text)))


def extract_with_ollama(prompt: str, model: str, host: str) -> BuildingSpec:
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": ai_system_prompt()},
            {"role": "user", "content": prompt},
        ],
        "format": building_spec_json_schema(),
    }
    data = post_json(f"{host.rstrip('/')}/api/chat", payload, {}, timeout=120)
    return validate_spec(spec_from_dict(parse_json_from_text(data["message"]["content"])))


def extract_spec(prompt: str, provider: str, api_key: str, model: str, ollama_host: str) -> tuple[BuildingSpec, str]:
    if provider == "OpenAI":
        if not api_key:
            raise ValueError("OpenAI selected, but no API key was provided.")
        return merge_ai_with_explicit_prompt(prompt, extract_with_openai(prompt, api_key, model)), "OpenAI"
    if provider == "Google Gemini":
        if not api_key:
            raise ValueError("Google Gemini selected, but no API key was provided.")
        return merge_ai_with_explicit_prompt(prompt, extract_with_gemini(prompt, api_key, model)), "Google Gemini"
    if provider == "Ollama Local":
        return merge_ai_with_explicit_prompt(prompt, extract_with_ollama(prompt, model, ollama_host)), "Ollama Local"
    return extract_with_local_parser(prompt), "Local parser"


def validate_spec(spec: BuildingSpec) -> BuildingSpec:
    roof_style = spec.roof_style if spec.roof_style in {"Gable", "Flat", "Mono-slope"} else "Gable"
    roof_sheet_option = spec.roof_sheet_option if spec.roof_sheet_option in CLADDING_CATALOG else "CORRUGATED_GALV"
    wall_sheet_option = spec.wall_sheet_option if spec.wall_sheet_option in CLADDING_CATALOG else "CORRUGATED_GALV"
    return replace(
        spec,
        length_m=round(clamp(float(spec.length_m), 6, 250), 2),
        width_m=round(clamp(float(spec.width_m), 4, 120), 2),
        eave_height_m=round(clamp(float(spec.eave_height_m), 3, 40), 2),
        bay_count=int(clamp(int(spec.bay_count), 1, 40)),
        roof_style=roof_style,
        roof_pitch_deg=round(clamp(float(spec.roof_pitch_deg), 0, 35), 2),
        frame_section_m=round(clamp(float(spec.frame_section_m), 0.12, 1.2), 3),
        secondary_section_m=round(clamp(float(spec.secondary_section_m), 0.06, 0.6), 3),
        slab_thickness_m=round(clamp(float(spec.slab_thickness_m), 0.08, 0.5), 3),
        roof_sheet_option=roof_sheet_option,
        wall_sheet_option=wall_sheet_option,
    )


def roof_z(spec: BuildingSpec, y: float) -> float:
    half_w = spec.width_m / 2
    if spec.roof_style == "Flat":
        return spec.eave_height_m
    if spec.roof_style == "Mono-slope":
        rise = spec.width_m * math.tan(math.radians(spec.roof_pitch_deg))
        return spec.eave_height_m + ((y + half_w) / spec.width_m) * rise

    rise = half_w * math.tan(math.radians(spec.roof_pitch_deg))
    return spec.eave_height_m + (1 - abs(y) / half_w) * rise


def x_positions(spec: BuildingSpec) -> list[float]:
    if spec.bay_count <= 0:
        return [-spec.length_m / 2, spec.length_m / 2]
    bay = spec.length_m / spec.bay_count
    return [-spec.length_m / 2 + bay * i for i in range(spec.bay_count + 1)]


def add_member(
    members: list[Member],
    name: str,
    role: str,
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    size_m: float,
    section_id: str,
) -> None:
    if distance(start, end) > 0.001:
        members.append(Member(name, role, start, end, size_m, section_id))


def generate_members(spec: BuildingSpec) -> list[Member]:
    members: list[Member] = []
    xs = x_positions(spec)
    half_w = spec.width_m / 2
    primary_section = choose_primary_section(spec)
    purlin_section = choose_purlin_section(spec, "roof")
    girt_section = choose_purlin_section(spec, "girt")
    strut_section = choose_purlin_section(spec, "eave")
    brace_section = "ROD20"
    frame = section_depth(primary_section, spec.frame_section_m)
    secondary = section_depth(purlin_section, spec.secondary_section_m)

    for index, x in enumerate(xs):
        for side, y in (("L", -half_w), ("R", half_w)):
            add_member(
                members,
                f"Frame {index + 1} column {side}",
                "Primary columns",
                (x, y, 0),
                (x, y, spec.eave_height_m),
                frame,
                primary_section,
            )

        if spec.roof_style == "Gable":
            apex = (x, 0, roof_z(spec, 0))
            add_member(members, f"Frame {index + 1} left rafter", "Primary rafters", (x, -half_w, spec.eave_height_m), apex, frame, primary_section)
            add_member(members, f"Frame {index + 1} right rafter", "Primary rafters", apex, (x, half_w, spec.eave_height_m), frame, primary_section)
        else:
            add_member(
                members,
                f"Frame {index + 1} roof beam",
                "Primary rafters",
                (x, -half_w, roof_z(spec, -half_w)),
                (x, half_w, roof_z(spec, half_w)),
                frame,
                primary_section,
            )

    for y in (-half_w, half_w):
        add_member(members, "Left eave strut" if y < 0 else "Right eave strut", "Eave struts", (xs[0], y, roof_z(spec, y)), (xs[-1], y, roof_z(spec, y)), section_depth(strut_section, secondary), strut_section)

    if spec.roof_style == "Gable":
        add_member(members, "Ridge beam", "Ridge beam", (xs[0], 0, roof_z(spec, 0)), (xs[-1], 0, roof_z(spec, 0)), section_depth(strut_section, secondary), strut_section)

    if spec.include_roof_purlins:
        purlin_count = max(3, min(9, int(round(spec.width_m / 3))))
        for i in range(1, purlin_count):
            y = -half_w + spec.width_m * i / purlin_count
            if abs(y) < 0.01 and spec.roof_style == "Gable":
                continue
            add_member(members, f"Roof purlin {i}", "Roof purlins", (xs[0], y, roof_z(spec, y)), (xs[-1], y, roof_z(spec, y)), secondary, purlin_section)

    if spec.include_wall_girts:
        girt_levels = max(2, min(6, int(round(spec.eave_height_m / 2.5))))
        for level in range(1, girt_levels + 1):
            z = spec.eave_height_m * level / (girt_levels + 1)
            for y in (-half_w, half_w):
                add_member(members, f"Wall girt {level} {'left' if y < 0 else 'right'}", "Wall girts", (xs[0], y, z), (xs[-1], y, z), section_depth(girt_section, secondary), girt_section)

    if spec.include_bracing and len(xs) >= 2:
        brace_size = section_depth(brace_section, max(secondary * 0.7, 0.06))
        brace_bays = [(xs[0], xs[1]), (xs[-2], xs[-1])] if len(xs) > 2 else [(xs[0], xs[-1])]
        for bay_index, (x0, x1) in enumerate(brace_bays, start=1):
            for y in (-half_w, half_w):
                add_member(members, f"Sidewall X brace {bay_index}A", "Cross bracing", (x0, y, 0.4), (x1, y, spec.eave_height_m - 0.4), brace_size, brace_section)
                add_member(members, f"Sidewall X brace {bay_index}B", "Cross bracing", (x1, y, 0.4), (x0, y, spec.eave_height_m - 0.4), brace_size, brace_section)
            add_member(members, f"Roof X brace {bay_index}A", "Roof bracing", (x0, -half_w, roof_z(spec, -half_w)), (x1, half_w, roof_z(spec, half_w)), brace_size, brace_section)
            add_member(members, f"Roof X brace {bay_index}B", "Roof bracing", (x1, -half_w, roof_z(spec, -half_w)), (x0, half_w, roof_z(spec, half_w)), brace_size, brace_section)

        knee_len = min(spec.width_m * 0.12, spec.eave_height_m * 0.28, 3.0)
        knee_section = "HSS100X100X6" if "HSS100X100X6" in SECTION_CATALOG else strut_section
        knee_size = section_depth(knee_section, secondary)
        for index, x in enumerate(xs, start=1):
            for side, y in (("left", -half_w), ("right", half_w)):
                inward = 1 if y < 0 else -1
                eave = (x, y, spec.eave_height_m)
                low = (x, y, max(0.5, spec.eave_height_m - knee_len))
                roof_point = (x, y + inward * knee_len, roof_z(spec, y + inward * knee_len))
                add_member(members, f"Frame {index} {side} knee brace column", "Knee bracing", low, roof_point, knee_size, knee_section)

    return members


def oriented_box_mesh(
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    size: float,
) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    return oriented_rect_prism_mesh(start, end, size, size)


def local_axes_for_member(
    start: tuple[float, float, float],
    end: tuple[float, float, float],
) -> tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]:
    axis = vec_sub(end, start)
    axis_n = vec_norm(axis)
    if axis_n == (0.0, 0.0, 0.0):
        return axis_n, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)

    helper = (0.0, 0.0, 1.0)
    if abs(vec_dot(axis_n, helper)) > 0.92:
        helper = (0.0, 1.0, 0.0)
    u = vec_norm(vec_cross(axis_n, helper))
    v = vec_norm(vec_cross(axis_n, u))
    return axis_n, u, v


def oriented_rect_prism_mesh(
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    width_u: float,
    depth_v: float,
    offset_u: float = 0.0,
    offset_v: float = 0.0,
) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    axis_n, u, v = local_axes_for_member(start, end)
    if axis_n == (0.0, 0.0, 0.0):
        return [], []

    half_u = width_u / 2
    half_v = depth_v / 2
    center_offset = vec_add(vec_mul(u, offset_u), vec_mul(v, offset_v))
    start = vec_add(start, center_offset)
    end = vec_add(end, center_offset)
    offsets = [
        vec_add(vec_mul(u, -half_u), vec_mul(v, -half_v)),
        vec_add(vec_mul(u, half_u), vec_mul(v, -half_v)),
        vec_add(vec_mul(u, half_u), vec_mul(v, half_v)),
        vec_add(vec_mul(u, -half_u), vec_mul(v, half_v)),
    ]
    vertices = [vec_add(start, offset) for offset in offsets] + [vec_add(end, offset) for offset in offsets]
    faces = [
        (0, 1, 2),
        (0, 2, 3),
        (4, 6, 5),
        (4, 7, 6),
        (0, 4, 5),
        (0, 5, 1),
        (1, 5, 6),
        (1, 6, 2),
        (2, 6, 7),
        (2, 7, 3),
        (3, 7, 4),
        (3, 4, 0),
    ]
    return vertices, faces


def oriented_cylinder_mesh(
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    diameter: float,
    sides: int = 12,
) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    axis_n, u, v = local_axes_for_member(start, end)
    if axis_n == (0.0, 0.0, 0.0):
        return [], []

    radius = diameter / 2
    vertices: list[tuple[float, float, float]] = []
    for base in (start, end):
        for index in range(sides):
            angle = 2 * math.pi * index / sides
            offset = vec_add(vec_mul(u, math.cos(angle) * radius), vec_mul(v, math.sin(angle) * radius))
            vertices.append(vec_add(base, offset))

    faces: list[tuple[int, int, int]] = []
    for index in range(sides):
        nxt = (index + 1) % sides
        faces.append((index, nxt, sides + nxt))
        faces.append((index, sides + nxt, sides + index))
        faces.append((0, nxt, index))
        faces.append((sides, sides + index, sides + nxt))
    return vertices, faces


def member_mesh(member: Member) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    section = member.section
    if not section:
        return oriented_box_mesh(member.start, member.end, member.size_m)

    if section.family in {"W", "M", "S", "HP"}:
        meshes = [
            oriented_rect_prism_mesh(member.start, member.end, section.web_thickness_m, section.depth_m),
            oriented_rect_prism_mesh(
                member.start,
                member.end,
                section.flange_width_m,
                section.flange_thickness_m,
                offset_v=(section.depth_m - section.flange_thickness_m) / 2,
            ),
            oriented_rect_prism_mesh(
                member.start,
                member.end,
                section.flange_width_m,
                section.flange_thickness_m,
                offset_v=-(section.depth_m - section.flange_thickness_m) / 2,
            ),
        ]
        return combine_meshes(meshes)

    if section.family in {"C", "MC", "HAT"}:
        t = section.wall_thickness_m or section.web_thickness_m
        meshes = [
            oriented_rect_prism_mesh(member.start, member.end, t, section.depth_m),
            oriented_rect_prism_mesh(member.start, member.end, section.flange_width_m, t, offset_u=section.flange_width_m / 2, offset_v=(section.depth_m - t) / 2),
            oriented_rect_prism_mesh(member.start, member.end, section.flange_width_m, t, offset_u=section.flange_width_m / 2, offset_v=-(section.depth_m - t) / 2),
        ]
        return combine_meshes(meshes)

    if section.family in {"Z", "SIGMA"}:
        t = section.wall_thickness_m or section.web_thickness_m
        meshes = [
            oriented_rect_prism_mesh(member.start, member.end, t, section.depth_m),
            oriented_rect_prism_mesh(member.start, member.end, section.flange_width_m, t, offset_u=section.flange_width_m / 2, offset_v=(section.depth_m - t) / 2),
            oriented_rect_prism_mesh(member.start, member.end, section.flange_width_m, t, offset_u=-section.flange_width_m / 2, offset_v=-(section.depth_m - t) / 2),
        ]
        return combine_meshes(meshes)

    if section.family in {"ROD", "PIPE"}:
        return oriented_cylinder_mesh(member.start, member.end, section.depth_m)

    if section.family == "T":
        meshes = [
            oriented_rect_prism_mesh(member.start, member.end, section.web_thickness_m, section.depth_m),
            oriented_rect_prism_mesh(
                member.start,
                member.end,
                section.flange_width_m,
                section.flange_thickness_m,
                offset_v=(section.depth_m - section.flange_thickness_m) / 2,
            ),
        ]
        return combine_meshes(meshes)

    if section.family == "L":
        t = section.web_thickness_m
        meshes = [
            oriented_rect_prism_mesh(member.start, member.end, t, section.depth_m, offset_u=-(section.flange_width_m - t) / 2),
            oriented_rect_prism_mesh(member.start, member.end, section.flange_width_m, t, offset_v=-(section.depth_m - t) / 2),
        ]
        return combine_meshes(meshes)

    return oriented_rect_prism_mesh(member.start, member.end, section.flange_width_m, section.depth_m)


def axis_aligned_box_mesh(
    center: tuple[float, float, float],
    dims: tuple[float, float, float],
) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    cx, cy, cz = center
    dx, dy, dz = (dims[0] / 2, dims[1] / 2, dims[2] / 2)
    vertices = [
        (cx - dx, cy - dy, cz - dz),
        (cx + dx, cy - dy, cz - dz),
        (cx + dx, cy + dy, cz - dz),
        (cx - dx, cy + dy, cz - dz),
        (cx - dx, cy - dy, cz + dz),
        (cx + dx, cy - dy, cz + dz),
        (cx + dx, cy + dy, cz + dz),
        (cx - dx, cy + dy, cz + dz),
    ]
    faces = [
        (0, 2, 1),
        (0, 3, 2),
        (4, 5, 6),
        (4, 6, 7),
        (0, 1, 5),
        (0, 5, 4),
        (1, 2, 6),
        (1, 6, 5),
        (2, 3, 7),
        (2, 7, 6),
        (3, 0, 4),
        (3, 4, 7),
    ]
    return vertices, faces


def combine_meshes(meshes: Iterable[tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]]) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    for mesh_vertices, mesh_faces in meshes:
        offset = len(vertices)
        vertices.extend(mesh_vertices)
        faces.extend((a + offset, b + offset, c + offset) for a, b, c in mesh_faces)
    return vertices, faces


def build_model(spec: BuildingSpec) -> ModelPackage:
    spec = validate_spec(spec)
    warnings = [
        "Conceptual geometry only: this is not a stamped structural design and is not permit-ready.",
        "Member sections come from a starter visual catalog. A licensed structural engineer must verify member sizes, foundations, connections, and bracing.",
        "Connection details shown are typical placeholders only; bolt grades, weld sizes, plates, and brackets must be engineered for the actual loads and code jurisdiction.",
    ]
    if spec.length_m / max(spec.width_m, 0.001) > 6:
        warnings.append("The building is very long relative to its width; review expansion joints and longitudinal stability.")
    if spec.eave_height_m / max(spec.width_m, 0.001) > 0.8:
        warnings.append("The height/span ratio is high; lateral drift and wind bracing will need careful engineering.")

    members = generate_members(spec)
    member_meshes = [member_mesh(member) for member in members]
    slab_mesh = axis_aligned_box_mesh(
        (0, 0, -spec.slab_thickness_m / 2),
        (spec.length_m, spec.width_m, spec.slab_thickness_m),
    )
    vertices, faces = combine_meshes([slab_mesh, *member_meshes])
    return ModelPackage(
        spec,
        members,
        vertices,
        faces,
        bom_rows=build_bom(members, spec),
        connection_rows=build_connection_schedule(members, spec),
        warnings=warnings,
    )


def roof_surface_area(spec: BuildingSpec) -> float:
    half_w = spec.width_m / 2
    if spec.roof_style == "Gable":
        rise = max(roof_z(spec, 0) - spec.eave_height_m, 0.0)
        slope = math.sqrt(half_w * half_w + rise * rise)
        return 2 * slope * spec.length_m
    if spec.roof_style == "Mono-slope":
        rise = max(roof_z(spec, half_w) - roof_z(spec, -half_w), 0.0)
        slope = math.sqrt(spec.width_m * spec.width_m + rise * rise)
        return slope * spec.length_m
    return spec.length_m * spec.width_m


def wall_surface_area(spec: BuildingSpec) -> float:
    half_w = spec.width_m / 2
    sidewalls = 2 * spec.length_m * spec.eave_height_m
    if spec.roof_style == "Gable":
        rise = max(roof_z(spec, 0) - spec.eave_height_m, 0.0)
        endwalls = 2 * (spec.width_m * spec.eave_height_m + 0.5 * spec.width_m * rise)
    elif spec.roof_style == "Mono-slope":
        rise = max(roof_z(spec, half_w) - roof_z(spec, -half_w), 0.0)
        endwalls = 2 * (spec.width_m * spec.eave_height_m + 0.5 * spec.width_m * rise)
    else:
        endwalls = 2 * spec.width_m * spec.eave_height_m
    return sidewalls + endwalls


def roof_panel_count(spec: BuildingSpec, option: CladdingOption) -> int:
    panels_along_length = max(1, math.ceil(spec.length_m / max(option.coverage_width_m, 0.1)))
    return panels_along_length * (2 if spec.roof_style == "Gable" else 1)


def wall_panel_count(spec: BuildingSpec, option: CladdingOption) -> int:
    panels_on_sidewalls = 2 * math.ceil(spec.length_m / max(option.coverage_width_m, 0.1))
    panels_on_endwalls = 2 * math.ceil(spec.width_m / max(option.coverage_width_m, 0.1))
    return max(1, panels_on_sidewalls + panels_on_endwalls)


def build_cladding_bom(spec: BuildingSpec) -> list[dict[str, object]]:
    roof = get_cladding_option(spec.roof_sheet_option)
    wall = get_cladding_option(spec.wall_sheet_option)
    roof_area = roof_surface_area(spec)
    wall_area = wall_surface_area(spec)
    rows = [
        {
            "role": "Roof sheeting area",
            "section": roof.option_id,
            "profile": roof.panel_type,
            "depth_m": roof.rib_height_mm / 1000,
            "quantity": roof_panel_count(spec, roof),
            "total_length_m": roof_area,
            "estimated_weight_kg": roof_area * roof.weight_kg_m2,
        },
        {
            "role": "Wall cladding area",
            "section": wall.option_id,
            "profile": wall.panel_type,
            "depth_m": wall.rib_height_mm / 1000,
            "quantity": wall_panel_count(spec, wall),
            "total_length_m": wall_area,
            "estimated_weight_kg": wall_area * wall.weight_kg_m2,
        },
        {
            "role": "Roof sheet fasteners",
            "section": roof.fastening_pattern,
            "profile": "FASTENERS",
            "depth_m": 0.0,
            "quantity": math.ceil(roof_area * 5),
            "total_length_m": 0.0,
            "estimated_weight_kg": "Fastener count is conceptual",
        },
        {
            "role": "Wall sheet fasteners",
            "section": wall.fastening_pattern,
            "profile": "FASTENERS",
            "depth_m": 0.0,
            "quantity": math.ceil(wall_area * 4),
            "total_length_m": 0.0,
            "estimated_weight_kg": "Fastener count is conceptual",
        },
    ]
    return rows


def build_bom(members: list[Member], spec: BuildingSpec) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], dict[str, object]] = {}
    for member in members:
        section = member.section
        key = (member.role, member.section_id)
        row = grouped.setdefault(
            key,
            {
                "role": member.role,
                "section": member.section_id,
                "profile": section.family if section else "BOX",
                "depth_m": section.depth_m if section else member.size_m,
                "quantity": 0,
                "total_length_m": 0.0,
                "estimated_weight_kg": 0.0,
            },
        )
        row["quantity"] = int(row["quantity"]) + 1
        row["total_length_m"] = float(row["total_length_m"]) + member.length_m
        row["estimated_weight_kg"] = float(row["estimated_weight_kg"]) + member.steel_weight_kg

    rows = list(grouped.values())
    rows.extend(build_cladding_bom(spec))
    rows.extend(build_hardware_bom(members, spec))
    rows.append(
        {
            "role": "Concrete slab allowance",
            "section": f"{spec.slab_thickness_m:g}m slab",
            "profile": "CONCRETE",
            "depth_m": spec.slab_thickness_m,
            "quantity": 1,
            "total_length_m": round(spec.length_m * spec.width_m, 2),
            "estimated_weight_kg": "Review by concrete supplier",
        }
    )

    for row in rows:
        if isinstance(row["total_length_m"], float):
            row["total_length_m"] = round(row["total_length_m"], 2)
        if isinstance(row["estimated_weight_kg"], float):
            row["estimated_weight_kg"] = round(row["estimated_weight_kg"], 1)
    return rows


def member_angle_to_horizontal(member: Member) -> float:
    dx = member.end[0] - member.start[0]
    dy = member.end[1] - member.start[1]
    dz = member.end[2] - member.start[2]
    horizontal = math.sqrt(dx * dx + dy * dy)
    return abs(math.degrees(math.atan2(dz, horizontal))) if horizontal or dz else 0.0


def select_brace_rule(member: Member) -> BraceConnectionRule:
    angle = member_angle_to_horizontal(member)
    role = member.role.lower()
    if "knee" in role:
        candidates = [rule for rule in BRACE_CONNECTION_CATALOG if "knee" in rule.brace_family.lower()]
    elif "roof" in role or "cross" in role:
        candidates = [rule for rule in BRACE_CONNECTION_CATALOG if "cross" in rule.brace_family.lower() or "bracing" in rule.brace_family.lower()]
    else:
        candidates = BRACE_CONNECTION_CATALOG

    for rule in candidates:
        if rule.min_angle_deg <= angle <= rule.max_angle_deg:
            return rule
    return candidates[0] if candidates else BRACE_CONNECTION_CATALOG[0]


def build_hardware_bom(members: list[Member], spec: BuildingSpec) -> list[dict[str, object]]:
    hardware: dict[str, dict[str, object]] = {}

    def add_hardware(role: str, section: str, quantity: int) -> None:
        row = hardware.setdefault(
            (role, section),
            {
                "role": role,
                "section": section,
                "profile": "HARDWARE",
                "depth_m": 0.0,
                "quantity": 0,
                "total_length_m": 0.0,
                "estimated_weight_kg": "Connection hardware - engineer quantity/grade",
            },
        )
        row["quantity"] = int(row["quantity"]) + quantity

    frame_count = spec.bay_count + 1
    add_hardware("Anchor rods", "Typical 4 per column base", frame_count * 2 * 4)
    add_hardware("Primary frame bolts", "M20 class 8.8 placeholder", frame_count * 18)

    for member in members:
        if member.role in {"Roof purlins", "Wall girts"}:
            add_hardware(f"{member.role} fasteners", "M12 self-drilling/bolted clip placeholder", max(2, spec.bay_count * 2))
        if "bracing" in member.role.lower() or "brace" in member.role.lower():
            rule = select_brace_rule(member)
            add_hardware(f"{member.role} bolts", rule.bolt_spec, rule.bolts_per_end * 2)
            add_hardware(f"{member.role} plates", rule.connection_plate, 2)

    return list(hardware.values())


def build_connection_schedule(members: list[Member], spec: BuildingSpec) -> list[dict[str, object]]:
    primary = choose_primary_section(spec)
    roof_sheet = get_cladding_option(spec.roof_sheet_option)
    wall_sheet = get_cladding_option(spec.wall_sheet_option)
    purlin_count = len([member for member in members if member.role == "Roof purlins"])
    girt_count = len([member for member in members if member.role == "Wall girts"])
    brace_count = len([member for member in members if "bracing" in member.role.lower()])
    frame_count = spec.bay_count + 1

    rows = [
        {
            "detail": "C1 column base plate",
            "applies_to": f"{frame_count * 2} column bases",
            "primary_members": f"{primary} column to concrete slab/foundation",
            "bolts": "Typical: 4 anchor rods per column base. Engineer diameter, embedment, grade, and edge distance.",
            "welds": "Typical: shop weld column to base plate. Engineer weld size and plate thickness.",
            "brackets_plates": "Base plate with leveling nuts/grout pad. Add shear lug only if engineered.",
            "status": "Concept placeholder",
        },
        {
            "detail": "C2 eave/knee connection",
            "applies_to": f"{frame_count * 2} eave knees",
            "primary_members": f"{primary} column to {primary} rafter",
            "bolts": "Typical: bolted end-plate or haunch connection. Engineer bolt count, spacing, and slip/pretension class.",
            "welds": "Typical: shop weld end plate/haunch stiffeners to member. Engineer weld size.",
            "brackets_plates": "Haunch or bolted end plate with stiffeners as required by frame analysis.",
            "status": "Concept placeholder",
        },
        {
            "detail": "C3 ridge/rafter splice",
            "applies_to": f"{frame_count} ridge or roof-beam splices",
            "primary_members": f"{primary} rafter to {primary} rafter",
            "bolts": "Typical: bolted splice/end plate. Engineer bolt pattern for moment and shear.",
            "welds": "Shop weld splice plates/end plates as engineered.",
            "brackets_plates": "Ridge plate or bolted splice plate with web/flange stiffeners if required.",
            "status": "Concept placeholder",
        },
        {
            "detail": "C4 purlin clip",
            "applies_to": f"{purlin_count} purlin lines across primary frames",
            "primary_members": "Z200X2.5 purlin to primary rafter",
            "bolts": "Typical: 2 bolts/screws per purlin seat. Engineer fastener type and spacing.",
            "welds": "Prefer bolted/screwed field connection; shop weld clips to primary member if specified.",
            "brackets_plates": "Cold-formed purlin cleat or angle clip.",
            "status": "Concept placeholder",
        },
        {
            "detail": "C5 wall girt clip",
            "applies_to": f"{girt_count} girt lines",
            "primary_members": "C200X2.5 girt to primary column",
            "bolts": "Typical: 2 bolts/screws per girt clip. Engineer fastener type and spacing.",
            "welds": "Prefer bolted/screwed field connection; shop weld clips only if specified.",
            "brackets_plates": "Girt clip angle or stand-off bracket aligned to cladding system.",
            "status": "Concept placeholder",
        },
        {
            "detail": "C6 bracing gusset",
            "applies_to": f"{brace_count} brace members",
            "primary_members": "ROD20 bracing to frame",
            "bolts": "Typical: clevis/pin or bolted gusset. Engineer rod diameter, turnbuckle, and gusset thickness.",
            "welds": "Shop weld gusset plates to primary frame only if verified by engineer.",
            "brackets_plates": "Gusset plates with turnbuckles for tension-only bracing where applicable.",
            "status": "Concept placeholder",
        },
        {
            "detail": "C7 cladding fasteners and trims",
            "applies_to": f"{round(roof_surface_area(spec))} m2 roof, {round(wall_surface_area(spec))} m2 wall cladding",
            "primary_members": f"{roof_sheet.display_name} roof panels and {wall_sheet.display_name} wall panels",
            "bolts": f"Roof: {roof_sheet.fastening_pattern}. Wall: {wall_sheet.fastening_pattern}. Engineer wind uplift and edge-zone spacing.",
            "welds": "No field welds to sheets; use compatible screws, clips, washers, and sealants per manufacturer.",
            "brackets_plates": "Ridge caps, eave trims, closures, base trim, corner trim, flashing, and compatible panel clips.",
            "status": "Concept placeholder",
        },
    ]

    brace_members = [member for member in members if "bracing" in member.role.lower() or "brace" in member.role.lower()]
    grouped: dict[str, dict[str, object]] = {}
    for member in brace_members:
        rule = select_brace_rule(member)
        angle = member_angle_to_horizontal(member)
        key = rule.rule_id
        row = grouped.setdefault(
            key,
            {
                "detail": f"B-{rule.rule_id}",
                "applies_to": 0,
                "primary_members": f"{rule.preferred_section} selected by {angle:.1f} degree brace angle",
                "bolts": f"{rule.bolts_per_end} per end, {rule.bolt_spec}",
                "welds": rule.weld_detail,
                "brackets_plates": rule.connection_plate,
                "status": rule.status,
            },
        )
        row["applies_to"] = int(row["applies_to"]) + 1
    for row in grouped.values():
        row["applies_to"] = f"{row['applies_to']} brace members"
        rows.append(row)
    return rows


def face_normal(a: tuple[float, float, float], b: tuple[float, float, float], c: tuple[float, float, float]) -> tuple[float, float, float]:
    return vec_norm(vec_cross(vec_sub(b, a), vec_sub(c, a)))


def export_stl(package: ModelPackage) -> bytes:
    lines = ["solid steel_structure"]
    for face in package.faces:
        a, b, c = (package.vertices[index] for index in face)
        n = face_normal(a, b, c)
        lines.append(f"  facet normal {n[0]:.6f} {n[1]:.6f} {n[2]:.6f}")
        lines.append("    outer loop")
        for vertex in (a, b, c):
            lines.append(f"      vertex {vertex[0]:.6f} {vertex[1]:.6f} {vertex[2]:.6f}")
        lines.append("    endloop")
        lines.append("  endfacet")
    lines.append("endsolid steel_structure")
    return "\n".join(lines).encode("utf-8")


def export_obj(package: ModelPackage) -> bytes:
    lines = ["# AI Steel Structure conceptual OBJ"]
    for vertex in package.vertices:
        lines.append(f"v {vertex[0]:.6f} {vertex[1]:.6f} {vertex[2]:.6f}")
    for face in package.faces:
        lines.append(f"f {face[0] + 1} {face[1] + 1} {face[2] + 1}")
    return "\n".join(lines).encode("utf-8")


def export_json(package: ModelPackage) -> bytes:
    payload = {
        "app_version": APP_VERSION,
        "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "spec": spec_to_dict(package.spec),
        "warnings": package.warnings,
        "members": [
            {
                "name": member.name,
                "role": member.role,
                "section": member.section_id,
                "start": member.start,
                "end": member.end,
                "size_m": member.size_m,
                "length_m": round(member.length_m, 3),
                "estimated_weight_kg": round(member.steel_weight_kg, 1),
            }
            for member in package.members
        ],
        "bom": package.bom_rows,
        "connections": package.connection_rows,
        "section_catalog_used": {key: asdict(value) for key, value in SECTION_CATALOG.items()},
        "cladding_catalog_used": {key: asdict(value) for key, value in CLADDING_CATALOG.items()},
    }
    return json.dumps(payload, indent=2).encode("utf-8")


def export_bom_csv(package: ModelPackage) -> bytes:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["role", "section", "profile", "depth_m", "quantity", "total_length_m", "estimated_weight_kg"])
    writer.writeheader()
    writer.writerows(package.bom_rows)
    return output.getvalue().encode("utf-8")


def export_connections_csv(package: ModelPackage) -> bytes:
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["detail", "applies_to", "primary_members", "bolts", "welds", "brackets_plates", "status"],
    )
    writer.writeheader()
    writer.writerows(package.connection_rows)
    return output.getvalue().encode("utf-8")


def dxf_header() -> list[str]:
    return ["0", "SECTION", "2", "HEADER", "0", "ENDSEC", "0", "SECTION", "2", "ENTITIES"]


def dxf_footer() -> list[str]:
    return ["0", "ENDSEC", "0", "EOF"]


def dxf_line(layer: str, a: tuple[float, float], b: tuple[float, float]) -> list[str]:
    return [
        "0",
        "LINE",
        "8",
        layer,
        "10",
        f"{a[0]:.3f}",
        "20",
        f"{a[1]:.3f}",
        "30",
        "0",
        "11",
        f"{b[0]:.3f}",
        "21",
        f"{b[1]:.3f}",
        "31",
        "0",
    ]


def dxf_text(layer: str, at: tuple[float, float], text: str, height: float = 0.45) -> list[str]:
    return [
        "0",
        "TEXT",
        "8",
        layer,
        "10",
        f"{at[0]:.3f}",
        "20",
        f"{at[1]:.3f}",
        "30",
        "0",
        "40",
        f"{height:.3f}",
        "1",
        text,
    ]


def export_dxf(package: ModelPackage) -> bytes:
    spec = package.spec
    half_l = spec.length_m / 2
    half_w = spec.width_m / 2
    xs = x_positions(spec)
    roof_option = get_cladding_option(spec.roof_sheet_option)
    wall_option = get_cladding_option(spec.wall_sheet_option)
    purlin_ys: list[float] = []
    if spec.include_roof_purlins:
        purlin_count = max(3, min(9, int(round(spec.width_m / 3))))
        for index in range(1, purlin_count):
            y = -half_w + spec.width_m * index / purlin_count
            if abs(y) >= 0.01 or spec.roof_style != "Gable":
                purlin_ys.append(y)
    girt_zs: list[float] = []
    if spec.include_wall_girts:
        girt_levels = max(2, min(6, int(round(spec.eave_height_m / 2.5))))
        girt_zs = [spec.eave_height_m * level / (girt_levels + 1) for level in range(1, girt_levels + 1)]
    lines = dxf_header()

    plan_offset = (0.0, 0.0)
    elev_offset = (0.0, -(spec.width_m + spec.eave_height_m + 8))
    section_offset = (spec.length_m + 12, 0.0)

    plan = [(-half_l, -half_w), (half_l, -half_w), (half_l, half_w), (-half_l, half_w), (-half_l, -half_w)]
    for a, b in zip(plan, plan[1:]):
        lines.extend(dxf_line("PLAN_OUTLINE", a, b))
    for x in xs:
        lines.extend(dxf_line("FRAME_LINES", (x, -half_w), (x, half_w)))
    for y in purlin_ys:
        lines.extend(dxf_line("ROOF_PURLINS", (-half_l, y), (half_l, y)))
    for x in spaced_values(-half_l, half_l, roof_option.coverage_width_m, 120):
        lines.extend(dxf_line("ROOF_PANEL_SEAMS", (x, -half_w), (x, half_w)))
    if spec.include_bracing:
        bay = spec.length_m / max(spec.bay_count, 1)
        lines.extend(dxf_line("BRACING", (-half_l, -half_w), (-half_l + bay, half_w)))
        lines.extend(dxf_line("BRACING", (-half_l + bay, -half_w), (-half_l, half_w)))
        lines.extend(dxf_line("BRACING", (half_l - bay, -half_w), (half_l, half_w)))
        lines.extend(dxf_line("BRACING", (half_l, -half_w), (half_l - bay, half_w)))
    lines.extend(dxf_text("NOTES", (-half_l, half_w + 2), f"PLAN - {spec.length_m:g}m x {spec.width_m:g}m"))
    lines.extend(dxf_text("NOTES", (-half_l, half_w + 3.2), f"Roof panel: {roof_option.display_name}", 0.32))

    z0 = elev_offset[1]
    elevation = [(-half_l, z0), (half_l, z0), (half_l, z0 + spec.eave_height_m), (-half_l, z0 + spec.eave_height_m), (-half_l, z0)]
    for a, b in zip(elevation, elevation[1:]):
        lines.extend(dxf_line("SIDE_ELEVATION", a, b))
    for x in xs:
        lines.extend(dxf_line("FRAME_LINES", (x, z0), (x, z0 + spec.eave_height_m)))
    for z in girt_zs:
        lines.extend(dxf_line("WALL_GIRTS", (-half_l, z0 + z), (half_l, z0 + z)))
    for x in spaced_values(-half_l, half_l, wall_option.coverage_width_m, 120):
        lines.extend(dxf_line("WALL_PANEL_SEAMS", (x, z0), (x, z0 + spec.eave_height_m)))
    if spec.include_bracing and len(xs) >= 2:
        lines.extend(dxf_line("BRACING", (xs[0], z0 + 0.4), (xs[1], z0 + spec.eave_height_m - 0.4)))
        lines.extend(dxf_line("BRACING", (xs[1], z0 + 0.4), (xs[0], z0 + spec.eave_height_m - 0.4)))
        lines.extend(dxf_line("BRACING", (xs[-2], z0 + 0.4), (xs[-1], z0 + spec.eave_height_m - 0.4)))
        lines.extend(dxf_line("BRACING", (xs[-1], z0 + 0.4), (xs[-2], z0 + spec.eave_height_m - 0.4)))
    lines.extend(dxf_text("NOTES", (-half_l, z0 + spec.eave_height_m + 2), "SIDE ELEVATION"))
    lines.extend(dxf_text("NOTES", (-half_l, z0 + spec.eave_height_m + 3.2), f"Wall panel: {wall_option.display_name}", 0.32))

    sx = section_offset[0]
    left = (sx - half_w, 0)
    right = (sx + half_w, 0)
    left_eave = (sx - half_w, spec.eave_height_m)
    right_eave = (sx + half_w, roof_z(spec, half_w))
    if spec.roof_style == "Gable":
        apex = (sx, roof_z(spec, 0))
        section_points = [left, left_eave, apex, right_eave, right]
    else:
        section_points = [left, left_eave, right_eave, right]
    for a, b in zip(section_points, section_points[1:]):
        lines.extend(dxf_line("CROSS_SECTION", a, b))
    lines.extend(dxf_line("CROSS_SECTION", right, left))
    for y in purlin_ys:
        px = sx + y
        pz = roof_z(spec, y)
        lines.extend(dxf_line("ROOF_PURLINS", (px - 0.25, pz), (px + 0.25, pz)))
    for z in girt_zs:
        lines.extend(dxf_line("WALL_GIRTS", (sx - half_w - 0.25, z), (sx - half_w + 0.25, z)))
        lines.extend(dxf_line("WALL_GIRTS", (sx + half_w - 0.25, z), (sx + half_w + 0.25, z)))
    lines.extend(dxf_text("CONNECTION_NOTES", (sx - half_w, -1.3), f"C1 base plates | C2 eave plates | C3 ridge splice | C4 purlin clips | C5 girt clips", 0.25))
    lines.extend(dxf_text("NOTES", (sx - half_w, max(point[1] for point in section_points) + 2), "CROSS SECTION"))

    note_x = section_offset[0]
    note_y = -(spec.width_m + spec.eave_height_m + 8)
    lines.extend(dxf_text("CONNECTION_NOTES", (note_x, note_y + 10), "CONCEPT CONNECTION SCHEDULE - ENGINEER BEFORE CONSTRUCTION", 0.38))
    for index, row in enumerate(package.connection_rows[:6]):
        text = f"{row['detail']}: {row['primary_members']} | {row['bolts']}"
        lines.extend(dxf_text("CONNECTION_NOTES", (note_x, note_y + 8 - index * 1.0), text[:220], 0.26))

    lines.extend(dxf_footer())
    return "\n".join(lines).encode("utf-8")


def svg_line(a: tuple[float, float], b: tuple[float, float], scale: float, offset: tuple[float, float], klass: str = "line") -> str:
    x1, y1 = a[0] * scale + offset[0], -a[1] * scale + offset[1]
    x2, y2 = b[0] * scale + offset[0], -b[1] * scale + offset[1]
    return f'<line class="{klass}" x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" />'


def svg_point(point: tuple[float, float], scale: float, offset: tuple[float, float]) -> tuple[float, float]:
    return (point[0] * scale + offset[0], -point[1] * scale + offset[1])


def svg_text(text: object, x: float, y: float, klass: str = "small", anchor: str = "start") -> str:
    return f'<text class="{klass}" x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}">{html.escape(str(text))}</text>'


def svg_circle(x: float, y: float, radius: float, klass: str = "callout") -> str:
    return f'<circle class="{klass}" cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" />'


def svg_rect(x: float, y: float, width: float, height: float, klass: str = "panel", rx: float = 12) -> str:
    return f'<rect class="{klass}" x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{height:.1f}" rx="{rx:.1f}" />'


def svg_dim(x1: float, y1: float, x2: float, y2: float, text: str, offset: float = 20, vertical: bool = False) -> list[str]:
    if vertical:
        dim_x = x1 + offset
        return [
            f'<line class="dim" x1="{dim_x:.1f}" y1="{y1:.1f}" x2="{dim_x:.1f}" y2="{y2:.1f}" />',
            f'<line class="dim" x1="{x1:.1f}" y1="{y1:.1f}" x2="{dim_x:.1f}" y2="{y1:.1f}" />',
            f'<line class="dim" x1="{x2:.1f}" y1="{y2:.1f}" x2="{dim_x:.1f}" y2="{y2:.1f}" />',
            svg_text(text, dim_x + (6 if offset > 0 else -6), (y1 + y2) / 2, "dimtext", "start" if offset > 0 else "end"),
        ]
    dim_y = y1 + offset
    return [
        f'<line class="dim" x1="{x1:.1f}" y1="{dim_y:.1f}" x2="{x2:.1f}" y2="{dim_y:.1f}" />',
        f'<line class="dim" x1="{x1:.1f}" y1="{y1:.1f}" x2="{x1:.1f}" y2="{dim_y:.1f}" />',
        f'<line class="dim" x1="{x2:.1f}" y1="{y2:.1f}" x2="{x2:.1f}" y2="{dim_y:.1f}" />',
        svg_text(text, (x1 + x2) / 2, dim_y - 6 if offset < 0 else dim_y + 16, "dimtext", "middle"),
    ]


def export_svg(package: ModelPackage) -> bytes:
    spec = package.spec
    scale = min(7.0, 620 / max(spec.length_m + spec.width_m + 20, 1))
    half_l = spec.length_m / 2
    half_w = spec.width_m / 2
    width = 1280
    height = 1180
    xs = x_positions(spec)
    roof_option = get_cladding_option(spec.roof_sheet_option)
    wall_option = get_cladding_option(spec.wall_sheet_option)
    purlin_ys: list[float] = []
    if spec.include_roof_purlins:
        purlin_count = max(3, min(9, int(round(spec.width_m / 3))))
        for index in range(1, purlin_count):
            y = -half_w + spec.width_m * index / purlin_count
            if abs(y) >= 0.01 or spec.roof_style != "Gable":
                purlin_ys.append(y)
    girt_zs: list[float] = []
    if spec.include_wall_girts:
        girt_levels = max(2, min(6, int(round(spec.eave_height_m / 2.5))))
        girt_zs = [spec.eave_height_m * level / (girt_levels + 1) for level in range(1, girt_levels + 1)]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<style>",
        ".bg{fill:#f5f5f7}.title{font:800 25px Arial,sans-serif;fill:#101114}.subtitle{font:13px Arial,sans-serif;fill:#4f5562}.label{font:700 14px Arial,sans-serif;fill:#101114}.small{font:12px Arial,sans-serif;fill:#101114}.dimtext{font:11px Consolas,monospace;fill:#4f5562}.line{stroke:#101114;stroke-width:2;fill:none}.grid{stroke:#9aa5b1;stroke-width:1;stroke-dasharray:5 5}.secondary{stroke:#64748b;stroke-width:1.3;fill:none}.cladding{stroke:#0071e3;stroke-width:1.1;stroke-dasharray:2 4;fill:none}.brace{stroke:#b45309;stroke-width:1.7}.dim{stroke:#4f5562;stroke-width:1;fill:none}.panel{fill:#fff;stroke:#d8dee6;stroke-width:1.2}.callout{fill:#fff;stroke:#0071e3;stroke-width:1.5}.bolt{fill:#101114}.plate{fill:none;stroke:#101114;stroke-width:1.5}",
        "</style>",
        f'<rect class="bg" x="0" y="0" width="{width}" height="{height}" />',
        svg_text(f"{spec.project_name} - Concept Steel Layout", 42, 48, "title"),
        svg_text(
            f"{spec.building_type} | {spec.length_m:g}m L x {spec.width_m:g}m W x {spec.eave_height_m:g}m eave | {spec.roof_style} roof | Roof panel: {roof_option.display_name} | Wall panel: {wall_option.display_name}",
            42,
            76,
            "subtitle",
        ),
    ]

    plan_offset = (315, 225)
    plan = [(-half_l, -half_w), (half_l, -half_w), (half_l, half_w), (-half_l, half_w), (-half_l, -half_w)]
    parts.append(svg_text("Plan with grid, roof panels, purlins, and bracing", 42, 122, "label"))
    for a, b in zip(plan, plan[1:]):
        parts.append(svg_line(a, b, scale, plan_offset))
    for grid_index, x in enumerate(xs, start=1):
        parts.append(svg_line((x, -half_w), (x, half_w), scale, plan_offset, "grid"))
        sx, sy = svg_point((x, half_w), scale, plan_offset)
        parts.append(svg_text(grid_index, sx, sy - 10, "dimtext", "middle"))
    for y in purlin_ys:
        parts.append(svg_line((-half_l, y), (half_l, y), scale, plan_offset, "secondary"))
    for x in spaced_values(-half_l, half_l, roof_option.coverage_width_m, 80):
        parts.append(svg_line((x, -half_w), (x, half_w), scale, plan_offset, "cladding"))

    elev_offset = (300, 470)
    parts.append(svg_text("Side elevation with girts, cladding seams, and bracing", 42, 372, "label"))
    elevation = [(-half_l, 0), (half_l, 0), (half_l, spec.eave_height_m), (-half_l, spec.eave_height_m), (-half_l, 0)]
    for a, b in zip(elevation, elevation[1:]):
        parts.append(svg_line(a, b, scale, elev_offset))
    for grid_index, x in enumerate(xs, start=1):
        parts.append(svg_line((x, 0), (x, spec.eave_height_m), scale, elev_offset, "grid"))
        sx, sy = svg_point((x, 0), scale, elev_offset)
        parts.append(svg_text(grid_index, sx, sy + 18, "dimtext", "middle"))
    for z in girt_zs:
        parts.append(svg_line((-half_l, z), (half_l, z), scale, elev_offset, "secondary"))
    for x in spaced_values(-half_l, half_l, wall_option.coverage_width_m, 80):
        parts.append(svg_line((x, 0), (x, spec.eave_height_m), scale, elev_offset, "cladding"))

    if spec.include_bracing:
        parts.append(svg_line((-half_l, -half_w), (-half_l + spec.length_m / spec.bay_count, half_w), scale, plan_offset, "brace"))
        parts.append(svg_line((-half_l + spec.length_m / spec.bay_count, -half_w), (-half_l, half_w), scale, plan_offset, "brace"))
        parts.append(svg_line((half_l - spec.length_m / spec.bay_count, -half_w), (half_l, half_w), scale, plan_offset, "brace"))
        parts.append(svg_line((half_l, -half_w), (half_l - spec.length_m / spec.bay_count, half_w), scale, plan_offset, "brace"))
        if len(xs) >= 2:
            parts.append(svg_line((xs[0], 0.4), (xs[1], spec.eave_height_m - 0.4), scale, elev_offset, "brace"))
            parts.append(svg_line((xs[1], 0.4), (xs[0], spec.eave_height_m - 0.4), scale, elev_offset, "brace"))
            parts.append(svg_line((xs[-2], 0.4), (xs[-1], spec.eave_height_m - 0.4), scale, elev_offset, "brace"))
            parts.append(svg_line((xs[-1], 0.4), (xs[-2], spec.eave_height_m - 0.4), scale, elev_offset, "brace"))

    px1, py1 = svg_point((-half_l, -half_w), scale, plan_offset)
    px2, py2 = svg_point((half_l, -half_w), scale, plan_offset)
    px3, py3 = svg_point((half_l, half_w), scale, plan_offset)
    parts.extend(svg_dim(px1, py1, px2, py2, f"{spec.length_m:g} m overall length", 28))
    parts.extend(svg_dim(px2, py2, px3, py3, f"{spec.width_m:g} m span", 28, vertical=True))
    ex1, ey1 = svg_point((-half_l, 0), scale, elev_offset)
    ex2, ey2 = svg_point((half_l, 0), scale, elev_offset)
    ex3, ey3 = svg_point((-half_l, spec.eave_height_m), scale, elev_offset)
    parts.extend(svg_dim(ex1, ey1, ex2, ey2, f"{spec.length_m:g} m", 26))
    parts.extend(svg_dim(ex1, ey1, ex3, ey3, f"{spec.eave_height_m:g} m eave", -28, vertical=True))

    section_offset = (930, 390)
    section_scale = scale * 1.35
    parts.append(svg_text("Typical frame section", 720, 122, "label"))
    left = (-half_w, 0)
    right = (half_w, 0)
    left_eave = (-half_w, spec.eave_height_m)
    right_eave = (half_w, roof_z(spec, half_w))
    if spec.roof_style == "Gable":
        apex = (0, roof_z(spec, 0))
        section = [left, left_eave, apex, right_eave, right, left]
    else:
        section = [left, left_eave, right_eave, right, left]
    for a, b in zip(section, section[1:]):
        parts.append(svg_line(a, b, section_scale, section_offset))
    for y in purlin_ys:
        sx, sy = svg_point((y, roof_z(spec, y)), section_scale, section_offset)
        parts.append(svg_rect(sx - 4, sy - 4, 8, 8, "secondary", 2))
    for z in girt_zs:
        for y in (-half_w, half_w):
            sx, sy = svg_point((y, z), section_scale, section_offset)
            parts.append(svg_rect(sx - 4, sy - 4, 8, 8, "secondary", 2))
    sec_left_base = svg_point(left, section_scale, section_offset)
    sec_right_base = svg_point(right, section_scale, section_offset)
    sec_left_eave = svg_point(left_eave, section_scale, section_offset)
    sec_right_eave = svg_point(right_eave, section_scale, section_offset)
    parts.extend(svg_dim(sec_left_base[0], sec_left_base[1], sec_right_base[0], sec_right_base[1], f"{spec.width_m:g} m clear span", 26))
    parts.extend(svg_dim(sec_left_base[0], sec_left_base[1], sec_left_eave[0], sec_left_eave[1], f"{spec.eave_height_m:g} m", -32, vertical=True))
    if spec.roof_style == "Gable":
        peak = svg_point((0, roof_z(spec, 0)), section_scale, section_offset)
        parts.extend(svg_dim(peak[0], sec_left_base[1], peak[0], peak[1], f"{roof_z(spec, 0):.2f} m peak", 28, vertical=True))
        parts.append(svg_circle(peak[0], peak[1], 12))
        parts.append(svg_text("C3", peak[0], peak[1] + 4, "dimtext", "middle"))
    for code, point in [("C1", sec_left_base), ("C1", sec_right_base), ("C2", sec_left_eave), ("C2", sec_right_eave)]:
        parts.append(svg_circle(point[0], point[1], 12))
        parts.append(svg_text(code, point[0], point[1] + 4, "dimtext", "middle"))
    parts.append(svg_text(f"Roof pitch: {spec.roof_pitch_deg:g} deg | primary: {choose_primary_section(spec)} | purlin: {choose_purlin_section(spec, 'roof')}", 720, 146, "small"))

    parts.append(svg_rect(42, 690, 1188, 390, "panel", 18))
    parts.append(svg_text("Concept connection details and schedule - engineer before construction", 62, 722, "label"))
    for x, title in zip([70, 260, 450, 640], ["C1 base plate", "C2 eave plate", "C4 purlin clip", "C6 brace gusset"]):
        parts.append(svg_text(title, x, 748, "small"))
    parts.append(svg_rect(92, 770, 72, 54, "plate", 4))
    for bx, by in [(108, 784), (148, 784), (108, 810), (148, 810)]:
        parts.append(svg_circle(bx, by, 3.5, "bolt"))
    parts.append('<line class="line" x1="128" y1="770" x2="128" y2="742" />')
    parts.append(svg_rect(292, 768, 12, 62, "plate", 2))
    parts.append('<line class="line" x1="304" y1="800" x2="354" y2="760" />')
    parts.append('<line class="line" x1="304" y1="800" x2="354" y2="842" />')
    for by in [782, 798, 814]:
        parts.append(svg_circle(298, by, 3, "bolt"))
    parts.append('<line class="line" x1="462" y1="810" x2="540" y2="810" />')
    parts.append(svg_rect(496, 776, 24, 34, "plate", 3))
    parts.append('<line class="secondary" x1="484" y1="790" x2="548" y2="790" />')
    for bx in [504, 514]:
        parts.append(svg_circle(bx, 792, 3, "bolt"))
    parts.append('<polygon class="plate" points="670,828 734,828 670,766" />')
    parts.append('<line class="brace" x1="676" y1="820" x2="732" y2="768" />')
    for point in [(684, 814), (700, 800)]:
        parts.append(svg_circle(point[0], point[1], 3, "bolt"))

    y_text = 870
    for row in package.connection_rows[:7]:
        detail = html.escape(str(row["detail"]))
        members = html.escape(str(row["primary_members"]))
        bolts = html.escape(str(row["bolts"]).replace("Typical: ", ""))
        parts.append(f'<text class="small" x="62" y="{y_text}">{detail}: {members}</text>')
        y_text += 18
        parts.append(f'<text class="dimtext" x="82" y="{y_text}">Bolts/plates: {bolts[:170]}</text>')
        y_text += 22

    warning = "Concept only. Engineering, code checks, connection design, and foundations are required before construction."
    parts.append(svg_text(warning, 42, 1125, "label"))
    parts.append("</svg>")
    return "\n".join(parts).encode("utf-8")


def quad_mesh(points: list[tuple[float, float, float]]) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    return points, [(0, 1, 2), (0, 2, 3)]


def triangle_mesh(points: list[tuple[float, float, float]]) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    return points, [(0, 1, 2)]


def cladding_meshes(spec: BuildingSpec) -> tuple[
    list[tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]],
    list[tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]],
]:
    half_l = spec.length_m / 2
    half_w = spec.width_m / 2
    roof_meshes: list[tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]] = []
    wall_meshes: list[tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]] = []

    if spec.roof_style == "Gable":
        roof_meshes.append(
            quad_mesh(
                [
                    (-half_l, -half_w, roof_z(spec, -half_w)),
                    (half_l, -half_w, roof_z(spec, -half_w)),
                    (half_l, 0, roof_z(spec, 0)),
                    (-half_l, 0, roof_z(spec, 0)),
                ]
            )
        )
        roof_meshes.append(
            quad_mesh(
                [
                    (-half_l, 0, roof_z(spec, 0)),
                    (half_l, 0, roof_z(spec, 0)),
                    (half_l, half_w, roof_z(spec, half_w)),
                    (-half_l, half_w, roof_z(spec, half_w)),
                ]
            )
        )
    else:
        roof_meshes.append(
            quad_mesh(
                [
                    (-half_l, -half_w, roof_z(spec, -half_w)),
                    (half_l, -half_w, roof_z(spec, -half_w)),
                    (half_l, half_w, roof_z(spec, half_w)),
                    (-half_l, half_w, roof_z(spec, half_w)),
                ]
            )
        )

    wall_meshes.extend(
        [
            quad_mesh([(-half_l, -half_w, 0), (half_l, -half_w, 0), (half_l, -half_w, spec.eave_height_m), (-half_l, -half_w, spec.eave_height_m)]),
            quad_mesh([(-half_l, half_w, 0), (half_l, half_w, 0), (half_l, half_w, spec.eave_height_m), (-half_l, half_w, spec.eave_height_m)]),
        ]
    )

    if spec.roof_style == "Gable":
        for x in (-half_l, half_l):
            wall_meshes.append(quad_mesh([(x, -half_w, 0), (x, half_w, 0), (x, half_w, spec.eave_height_m), (x, -half_w, spec.eave_height_m)]))
            wall_meshes.append(triangle_mesh([(x, -half_w, spec.eave_height_m), (x, half_w, spec.eave_height_m), (x, 0, roof_z(spec, 0))]))
    else:
        for x in (-half_l, half_l):
            wall_meshes.append(quad_mesh([(x, -half_w, 0), (x, half_w, 0), (x, half_w, roof_z(spec, half_w)), (x, -half_w, roof_z(spec, -half_w))]))

    return roof_meshes, wall_meshes


def point_key(point: tuple[float, float, float], precision: int = 2) -> tuple[float, float, float]:
    return (round(point[0], precision), round(point[1], precision), round(point[2], precision))


def build_connection_visuals(package: ModelPackage) -> tuple[
    list[tuple[float, float, float]],
    list[tuple[int, int, int]],
    list[tuple[float, float, float]],
    list[str],
]:
    spec = package.spec
    xs = x_positions(spec)
    scale = clamp(min(spec.length_m, spec.width_m) / 58, 0.14, 0.52)
    plate_thick = clamp(scale * 0.12, 0.025, 0.065)
    plate_meshes: list[tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]] = []
    bolt_points: list[tuple[float, float, float]] = []
    bolt_labels: list[str] = []
    seen_plates: set[tuple[str, tuple[float, float, float]]] = set()

    def add_bolts(center: tuple[float, float, float], spacing: float, label: str, count: int = 4) -> None:
        if count <= 2:
            offsets = [(-spacing / 2, 0.0, 0.0), (spacing / 2, 0.0, 0.0)]
        else:
            offsets = [
                (-spacing / 2, -spacing / 2, 0.0),
                (spacing / 2, -spacing / 2, 0.0),
                (spacing / 2, spacing / 2, 0.0),
                (-spacing / 2, spacing / 2, 0.0),
            ]
        for offset in offsets:
            bolt_points.append((center[0] + offset[0], center[1] + offset[1], center[2] + offset[2]))
            bolt_labels.append(label)

    def add_plate(center: tuple[float, float, float], dims: tuple[float, float, float], label: str, bolt_count: int = 4) -> None:
        key = (label, point_key(center))
        if key in seen_plates:
            return
        seen_plates.add(key)
        plate_meshes.append(axis_aligned_box_mesh(center, dims))
        add_bolts((center[0], center[1], center[2] + dims[2] / 2 + 0.015), max(dims[0], dims[1]) * 0.55, label, bolt_count)

    base_dims = (scale * 1.7, scale * 1.7, plate_thick)
    frame_plate_dims = (plate_thick, scale * 1.25, scale * 1.25)
    clip_dims = (plate_thick, scale * 0.55, scale * 0.45)
    girt_clip_dims = (plate_thick, scale * 0.45, scale * 0.45)
    gusset_dims = (scale * 0.9, scale * 0.12, scale * 0.9)

    for member in package.members:
        if member.role == "Primary columns":
            bottom = member.start if member.start[2] <= member.end[2] else member.end
            add_plate((bottom[0], bottom[1], plate_thick / 2), base_dims, "C1 base plate and anchor rods", 4)
        if member.role == "Primary rafters":
            for point in (member.start, member.end):
                add_plate(point, frame_plate_dims, "C2/C3 primary frame plate", 4)
        if member.role in {"Cross bracing", "Roof bracing", "Knee bracing"}:
            rule = select_brace_rule(member) if "brace" in member.role.lower() or "bracing" in member.role.lower() else None
            label = f"Brace gusset - {rule.connection_plate}" if rule else "Brace gusset plate"
            add_plate(member.start, gusset_dims, label, 2)
            add_plate(member.end, gusset_dims, label, 2)

    for member in package.members:
        if member.role == "Roof purlins":
            y = member.start[1]
            for x in xs:
                add_plate((x, y, roof_z(spec, y)), clip_dims, "C4 purlin clip with bolts", 2)
        elif member.role == "Wall girts":
            y = member.start[1]
            z = member.start[2]
            for x in xs:
                add_plate((x, y, z), girt_clip_dims, "C5 wall girt clip with bolts", 2)

    vertices, faces = combine_meshes(plate_meshes)
    return vertices, faces, bolt_points, bolt_labels


def member_layer(role: str) -> str:
    if role in {"Primary columns", "Primary rafters"}:
        return "Primary steel"
    if "brace" in role.lower() or "bracing" in role.lower():
        return "Bracing"
    return "Secondary steel"


def layer_enabled(layers: set[str], layer: str) -> bool:
    return layer in layers


def spaced_values(start: float, end: float, spacing: float, max_count: int = 120) -> list[float]:
    spacing = max(spacing, 0.3)
    count = min(max_count, max(1, int(math.floor((end - start) / spacing)) + 1))
    if count <= 1:
        return [start]
    actual_spacing = (end - start) / (count - 1)
    return [start + actual_spacing * index for index in range(count)]


def cladding_line_sets(spec: BuildingSpec) -> list[dict[str, object]]:
    half_l = spec.length_m / 2
    half_w = spec.width_m / 2
    roof_option = get_cladding_option(spec.roof_sheet_option)
    wall_option = get_cladding_option(spec.wall_sheet_option)
    z_offset = 0.06
    sets: list[dict[str, object]] = []

    roof_xs = spaced_values(-half_l, half_l, roof_option.coverage_width_m, 150)
    roof_x: list[float | None] = []
    roof_y: list[float | None] = []
    roof_zs: list[float | None] = []
    for x in roof_xs:
        if spec.roof_style == "Gable":
            segments = [(-half_w, 0.0), (0.0, half_w)]
        else:
            segments = [(-half_w, half_w)]
        for y0, y1 in segments:
            roof_x.extend([x, x, None])
            roof_y.extend([y0, y1, None])
            roof_zs.extend([roof_z(spec, y0) + z_offset, roof_z(spec, y1) + z_offset, None])
    sets.append(
        {
            "name": f"roof panel seams - {roof_option.option_id}",
            "x": roof_x,
            "y": roof_y,
            "z": roof_zs,
            "color": "#0f172a",
            "width": 1.4,
            "dash": "dot",
        }
    )

    trim_x: list[float | None] = []
    trim_y: list[float | None] = []
    trim_z: list[float | None] = []
    for y in (-half_w, half_w):
        trim_x.extend([-half_l, half_l, None])
        trim_y.extend([y, y, None])
        trim_z.extend([roof_z(spec, y) + z_offset * 1.4, roof_z(spec, y) + z_offset * 1.4, None])
    if spec.roof_style == "Gable":
        trim_x.extend([-half_l, half_l, None])
        trim_y.extend([0.0, 0.0, None])
        trim_z.extend([roof_z(spec, 0) + z_offset * 1.6, roof_z(spec, 0) + z_offset * 1.6, None])
    sets.append({"name": "ridge and eave trim lines", "x": trim_x, "y": trim_y, "z": trim_z, "color": "#0055b8", "width": 4, "dash": "solid"})

    wall_spacing = wall_option.coverage_width_m
    wall_x: list[float | None] = []
    wall_y: list[float | None] = []
    wall_zs: list[float | None] = []
    for x in spaced_values(-half_l, half_l, wall_spacing, 150):
        for y in (-half_w, half_w):
            wall_x.extend([x, x, None])
            wall_y.extend([y, y, None])
            wall_zs.extend([0.0, spec.eave_height_m, None])
    for y in spaced_values(-half_w, half_w, wall_spacing, 80):
        for x in (-half_l, half_l):
            wall_x.extend([x, x, None])
            wall_y.extend([y, y, None])
            wall_zs.extend([0.0, roof_z(spec, y), None])
    sets.append(
        {
            "name": f"wall panel seams - {wall_option.option_id}",
            "x": wall_x,
            "y": wall_y,
            "z": wall_zs,
            "color": "#334155",
            "width": 1.2,
            "dash": "dot",
        }
    )
    return sets


def member_label_points(members: list[Member], max_labels: int = 48) -> tuple[list[float], list[float], list[float], list[str]]:
    labels: list[tuple[float, float, float, str]] = []
    seen: set[tuple[str, str]] = set()
    for member in members:
        key = (member.role, member.section_id)
        midpoint = (
            (member.start[0] + member.end[0]) / 2,
            (member.start[1] + member.end[1]) / 2,
            (member.start[2] + member.end[2]) / 2,
        )
        if key in seen and len(labels) >= 18:
            continue
        seen.add(key)
        labels.append((midpoint[0], midpoint[1], midpoint[2] + 0.25, f"{member.role}<br>{member.section_id}"))
        if len(labels) >= max_labels:
            break
    if not labels:
        return [], [], [], []
    xs, ys, zs, text = zip(*labels)
    return list(xs), list(ys), list(zs), list(text)


def plotly_camera_for_view(view: str) -> dict[str, object]:
    cameras = {
        "Top plan": {"eye": {"x": 0.0, "y": 0.0, "z": 2.7}, "up": {"x": 0, "y": 1, "z": 0}},
        "Front elevation": {"eye": {"x": 0.0, "y": -2.8, "z": 0.85}, "up": {"x": 0, "y": 0, "z": 1}},
        "End frame": {"eye": {"x": 2.8, "y": 0.0, "z": 0.85}, "up": {"x": 0, "y": 0, "z": 1}},
        "Low perspective": {"eye": {"x": 1.8, "y": -2.2, "z": 0.75}, "up": {"x": 0, "y": 0, "z": 1}},
        "Isometric": {"eye": {"x": 1.6, "y": -1.8, "z": 1.25}, "up": {"x": 0, "y": 0, "z": 1}},
    }
    return cameras.get(view, cameras["Isometric"])


def create_plotly_figure(package: ModelPackage, layers: set[str] | None = None, view: str = "Isometric"):
    if go is None:
        return None

    layers = set(layers or DEFAULT_VISUALIZER_LAYERS)
    role_colors = {
        "Primary columns": "#2f4858",
        "Primary rafters": "#2f4858",
        "Eave struts": "#557c55",
        "Ridge beam": "#557c55",
        "Roof purlins": "#7c9a63",
        "Wall girts": "#819b9f",
        "Cross bracing": "#c26a3d",
        "Roof bracing": "#c26a3d",
        "Knee bracing": "#9f4f28",
    }

    spec = package.spec
    fig = go.Figure()

    if layer_enabled(layers, "Slab"):
        slab_vertices, slab_faces = axis_aligned_box_mesh(
            (0, 0, -spec.slab_thickness_m / 2),
            (spec.length_m, spec.width_m, spec.slab_thickness_m),
        )
        x, y, z = zip(*slab_vertices)
        i, j, k = zip(*slab_faces)
        fig.add_trace(
            go.Mesh3d(
                x=x,
                y=y,
                z=z,
                i=i,
                j=j,
                k=k,
                color="#c8c1b2",
                opacity=0.35,
                name="concrete slab",
                hoverinfo="skip",
            )
        )

    if layer_enabled(layers, "Cladding"):
        roof_meshes, wall_meshes = cladding_meshes(spec)
        roof_vertices, roof_faces = combine_meshes(roof_meshes)
        if roof_vertices and roof_faces:
            x, y, z = zip(*roof_vertices)
            i, j, k = zip(*roof_faces)
            roof_option = get_cladding_option(spec.roof_sheet_option)
            fig.add_trace(
                go.Mesh3d(
                    x=x,
                    y=y,
                    z=z,
                    i=i,
                    j=j,
                    k=k,
                    color="#d8b15f",
                    opacity=0.22,
                    flatshading=True,
                    name=f"roof sheets - {roof_option.display_name}",
                    hovertemplate=f"Roof sheets<br>{roof_option.display_name}<br>{roof_option.fastening_pattern}<extra></extra>",
                )
            )
        wall_vertices, wall_faces = combine_meshes(wall_meshes)
        if wall_vertices and wall_faces:
            x, y, z = zip(*wall_vertices)
            i, j, k = zip(*wall_faces)
            wall_option = get_cladding_option(spec.wall_sheet_option)
            fig.add_trace(
                go.Mesh3d(
                    x=x,
                    y=y,
                    z=z,
                    i=i,
                    j=j,
                    k=k,
                    color="#cfd9d2",
                    opacity=0.18,
                    flatshading=True,
                    name=f"wall sheets - {wall_option.display_name}",
                    hovertemplate=f"Wall cladding<br>{wall_option.display_name}<br>{wall_option.fastening_pattern}<extra></extra>",
                )
            )

    if layer_enabled(layers, "Panel seams"):
        for line_set in cladding_line_sets(spec):
            fig.add_trace(
                go.Scatter3d(
                    x=line_set["x"],
                    y=line_set["y"],
                    z=line_set["z"],
                    mode="lines",
                    line={"color": line_set["color"], "width": line_set["width"], "dash": line_set["dash"]},
                    name=str(line_set["name"]),
                    hoverinfo="skip",
                )
            )

    for role, section_id in sorted({(member.role, member.section_id) for member in package.members}):
        if not layer_enabled(layers, member_layer(role)):
            continue
        meshes = [member_mesh(member) for member in package.members if member.role == role and member.section_id == section_id]
        vertices, faces = combine_meshes(meshes)
        if not vertices or not faces:
            continue
        x, y, z = zip(*vertices)
        i, j, k = zip(*faces)
        fig.add_trace(
            go.Mesh3d(
                x=x,
                y=y,
                z=z,
                i=i,
                j=j,
                k=k,
                color=role_colors.get(role, "#445566"),
                opacity=1.0,
                flatshading=True,
                name=f"{role} profile - {section_id}",
                hovertemplate=f"{role}<br>{section_id}<extra></extra>",
            )
        )

    if layer_enabled(layers, "Connections") or layer_enabled(layers, "Bolts"):
        connection_vertices, connection_faces, bolt_points, bolt_labels = build_connection_visuals(package)
        if layer_enabled(layers, "Connections") and connection_vertices and connection_faces:
            x, y, z = zip(*connection_vertices)
            i, j, k = zip(*connection_faces)
            fig.add_trace(
                go.Mesh3d(
                    x=x,
                    y=y,
                    z=z,
                    i=i,
                    j=j,
                    k=k,
                    color="#d19831",
                    opacity=1.0,
                    flatshading=True,
                    name="connection plates, clips, and gussets",
                    hovertemplate="Connection plate / clip / gusset<extra></extra>",
                )
            )
        if layer_enabled(layers, "Bolts") and bolt_points:
            bx, by, bz = zip(*bolt_points)
            fig.add_trace(
                go.Scatter3d(
                    x=bx,
                    y=by,
                    z=bz,
                    mode="markers",
                    marker={"size": 3.2, "color": "#111111", "symbol": "circle"},
                    text=bolt_labels,
                    name="bolts and anchors",
                    hovertemplate="%{text}<extra></extra>",
                )
            )

    if layer_enabled(layers, "Member labels"):
        lx, ly, lz, text = member_label_points(package.members)
        if lx:
            fig.add_trace(
                go.Scatter3d(
                    x=lx,
                    y=ly,
                    z=lz,
                    mode="text",
                    text=text,
                    textfont={"color": "#101114", "size": 10},
                    name="member labels",
                    hoverinfo="skip",
                )
            )

    if layer_enabled(layers, "Centerlines"):
        for role, section_id in sorted({(member.role, member.section_id) for member in package.members}):
            if not layer_enabled(layers, member_layer(role)):
                continue
            xs: list[float | None] = []
            ys: list[float | None] = []
            zs: list[float | None] = []
            labels: list[str | None] = []
            for member in package.members:
                if member.role != role or member.section_id != section_id:
                    continue
                xs.extend([member.start[0], member.end[0], None])
                ys.extend([member.start[1], member.end[1], None])
                zs.extend([member.start[2], member.end[2], None])
                labels.extend([f"{member.role} | {member.section_id}", f"{member.name} | {member.section_id}", None])
            fig.add_trace(
                go.Scatter3d(
                    x=xs,
                    y=ys,
                    z=zs,
                    mode="lines",
                    line={"width": 3 if "Primary" in role else 2, "color": "#111111"},
                    name=f"{role} centerline - {section_id}",
                    text=labels,
                    hovertemplate="%{text}<extra></extra>",
                    showlegend=False,
                )
            )

    # Small origin/grid reference improves orientation in full-screen mode.
    fig.add_trace(
        go.Scatter3d(
            x=[-spec.length_m / 2, spec.length_m / 2, None, -spec.length_m / 2, -spec.length_m / 2],
            y=[-spec.width_m / 2, -spec.width_m / 2, None, -spec.width_m / 2, spec.width_m / 2],
            z=[0, 0, None, 0, 0],
            mode="lines",
            line={"color": "rgba(16,17,20,0.35)", "width": 2},
            name="plan reference edges",
            hoverinfo="skip",
            showlegend=False,
        )
    )

    camera = plotly_camera_for_view(view)
    fig.update_layout(
        height=610,
        margin={"l": 0, "r": 0, "t": 30, "b": 0},
        paper_bgcolor="rgba(0,0,0,0)",
        font={"color": "#111111"},
        scene={
            "xaxis_title": "Length (m)",
            "yaxis_title": "Width (m)",
            "zaxis_title": "Height (m)",
            "xaxis": {"color": "#111111", "gridcolor": "#d0d6de", "zerolinecolor": "#94a3b8"},
            "yaxis": {"color": "#111111", "gridcolor": "#d0d6de", "zerolinecolor": "#94a3b8"},
            "zaxis": {"color": "#111111", "gridcolor": "#d0d6de", "zerolinecolor": "#94a3b8"},
            "camera": camera,
            "aspectmode": "manual",
            "aspectratio": {
                "x": max(spec.length_m / max(spec.width_m, 1), 1),
                "y": 1,
                "z": max(spec.eave_height_m / max(spec.width_m, 1), 0.35),
            },
        },
        legend={"orientation": "h", "y": -0.05, "font": {"color": "#111111"}},
    )
    return fig


def render_metric(label: str, value: str, help_text: str | None = None) -> None:
    st.metric(label, value, help=help_text)


def init_state() -> None:
    if "spec" not in st.session_state:
        st.session_state.spec = spec_to_dict(BuildingSpec())
    if "prompt" not in st.session_state:
        st.session_state.prompt = DEFAULT_PROMPT
    if "extraction_notice" not in st.session_state:
        st.session_state.extraction_notice = None
    if "project_history" not in st.session_state:
        st.session_state.project_history = []
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = [
            {
                "role": "assistant",
                "content": "Describe the steel building you want. I will create the first rendition, then you can keep asking for changes in this same chat.",
            }
        ]
    if "ai_provider" not in st.session_state:
        st.session_state.ai_provider = os.getenv("AI_PROVIDER", "Ollama Local")
    if "ai_model" not in st.session_state:
        st.session_state.ai_model = os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)
    if "ollama_host" not in st.session_state:
        st.session_state.ollama_host = os.getenv("OLLAMA_HOST", DEFAULT_OLLAMA_HOST)
    if "openai_api_key" not in st.session_state:
        st.session_state.openai_api_key = os.getenv("OPENAI_API_KEY", "")
    if "gemini_api_key" not in st.session_state:
        st.session_state.gemini_api_key = os.getenv("GEMINI_API_KEY", "")


def current_ai_settings() -> tuple[str, str, str, str]:
    provider = st.session_state.get("ai_provider", "Ollama Local")
    model = st.session_state.get("ai_model", DEFAULT_OLLAMA_MODEL)
    ollama_host = st.session_state.get("ollama_host", DEFAULT_OLLAMA_HOST)
    api_key = ""
    if provider == "OpenAI":
        api_key = st.session_state.get("openai_api_key", "")
    elif provider == "Google Gemini":
        api_key = st.session_state.get("gemini_api_key", "")
    return provider, api_key, model, ollama_host


def load_css() -> None:
    st.markdown(
        """
        <style>
            @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
            :root {
                --bg: #f5f5f7;
                --bg-elevated: rgba(255, 255, 255, 0.76);
                --surface: #ffffff;
                --surface-soft: #fbfbfd;
                --surface-strong: rgba(255, 255, 255, 0.92);
                --text-primary: #101114;
                --text-secondary: #4f5562;
                --text-tertiary: #707887;
                --border: rgba(16, 17, 20, 0.08);
                --border-strong: rgba(16, 17, 20, 0.12);
                --shadow-lg: 0 30px 80px rgba(15, 23, 42, 0.12);
                --shadow-md: 0 20px 50px rgba(15, 23, 42, 0.08);
                --shadow-sm: 0 10px 30px rgba(15, 23, 42, 0.05);
                --accent: #0071e3;
                --accent-deep: #0055b8;
                --accent-soft: rgba(0, 113, 227, 0.10);
                --accent-soft-strong: rgba(0, 113, 227, 0.18);
                --radius-xl: 32px;
                --radius-lg: 24px;
                --radius-md: 18px;
                --radius-sm: 12px;
            }
            #MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"],
            [data-testid="stStatusWidget"], .stDeployButton {
                display: none !important;
                visibility: hidden !important;
            }
            .stApp {
                background:
                    radial-gradient(circle at top left, rgba(0, 113, 227, 0.14), transparent 28%),
                    radial-gradient(circle at top right, rgba(122, 139, 255, 0.12), transparent 24%),
                    linear-gradient(180deg, #f8f8fb 0%, #f4f5f7 54%, #eceef2 100%);
                color: var(--text-primary) !important;
                font-family: "Plus Jakarta Sans", sans-serif;
            }
            [data-testid="stHeader"] {
                background: rgba(245, 245, 247, 0.78);
                backdrop-filter: blur(18px);
                border-bottom: 1px solid rgba(16, 17, 20, 0.06);
                color: var(--text-primary) !important;
            }
            [data-testid="stSidebar"] {
                background: rgba(255, 255, 255, 0.78) !important;
                border-right: 1px solid var(--border);
                color: var(--text-primary) !important;
                backdrop-filter: blur(18px);
            }
            .stApp,
            [data-testid="stMarkdownContainer"],
            [data-testid="stMarkdownContainer"] *,
            .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6,
            [data-testid="stSidebar"],
            [data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
            [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] * {
                color: var(--text-primary) !important;
                font-family: "Plus Jakarta Sans", sans-serif;
            }
            [data-testid="stMarkdownContainer"] p,
            [data-testid="stMarkdownContainer"] li {
                color: var(--text-secondary) !important;
                font-size: 1rem;
                line-height: 1.72;
            }
            [data-testid="stWidgetLabel"],
            [data-testid="stWidgetLabel"] * {
                color: var(--text-primary) !important;
                font-size: 0.92rem !important;
                line-height: 1.35 !important;
            }
            h1, h2, h3 {
                color: var(--text-primary) !important;
                font-family: "Plus Jakarta Sans", sans-serif;
                letter-spacing: -0.04em;
                margin: 0;
            }
            h1 {
                font-size: clamp(2.7rem, 6vw, 5rem) !important;
                line-height: 0.94 !important;
                margin-bottom: 0.35rem !important;
            }
            h2, h3 {
                line-height: 0.98 !important;
            }
            .block-container {
                max-width: 1180px;
                padding-top: 1.1rem;
            }
            [data-testid="stCaptionContainer"],
            [data-testid="stCaptionContainer"] * {
                color: var(--text-secondary) !important;
            }
            .site-header-shell {
                align-items: center;
                background: rgba(245, 245, 247, 0.78);
                border: 1px solid rgba(16, 17, 20, 0.06);
                border-radius: 28px;
                box-shadow: var(--shadow-sm);
                display: flex;
                gap: 24px;
                justify-content: space-between;
                margin-bottom: 14px;
                padding: 18px 22px;
                backdrop-filter: blur(18px);
            }
            .brand-mark {
                align-items: center;
                display: inline-flex;
                gap: 14px;
                min-width: 0;
                text-decoration: none;
            }
            .brand-mark__monogram {
                background: linear-gradient(135deg, #0e203b, #0071e3);
                border-radius: 14px;
                box-shadow: 0 12px 24px rgba(0, 113, 227, 0.18);
                color: #ffffff !important;
                display: inline-grid;
                font-size: 0.82rem;
                font-weight: 700;
                height: 42px;
                letter-spacing: 0.06em;
                place-items: center;
                width: 42px;
            }
            .brand-mark__text {
                display: flex;
                flex-direction: column;
                min-width: 0;
            }
            .brand-mark__text strong {
                color: var(--text-primary) !important;
                font-size: 0.95rem;
                font-weight: 700;
            }
            .brand-mark__text span {
                color: var(--text-tertiary) !important;
                font-size: 0.76rem;
                white-space: nowrap;
            }
            .st-key-top_nav_shell {
                background: rgba(255, 255, 255, 0.76);
                border: 1px solid var(--border);
                border-radius: var(--radius-lg);
                box-shadow: var(--shadow-sm);
                margin: 0 0 42px;
                padding: 8px 10px;
                backdrop-filter: blur(18px);
            }
            .st-key-top_nav_shell [data-testid="stPills"] {
                width: 100%;
            }
            .st-key-top_nav_shell [data-testid="stPills"] [role="radiogroup"],
            .st-key-top_nav_shell [data-testid="stPills"] div[role="group"] {
                align-items: center;
                display: flex;
                flex-wrap: wrap;
                gap: 6px;
            }
            .st-key-top_nav_shell [data-testid="stPills"] button,
            .st-key-top_nav_shell [data-testid="stPills"] [role="radio"] {
                background: transparent !important;
                border: 0 !important;
                border-radius: 999px !important;
                box-shadow: none !important;
                color: var(--text-secondary) !important;
                font-size: 0.92rem !important;
                font-weight: 600 !important;
                min-height: 42px !important;
                padding: 9px 14px !important;
            }
            .st-key-top_nav_shell [data-testid="stPills"] button[aria-checked="true"],
            .st-key-top_nav_shell [data-testid="stPills"] [role="radio"][aria-checked="true"] {
                background: rgba(16, 17, 20, 0.06) !important;
                color: var(--text-primary) !important;
            }
            .st-key-top_nav_shell label {
                display: none !important;
            }
            .hero-panel {
                display: grid;
                gap: 18px;
                margin: 0 0 30px;
                max-width: 760px;
            }
            .eyebrow {
                align-items: center;
                color: var(--accent) !important;
                display: inline-flex;
                font-family: "IBM Plex Mono", monospace !important;
                font-size: 0.78rem;
                font-weight: 700;
                gap: 10px;
                letter-spacing: 0.16em;
                text-transform: uppercase;
            }
            .eyebrow::before {
                background: rgba(0, 113, 227, 0.45);
                content: "";
                height: 1px;
                width: 30px;
            }
            .hero-summary {
                color: var(--text-secondary) !important;
                font-size: 1.08rem;
                line-height: 1.72;
                margin: 0;
                max-width: 630px;
            }
            .stTextInput input, .stTextArea textarea, .stNumberInput input,
            [data-testid="stSidebar"] input, [data-testid="stSidebar"] textarea {
                background: var(--surface-strong) !important;
                border: 1px solid var(--border) !important;
                border-radius: 14px !important;
                box-shadow: none !important;
                caret-color: var(--text-primary) !important;
                color: var(--text-primary) !important;
                -webkit-text-fill-color: var(--text-primary) !important;
            }
            .stTextInput input:focus, .stTextArea textarea:focus, .stNumberInput input:focus,
            [data-testid="stChatInput"] textarea:focus {
                border-color: rgba(0, 113, 227, 0.35) !important;
                box-shadow: 0 0 0 4px var(--accent-soft) !important;
                outline: none !important;
            }
            input::placeholder, textarea::placeholder,
            [data-testid="stChatInput"] textarea::placeholder {
                color: var(--text-tertiary) !important;
                opacity: 1 !important;
                -webkit-text-fill-color: var(--text-tertiary) !important;
            }
            [data-testid="stChatInput"] {
                background: var(--surface-strong) !important;
                border: 1px solid var(--border) !important;
                border-radius: 24px !important;
                box-shadow: var(--shadow-sm) !important;
                color: var(--text-primary) !important;
            }
            [data-testid="stChatInput"] textarea,
            [data-testid="stChatInputTextArea"] {
                background: transparent !important;
                border: 0 !important;
                color: var(--text-primary) !important;
                caret-color: var(--text-primary) !important;
                -webkit-text-fill-color: var(--text-primary) !important;
            }
            .prompt-composer {
                background: var(--bg-elevated);
                border: 1px solid var(--border);
                border-radius: var(--radius-xl);
                box-shadow: var(--shadow-sm);
                margin: 18px 0 12px;
                padding: 22px;
                backdrop-filter: blur(18px);
            }
            .prompt-composer-title {
                color: var(--text-primary) !important;
                font-size: 1.15rem;
                font-weight: 700;
                letter-spacing: -0.02em;
                margin-bottom: 6px;
            }
            .prompt-composer-copy {
                color: var(--text-secondary) !important;
                line-height: 1.6;
                margin: 0 0 14px;
            }
            [data-testid="stForm"] {
                background: var(--bg-elevated);
                border: 1px solid var(--border);
                border-radius: var(--radius-xl);
                box-shadow: var(--shadow-sm);
                padding: 18px 18px 16px;
                backdrop-filter: blur(18px);
            }
            [data-testid="stForm"] textarea {
                background: #ffffff !important;
                border: 1px solid var(--border) !important;
                border-radius: 22px !important;
                box-shadow: inset 0 0 0 1px rgba(16, 17, 20, 0.02) !important;
                color: var(--text-primary) !important;
                font-size: 1.02rem !important;
                line-height: 1.62 !important;
                padding: 16px 18px !important;
                -webkit-text-fill-color: var(--text-primary) !important;
            }
            div[data-baseweb="select"] > div {
                background: var(--surface-strong) !important;
                border-color: var(--border) !important;
                border-radius: 14px !important;
                color: var(--text-primary) !important;
            }
            div[data-baseweb="select"] span,
            div[data-baseweb="select"] div,
            div[data-baseweb="popover"],
            div[data-baseweb="popover"] *,
            ul[role="listbox"],
            ul[role="listbox"] * {
                background-color: var(--surface) !important;
                color: var(--text-primary) !important;
            }
            [data-testid="stSidebar"] [data-testid="stWidgetLabel"],
            [data-testid="stSidebar"] [data-testid="stWidgetLabel"] *,
            [data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
            [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] * {
                color: var(--text-primary) !important;
            }
            [data-testid="stDataFrame"] *, [data-testid="stTable"] *,
            [data-baseweb="tab"], [data-baseweb="tab"] *,
            [data-testid="stMetric"], [data-testid="stMetric"] *,
            [data-testid="stAlert"], [data-testid="stAlert"] * {
                color: var(--text-primary) !important;
            }
            [data-testid="stChatMessage"] {
                background: var(--bg-elevated) !important;
                border: 1px solid var(--border) !important;
                border-radius: 24px !important;
                box-shadow: var(--shadow-sm);
                backdrop-filter: blur(18px);
            }
            [data-testid="stChatMessage"] * {
                color: var(--text-primary) !important;
            }
            .stButton > button,
            .stDownloadButton > button,
            [data-testid="stFormSubmitButton"] button,
            button,
            [role="button"],
            [data-testid="stBaseButton-secondary"],
            [data-testid="stBaseButton-primary"],
            [data-testid="baseButton-secondary"],
            [data-testid="baseButton-primary"] {
                background: rgba(255, 255, 255, 0.72) !important;
                border: 1px solid var(--border) !important;
                border-radius: 999px !important;
                box-shadow: none !important;
                color: var(--text-primary) !important;
                font-weight: 600 !important;
                min-height: 46px;
                transition: transform 220ms ease, box-shadow 220ms ease, background 220ms ease, border-color 220ms ease, color 220ms ease;
            }
            .stButton > button *,
            .stDownloadButton > button *,
            [data-testid="stFormSubmitButton"] button *,
            button *,
            [role="button"] *,
            [data-testid="stBaseButton-secondary"] *,
            [data-testid="stBaseButton-primary"] *,
            [data-testid="baseButton-secondary"] *,
            [data-testid="baseButton-primary"] * {
                color: var(--text-primary) !important;
            }
            .stButton > button:hover,
            .stDownloadButton > button:hover,
            [data-testid="stFormSubmitButton"] button:hover,
            button:hover,
            [role="button"]:hover {
                background: #ffffff !important;
                border-color: var(--border-strong) !important;
                color: var(--text-primary) !important;
                transform: translateY(-1px);
            }
            .stButton > button[kind="primary"],
            [data-testid="stFormSubmitButton"] button[kind="primary"],
            button[kind="primary"],
            [data-testid="stBaseButton-primary"],
            [data-testid="baseButton-primary"] {
                background: linear-gradient(135deg, #0d4b96, var(--accent)) !important;
                border-color: transparent !important;
                box-shadow: 0 18px 30px rgba(0, 113, 227, 0.2) !important;
                color: #ffffff !important;
            }
            .stButton > button[kind="primary"] *,
            [data-testid="stFormSubmitButton"] button[kind="primary"] *,
            button[kind="primary"] *,
            [data-testid="stBaseButton-primary"] *,
            [data-testid="baseButton-primary"] * {
                color: #ffffff !important;
            }
            [data-testid="stTabs"] button {
                background: transparent !important;
                border: 0 !important;
                border-radius: 999px !important;
                color: var(--text-secondary) !important;
                font-weight: 600 !important;
                padding: 10px 14px !important;
            }
            [data-testid="stTabs"] button[aria-selected="true"] {
                background: rgba(16, 17, 20, 0.06) !important;
                color: var(--text-primary) !important;
            }
            [data-testid="stMetric"] {
                background: var(--bg-elevated);
                border: 1px solid var(--border);
                border-radius: var(--radius-lg);
                box-shadow: var(--shadow-sm);
                padding: 20px;
                backdrop-filter: blur(18px);
            }
            [data-testid="stAlert"] {
                background: rgba(255, 255, 255, 0.86) !important;
                border: 1px solid var(--border) !important;
                border-radius: var(--radius-md);
                color: var(--text-primary) !important;
            }
            code, pre {
                background: rgba(16, 17, 20, 0.04) !important;
                color: var(--text-primary) !important;
                font-family: "IBM Plex Mono", monospace !important;
            }
            hr {
                border-color: var(--border) !important;
            }
            .notice {
                background: var(--bg-elevated);
                border: 1px solid var(--border);
                border-radius: var(--radius-lg);
                box-shadow: var(--shadow-sm);
                color: var(--text-primary) !important;
                padding: 0.85rem 1rem;
                backdrop-filter: blur(18px);
            }
            .notice * {
                color: var(--text-primary) !important;
            }
            @media (max-width: 920px) {
                .site-header-shell {
                    align-items: flex-start;
                    flex-direction: column;
                }
                .st-key-top_nav_shell [data-testid="stPills"] [role="radiogroup"],
                .st-key-top_nav_shell [data-testid="stPills"] div[role="group"] {
                    justify-content: flex-start;
                }
                .brand-mark__text span {
                    white-space: normal;
                }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_site_header() -> None:
    st.markdown(
        """
        <div class="site-header-shell">
            <div class="brand-mark">
                <span class="brand-mark__monogram">MM</span>
                <span class="brand-mark__text">
                    <strong>Mihir Madhaparia</strong>
                    <span>Mechanical engineer and medical technology researcher</span>
                </span>
            </div>
        </div>
        <section class="hero-panel">
            <span class="eyebrow">AI Steel Structure Studio</span>
            <h1>Prompt-driven steel building concepts.</h1>
            <p class="hero-summary">
                Generate conceptual warehouse and factory frames, cladding takeoffs, connection schedules,
                drawings, and 3D previews from one clean project chat.
            </p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_top_nav() -> str:
    if "active_page" not in st.session_state or st.session_state.active_page not in NAV_PAGES:
        st.session_state.active_page = "Prompt"
    with st.container(key="top_nav_shell"):
        selected = st.pills(
            "Main navigation",
            NAV_PAGES,
            key="active_page",
            label_visibility="collapsed",
            width="stretch",
        )
    return selected or "Prompt"


def render_sidebar(spec: BuildingSpec) -> BuildingSpec:
    with st.sidebar:
        st.header("Design Controls")
        st.caption("Use the prompt first, then fine-tune anything here.")
        project_name = st.text_input("Project name", spec.project_name)
        building_type = st.selectbox(
            "Building type",
            ["Warehouse", "Factory", "Workshop", "Aircraft Hangar"],
            index=["Warehouse", "Factory", "Workshop", "Aircraft Hangar"].index(spec.building_type)
            if spec.building_type in ["Warehouse", "Factory", "Workshop", "Aircraft Hangar"]
            else 0,
        )
        length_m = st.number_input("Length (m)", min_value=6.0, max_value=250.0, value=float(spec.length_m), step=1.0)
        width_m = st.number_input("Width / span (m)", min_value=4.0, max_value=120.0, value=float(spec.width_m), step=1.0)
        eave_height_m = st.number_input("Eave height (m)", min_value=3.0, max_value=40.0, value=float(spec.eave_height_m), step=0.5)
        bay_count = st.slider("Bay count", min_value=1, max_value=40, value=int(spec.bay_count))
        roof_style = st.selectbox(
            "Roof style",
            ["Gable", "Flat", "Mono-slope"],
            index=["Gable", "Flat", "Mono-slope"].index(spec.roof_style) if spec.roof_style in ["Gable", "Flat", "Mono-slope"] else 0,
        )
        roof_pitch_deg = st.slider("Roof pitch (degrees)", min_value=0.0, max_value=35.0, value=float(spec.roof_pitch_deg), step=0.5)
        frame_section_m = st.number_input("Primary member visual size (m)", min_value=0.12, max_value=1.2, value=float(spec.frame_section_m), step=0.03)
        secondary_section_m = st.number_input("Secondary member visual size (m)", min_value=0.06, max_value=0.6, value=float(spec.secondary_section_m), step=0.02)
        slab_thickness_m = st.number_input("Slab thickness (m)", min_value=0.08, max_value=0.5, value=float(spec.slab_thickness_m), step=0.02)
        include_bracing = st.checkbox("Include cross bracing", value=spec.include_bracing)
        include_wall_girts = st.checkbox("Include wall girts", value=spec.include_wall_girts)
        include_roof_purlins = st.checkbox("Include roof purlins", value=spec.include_roof_purlins)
        cladding_ids = cladding_options_for_ui()
        roof_sheet_label = st.selectbox(
            "Roof sheet / deck option",
            [cladding_label(option_id) for option_id in cladding_ids],
            index=cladding_ids.index(spec.roof_sheet_option) if spec.roof_sheet_option in cladding_ids else 0,
            help="Conceptual panel family used for the roof takeoff and cladding connection notes.",
        )
        wall_sheet_label = st.selectbox(
            "Wall sheet / cladding option",
            [cladding_label(option_id) for option_id in cladding_ids],
            index=cladding_ids.index(spec.wall_sheet_option) if spec.wall_sheet_option in cladding_ids else 0,
            help="Conceptual panel family used for wall takeoff, fasteners, and trims.",
        )

    updated = BuildingSpec(
        project_name=project_name,
        building_type=building_type,
        length_m=length_m,
        width_m=width_m,
        eave_height_m=eave_height_m,
        bay_count=bay_count,
        roof_style=roof_style,
        roof_pitch_deg=roof_pitch_deg,
        frame_section_m=frame_section_m,
        secondary_section_m=secondary_section_m,
        slab_thickness_m=slab_thickness_m,
        include_bracing=include_bracing,
        include_wall_girts=include_wall_girts,
        include_roof_purlins=include_roof_purlins,
        roof_sheet_option=select_cladding_from_label(roof_sheet_label),
        wall_sheet_option=select_cladding_from_label(wall_sheet_label),
        design_notes=spec.design_notes,
    )
    st.session_state.spec = spec_to_dict(validate_spec(updated))
    return validate_spec(updated)


def render_prompt_tab() -> None:
    st.subheader("Project Chat")
    st.write("Work on one active project at a time. Start with a building description, then keep asking for changes until the design matches your vision.")

    if st.session_state.extraction_notice:
        level, message = st.session_state.extraction_notice
        if level == "success":
            st.success(message)
        else:
            st.warning(message)

    provider, api_key, model, ollama_host = current_ai_settings()
    st.caption(f"Current AI engine: {provider} | Model: {model if provider != 'Free local parser' else 'rules'}")

    for message in st.session_state.chat_messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    reset_col, setup_col = st.columns([1, 2])
    with reset_col:
        if st.button("Reset Project Chat", use_container_width=True):
            st.session_state.spec = spec_to_dict(BuildingSpec())
            st.session_state.project_history = []
            st.session_state.chat_messages = [
                {
                    "role": "assistant",
                    "content": "Project reset. Describe the steel building you want to create.",
                }
            ]
            st.session_state.extraction_notice = None
            st.rerun()
    with setup_col:
        st.caption("Change the AI engine, model, or Ollama host in the AI Setup tab.")

    st.markdown(
        """
        <div class="prompt-composer">
            <div class="prompt-composer-title">Tell the studio what to build next.</div>
            <p class="prompt-composer-copy">
                Use one clear sentence, or ask for a change to the active project. Example:
                "Use standing seam roof sheets, insulated wall panels, and make it 5m wider."
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.form("project_chat_composer", clear_on_submit=True):
        user_message = st.text_area(
            "Project prompt",
            placeholder="Describe the first design or ask for a change...",
            label_visibility="collapsed",
            height=120,
        )
        submitted = st.form_submit_button("Send to AI", type="primary", use_container_width=True)

    if submitted and user_message.strip():
        user_message = user_message.strip()
        st.session_state.chat_messages.append({"role": "user", "content": user_message})
        has_active_project = len(st.session_state.project_history) > 0
        try:
            if has_active_project:
                current = spec_from_dict(st.session_state.spec)
                updated, source = apply_followup_with_provider(
                    current,
                    user_message,
                    provider.replace("Free local parser", "Local"),
                    api_key,
                    model,
                    ollama_host,
                )
                st.session_state.spec = spec_to_dict(updated)
                st.session_state.project_history.append(f"Follow-up via {source}: {user_message}")
                response = f"Updated the current project with {source}. The preview, drawings, BOM, and exports have been refreshed."
            else:
                spec, source = extract_spec(
                    user_message,
                    provider.replace("Free local parser", "Local"),
                    api_key,
                    model,
                    ollama_host,
                )
                st.session_state.spec = spec_to_dict(spec)
                st.session_state.project_history = [f"Initial rendition via {source}: {user_message}"]
                response = f"Created the first rendition with {source}. You can keep asking for refinements here."
            st.session_state.chat_messages.append({"role": "assistant", "content": response})
            st.session_state.extraction_notice = ("success", response)
            st.rerun()
        except (ValueError, KeyError, urllib.error.URLError, TimeoutError) as exc:
            current = spec_from_dict(st.session_state.spec)
            if has_active_project:
                updated = apply_followup_local(current, user_message)
                st.session_state.spec = spec_to_dict(updated)
                st.session_state.project_history.append(f"Follow-up via fallback local parser: {user_message}")
                response = f"The selected AI failed, so I applied deterministic changes where possible. Details: {exc}"
            else:
                fallback = extract_with_local_parser(user_message)
                st.session_state.spec = spec_to_dict(fallback)
                st.session_state.project_history = [f"Initial rendition via fallback local parser: {user_message}"]
                response = f"The selected AI failed, so I used the free local parser. Details: {exc}"
            st.session_state.chat_messages.append({"role": "assistant", "content": response})
            st.session_state.extraction_notice = ("warning", response)
            st.rerun()

    if st.session_state.project_history:
        with st.expander("Project change history", expanded=False):
            for index, item in enumerate(st.session_state.project_history, start=1):
                st.write(f"{index}. {item}")

    st.markdown(
        """
        <div class="notice">
        This app intentionally separates AI interpretation from geometry generation. That keeps the CAD output predictable:
        the AI extracts parameters, then deterministic code creates the model, drawings, and BOM.
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_preview_tab(package: ModelPackage) -> None:
    st.subheader("3D Concept Preview")
    control_cols = st.columns([1.15, 2.2])
    with control_cols[0]:
        view_preset = st.selectbox("Camera view", VIEW_PRESETS, index=0, help="Use orthogonal presets for plan/elevation checks or low perspective for inspection.")
    with control_cols[1]:
        selected_layers = st.multiselect(
            "Visible model layers",
            VISUALIZER_LAYERS,
            default=DEFAULT_VISUALIZER_LAYERS,
            help="Toggle structural steel, bracing, cladding, seams, connection hardware, and labels.",
        )
    layer_set = set(selected_layers or DEFAULT_VISUALIZER_LAYERS)
    fig = create_plotly_figure(package, layer_set, view_preset)
    plot_config = {"displaylogo": False, "scrollZoom": True, "responsive": True}
    if fig is None:
        st.error("Plotly is not installed. Run `python -m pip install -r requirements.txt` and restart Streamlit.")
    else:
        st.plotly_chart(fig, use_container_width=True, config=plot_config)
        if st.toggle("Open large visualizer with full-screen button", value=False):
            large_fig = create_plotly_figure(package, layer_set, view_preset)
            if large_fig is not None:
                large_fig.update_layout(height=820, margin={"l": 0, "r": 0, "t": 18, "b": 0})
                figure_html = large_fig.to_html(full_html=False, include_plotlyjs=True, config=plot_config)
                components.html(
                    f"""
                    <style>
                        :root {{
                            --ink: #101114;
                            --paper: #f5f5f7;
                            --card: #ffffff;
                            --line: rgba(16,17,20,0.08);
                            --accent: #0071e3;
                        }}
                        body {{
                            margin: 0;
                            background: var(--paper);
                            color: var(--ink);
                            font-family: "Plus Jakarta Sans", sans-serif;
                        }}
                        #steel-viewer-shell {{
                            background: linear-gradient(180deg, #ffffff 0%, #f5f5f7 100%);
                            border: 1px solid var(--line);
                            border-radius: 22px;
                            box-sizing: border-box;
                            color: var(--ink);
                            min-height: 880px;
                            overflow: hidden;
                            padding: 14px;
                        }}
                        #steel-viewer-toolbar {{
                            align-items: center;
                            display: flex;
                            gap: 12px;
                            justify-content: space-between;
                            padding: 4px 4px 12px;
                        }}
                        #steel-viewer-toolbar strong,
                        #steel-viewer-toolbar span {{
                            color: var(--ink);
                        }}
                        #steel-fullscreen-btn {{
                            background: var(--ink);
                            border: 1px solid var(--ink);
                            border-radius: 999px;
                            color: #ffffff;
                            cursor: pointer;
                            font-weight: 700;
                            padding: 10px 16px;
                        }}
                        #steel-fullscreen-btn:hover {{
                            background: var(--accent);
                            border-color: var(--accent);
                            color: #ffffff;
                        }}
                        #steel-viewer-shell:fullscreen {{
                            border-radius: 0;
                            height: 100vh;
                            padding: 18px;
                            width: 100vw;
                        }}
                    </style>
                    <div id="steel-viewer-shell">
                        <div id="steel-viewer-toolbar">
                            <strong>Large steel structure visualizer</strong>
                            <span>Scroll to zoom, drag to orbit, use layers/presets above, and hover members or bolts for metadata.</span>
                            <button id="steel-fullscreen-btn" type="button">Full screen</button>
                        </div>
                        {figure_html}
                    </div>
                    <script>
                        const shell = document.getElementById("steel-viewer-shell");
                        const button = document.getElementById("steel-fullscreen-btn");
                        button.addEventListener("click", async () => {{
                            if (!document.fullscreenElement && shell.requestFullscreen) {{
                                await shell.requestFullscreen();
                                button.textContent = "Exit full screen";
                            }} else if (document.exitFullscreen) {{
                                await document.exitFullscreen();
                                button.textContent = "Full screen";
                            }}
                        }});
                        document.addEventListener("fullscreenchange", () => {{
                            button.textContent = document.fullscreenElement ? "Exit full screen" : "Full screen";
                        }});
                    </script>
                    """,
                    height=930,
                    scrolling=False,
                )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_metric("Primary frames", str(package.spec.bay_count + 1))
    with c2:
        render_metric("Members", str(len(package.members)))
    with c3:
        steel_weight = sum(member.steel_weight_kg for member in package.members)
        render_metric("Visual steel estimate", f"{steel_weight / 1000:.1f} t", "Based on the starter section catalog, not engineered sizing.")
    with c4:
        roof_peak = max(vertex[2] for vertex in package.vertices)
        render_metric("Peak height", f"{roof_peak:.1f} m")

    for warning in package.warnings:
        st.warning(warning)


def render_drawings_tab(package: ModelPackage) -> None:
    st.subheader("2D Drawings And Quantity Takeoff")
    svg_markup = export_svg(package).decode("utf-8")
    components.html(svg_markup, height=960, scrolling=True)
    st.caption("Plan, side elevation, and typical frame section")
    st.markdown("#### Bill Of Materials")
    st.dataframe(package.bom_rows, use_container_width=True, hide_index=True)
    st.markdown("#### Conceptual Connection Details")
    st.warning("These bolt, weld, bracket, and plate details are typical placeholders only. Do not use them for fabrication or construction until a licensed structural engineer designs and stamps the connections.")
    st.dataframe(package.connection_rows, use_container_width=True, hide_index=True)


def render_exports_tab(package: ModelPackage) -> None:
    st.subheader("Download Package")
    base = sanitize_filename(package.spec.project_name)
    st.write("These files are generated in memory and can be imported into common CAD, mesh, and documentation workflows.")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.download_button("Download STL mesh", export_stl(package), f"{base}.stl", "model/stl", use_container_width=True)
        st.download_button("Download DXF drawings", export_dxf(package), f"{base}_drawings.dxf", "application/dxf", use_container_width=True)
    with col2:
        st.download_button("Download OBJ mesh", export_obj(package), f"{base}.obj", "text/plain", use_container_width=True)
        st.download_button("Download SVG drawing", export_svg(package), f"{base}_drawing.svg", "image/svg+xml", use_container_width=True)
    with col3:
        st.download_button("Download BOM CSV", export_bom_csv(package), f"{base}_bom.csv", "text/csv", use_container_width=True)
        st.download_button("Download connections CSV", export_connections_csv(package), f"{base}_connections.csv", "text/csv", use_container_width=True)
        st.download_button("Download project JSON", export_json(package), f"{base}_project.json", "application/json", use_container_width=True)

    st.info(
        "For a true STEP/SolidWorks-grade workflow later, add a CAD kernel service such as CadQuery/OpenCascade or FreeCAD in a backend worker. "
        "This MVP keeps the exports dependency-light so you can run it immediately."
    )


def render_ai_setup_tab() -> None:
    st.subheader("AI Setup")
    st.write("Configure the AI used by the clean chat page. These settings apply to the single active project.")

    providers = ["Ollama Local", "Free local parser", "OpenAI", "Google Gemini"]
    provider = st.selectbox(
        "Extraction engine",
        providers,
        index=providers.index(st.session_state.ai_provider) if st.session_state.ai_provider in providers else 0,
        help="Ollama is the free local AI path. If it is not running, the chat falls back to the deterministic parser.",
    )
    st.session_state.ai_provider = provider

    if provider == "Ollama Local":
        st.session_state.ai_model = st.text_input("Model", value=st.session_state.ai_model or DEFAULT_OLLAMA_MODEL)
        st.session_state.ollama_host = st.text_input("Ollama host", value=st.session_state.ollama_host or DEFAULT_OLLAMA_HOST)
        if st.button("Test Ollama Connection", use_container_width=True):
            ok, message = check_ollama_status(st.session_state.ollama_host)
            if ok:
                st.success(message)
            else:
                st.warning(message)
    elif provider == "OpenAI":
        st.session_state.ai_model = st.text_input("Model", value=st.session_state.ai_model or os.getenv("OPENAI_MODEL", "gpt-5.4-mini"))
        st.session_state.openai_api_key = st.text_input("OpenAI API key", value=st.session_state.openai_api_key, type="password")
    elif provider == "Google Gemini":
        st.session_state.ai_model = st.text_input("Model", value=st.session_state.ai_model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
        st.session_state.gemini_api_key = st.text_input("Gemini API key", value=st.session_state.gemini_api_key, type="password")
    else:
        st.session_state.ai_model = "rules"
        st.info("The free local parser needs no model, host, or API key.")

    st.divider()
    st.subheader("AI Agent Integration Options")
    st.markdown(
        """
        **Best free path:** start with the built-in parser, then try **Ollama Local** if your computer can run a local model.

        **Most practical paid path:** use an API model only for parameter extraction, not for geometry. That keeps token usage tiny
        because the expensive CAD work is deterministic Python.

        **Website-ready architecture:** keep Streamlit for the prototype, then move the geometry functions into a FastAPI backend.
        Your website can call `/extract`, `/generate`, and `/download` endpoints while a React/Next.js frontend handles the UI.
        """
    )

    with st.expander("Free/local: built-in parser and Ollama"):
        st.code(
            textwrap.dedent(
                """
                # Built-in parser
                # No setup needed.

                # Ollama local option
                # 1. Install Ollama from https://ollama.com
                # 2. Pull a model:
                ollama pull llama3.2:1b

                # 3. In this app select "Ollama Local"
                #    Host: http://localhost:11434
                #    Model: llama3.2:1b
                """
            ).strip(),
            language="bash",
        )

    with st.expander("Paid/API: OpenAI"):
        st.code(
            textwrap.dedent(
                """
                # PowerShell
                $env:OPENAI_API_KEY="your_api_key_here"
                $env:OPENAI_MODEL="gpt-5.4-mini"
                python -m streamlit run app.py
                """
            ).strip(),
            language="powershell",
        )
        st.write("OpenAI is a strong option when prompts are messy, multi-step, or need robust extraction from vague language.")

    with st.expander("Paid/API: Google Gemini"):
        st.code(
            textwrap.dedent(
                """
                # PowerShell
                $env:GEMINI_API_KEY="your_api_key_here"
                $env:GEMINI_MODEL="gemini-2.5-flash"
                python -m streamlit run app.py
                """
            ).strip(),
            language="powershell",
        )
        st.write("Gemini is another low-cost option for structured extraction and can be swapped in without changing the CAD generator.")

    with st.expander("Future agents to add"):
        st.markdown(
            """
            - **Structural review agent:** checks span, bay spacing, height/span ratio, bracing assumptions, and missing loads.
            - **Costing agent:** maps BOM rows to steel, cladding, slab, and erection cost assumptions.
            - **Code checklist agent:** asks for location, occupancy, wind/snow/seismic category, and produces a requirements checklist.
            - **Website sales agent:** turns the generated package into a customer-facing proposal page.
            """
        )


def main() -> None:
    st.set_page_config(page_title="AI Steel Structure Studio", layout="wide")
    init_state()
    load_css()

    render_site_header()
    active_page = render_top_nav()

    current_spec = spec_from_dict(st.session_state.spec)
    spec = render_sidebar(current_spec)
    package = build_model(spec)

    if active_page == "Prompt":
        render_prompt_tab()
    elif active_page == "3D Preview":
        render_preview_tab(package)
    elif active_page == "Drawings + BOM":
        render_drawings_tab(package)
    elif active_page == "Exports":
        render_exports_tab(package)
    elif active_page == "AI Setup":
        render_ai_setup_tab()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        st.set_page_config(page_title="AI Steel Structure Studio", layout="wide")
        st.error("The app hit a startup error before it could fully render.")
        st.code(traceback.format_exc())
