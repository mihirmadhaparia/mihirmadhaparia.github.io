from __future__ import annotations

import csv
from pathlib import Path

IN_TO_M = 0.0254
LBFT_TO_KGM = 1.48816394357


def safe_float(value, default: float = 0.0) -> float:
    try:
        if value in (None, "", "--"):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def section_row(name: str, family: str, props: dict[str, object], source: str) -> dict[str, object]:
    d = safe_float(props.get("d") or props.get("Ht") or props.get("OD"))
    bf = safe_float(props.get("bf") or props.get("B") or props.get("OD") or d)
    tw = safe_float(props.get("tw") or props.get("tdes") or props.get("tnom") or props.get("t"))
    tf = safe_float(props.get("tf") or props.get("tdes") or props.get("tnom") or props.get("t") or tw)
    weight = safe_float(props.get("weight"))
    family_visual = family
    if family in {"HSS_R", "PIPE"}:
        family_visual = "ROD" if d <= 1.5 else "PIPE"
    if family in {"HSS"}:
        family_visual = "HSS"
    if family in {"WT", "MT", "ST"}:
        family_visual = "T"
    if family in {"L", "DBL_L"}:
        family_visual = "L"

    return {
        "section_id": name.replace("_", "."),
        "family": family_visual,
        "depth_m": round(max(d * IN_TO_M, 0.001), 6),
        "flange_width_m": round(max(bf * IN_TO_M, 0.001), 6),
        "web_thickness_m": round(max(tw * IN_TO_M, 0.001), 6),
        "flange_thickness_m": round(max(tf * IN_TO_M, 0.001), 6),
        "weight_kg_m": round(max(weight * LBFT_TO_KGM, 0.001), 4),
        "wall_thickness_m": round(max(tw * IN_TO_M, 0.0), 6) if family in {"HSS", "HSS_R", "PIPE"} else 0,
        "lip_m": 0,
        "source_note": source,
    }


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def build_steel_sections() -> list[dict[str, object]]:
    from steelpy import aisc

    groups = [
        ("W_shapes", "W"),
        ("M_shapes", "M"),
        ("S_shapes", "S"),
        ("HP_shapes", "HP"),
        ("C_shapes", "C"),
        ("MC_shapes", "MC"),
        ("HSS_shapes", "HSS"),
        ("HSS_R_shapes", "HSS_R"),
        ("PIPE_shapes", "PIPE"),
        ("WT_shapes", "WT"),
        ("MT_shapes", "MT"),
        ("ST_shapes", "ST"),
        ("L_shapes", "L"),
        ("DBL_L_shapes", "DBL_L"),
    ]
    rows: list[dict[str, object]] = []
    for attr, family in groups:
        profile = getattr(aisc, attr)
        for name, section in profile.sections.items():
            source = "steelpy packaged AISC-style section properties; verify against official AISC Shapes Database v16.0 before engineering use."
            rows.append(section_row(name, family, section.properties, source))

    rows.sort(key=lambda row: (str(row["family"]), str(row["section_id"])))
    return rows


def build_purlins() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    systems = [
        ("Z", "Zee purlin", "Z"),
        ("ZLAP", "Lapped zee purlin", "Z"),
        ("C", "Cee purlin/girt", "C"),
        ("SIGMA", "Sigma purlin", "SIGMA"),
        ("HAT", "Hat/channel purlin", "HAT"),
        ("EAVE", "Eave strut", "HSS"),
    ]
    depths_mm = [100, 120, 150, 175, 200, 225, 250, 300, 350, 400]
    thicknesses_mm = [1.5, 1.9, 2.0, 2.5, 3.0, 3.2, 4.0]
    for prefix, description, family in systems:
        for depth in depths_mm:
            for thickness in thicknesses_mm:
                if prefix in {"HAT"} and depth > 250:
                    continue
                if prefix in {"EAVE"} and depth < 150:
                    continue
                width = max(45, min(95, round(depth * 0.32)))
                lip = 0 if prefix in {"HAT", "EAVE"} else 18
                area_m2 = max(0.00012, (depth + 2 * width + 2 * lip) * thickness / 1_000_000)
                weight = area_m2 * 7850
                rows.append(
                    {
                        "section_id": f"{prefix}{depth}X{str(thickness).replace('.', 'P')}",
                        "family": family,
                        "depth_m": round(depth / 1000, 4),
                        "flange_width_m": round(width / 1000, 4),
                        "web_thickness_m": round(thickness / 1000, 4),
                        "flange_thickness_m": round(thickness / 1000, 4),
                        "weight_kg_m": round(weight, 3),
                        "wall_thickness_m": round(thickness / 1000, 4),
                        "lip_m": round(lip / 1000, 4),
                        "source_note": f"Generated common cold-formed {description} size for conceptual modeling; verify against manufacturer tables.",
                    }
                )
    return rows


def build_metric_misc_sections() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for diameter in [12, 16, 20, 24, 30, 36]:
        area_m2 = 3.141592653589793 * (diameter / 1000) ** 2 / 4
        rows.append(
            {
                "section_id": f"ROD{diameter}",
                "family": "ROD",
                "depth_m": round(diameter / 1000, 4),
                "flange_width_m": round(diameter / 1000, 4),
                "web_thickness_m": round(diameter / 1000, 4),
                "flange_thickness_m": round(diameter / 1000, 4),
                "weight_kg_m": round(area_m2 * 7850, 4),
                "wall_thickness_m": 0,
                "lip_m": 0,
                "source_note": "Generated metric rod brace placeholder; verify rod grade/area with engineer.",
            }
        )
    for size, thickness in [(75, 8), (100, 6), (125, 6), (150, 8)]:
        wall_area_m2 = ((size / 1000) ** 2 - ((size - 2 * thickness) / 1000) ** 2)
        rows.append(
            {
                "section_id": f"HSS{size}X{size}X{thickness}",
                "family": "HSS",
                "depth_m": round(size / 1000, 4),
                "flange_width_m": round(size / 1000, 4),
                "web_thickness_m": round(thickness / 1000, 4),
                "flange_thickness_m": round(thickness / 1000, 4),
                "weight_kg_m": round(wall_area_m2 * 7850, 4),
                "wall_thickness_m": round(thickness / 1000, 4),
                "lip_m": 0,
                "source_note": "Generated metric HSS brace placeholder; verify against manufacturer/AISC HSS data.",
            }
        )
    angle_area_m2 = 2 * 0.075 * 0.008 - 0.008 * 0.008
    rows.append(
        {
            "section_id": "L75X75X8",
            "family": "L",
            "depth_m": 0.075,
            "flange_width_m": 0.075,
            "web_thickness_m": 0.008,
            "flange_thickness_m": 0.008,
            "weight_kg_m": round(angle_area_m2 * 7850, 4),
            "wall_thickness_m": 0,
            "lip_m": 0,
            "source_note": "Generated metric angle placeholder; verify against manufacturer tables.",
        }
    )
    return rows


def build_brace_connections() -> list[dict[str, object]]:
    rows = [
        ("ROD_X_BRACE_LOW", "Cross bracing", 0, 35, "ROD20", "6mm gusset plate", "M16 class 8.8 bolts", 1, 16, "5mm fillet shop weld to frame where engineered", "Low-angle tension rod cross brace"),
        ("ROD_X_BRACE_STD", "Cross bracing", 35, 55, "ROD24", "8mm gusset plate", "M20 class 8.8 bolts", 1, 20, "6mm fillet shop weld to frame where engineered", "Typical tension rod cross brace"),
        ("ROD_X_BRACE_STEEP", "Cross bracing", 55, 90, "ROD30", "10mm gusset plate", "M24 class 8.8 bolts", 1, 24, "6mm fillet shop weld to frame where engineered", "Steep tension rod cross brace"),
        ("HSS_DIAGONAL_LOW", "Compression bracing", 0, 35, "HSS100X100X6", "10mm slotted gusset plate", "M20 class 8.8 bolts", 2, 20, "6mm fillet weld to cap plate", "Low-angle HSS diagonal brace"),
        ("HSS_DIAGONAL_STD", "Compression bracing", 35, 60, "HSS125X125X6", "12mm gusset plate", "M22 class 8.8 bolts", 2, 22, "6mm fillet weld to cap plate", "Typical HSS diagonal brace"),
        ("HSS_KNEE_BRACE", "Knee bracing", 30, 70, "HSS100X100X6", "10mm end plate pair", "M20 class 8.8 bolts", 4, 20, "6mm fillet weld all around end plate", "Knee brace between column and rafter"),
        ("ANGLE_KICKER", "Kicker bracing", 20, 70, "L75X75X8", "8mm clip angle", "M16 class 8.8 bolts", 2, 16, "5mm fillet weld to clip where engineered", "Secondary kicker/anti-sag brace"),
        ("PURLIN_SAG_ROD", "Purlin bridging", 0, 25, "ROD12", "Manufacturer bridging clip", "M12 bolts/screws", 1, 12, "No field weld preferred", "Sag rod or anti-sag purlin bracing"),
        ("PORTAL_BRACE", "Portal bracing", 70, 90, "W8X10", "Moment end plate", "M20 class 8.8 bolts", 6, 20, "Engineer welds for portal moment frame", "Portal frame bracing bay"),
    ]
    return [
        {
            "rule_id": rule_id,
            "brace_family": family,
            "min_angle_deg": min_angle,
            "max_angle_deg": max_angle,
            "preferred_section": section,
            "connection_plate": plate,
            "bolt_spec": bolt_spec,
            "bolts_per_end": bolts,
            "bolt_diameter_mm": diameter,
            "weld_detail": weld,
            "use_case": use_case,
            "status": "Concept placeholder - engineer before fabrication",
        }
        for rule_id, family, min_angle, max_angle, section, plate, bolt_spec, bolts, diameter, weld, use_case in rows
    ]


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    steel_rows = build_steel_sections()
    purlin_rows = build_purlins()
    misc_rows = build_metric_misc_sections()
    # Keep purlins in the master section catalog so the visualizer and BOM share one source.
    write_csv(root / "steel_sections.csv", steel_rows + purlin_rows + misc_rows)
    write_csv(root / "purlin_sections.csv", purlin_rows)
    write_csv(root / "brace_connection_catalog.csv", build_brace_connections())
    print(f"Wrote {len(steel_rows) + len(purlin_rows) + len(misc_rows)} steel section rows")
    print(f"Wrote {len(purlin_rows)} purlin rows")
    print("Wrote brace connection catalog")


if __name__ == "__main__":
    main()
