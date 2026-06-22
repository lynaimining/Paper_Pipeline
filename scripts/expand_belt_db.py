#!/usr/bin/env python3
"""
成矿带坐标库扩充工具
两种策略：
1. Nominatim geocoding API（自动）：对标准地名有效
2. 手动补充（兜底）：对专业地质单元名称

以6个缺失案例为切入点，设计可复用的扩充流程
"""
import json
import time
import requests
from pathlib import Path
from match_belt_coordinates import BELT_COORDINATES

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


# ============================================================
# 策略1：Nominatim 自动地理编码
# ============================================================

def geocode_belt(belt_name: str, country: str = None, max_retries: int = 2) -> dict:
    """
    用 Nominatim 查询成矿带/地质单元的坐标
    返回: {"lat": float, "lon": float, "display": str} 或 None
    """
    # 清理名称（去掉中文、括号内容）
    import re
    clean_name = re.sub(r'[一-鿿]+', '', belt_name).strip()
    clean_name = re.sub(r'\([^)]*\)', '', clean_name).strip()
    clean_name = re.sub(r'（[^）]*）', '', clean_name).strip()

    queries = [clean_name]
    if country:
        queries.append(f"{clean_name}, {country}")

    for query in queries:
        if not query.strip():
            continue

        params = {
            "q": query,
            "format": "json",
            "limit": 3,
            "addressdetails": 1,
        }
        if country:
            params["countrycodes"] = country[:2].lower()

        try:
            headers = {"User-Agent": "NRR-GeoExtractor/1.0"}
            resp = requests.get(NOMINATIM_URL, params=params,
                                headers=headers, timeout=10)
            time.sleep(1.1)  # Nominatim 限速：1次/秒

            if resp.status_code == 200:
                results = resp.json()
                if results:
                    best = results[0]
                    return {
                        "lat": float(best["lat"]),
                        "lon": float(best["lon"]),
                        "display": best.get("display_name", ""),
                        "type": best.get("type", ""),
                        "source": "Nominatim"
                    }

        except Exception as e:
            print(f"    Nominatim error: {e}")

    return None


# ============================================================
# 策略2：手动补充（专业地质术语，Nominatim查不到）
# ============================================================

MANUAL_BELT_ADDITIONS = {
    # ---- 以本次缺失案例为基础 ----

    # 非洲
    "Kibaran belt": (-5.0, 29.0),           # 中非，Rwanda-Burundi-Congo
    "Kibaran mobile belt": (-5.0, 29.0),
    "Kibaran": (-5.0, 29.0),

    # 澳大利亚
    "New England orogen": (-30.0, 151.5),   # 东澳大利亚
    "New England Orogen": (-30.0, 151.5),
    "Delamerian Orogen": (-34.0, 138.5),    # 南澳大利亚
    "Delamerian": (-34.0, 138.5),
    "Thomson Orogen": (-26.0, 143.0),       # 昆士兰内陆
    "Hodgkinson Province": (-17.0, 145.0),

    # 欧洲
    "Rhenish Massif": (50.5, 7.0),          # 德国莱茵地盾
    "Rhenohercynian": (50.5, 7.0),
    "Variscan": (50.0, 12.0),               # 中欧华力西构造
    "Fore-Sudetic Monocline": (51.3, 16.5), # 波兰前苏台德斜坡
    "Fore-Sudetic": (51.3, 16.5),
    "Sudetic": (50.8, 16.5),
    "Zechstein basin": (52.0, 14.0),        # 中欧Zechstein盆地
    "Bohemian Massif": (50.0, 16.0),
    "Parnassos-Ghiona zone": (38.5, 22.5),  # 希腊中部
    "Parnassos-Ghiona": (38.5, 22.5),
    "Almopia zone": (41.0, 22.0),           # 希腊北部

    # 巴西
    "São Francisco Craton": (-18.0, -44.0),
    "São Francisco克拉通": (-18.0, -44.0),
    "São Francisco克拉通南部": (-20.0, -43.5),
    "São Francisco craton": (-18.0, -44.0),
    "Quadrilátero Ferrífero": (-20.0, -43.5),
    "Carajás Province": (-6.0, -50.3),
    "Gurupi Belt": (-2.0, -46.0),

    # 中国（扩充Sanjiang/Gangdese）
    "Sanjiang": (28.0, 99.0),
    "Gangdese belt": (29.5, 91.0),
    "Gangdese": (29.5, 91.0),
    "Eastern Tethyan": (28.0, 95.0),
    "Eastern Tethyan metallogenic domain": (28.0, 95.0),
    "Tethyan": (28.0, 90.0),
    "Sanjiang metallogenic belt": (28.0, 99.0),
    "Lhasa terrane": (29.5, 91.5),
    "Yarlung-Zangbo suture": (29.0, 90.0),
    "Yangtze craton": (30.0, 112.0),
    "North China Craton": (39.0, 116.0),
    "Central Asian Orogenic Belt": (45.0, 85.0),
    "Kunlun": (36.0, 90.0),

    # 俄罗斯/中亚（补充）
    "Ural": (60.0, 60.0),
    "Urals": (60.0, 60.0),
    "Southern Urals": (54.0, 58.0),
    "Polar Urals": (67.0, 65.0),
    "Altai-Sayan": (52.0, 87.0),

    # 北美（补充）
    "Appalachian": (38.0, -80.0),
    "Trans-Hudson": (55.0, -101.0),
    "Wopmay Orogen": (64.0, -116.0),
    "Grenville Province": (46.0, -75.0),

    # 中美/加勒比
    "Pacific Ring of Fire": (0.0, -150.0),  # 太宽泛，仅兜底

    # 海底/洋中脊（tectonic_setting只有这个）
    "Southwest Indian Ridge": (-45.0, 30.0),  # 西南印度洋中脊
    "Mid-Atlantic Ridge": (30.0, -40.0),
    "East Pacific Rise": (-15.0, -113.0),

    # 伊比利亚
    "Iberian Pyrite Belt": (37.7, -7.5),
    "Ossa-Morena Zone": (38.5, -7.0),

    # 北非/中东
    "Arabian-Nubian Shield": (22.0, 37.0),
    "Tethys": (30.0, 55.0),

    # 东南亚
    "Indochina Block": (15.0, 103.0),
    "Cathaysia": (25.0, 115.0),

    # ============================================================
    # 系统扩充：全球主要地质构造单元（2024年更新）
    # ============================================================

    # 澳大利亚盆地与克拉通
    "Cooper Basin": (-27.0, 140.0),
    "Cooper-Eromanga Basin": (-27.0, 140.0),
    "Canning Basin": (-21.0, 123.0),
    "Officer Basin": (-28.0, 125.0),
    "Amadeus Basin": (-23.0, 131.0),
    "Georgina Basin": (-22.0, 138.0),
    "Drummond Basin": (-23.0, 147.0),
    "Gawler Craton": (-32.0, 136.0),
    "Broken Hill Block": (-31.9, 141.5),
    "Tennant Creek": (-19.6, 134.2),
    "Capricorn Orogen": (-25.0, 118.0),
    "Arunta Block": (-23.0, 134.0),
    "North Australian Craton": (-18.0, 132.0),
    "Halls Creek Orogen": (-18.0, 127.0),
    "Tanami": (-19.7, 129.7),
    "Warramunga Province": (-19.5, 134.0),
    "Kingash Province": (-20.0, 135.0),

    # 巴布亚新几内亚及太平洋
    "New Guinea Mobile Belt": (-6.0, 145.0),
    "Papuan Fold Belt": (-7.0, 143.0),
    "Sepik Arc": (-4.5, 143.0),
    "Wau Basin": (-7.3, 146.7),
    "Tasman Sea": (-35.0, 160.0),
    "Woodlark Basin": (-9.5, 152.0),
    "Kulumadau": (-9.2, 152.0),

    # 非洲克拉通与造山带
    "West African Craton": (12.0, -5.0),
    "Birimian": (10.0, -2.0),
    "Leo-Man Shield": (9.0, -9.0),
    "Eburnean": (8.0, -5.0),
    "Saharan Metacraton": (20.0, 20.0),
    "Congo Craton": (-5.0, 22.0),
    "Kaapvaal Craton": (-26.0, 28.0),
    "Zimbabwe Craton": (-19.0, 30.0),
    "Limpopo Belt": (-22.5, 29.0),
    "Mozambique Belt": (-15.0, 35.0),
    "Ubendian Belt": (-8.5, 32.0),
    "Irumide Belt": (-14.0, 31.0),
    "Damara Orogen": (-21.0, 17.0),
    "Gariep Belt": (-28.5, 17.0),
    "Namaqua-Natal": (-29.0, 26.0),
    "Saldania Belt": (-33.5, 19.0),
    "Trans-Saharan Belt": (18.0, 5.0),
    "Pharusian Belt": (22.0, 0.0),
    "Hoggar Massif": (23.0, 6.0),
    "Reguibat Shield": (25.0, -9.0),
    "Yetti-Eglab": (28.0, -4.0),
    "Benin-Nigeria Shield": (10.0, 5.0),
    "Borborema Province": (-7.0, -36.0),
    "East African Rift": (-5.0, 36.0),
    "Zambia Copper Belt": (-13.0, 27.0),
    "Katangan": (-12.0, 28.0),
    "Tasman Orogenic Belt": (-30.0, 148.0),

    # 欧洲造山带与地质单元（扩充）
    "Carpathians": (49.0, 22.0),
    "Hellenides": (39.0, 22.0),
    "Dinarides": (44.0, 17.0),
    "Alps": (46.5, 10.0),
    "Pyrenees": (42.5, 1.0),
    "Massif Central": (45.5, 3.0),
    "Armorican Massif": (47.5, -2.0),
    "Tornquist Zone": (55.0, 15.0),
    "Baltic Shield": (64.0, 25.0),
    "East European Platform": (55.0, 40.0),
    "Troodos Ophiolite": (34.9, 32.9),
    "Apennines": (43.0, 13.0),
    "Rhodope Massif": (41.5, 24.5),
    "Transcarpathian Trough": (48.5, 23.0),

    # 中东/北非
    "Arabian Shield": (24.0, 42.0),
    "Neo-Tethys": (28.0, 60.0),
    "Zagros": (31.0, 49.0),
    "Alborz": (36.5, 52.0),
    "Pontides": (41.0, 35.0),
    "Anatolian Plate": (39.0, 35.0),
    "Turkish-Iranian Plateau": (38.0, 44.0),
    "Oman Ophiolite": (23.0, 57.5),
    "Nubian Shield": (19.0, 33.0),

    # 中亚（扩充）
    "Tian Shan": (42.0, 75.0),
    "West Tian Shan": (42.0, 70.0),
    "East Tian Shan": (42.0, 88.0),
    "Altai": (50.0, 88.0),
    "Junggar Basin": (45.5, 85.5),
    "Tarim Basin": (39.0, 83.0),
    "Pamir": (38.5, 73.5),
    "Hindu Kush": (35.5, 71.0),
    "Karakoram": (36.0, 76.0),
    "Mongol-Okhotsk Belt": (52.0, 115.0),
    "Transbaikal": (52.0, 113.0),
    "Baikal Rift": (53.5, 108.0),
    "Enisei Ridge": (58.0, 93.0),
    "Angara Shield": (58.0, 100.0),

    # 中国（扩充）
    "North China Craton": (38.0, 115.0),
    "Yangtze Craton": (30.0, 112.0),
    "Tibetan Plateau": (32.0, 88.0),
    "Qiangtang terrane": (32.5, 88.0),
    "Songpan-Ganzi": (32.0, 100.0),
    "South China Block": (26.0, 113.0),
    "Qinling": (33.5, 108.0),
    "Qinling-Dabie Orogen": (33.0, 113.0),
    "Ailaoshan": (23.5, 102.0),
    "Red River Fault": (22.0, 102.0),
    "Tengchong Block": (25.0, 98.5),
    "Emeishan": (27.5, 102.5),

    # 印度次大陆
    "Dharwar Craton": (14.0, 76.0),
    "Eastern Ghats": (17.0, 82.0),
    "Singhbhum Craton": (22.0, 86.0),
    "Aravalli-Delhi Belt": (26.0, 73.0),
    "Satpura Belt": (22.0, 78.0),
    "Cuddapah Basin": (15.0, 79.0),
    "Deccan Traps": (20.0, 76.0),

    # 北美（扩充）
    "Churchill Province": (60.0, -95.0),
    "Nain Province": (56.0, -62.0),
    "Trans-Hudson Orogen": (55.0, -101.0),
    "Great Bear Magmatic Zone": (65.0, -120.0),
    "Flin Flon Belt": (55.0, -102.0),
    "Snow Lake": (54.8, -101.0),
    "Colorado Mineral Belt": (39.5, -106.0),
    "Basin and Range": (34.0, -112.0),
    "Sierra Nevada": (38.0, -119.0),
    "Appalachians": (37.0, -81.0),
    "Piedmont": (35.5, -80.5),
    "Valley and Ridge": (37.0, -79.0),
    "Blue Ridge": (36.5, -81.5),
    "Great Plains": (43.0, -100.0),

    # 南美（扩充）
    "Amazon Craton": (-3.0, -57.0),
    "São Francisco Craton": (-17.0, -44.0),
    "Río de la Plata Craton": (-33.0, -58.0),
    "Guiana Shield": (4.0, -60.0),
    "Brazilian Shield": (-10.0, -46.0),
    "Tocantins Province": (-12.0, -47.0),
    "Mantiqueira Province": (-22.0, -43.0),
    "Andes": (-20.0, -68.0),
    "Northern Andes": (5.0, -74.0),
    "Central Andes": (-18.0, -68.0),
    "Southern Andes": (-40.0, -71.0),
    "Patagonian Massif": (-45.0, -68.0),
    "IOCG belt Brazil": (-5.0, -50.0),

    # 东亚/东南亚
    "Circum-Pacific Ring of Fire": (0.0, -150.0),
    "Philippine Arc": (13.0, 123.0),
    "Luzon Arc": (17.0, 121.0),
    "Mindanao": (7.5, 125.0),
    "Sulawesi": (-2.0, 121.0),
    "Banda Arc": (-8.0, 124.0),
    "Sunda Arc": (-7.0, 108.0),
    "Sumatra": (-1.0, 102.0),
    "Borneo": (1.0, 114.0),
    "Kontum Massif": (14.5, 108.0),
    "Truong Son Belt": (17.0, 106.0),
}


# ============================================================
# 主流程：自动+手动双策略扩充
# ============================================================

def expand_belt_database(missing_belts: list, countries_map: dict = None) -> dict:
    """
    对缺失的成矿带，先用Nominatim查，查不到再用手动库

    missing_belts: ["Rhenish Massif", "Kibaran belt", ...]
    countries_map: {"Rhenish Massif": "Germany", ...}
    """
    new_entries = {}
    countries_map = countries_map or {}

    print("=" * 70)
    print("成矿带坐标扩充（自动+手动双策略）")
    print("=" * 70)
    print()

    for belt in missing_belts:
        print(f"处理: {belt}")

        # 1. 先查手动库
        for key, coords in MANUAL_BELT_ADDITIONS.items():
            if key.lower() == belt.lower() or key.lower() in belt.lower() or belt.lower() in key.lower():
                new_entries[belt] = coords
                print(f"  ✅ 手动库: {coords}")
                break
        else:
            # 2. 尝试 Nominatim
            country = countries_map.get(belt)
            result = geocode_belt(belt, country)

            if result:
                new_entries[belt] = (result["lat"], result["lon"])
                print(f"  ✅ Nominatim: ({result['lat']:.2f}, {result['lon']:.2f})")
                print(f"     显示: {result['display'][:60]}")
            else:
                print(f"  ❌ 未找到坐标")

        print()

    return new_entries


def generate_updated_belt_db(new_entries: dict) -> str:
    """生成更新后的 match_belt_coordinates.py 代码片段"""
    lines = ["# 自动扩充的成矿带（expand_belt_db.py生成）"]

    for belt, coords in sorted(new_entries.items()):
        lat, lon = coords
        lines.append(f'    "{belt}": ({lat}, {lon}),')

    return "\n".join(lines)


def run_test_after_expansion(new_entries: dict):
    """用扩充后的库重新跑测试数据，统计改善"""
    # 动态扩充BELT_COORDINATES
    expanded = dict(BELT_COORDINATES)
    expanded.update(new_entries)
    expanded.update(MANUAL_BELT_ADDITIONS)

    # 测试数据
    test_file = Path(__file__).parent.parent / "complete_pilot_with_global_v2.json"
    if not test_file.exists():
        test_file = Path(__file__).parent.parent / "complete_pilot_results_cleaned.json"

    with open(test_file) as f:
        data = json.load(f)

    total = len(data)
    before = sum(1 for r in data if (r.get("extracted") or r).get("coordinates"))

    # 应用扩充后的成矿带库
    added = 0
    for r in data:
        rec = r.get("extracted") or r
        if rec.get("coordinates"):
            continue

        belt = (rec.get("metallogenic_belt") or "").strip()
        tectonic = (rec.get("tectonic_setting") or "").strip()

        # 精确匹配 + 模糊匹配
        match_text = f"{belt} {tectonic}".lower()
        for known_belt, coords in expanded.items():
            if known_belt.lower() in match_text or match_text.find(known_belt.lower()) >= 0:
                lat, lon = coords
                rec["coordinates"] = {
                    "latitude": lat,
                    "longitude": lon,
                    "precision": "成矿带级",
                    "source": f"扩充成矿带库-{known_belt}",
                    "confidence": 0.6,
                    "extraction_method": "成矿带推断（扩充版）"
                }
                added += 1
                break

    after = sum(1 for r in data if (r.get("extracted") or r).get("coordinates"))

    print("=" * 70)
    print("扩充后效果")
    print("=" * 70)
    print(f"扩充前: {before}/39 ({before/39*100:.1f}%)")
    print(f"新增:  +{added}篇")
    print(f"扩充后: {after}/39 ({after/39*100:.1f}%)")
    print()

    # 展示新增的
    print("新增坐标详情:")
    for r in data:
        rec = r.get("extracted") or r
        coords = rec.get("coordinates")
        if coords and "扩充" in coords.get("source", ""):
            paper_id = str(rec.get("paper_id", ""))[:50]
            print(f"  ✅ {paper_id}")
            print(f"     成矿带: {str(rec.get('metallogenic_belt') or '')[:40]}")
            print(f"     坐标: ({coords['latitude']:.2f}, {coords['longitude']:.2f})")
            print(f"     来源: {coords['source']}")

    # 仍无坐标
    still_missing = [(r.get("extracted") or r) for r in data
                    if not (r.get("extracted") or r).get("coordinates")]
    if still_missing:
        print()
        print(f"仍无坐标: {len(still_missing)}篇")
        for rec in still_missing:
            print(f"  - {str(rec.get('paper_id',''))[:50]}")
            print(f"    成矿带: {str(rec.get('metallogenic_belt') or '无')}")
            print(f"    构造背景: {str(rec.get('tectonic_setting','无'))[:60]}")

    # 保存
    output = test_file.parent / "complete_pilot_with_expanded_belt.json"
    with open(output, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\n✅ 结果保存: {output}")

    return after


def save_expanded_db(new_entries: dict):
    """将新条目永久追加到 match_belt_coordinates.py"""
    belt_file = Path(__file__).parent / "match_belt_coordinates.py"
    content = belt_file.read_text()

    # 找到BELT_COORDINATES字典的结束位置，在最后一个条目后追加
    insert_marker = "    # 以下为自动扩充条目"

    new_lines = ["\n    # 以下为自动扩充条目"]
    for belt, coords in sorted(new_entries.items()):
        lat, lon = coords
        escaped = belt.replace('"', '\\"')
        new_lines.append(f'    "{escaped}": ({lat}, {lon}),')

    if insert_marker in content:
        # 已有标记，替换
        idx = content.index(insert_marker)
        content = content[:idx] + "\n".join(new_lines)
        # 找到下一个 } 闭合
        rest = content[idx:]
        end = rest.index("\n}")
        content = content[:idx] + "\n".join(new_lines) + rest[end:]
    else:
        # 在字典末尾插入
        content = content.replace(
            "}\n\n\ndef match_belt_coordinates",
            "\n".join(new_lines) + "\n}\n\n\ndef match_belt_coordinates"
        )

    belt_file.write_text(content)
    print(f"✅ 已更新 match_belt_coordinates.py，追加 {len(new_entries)} 个成矿带")


if __name__ == "__main__":
    # ---- 以本次10篇无坐标样本为例 ----
    missing_belts = [
        "Kibaran belt",
        "New England orogen",
        "Delamerian Orogen",
        "São Francisco克拉通南部",
        "Parnassos-Ghiona zone",
        "Rhenish Massif",
        "Fore-Sudetic Monocline",
        "Eastern Tethyan metallogenic domain",
        "Southwest Indian Ridge",
    ]

    countries_map = {
        "Kibaran belt": "Burundi",
        "New England orogen": "Australia",
        "Delamerian Orogen": "Australia",
        "São Francisco克拉通南部": "Brazil",
        "Parnassos-Ghiona zone": "Greece",
        "Rhenish Massif": "Germany",
        "Fore-Sudetic Monocline": "Poland",
        "Eastern Tethyan metallogenic domain": "China",
        "Southwest Indian Ridge": None,
    }

    # Step 1: 扩充
    new_entries = expand_belt_database(missing_belts, countries_map)

    print(f"新增 {len(new_entries)} 个成矿带")
    print()

    # Step 2: 测试效果
    after = run_test_after_expansion(new_entries)

    # Step 3: 保存到 match_belt_coordinates.py
    if new_entries:
        save_expanded_db(new_entries)
