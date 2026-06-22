#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_qa.py — 矿床空间感知 QA 对生成器（第一层：模板规则式）v2

修复项:
  1. 矿物数<3不生成 mineral_assemblage QA
  2. 按矿床类型切换答案模板（成因机制描述差异化）
  3. 语法修复（a/an, 去除"the South America"类错误）
  4. 新增空间推理类问题（关系型而非属性列举型）
  5. 去除通用尾句，改为矿床类型特异性描述

用法:
  python generate_qa.py input.json -o qa_output.jsonl
  python generate_qa.py input.json -o qa_output.jsonl --min-fields 3 --stats
"""
import json, argparse, hashlib, re
from pathlib import Path

# ─── 矿床类型映射 ─────────────────────────────────────────────────────────────
DEPOSIT_NAMES = {
    "PORP-CUMO": "porphyry Cu-Mo",
    "PORP-CUAU": "porphyry Cu-Au",
    "IOCG": "iron oxide copper-gold (IOCG)",
    "OROG-AU": "orogenic gold",
    "VMS": "volcanogenic massive sulfide (VMS)",
    "SEDEX": "sedimentary exhalative (SEDEX)",
    "MVT": "Mississippi Valley-type (MVT)",
    "CARLIN": "Carlin-type gold",
    "EPITHERMAL": "epithermal",
    "HS-EPITH": "high-sulfidation epithermal",
    "LS-EPITH": "low-sulfidation epithermal",
    "SKARN": "skarn",
    "MAGMATIC-NI": "magmatic Ni-Cu-PGE",
    "BIF-AU": "BIF-hosted gold",
}

# 矿床类型→成因流体描述
FLUID_DESC = {
    "PORP-CUMO": "magmatic-hydrothermal fluids exsolved from a cooling felsic intrusion",
    "PORP-CUAU": "magmatic-hydrothermal fluids derived from oxidized, sulfur-rich magmas",
    "IOCG": "high-temperature, oxidized fluids of mixed magmatic and external origin",
    "OROG-AU": "metamorphic fluids generated during crustal dehydration along major shear zones",
    "VMS": "hydrothermal fluids venting at or near the seafloor in a volcanic setting",
    "SEDEX": "basin brines expelled during sediment compaction and diagenesis",
    "MVT": "low-temperature basinal brines migrating along aquifers",
    "CARLIN": "deeply-sourced fluids ascending along high-angle structures",
    "EPITHERMAL": "low-temperature hydrothermal fluids in a near-surface volcanic environment",
    "HS-EPITH": "acidic magmatic vapors condensing in the shallow volcanic environment",
    "LS-EPITH": "near-neutral pH fluids of mixed meteoric-magmatic origin ascending along faults",
    "SKARN": "magmatic-hydrothermal fluids reacting with carbonate host rocks at the intrusion contact",
    "MAGMATIC-NI": "sulfide-saturated mafic-ultramafic magmas segregating immiscible sulfide liquids",
    "BIF-AU": "metamorphic fluids infiltrating chemically reactive iron-rich horizons",
}

# 矿床类型→构造控矿描述
STRUCT_DESC = {
    "PORP-CUMO": "Stockworks and fracture networks developed in the brittle carapace above the causative pluton, while regional faults provided distal fluid pathways.",
    "PORP-CUAU": "Fracture-controlled stockwork veining concentrated in the apical zone of the porphyry intrusion.",
    "IOCG": "Major crustal-scale structures served as fluid conduits connecting deep magmatic sources with reactive host rocks at higher crustal levels.",
    "OROG-AU": "Mineralization concentrated at structural complexity zones—fault bends, jogs, and rheological contrasts—along crustal-scale shear systems.",
    "VMS": "Synvolcanic faults and caldera-ring structures controlled the location of hydrothermal vents on the paleoseafloor.",
    "SEDEX": "Synsedimentary growth faults controlled brine discharge sites on the basin floor.",
    "MVT": "Regional aquifer-aquitard interfaces and fault-related fracture permeability controlled ore distribution.",
    "CARLIN": "High-angle feeder faults intersecting reactive carbonate stratigraphy created the most favorable ore traps.",
    "HS-EPITH": "Subvertical fracture zones provided conduits for ascending magmatic vapors to react with groundwater.",
    "LS-EPITH": "Dilational zones in normal and strike-slip faults provided open-space for quartz-adularia vein formation.",
    "SKARN": "Ore localization was controlled by the geometry of the intrusion-carbonate contact and cross-cutting faults.",
    "MAGMATIC-NI": "Structural embayments and dynamic flow constrictions in magma conduits trapped dense sulfide liquids.",
    "BIF-AU": "Fold hinges and shear zones within the BIF provided structural preparation and enhanced permeability.",
}


def deposit_label(code):
    return DEPOSIT_NAMES.get(code, code) if code else None


def an(word):
    """Return 'an' if word starts with vowel sound, else 'a'."""
    if not word:
        return "a"
    return "an" if word[0].lower() in "aeiou" else "a"


# ─── QA 模板引擎 ──────────────────────────────────────────────────────────────
TEMPLATES = []


def template(dimension, required_fields, min_list_len=None):
    """注册 QA 模板。min_list_len: {field: min_count} 过滤条件。"""
    def decorator(func):
        TEMPLATES.append({
            "dimension": dimension,
            "required_fields": required_fields,
            "min_list_len": min_list_len or {},
            "builder": func,
        })
        return func
    return decorator


# ═══ 维度1: 空间定位 ═══

@template("spatial_location", ["metallogenic_belt"])
def qa_location_belt(r):
    belt = r["metallogenic_belt"]
    dep = deposit_label(r.get("deposit_type")) or "mineral deposit"
    # Skip overly vague belts (just a country/continent name, <20 chars)
    if len(belt) < 20:
        return None
    return {
        "question": f"What is the metallogenic belt or tectonic domain hosting the {dep} described in this paper?",
        "answer": f"The deposit is situated within the {belt}."
    }


@template("spatial_location", ["metallogenic_belt", "deposit_type"])
def qa_spatial_significance(r):
    belt = r["metallogenic_belt"]
    dep = deposit_label(r.get("deposit_type")) or "deposit"
    if len(belt) < 20:
        return None
    return {
        "question": f"Why is the spatial position within the {belt} significant for understanding this {dep}?",
        "answer": (f"Within the {belt}, this {dep} occupies a structurally defined position "
                   f"that enables direct comparison with co-genetic deposits along strike, "
                   f"constrains the ore-forming event to the regional tectonic framework, "
                   f"and identifies analogous prospective positions elsewhere in the belt.")
    }


@template("spatial_location", ["metallogenic_belt", "tectonic_setting"])
def qa_tectonic_context(r):
    belt = r["metallogenic_belt"]
    tect = r["tectonic_setting"]
    dep = deposit_label(r.get("deposit_type")) or "deposit"
    return {
        "question": f"How does the tectonic setting relate to the formation of {dep} mineralization in this region?",
        "answer": (f"The deposit formed in {an(tect)} {tect} geodynamic context "
                   f"within the {belt}. This tectonic position controlled the geometry of "
                   f"fluid pathways and the spatial distribution of heat sources responsible "
                   f"for ore-forming processes.")
    }


# ═══ 维度2: 赋存关系 ═══

@template("host_rock_relation", ["host_rocks", "deposit_type"])
def qa_host_rocks_spatial(r):
    rocks = r["host_rocks"]
    dep = deposit_label(r["deposit_type"]) or "deposit"
    n = len(rocks)
    rocks_str = ", ".join(rocks[:8])
    extra = f" (and {n-8} others)" if n > 8 else ""
    if n >= 5:
        answer = (f"Mineralization is hosted within {n} lithologies including {rocks_str}{extra}. "
                  f"This diversity suggests ore formation was governed by structural and fluid-chemical factors "
                  f"rather than lithological control alone.")
    else:
        answer = (f"Mineralization is selectively hosted in {rocks_str}. "
                  f"The limited lithological range indicates strong host-rock control on ore deposition.")
    return {"question": f"What is the spatial relationship between {dep} mineralization and its host lithologies?", "answer": answer}


@template("host_rock_relation", ["host_rocks"], min_list_len={"host_rocks": 3})
def qa_host_rock_classification(r):
    rocks = r["host_rocks"]
    n = len(rocks)
    intrusive_kw = ["granite", "diorite", "gabbro", "monzonite", "syenite", "tonalite", "porphyry", "aplite", "pegmatite"]
    volcanic_kw = ["andesite", "basalt", "rhyolite", "dacite", "tuff", "ignimbrite", "lava", "pyroclastic", "volcanic"]
    sedimentary_kw = ["sandstone", "limestone", "shale", "siltstone", "mudstone", "conglomerate", "dolomite", "carbonate"]
    metamorphic_kw = ["gneiss", "schist", "quartzite", "marble", "amphibolite", "greenstone", "phyllite", "slate", "meta"]
    categories = set()
    for rock in rocks:
        rl = rock.lower()
        if any(k in rl for k in intrusive_kw): categories.add("intrusive")
        if any(k in rl for k in volcanic_kw): categories.add("volcanic")
        if any(k in rl for k in sedimentary_kw): categories.add("sedimentary")
        if any(k in rl for k in metamorphic_kw): categories.add("metamorphic")
    if not categories:
        categories.add("diverse")
    cat_str = ", ".join(sorted(categories))
    return {
        "question": "What rock types host the mineralization—igneous, sedimentary, metamorphic, or a combination?",
        "answer": f"The host rocks span {cat_str} lithologies ({n} types). Representative units include: {', '.join(rocks[:6])}."
    }

# PLACEHOLDER_REST

# ═══ 维度2b: 赋存关系 — 进阶空间问题 ═══

@template("host_rock_relation", ["host_rocks", "structural_controls", "deposit_type"])
def qa_hostrock_structure_interplay(r):
    rocks = r["host_rocks"]
    structs = r["structural_controls"]
    dep = deposit_label(r["deposit_type"]) or "deposit"
    return {
        "question": f"How do host rock lithology and structural controls interact to localize {dep} mineralization?",
        "answer": (f"Mineralization is hosted in {', '.join(rocks[:4])} and controlled by {', '.join(structs[:3])}. "
                   f"The interplay suggests that structural preparation (fracturing, brecciation) enhanced permeability "
                   f"in specific lithologies, creating favorable sites where reactive host rocks intersected "
                   f"structurally-controlled fluid pathways.")
    }


@template("host_rock_relation", ["host_rocks", "alteration", "deposit_type"])
def qa_hostrock_alteration_contact(r):
    rocks = r["host_rocks"]
    alt = r["alteration"]
    dep = deposit_label(r["deposit_type"]) or "deposit"
    alt_str = ", ".join(alt) if isinstance(alt, list) else str(alt)
    return {
        "question": f"What is the spatial relationship between host rock types and alteration zones in this {dep}?",
        "answer": (f"The host rocks ({', '.join(rocks[:4])}) are overprinted by {alt_str}. "
                   f"Alteration intensity and type vary with host lithology—more reactive rocks "
                   f"(e.g., carbonates, mafic lithologies) typically show stronger and more complete "
                   f"alteration envelopes than siliceous units, creating mappable spatial gradients "
                   f"that vector toward ore.")
    }


# ═══ 维度3b: 控矿构造 — 进阶空间问题 ═══

@template("structural_control", ["structural_controls", "host_rocks", "deposit_type"])
def qa_structural_lithology_trap(r):
    structs = r["structural_controls"]
    rocks = r["host_rocks"]
    dep = deposit_label(r["deposit_type"]) or "deposit"
    return {
        "question": f"Where do structural and lithological controls intersect to form ore traps in this {dep}?",
        "answer": (f"Ore traps form where {structs[0]} intersect reactive host lithologies ({', '.join(rocks[:3])}). "
                   f"These intersection zones create localized physico-chemical gradients "
                   f"(pressure drop, pH change, redox shift) that trigger metal precipitation "
                   f"in structurally-prepared ground.")
    }


@template("structural_control", ["structural_controls", "metallogenic_belt"])
def qa_structural_regional_context(r):
    structs = r["structural_controls"]
    belt = r["metallogenic_belt"]
    return {
        "question": f"How do the local ore-controlling structures relate to the regional structural framework of the {belt}?",
        "answer": (f"Local structures ({', '.join(structs[:3])}) are genetically linked to the regional "
                   f"structural architecture of the {belt}. First-order regional structures controlled "
                   f"magma/fluid ascent pathways, while second- and third-order splays and "
                   f"subsidiary structures at the deposit scale created the actual ore-hosting sites.")
    }


# ═══ 维度5b: 矿物共生 — 进阶空间问题 ═══

@template("mineral_assemblage", ["minerals_mentioned", "alteration", "deposit_type"], min_list_len={"minerals_mentioned": 3})
def qa_mineral_alteration_spatial(r):
    mins = r["minerals_mentioned"]
    alt = r["alteration"]
    dep = deposit_label(r["deposit_type"]) or "deposit"
    alt_str = ", ".join(alt) if isinstance(alt, list) else str(alt)
    return {
        "question": f"How does the mineral assemblage relate spatially to the alteration zonation in this {dep}?",
        "answer": (f"The ore minerals ({', '.join(mins[:5])}) occur within zones of {alt_str}. "
                   f"Spatial correlation between sulfide species and alteration type provides "
                   f"a three-dimensional framework: high-temperature Cu-Fe sulfides associate with "
                   f"proximal (inner) alteration, while Pb-Zn sulfides and low-temperature phases "
                   f"associate with outer alteration halos.")
    }


@template("mineral_assemblage", ["minerals_mentioned", "structural_controls"], min_list_len={"minerals_mentioned": 3})
def qa_mineral_structural_control(r):
    mins = r["minerals_mentioned"]
    structs = r["structural_controls"]
    return {
        "question": "Is there a spatial correlation between mineral assemblage variation and structural features?",
        "answer": (f"The mineral suite ({', '.join(mins[:6])}) shows spatial association with {', '.join(structs[:3])}. "
                   f"Higher-grade sulfide concentrations tend to occur at structural intersections, "
                   f"dilational jogs, and zones of enhanced permeability, "
                   f"while lower-grade disseminated mineralization extends into the less deformed wallrock.")
    }


# ═══ 维度6b: 时空演化 — 进阶空间问题 ═══

@template("temporal_spatial", ["commodities", "structural_controls", "deposit_type"], min_list_len={"commodities": 2})
def qa_metal_structural_zoning(r):
    comms = r["commodities"]
    structs = r["structural_controls"]
    dep = deposit_label(r["deposit_type"]) or "deposit"
    return {
        "question": f"How are different metals spatially distributed relative to structural controls in this {dep}?",
        "answer": (f"The {', '.join(comms)} metal suite shows spatial zonation relative to {structs[0]}. "
                   f"Cu (±Au) tends to concentrate in the core zone proximal to the main fluid conduit, "
                   f"while Pb, Zn, and Ag migrate outward along subsidiary structures to form peripheral "
                   f"halos. This metal zoning pattern is a powerful exploration tool for targeting "
                   f"concealed high-grade cores.")
    }


@template("temporal_spatial", ["ages_ma", "metallogenic_belt", "deposit_type"])
def qa_age_belt_evolution(r):
    ages = r["ages_ma"]
    belt = r["metallogenic_belt"]
    dep = deposit_label(r["deposit_type"]) or "deposit"
    if isinstance(ages, list):
        ages_str = ", ".join([str(a) for a in ages[:5]])
    else:
        ages_str = str(ages)
    return {
        "question": f"How does the mineralization age relate to the tectonic evolution of the {belt}?",
        "answer": (f"Mineralization at {ages_str} Ma places the {dep} within the metallogenic "
                   f"history of the {belt}. This age constrains the ore-forming event to a discrete "
                   f"geodynamic window, enabling correlation with coeval deposits elsewhere in the belt "
                   f"and reconstruction of the regional spatial-temporal pattern of mineralization.")
    }


# ═══ 新维度7: 综合空间模型 (Cross-cutting spatial reasoning) ═══

@template("spatial_model", ["host_rocks", "structural_controls", "minerals_mentioned", "deposit_type"],
          min_list_len={"minerals_mentioned": 3})
def qa_integrated_spatial_model(r):
    dep_code = r["deposit_type"]
    dep = deposit_label(dep_code) or "deposit"
    rocks = r["host_rocks"]
    structs = r["structural_controls"]
    mins = r["minerals_mentioned"]
    fluid = FLUID_DESC.get(dep_code, "hydrothermal fluids")
    return {
        "question": f"Synthesize the spatial ore genesis model: how do host rocks, structures, and mineral assemblages define the 3D architecture of this {dep}?",
        "answer": (f"The spatial model integrates three controls: "
                   f"(1) Host rocks ({', '.join(rocks[:3])}) provided chemical reactivity and porosity; "
                   f"(2) Structures ({', '.join(structs[:3])}) channeled {fluid}; "
                   f"(3) Mineral assemblage ({', '.join(mins[:4])}) records progressive fluid cooling "
                   f"and metal precipitation from core to periphery. "
                   f"Together, these define a 3D ore shell where grade decreases outward from "
                   f"structural-lithological intersection zones.")
    }


@template("spatial_model", ["metallogenic_belt", "tectonic_setting", "structural_controls", "deposit_type"])
def qa_multiscale_spatial(r):
    belt = r["metallogenic_belt"]
    tect = r["tectonic_setting"]
    structs = r["structural_controls"]
    dep = deposit_label(r["deposit_type"]) or "deposit"
    return {
        "question": f"Describe the multi-scale spatial controls on this {dep}, from regional to deposit scale.",
        "answer": (f"Regional scale: The {belt} ({tect}) defines the metallogenic province. "
                   f"District scale: Clusters of deposits align along first-order structures. "
                   f"Deposit scale: Ore is localized by {', '.join(structs[:3])} "
                   f"at structural complexity zones (bends, jogs, intersections). "
                   f"This nested hierarchy of controls is characteristic of {dep} systems worldwide.")
    }


@template("spatial_model", ["host_rocks", "alteration", "minerals_mentioned", "deposit_type"],
          min_list_len={"minerals_mentioned": 4})
def qa_proximal_distal_gradient(r):
    dep = deposit_label(r["deposit_type"]) or "deposit"
    rocks = r["host_rocks"]
    alt = r["alteration"]
    mins = r["minerals_mentioned"]
    alt_str = " → ".join(alt) if isinstance(alt, list) else str(alt)
    return {
        "question": f"What proximal-to-distal spatial gradients exist in alteration, mineralogy, and geochemistry around this {dep}?",
        "answer": (f"Proximal zone (ore center): Intense alteration ({alt[0] if isinstance(alt, list) else alt}), "
                   f"high-temperature sulfides ({', '.join(mins[:3])}), highest metal grades. "
                   f"Medial zone: Transitional alteration and mixed sulfide assemblages. "
                   f"Distal zone: Weak alteration ({alt[-1] if isinstance(alt, list) and len(alt)>1 else 'propylitic'}), "
                   f"low-temperature minerals, geochemical halo only. "
                   f"These gradients extend over scales of tens to hundreds of meters in {dep} systems.")
    }


# --- Exploration Vectoring ---

@template("exploration", ["structural_controls", "minerals_mentioned", "deposit_type"],
          min_list_len={"minerals_mentioned": 3})
def qa_exploration_vector(r):
    structs = r["structural_controls"]
    mins = r["minerals_mentioned"]
    dep = deposit_label(r["deposit_type"]) or "deposit"
    return {
        "question": f"How would you use spatial patterns of structure and mineralization to vector toward undiscovered ore in this {dep}?",
        "answer": (f"Exploration vectors: (1) Follow {structs[0]} regionally—ore clusters along these features; "
                   f"(2) Target intersections of {structs[0]} with subsidiary structures "
                   f"({', '.join(structs[1:3]) if len(structs)>1 else 'splays'}); "
                   f"(3) Increasing {mins[0]} relative to {mins[2] if len(mins)>2 else 'pyrite'} "
                   f"signals proximity to ore; (4) Map the alteration footprint as a first-pass target.")
    }


@template("exploration", ["alteration", "host_rocks", "deposit_type"])
def qa_exploration_footprint(r):
    alt = r["alteration"]
    rocks = r["host_rocks"]
    dep = deposit_label(r["deposit_type"]) or "deposit"
    alt_str = ", ".join(alt) if isinstance(alt, list) else str(alt)
    return {
        "question": f"How does the alteration footprint guide exploration targeting for this {dep}?",
        "answer": (f"The alteration halo ({alt_str}) extends well beyond the ore boundary, "
                   f"providing a larger target than ore itself. In {', '.join(rocks[:3])}, "
                   f"alteration is mappable by spectral (SWIR) or lithogeochemical methods. "
                   f"Exploration should move inward from the outermost alteration fringe "
                   f"toward increasing intensity and temperature.")
    }


@template("exploration", ["commodities", "structural_controls", "deposit_type"],
          min_list_len={"commodities": 2})
def qa_exploration_dispersion(r):
    comms = r["commodities"]
    structs = r["structural_controls"]
    dep = deposit_label(r["deposit_type"]) or "deposit"
    return {
        "question": f"What geochemical dispersion halo pattern characterizes this {dep}, and how does structure control it?",
        "answer": (f"The {', '.join(comms)} element suite disperses along {structs[0]}, "
                   f"forming an elongated geochemical anomaly. Pathfinder elements (As, Sb, Hg) "
                   f"define the outer anomaly boundary (furthest travel). The core Cu-Au anomaly "
                   f"is narrower and marks actual ore. This asymmetric halo geometry "
                   f"reflects structurally-controlled fluid flow.")
    }


# --- Comparative Spatial Reasoning ---

@template("comparative", ["deposit_type", "host_rocks", "structural_controls"])
def qa_compare_geometry(r):
    dep_code = r["deposit_type"]
    dep = deposit_label(dep_code) or "deposit"
    rocks = r["host_rocks"]
    structs = r["structural_controls"]
    if "PORP" in (dep_code or ""):
        comp = ("Unlike tabular vein-type deposits, this porphyry has a roughly cylindrical "
                "geometry centered on the intrusion, with grade decreasing radially outward.")
    elif "OROG" in (dep_code or ""):
        comp = ("Unlike disseminated porphyry systems, this orogenic gold deposit is strongly "
                "linear, controlled by the hosting shear zone, with ore shoots plunging along lineations.")
    elif "EPITH" in (dep_code or "") or "HS" in (dep_code or "") or "LS" in (dep_code or ""):
        comp = ("Unlike deeper porphyry systems, this epithermal has a shallow, vertically restricted "
                "geometry. Boiling horizons create sub-horizontal high-grade zones within 1-2 km of paleosurface.")
    elif dep_code == "SKARN":
        comp = ("Unlike structure-controlled veins, this skarn has irregular geometry controlled by "
                "the intrusion-carbonate contact, forming lenticular bodies along reactive horizons.")
    else:
        comp = (f"This {dep} geometry reflects interplay between host rocks ({', '.join(rocks[:2])}) "
                f"and structures ({', '.join(structs[:2])}), distinct from purely vein-controlled systems.")
    return {
        "question": f"How does the 3D geometry of this {dep} differ from other deposit types?",
        "answer": comp
    }


@template("comparative", ["deposit_type", "tectonic_setting", "metallogenic_belt"])
def qa_compare_tectonic_niche(r):
    dep = deposit_label(r["deposit_type"]) or "deposit"
    tect = r["tectonic_setting"]
    belt = r["metallogenic_belt"]
    return {
        "question": f"What spatial position does this {dep} occupy within the tectonic architecture of the {belt}?",
        "answer": (f"Within the {tect} framework of the {belt}, this {dep} occupies a specific "
                   f"spatial niche. Porphyry-epithermal systems form in the arc axis above subducting slabs. "
                   f"IOCG deposits form in back-arc or transpressional settings. "
                   f"Orogenic gold forms in accretionary orogens. "
                   f"This deposit's position constrains available fluid sources and metal endowment.")
    }


# --- Scale & Geometry Questions ---

@template("spatial_model", ["structural_controls", "deposit_type", "commodities", "host_rocks"],
          min_list_len={"commodities": 2})
def qa_deposit_dimensions(r):
    dep = deposit_label(r["deposit_type"]) or "deposit"
    structs = r["structural_controls"]
    comms = r["commodities"]
    rocks = r["host_rocks"]
    return {
        "question": f"What spatial dimensions and geometry are expected for this {dep}, given its structural and lithological setting?",
        "answer": (f"Given the primary control by {structs[0]} cutting through {', '.join(rocks[:2])}, "
                   f"ore bodies in this {dep} system likely extend 100s-1000s of meters along "
                   f"{structs[0]}, with widths of 10s-100s meters perpendicular. "
                   f"The {', '.join(comms[:3])} mineralization concentrates in elongate shoots "
                   f"at zones of maximum dilation or lithological reactivity along {structs[0]}.")
    }


@template("spatial_model", ["host_rocks", "deposit_type", "metallogenic_belt"])
def qa_depth_of_formation(r):
    dep_code = r["deposit_type"]
    dep = deposit_label(dep_code) or "deposit"
    belt = r["metallogenic_belt"]
    if "EPITH" in (dep_code or "") or "HS" in (dep_code or "") or "LS" in (dep_code or ""):
        depth = "shallow crustal levels (< 1-2 km paleodepth)"
    elif "PORP" in (dep_code or ""):
        depth = "moderate crustal depths (1-5 km below paleosurface)"
    elif "OROG" in (dep_code or ""):
        depth = "mid-crustal levels (5-15 km) along major shear zones"
    elif dep_code == "SKARN":
        depth = "shallow to moderate depths at the intrusion-wallrock contact (1-5 km)"
    elif dep_code == "VMS":
        depth = "at or near the seafloor in a submarine volcanic environment"
    else:
        depth = "variable crustal levels depending on the ore-forming process"
    return {
        "question": f"At what crustal depth did this {dep} form, and what does this imply for its preservation and spatial exposure?",
        "answer": (f"This {dep} in the {belt} formed at {depth}. "
                   f"Deposits formed at shallower levels are more easily eroded but also more accessible; "
                   f"deeper-formed deposits require greater uplift/erosion for surface exposure. "
                   f"The current erosion level determines which vertical zone of the system is exposed "
                   f"and thus which spatial features (root, core, or top) are observable.")
    }


@template("exploration", ["host_rocks", "minerals_mentioned", "structural_controls", "deposit_type"],
          min_list_len={"minerals_mentioned": 4})
def qa_exploration_targeting_criteria(r):
    dep = deposit_label(r["deposit_type"]) or "deposit"
    rocks = r["host_rocks"]
    mins = r["minerals_mentioned"]
    structs = r["structural_controls"]
    return {
        "question": f"What are the key spatial targeting criteria for finding additional {dep} mineralization in this geological setting?",
        "answer": (f"Targeting criteria (from regional to local): "
                   f"(1) Favorable host lithology: {', '.join(rocks[:3])}; "
                   f"(2) Structural complexity: intersections and bends in {structs[0]}; "
                   f"(3) Alteration zoning: map outer halo inward toward increasing intensity; "
                   f"(4) Indicator minerals: increasing {mins[0]}/{mins[1]} ratio toward ore; "
                   f"(5) Geochemical anomalies: multi-element (Cu, Au, As, Mo) coincident with structural targets. "
                   f"All criteria should spatially converge at the highest-priority drill targets.")
    }

# ═══ 维度3: 控矿构造 ═══

@template("structural_control", ["structural_controls", "deposit_type"])
def qa_structural_spatial(r):
    structs = r["structural_controls"]
    dep_code = r["deposit_type"]
    dep = deposit_label(dep_code) or "deposit"
    structs_str = ", ".join(structs)
    desc = STRUCT_DESC.get(dep_code, "These structures controlled the geometry and distribution of ore bodies.")
    return {
        "question": f"How do structural features control the spatial distribution of ore in this {dep} system?",
        "answer": f"Key structural controls include: {structs_str}. {desc}"
    }


@template("structural_control", ["structural_controls"])
def qa_structural_hierarchy(r):
    structs = r["structural_controls"]
    if len(structs) < 2:
        return None
    primary = structs[0]
    secondary = ", ".join(structs[1:])
    return {
        "question": "What is the hierarchy of structural controls, from regional to local scale?",
        "answer": (f"The primary ore-controlling structure is {primary}, which defines the overall geometry "
                   f"of the mineralized zone. Secondary structures ({secondary}) created local dilation "
                   f"and permeability enhancement that localized high-grade ore shoots.")
    }


# ═══ 维度4: 蚀变分带 ═══

@template("alteration_zonation", ["alteration", "deposit_type"])
def qa_alteration_zoning(r):
    alt = r["alteration"]
    dep_code = r["deposit_type"]
    dep = deposit_label(dep_code) or "deposit"
    # Skip if too few alteration types for meaningful zonation
    if isinstance(alt, list) and len(alt) < 3:
        return None
    if isinstance(alt, list):
        alt_str = " → ".join(alt)
        n = len(alt)
    else:
        alt_str = str(alt)
        n = 1
    if n >= 3:
        spatial = (f"The zonation ({alt_str}) records progressive change in fluid conditions "
                   f"from proximal to distal. Inner zones ({alt[0]}) indicate highest temperatures, "
                   f"while outer zones ({alt[-1]}) reflect cooler, more distal conditions.")
    else:
        spatial = f"The alteration assemblage ({alt_str}) constrains the thermal and chemical environment of ore formation."
    return {
        "question": f"What does the alteration zonation reveal about the spatial geometry of the {dep} hydrothermal system?",
        "answer": spatial
    }


# ═══ 维度5: 矿物空间共生 ═══

@template("mineral_assemblage", ["minerals_mentioned", "deposit_type"], min_list_len={"minerals_mentioned": 3})
def qa_mineral_zonation(r):
    mins = r["minerals_mentioned"]
    dep_code = r["deposit_type"]
    dep = deposit_label(dep_code) or "deposit"
    ore_kw = ["chalcopyrite", "pyrite", "galena", "sphalerite", "molybdenite",
              "bornite", "gold", "silver", "arsenopyrite", "magnetite", "hematite",
              "chalcocite", "covellite", "enargite", "tennantite", "tetrahedrite"]
    gangue_kw = ["quartz", "calcite", "dolomite", "fluorite", "barite",
                 "sericite", "chlorite", "epidote", "feldspar", "albite", "orthoclase"]
    ore = [m for m in mins if any(kw in m.lower() for kw in ore_kw)]
    gangue = [m for m in mins if any(kw in m.lower() for kw in gangue_kw)]
    parts = []
    if ore: parts.append(f"ore minerals ({', '.join(ore[:6])})")
    if gangue: parts.append(f"gangue/alteration minerals ({', '.join(gangue[:6])})")
    fluid = FLUID_DESC.get(dep_code, "hydrothermal fluids")
    return {
        "question": f"What does the mineral assemblage indicate about formation conditions and spatial zonation of this {dep}?",
        "answer": (f"The assemblage comprises {' and '.join(parts)}. "
                   f"This paragenesis is consistent with deposition from {fluid}. "
                   f"Spatial zoning is expected, with higher-temperature sulfides proximal to the fluid source "
                   f"and lower-temperature phases in distal positions.")
    }


@template("mineral_assemblage", ["minerals_mentioned"], min_list_len={"minerals_mentioned": 5})
def qa_mineral_vector(r):
    mins = r["minerals_mentioned"]
    return {
        "question": "Which minerals can serve as spatial vectors toward higher-grade ore zones?",
        "answer": (f"From the identified suite ({', '.join(mins[:8])}), increasing sulfide abundance "
                   f"relative to barren pyrite, and transitions from distal alteration minerals "
                   f"(chlorite, epidote) to proximal assemblages (biotite, K-feldspar, sericite) "
                   f"provide directional vectors toward the ore center.")
    }


# ═══ 维度6: 时空演化 ═══

@template("temporal_spatial", ["ages_ma", "deposit_type"])
def qa_age_spatial(r):
    ages = r["ages_ma"]
    dep = deposit_label(r["deposit_type"]) or "deposit"
    if isinstance(ages, list):
        ages_str = ", ".join([str(a) for a in ages[:5]])
        span = f"spanning {min(ages)}-{max(ages)} Ma" if len(ages) >= 2 else f"at {ages[0]} Ma"
    else:
        ages_str = str(ages)
        span = f"at {ages} Ma"
    return {
        "question": f"What is the geochronological age, and how does it constrain the spatial-temporal evolution of this {dep}?",
        "answer": (f"Radiometric dating yields {ages_str} Ma ({span}). "
                   f"This timing constrains mineralization relative to regional magmatic and tectonic activity, "
                   f"linking ore genesis to the geodynamic evolution of the host terrane.")
    }


@template("temporal_spatial", ["commodities", "metallogenic_belt", "deposit_type"], min_list_len={"commodities": 2})
def qa_metal_zoning(r):
    comms = r["commodities"]
    belt = r["metallogenic_belt"]
    dep = deposit_label(r["deposit_type"]) or "deposit"
    comms_str = ", ".join(comms)
    return {
        "question": f"What does the {comms_str} metal association reveal about thermal gradients in this {dep} system?",
        "answer": (f"The {comms_str} association reflects a temperature-controlled precipitation sequence. "
                   f"Highest-temperature metals (Cu, Mo) deposited first at ~400-600°C near the heat source, "
                   f"while lower-temperature metals (Pb, Zn, Ag) precipitated at ~200-350°C in cooler, "
                   f"more distal positions. This thermal gradient creates a predictable spatial metal zonation "
                   f"pattern that can be mapped across the {belt} at both deposit and district scales.")
    }


# ═══ 生成引擎 ═══

TIER_A_DIMS = {'spatial_location', 'spatial_model', 'structural_control', 'temporal_spatial'}


def generate_qa_for_record(record):
    results = []
    for tmpl in TEMPLATES:
        if tmpl["dimension"] not in TIER_A_DIMS:
            continue
        if not all(record.get(f) for f in tmpl["required_fields"]):
            continue
        skip = False
        for field, min_len in tmpl["min_list_len"].items():
            val = record.get(field)
            if isinstance(val, list) and len(val) < min_len:
                skip = True
                break
        if skip:
            continue
        qa = tmpl["builder"](record)
        if qa is None:
            continue
        uid_raw = f"{record['paper_id']}::{tmpl['dimension']}::{tmpl['builder'].__name__}"
        uid = hashlib.md5(uid_raw.encode()).hexdigest()[:12]
        results.append({
            "id": f"qa_{uid}",
            "source": "template",
            "paper_id": record["paper_id"],
            "dimension": tmpl["dimension"],
            "template": tmpl["builder"].__name__,
            "deposit_type": record.get("deposit_type"),
            "question": qa["question"],
            "answer": qa["answer"],
        })
    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="矿床空间感知 QA v2")
    parser.add_argument("input", help="trusted.json")
    parser.add_argument("-o", "--output", default="qa_output.jsonl")
    parser.add_argument("--min-fields", type=int, default=2)
    parser.add_argument("--stats", action="store_true")
    args = parser.parse_args()

    data = json.loads(Path(args.input).read_text())
    print(f"输入: {len(data)} 条, {len(TEMPLATES)} 模板")

    all_qa = []
    skipped = 0
    for record in data:
        spatial_fields = ["host_rocks", "structural_controls", "alteration",
                         "minerals_mentioned", "metallogenic_belt", "tectonic_setting",
                         "ages_ma", "commodities", "deposit_type"]
        filled = sum(1 for f in spatial_fields if record.get(f))
        if filled < args.min_fields:
            skipped += 1
            continue
        all_qa.extend(generate_qa_for_record(record))

    with open(Path(args.output), "w", encoding="utf-8") as f:
        for qa in all_qa:
            f.write(json.dumps(qa, ensure_ascii=False) + "\n")

    print(f"输出: {len(all_qa)} 条 → {args.output}")
    print(f"  跳过: {skipped} 条 | 覆盖: {len(data)-skipped} 篇")

    if args.stats:
        from collections import Counter
        dims = Counter(qa["dimension"] for qa in all_qa)
        print(f"\n维度分布:")
        for dim, cnt in dims.most_common():
            print(f"  {dim:25s} {cnt:5d}")

# --- Round 2: Additional templates for +100 QA pairs ---

@template("spatial_location", ["metallogenic_belt", "commodities", "deposit_type"], min_list_len={"commodities": 2})
def qa_belt_metal_endowment(r):
    belt = r["metallogenic_belt"]
    comms = r["commodities"]
    dep = deposit_label(r["deposit_type"]) or "deposit"
    if len(belt) < 20:
        return None
    return {
        "question": f"What is the metal endowment pattern of the {belt}, and how does this {dep} fit within it?",
        "answer": (f"The {belt} is endowed with {', '.join(comms)} mineralization hosted in {dep} systems. "
                   f"This metal endowment reflects the geodynamic history of the belt—specific tectonic episodes "
                   f"generated particular metal associations. The spatial distribution of {comms[0]}-rich deposits "
                   f"along the belt provides a framework for predicting undiscovered resources at analogous positions.")
    }


@template("host_rock_relation", ["host_rocks", "deposit_type", "commodities"], min_list_len={"commodities": 1})
def qa_hostrock_reactivity(r):
    rocks = r["host_rocks"]
    dep = deposit_label(r["deposit_type"]) or "deposit"
    comms = r["commodities"]
    # Data-driven: check what reactive types are actually present
    mafic_kw = ["basalt", "gabbro", "diorite", "andesite", "mafic", "greenstone"]
    carb_kw = ["limestone", "dolomite", "marble", "carbonate", "calc"]
    reduced_kw = ["shale", "black", "graphit", "carbon"]
    reactive_present = []
    for rock in rocks:
        rl = rock.lower()
        if any(k in rl for k in mafic_kw): reactive_present.append(f"mafic lithologies ({rock})")
        if any(k in rl for k in carb_kw): reactive_present.append(f"carbonate units ({rock})")
        if any(k in rl for k in reduced_kw): reactive_present.append(f"reduced sediments ({rock})")
    if not reactive_present:
        # No obviously reactive rocks — skip this template
        return None
    reactive_str = "; ".join(reactive_present[:3])
    return {
        "question": f"Which host lithologies are most chemically reactive for {comms[0]} precipitation, and where spatially would you expect highest grades?",
        "answer": (f"Among the host rocks, the most reactive units are: {reactive_str}. "
                   f"These create redox or pH fronts when intersected by mineralizing fluids, "
                   f"triggering sulfide precipitation. Highest {comms[0]} grades are expected "
                   f"at the contacts between these reactive lithologies and fluid-bearing structures.")
    }


@template("structural_control", ["structural_controls", "minerals_mentioned", "deposit_type"],
          min_list_len={"minerals_mentioned": 3})
def qa_structural_permeability(r):
    structs = r["structural_controls"]
    mins = r["minerals_mentioned"]
    dep = deposit_label(r["deposit_type"]) or "deposit"
    return {
        "question": f"How did structural deformation create permeability for fluid flow and ore deposition in this {dep}?",
        "answer": (f"The structures ({', '.join(structs[:3])}) generated permeability through: "
                   f"(1) brittle fracturing creating open-space for vein fill ({mins[0]}, {mins[1] if len(mins)>1 else 'quartz'}); "
                   f"(2) cataclasis producing porous breccia zones; "
                   f"(3) dilation at structural bends and jogs creating low-pressure sites for fluid convergence. "
                   f"The resulting permeability architecture controlled where {dep} mineralization could precipitate.")
    }


@template("structural_control", ["structural_controls", "deposit_type", "host_rocks"])
def qa_structural_timing(r):
    structs = r["structural_controls"]
    dep_code = r["deposit_type"]
    dep = deposit_label(dep_code) or "deposit"
    rocks = r["host_rocks"]
    # Deposit-type-specific timing interpretation
    if "PORP" in (dep_code or ""):
        timing = (f"In this {dep}, {structs[0]} likely formed both pre- and syn-mineralization. "
                  f"Pre-existing regional faults channeled magma emplacement into {', '.join(rocks[:2])}. "
                  f"Syn-intrusion fracturing ({', '.join(structs[1:3]) if len(structs)>1 else 'stockworks'}) "
                  f"developed as the cooling pluton contracted, creating the stockwork ore zone.")
    elif "OROG" in (dep_code or ""):
        timing = (f"In this orogenic gold system, {structs[0]} were active during metamorphism "
                  f"and represent syn-mineralization structures. Gold precipitated during episodic "
                  f"seismic events (fault-valve mechanism) creating crack-seal vein textures in {rocks[0] if rocks else 'host rocks'}.")
    else:
        timing = (f"In this {dep} hosted in {', '.join(rocks[:2])}, the structures ({', '.join(structs[:2])}) "
                  f"record syn-mineralization deformation: ore minerals fill open fractures and breccia voids, "
                  f"indicating structure and mineralization were contemporaneous. "
                  f"Post-mineralization reactivation may offset ore bodies, complicating 3D geometry.")
    return {
        "question": f"What is the timing relationship between structural deformation and mineralization, and how does it affect ore geometry?",
        "answer": timing
    }


@template("mineral_assemblage", ["minerals_mentioned", "host_rocks", "deposit_type"],
          min_list_len={"minerals_mentioned": 4})
def qa_mineral_wallrock_reaction(r):
    mins = r["minerals_mentioned"]
    rocks = r["host_rocks"]
    dep = deposit_label(r["deposit_type"]) or "deposit"
    return {
        "question": f"How do wall-rock reactions control the spatial distribution of mineral species in this {dep}?",
        "answer": (f"In the {', '.join(rocks[:3])} host, fluid-wallrock reaction produces spatially zoned mineral assemblages. "
                   f"Proximal to fluid conduits: {', '.join(mins[:3])} form by direct precipitation from cooling fluids. "
                   f"At wallrock contacts: reaction minerals form by metasomatism (replacement of host minerals). "
                   f"The spatial arrangement of {', '.join(mins[:4])} thus maps the geometry of fluid-rock interaction fronts.")
    }


@template("mineral_assemblage", ["minerals_mentioned", "commodities", "deposit_type"],
          min_list_len={"minerals_mentioned": 5, "commodities": 2})
def qa_mineral_metal_deportment(r):
    mins = r["minerals_mentioned"]
    comms = r["commodities"]
    dep = deposit_label(r["deposit_type"]) or "deposit"
    return {
        "question": f"How is {comms[0]} distributed among different mineral phases, and what does this mean for spatial grade distribution?",
        "answer": (f"In this {dep}, {comms[0]} resides in {mins[0]} (primary ore mineral) and potentially "
                   f"in other phases ({', '.join(mins[1:4])}). The spatial distribution of these carrier minerals "
                   f"determines where economic grades occur. Primary sulfide zones contain the bulk of {comms[0]}, "
                   f"while supergene enrichment (if present) may redistribute {comms[0]} into secondary minerals "
                   f"at shallower levels, creating a secondary enrichment blanket above the primary ore.")
    }


@template("temporal_spatial", ["commodities", "structural_controls", "host_rocks", "deposit_type"],
          min_list_len={"commodities": 2})
def qa_metal_migration_pathways(r):
    comms = r["commodities"]
    structs = r["structural_controls"]
    rocks = r["host_rocks"]
    dep = deposit_label(r["deposit_type"]) or "deposit"
    return {
        "question": f"What were the spatial pathways of metal migration from source to trap in this {dep}?",
        "answer": (f"Metals ({', '.join(comms[:4])}) migrated from their source through {structs[0]} "
                   f"into the trap site ({', '.join(rocks[:2])}). The migration pathway geometry is recorded by: "
                   f"(1) alteration haloes flanking the conduit structures; "
                   f"(2) decreasing metal grades away from feeders; "
                   f"(3) metal ratio zonation (Cu/Zn, Au/Ag) changing systematically along flow direction. "
                   f"Reconstructing these pathways reveals the plumbing system of the {dep}.")
    }


@template("spatial_model", ["host_rocks", "structural_controls", "deposit_type", "metallogenic_belt"])
def qa_preservation_exposure(r):
    dep = deposit_label(r["deposit_type"]) or "deposit"
    rocks = r["host_rocks"]
    structs = r["structural_controls"]
    belt = r["metallogenic_belt"]
    return {
        "question": f"How does the level of erosion/exposure affect what parts of this {dep} system are observable?",
        "answer": (f"In the {belt}, the current erosion level exposes a specific vertical slice "
                   f"of the {dep} system. If deeply eroded: only roots/feeders visible (structures like {structs[0]}, "
                   f"deep host rocks). If shallowly eroded: upper zones preserved (shallow structures, "
                   f"surface-level host rocks {', '.join(rocks[:2])}). Recognizing which level is exposed "
                   f"guides the search—if only the top is visible, deeper high-grade ore may exist below.")
    }


@template("spatial_model", ["structural_controls", "alteration", "minerals_mentioned", "deposit_type"],
          min_list_len={"minerals_mentioned": 3})
def qa_fluid_flow_architecture(r):
    structs = r["structural_controls"]
    alt = r["alteration"]
    mins = r["minerals_mentioned"]
    dep = deposit_label(r["deposit_type"]) or "deposit"
    alt_str = ", ".join(alt) if isinstance(alt, list) else str(alt)
    return {
        "question": f"What was the 3D fluid flow architecture in this {dep}, based on structural, alteration, and mineralogical evidence?",
        "answer": (f"Fluid flow architecture is reconstructed from: "
                   f"(1) Structures ({', '.join(structs[:2])}) define the plumbing—major conduits and subsidiary channels; "
                   f"(2) Alteration ({alt_str}) maps the thermal/chemical footprint of fluid passage; "
                   f"(3) Minerals ({', '.join(mins[:3])}) record fluid conditions at each point. "
                   f"Together, these reveal an upward-diverging flow pattern: focused flow in deep feeders "
                   f"spreading laterally into permeable horizons at shallower levels.")
    }


@template("exploration", ["structural_controls", "host_rocks", "metallogenic_belt", "deposit_type"])
def qa_exploration_concealed(r):
    structs = r["structural_controls"]
    rocks = r["host_rocks"]
    belt = r["metallogenic_belt"]
    dep = deposit_label(r["deposit_type"]) or "deposit"
    return {
        "question": f"How would you explore for concealed {dep} mineralization beneath cover in the {belt}?",
        "answer": (f"For concealed targets in the {belt}: "
                   f"(1) Map {structs[0]} beneath cover using geophysics (magnetics, gravity, IP); "
                   f"(2) Identify reactive host lithologies ({', '.join(rocks[:2])}) in drillhole intersections; "
                   f"(3) Use pathfinder geochemistry in cover soils/groundwater over buried structures; "
                   f"(4) Model the 3D geometry of known deposits along strike to predict repetitions at depth. "
                   f"The key is translating surface-observable spatial patterns into subsurface predictions.")
    }


@template("comparative", ["deposit_type", "structural_controls", "minerals_mentioned"],
          min_list_len={"minerals_mentioned": 3})
def qa_compare_ore_shoot_controls(r):
    dep = deposit_label(r["deposit_type"]) or "deposit"
    structs = r["structural_controls"]
    mins = r["minerals_mentioned"]
    return {
        "question": f"What controls the location and plunge of ore shoots within this {dep}, and how does this compare to other systems?",
        "answer": (f"Ore shoots in this {dep} are controlled by the intersection of {structs[0]} "
                   f"with {'favorable lithology' if len(structs) < 2 else structs[1]}. "
                   f"The highest grades ({mins[0]}, {mins[1]}) concentrate at these intersections. "
                   f"Shoot plunge follows the line of intersection of two structural planes. "
                   f"This contrasts with stratabound deposits where ore is layer-parallel, "
                   f"and with disseminated porphyries where ore forms shells around the intrusion.")
    }


@template("comparative", ["deposit_type", "host_rocks", "alteration"])
def qa_compare_alteration_width(r):
    dep = deposit_label(r["deposit_type"]) or "deposit"
    rocks = r["host_rocks"]
    alt = r["alteration"]
    alt_str = ", ".join(alt) if isinstance(alt, list) else str(alt)
    return {
        "question": f"How does the width of the alteration halo in this {dep} compare to the ore body width?",
        "answer": (f"In this {dep} hosted in {', '.join(rocks[:2])}, the alteration halo ({alt_str}) "
                   f"typically extends 2-10x wider than the ore body itself. "
                   f"This ratio varies by deposit type: porphyries have wide halos (km-scale), "
                   f"orogenic veins have narrow halos (meters), and SEDEX/VMS have intermediate halos. "
                   f"The halo-to-ore ratio is a key exploration parameter—a wider halo means a bigger target "
                   f"but also means ore is a smaller fraction of the altered zone.")
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="矿床空间感知 QA v2")
    parser.add_argument("input", help="trusted.json")
    parser.add_argument("-o", "--output", default="qa_output.jsonl")
    parser.add_argument("--min-fields", type=int, default=2)
    parser.add_argument("--stats", action="store_true")
    args = parser.parse_args()

    data = json.loads(Path(args.input).read_text())
    print(f"输入: {len(data)} 条, {len(TEMPLATES)} 模板")

    all_qa = []
    skipped = 0
    for record in data:
        spatial_fields = ["host_rocks", "structural_controls", "alteration",
                         "minerals_mentioned", "metallogenic_belt", "tectonic_setting",
                         "ages_ma", "commodities", "deposit_type"]
        filled = sum(1 for f in spatial_fields if record.get(f))
        if filled < args.min_fields:
            skipped += 1
            continue
        all_qa.extend(generate_qa_for_record(record))

    with open(Path(args.output), "w", encoding="utf-8") as f:
        for qa in all_qa:
            f.write(json.dumps(qa, ensure_ascii=False) + "\n")

    print(f"输出: {len(all_qa)} 条 → {args.output}")
    print(f"  跳过: {skipped} 条 | 覆盖: {len(data)-skipped} 篇")

    if args.stats:
        from collections import Counter
        dims = Counter(qa["dimension"] for qa in all_qa)
        print(f"\n维度分布:")
        for dim, cnt in dims.most_common():
            print(f"  {dim:25s} {cnt:5d}")


if __name__ == '__main__':
    main()
