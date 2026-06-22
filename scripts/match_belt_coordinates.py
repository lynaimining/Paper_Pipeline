#!/usr/bin/env python3
"""
Metallogenic Belt坐标映射
从成矿带名称推断大致坐标
"""
import json
import sys
from pathlib import Path

# 世界主要成矿带坐标
BELT_COORDINATES = {
    # 南非
    "Bushveld Complex": (-25.5, 28.5),
    "Witwatersrand Basin": (-26.2, 27.8),
    "Barberton Greenstone Belt": (-25.9, 31.1),

    # 澳大利亚
    "Yilgarn Craton": (-30.0, 120.0),
    "Pilbara Craton": (-21.0, 119.0),
    "Pine Creek Orogen": (-13.5, 131.8),
    "Mount Isa": (-20.7, 139.5),
    "Lachlan Orogen": (-35.0, 148.0),
    "New England orogen": (-30.5, 151.5),

    # 加拿大
    "Abitibi Greenstone Belt": (48.5, -78.0),
    "Superior Province": (49.0, -85.0),
    "Slave Province": (63.0, -112.0),

    # 美国
    "Carlin Trend": (40.7, -116.3),
    "Mother Lode": (38.5, -120.5),
    "Battle Mountain": (40.6, -116.9),

    # 南美
    "Quadrilátero Ferrífero": (-20.0, -43.5),
    "Carajás": (-6.0, -50.3),
    "Andes Cordillera": (-15.0, -72.0),

    # 中国
    "Jiaodong": (37.5, 120.5),
    "Sanjiang": (28.0, 99.0),
    "Qinling-Dabie": (33.0, 110.0),

    # 非洲
    "Kibara Belt": (-4.0, 29.3),
    "Damara Belt": (-21.0, 16.0),
    "Copperbelt": (-12.8, 28.2),

    # 欧洲
    "Fennoscandian Shield": (65.0, 25.0),
    "Iberian Pyrite Belt": (37.7, -7.5),

    # 中亚
    "Altaids": (45.0, 85.0),
    "Tien Shan": (42.0, 75.0),

    # 以下为自动扩充条目
    "Delamerian Orogen": (-34.0, 138.5),
    "Eastern Tethyan metallogenic domain": (28.0, 95.0),
    "Fore-Sudetic Monocline": (51.3, 16.5),
    "Kibaran belt": (-5.0, 29.0),
    "Parnassos-Ghiona zone": (38.5, 22.5),
    "Rhenish Massif": (50.5, 7.0),
    "Southwest Indian Ridge": (-45.0, 30.0),
    "São Francisco克拉通南部": (-18.0, -44.0),

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
    "Arabian-Nubian Shield": (22.0, 37.0),
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
    "Altai-Sayan": (52.0, 87.0),
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
    "Cathaysia": (25.0, 115.0),
    "Tibetan Plateau": (32.0, 88.0),
    "Qiangtang terrane": (32.5, 88.0),
    "Songpan-Ganzi": (32.0, 100.0),
    "Indochina Block": (15.0, 103.0),
    "South China Block": (26.0, 113.0),
    "Qinling": (33.5, 108.0),
    "Qinling-Dabie Orogen": (33.0, 113.0),
    "Ailaoshan": (23.5, 102.0),
    "Red River Fault": (22.0, 102.0),
    "Tengchong Block": (25.0, 98.5),
    "Emeishan": (27.5, 102.5),

    # ── 新增：未命中的中国成矿带 ──────────────────────────────
    # 南岭钨锡多金属
    "Nanling": (25.0, 113.0),
    "Nanling metallogenic belt": (25.0, 113.0),
    "Nanling tungsten": (25.0, 113.0),
    "South China tin belt": (25.0, 113.0),
    # 福建/闽西南
    "Southwestern Fujian": (25.5, 117.0),
    "Fujian metallogenic belt": (25.5, 117.0),
    "闽西南成矿带": (25.5, 117.0),
    "福建西南部": (25.5, 117.0),
    "Southwest Fujian": (25.5, 117.0),
    "Fujian Province": (26.0, 118.0),
    # 贵州/滇东
    "Guizhou": (27.0, 107.0),
    "Western Guizhou": (26.0, 104.5),
    "贵州西部": (26.0, 104.5),
    "Yunnan-Guizhou Plateau": (25.5, 105.0),
    # 内蒙/华北
    "Inner Mongolia": (44.0, 113.0),
    "Central Asian Orogenic Belt": (46.0, 100.0),
    "CAOB": (46.0, 100.0),
    "Yanbian": (43.0, 130.0),
    "Yanbian-Dongning": (43.0, 130.0),
    "Eastern Liaoning": (41.0, 123.0),
    # 长江中下游
    "Middle-Lower Yangtze": (30.5, 116.5),
    "Yangtze River Belt": (30.5, 116.5),
    "Middle and Lower Reaches": (30.5, 116.5),
    "Lower Yangtze": (31.0, 118.0),
    "Edong": (30.0, 115.0),
    "鄂东南": (30.0, 115.0),
    # 东北
    "Lesser Xing'an Range": (48.0, 129.0),
    "Xiao Hinggan Mountains": (48.0, 129.0),
    "Heilongjiang": (47.0, 130.0),
    "Jilin": (43.5, 126.0),
    # 新疆
    "Xinjiang": (41.0, 85.0),
    "East Kunlun": (35.5, 97.0),
    "East Kunlun Orogenic Belt": (35.5, 97.0),
    "Kunlun": (36.0, 90.0),
    "Altay": (47.5, 88.5),
    "Chinese Altay": (47.5, 88.5),
    "Bogda": (44.0, 88.0),
    "Kalatag": (43.5, 93.5),
    "Beishan": (41.5, 97.0),
    # 其他中国
    "Henan": (33.8, 113.0),
    "Anhui": (31.5, 117.5),
    "Western Shandong": (35.5, 117.5),
    "Jiaodong Peninsula": (37.5, 121.0),
    "Gangdese": (29.5, 91.0),
    "Gangdese belt": (29.5, 91.0),
    "Gangdese belt eastern": (29.5, 92.0),   # 东段：Qulong、Jiama、Nuri
    "Gangdese belt western": (30.0, 82.0),   # 西段
    "Eastern Gangdese": (29.5, 92.0),
    "Western Gangdese": (30.0, 82.0),
    "Lhasa terrane": (30.0, 91.5),
    "Lhasa terrane eastern": (29.7, 92.5),
    "Sanjiang belt": (28.0, 99.0),
    "Sanjiang belt northern": (28.5, 99.5),  # 北段：Yulong
    "Sanjiang belt southern": (26.0, 100.5), # 南段：Machangqing
    "Sanjiang Tethyan": (27.0, 99.0),
    "Baoshan": (25.0, 99.0),

    # ── 新增：未命中的其他国家成矿带 ────────────────────────────
    # 菲律宾/东南亚
    "Aroroy": (12.5, 123.4),
    "Palawan": (9.8, 118.7),
    "Bicol Arc": (13.0, 123.5),
    "Northern Luzon": (17.5, 121.0),
    # 伊朗/中东
    "Urumieh-Dokhtar": (30.5, 51.0),
    "Sanandaj-Sirjan": (32.0, 48.0),
    "Central Iran": (33.0, 52.0),
    "NE Iran": (36.5, 59.5),
    "Moaleman-Torbat": (35.5, 59.0),
    "Alborz Mountains": (36.5, 52.0),
    # 澳大利亚
    "Bowen Basin": (-23.0, 148.0),
    "Central Queensland": (-23.5, 148.0),
    "Surat Basin": (-27.0, 149.0),
    "Galilee Basin": (-24.0, 144.0),
    # 南美
    "Guiana Shield": (4.0, -60.0),
    "圭亚那地盾": (4.0, -60.0),
    "Amazon Basin": (-3.0, -60.0),
    # 中亚
    "Junggar": (45.0, 85.0),
    "Kazakhstan": (48.0, 67.0),
    "Turgai": (52.0, 65.0),
    # 欧洲
    "Bohemian Massif": (50.0, 15.0),
    "Erzgebirge": (50.5, 13.0),
    "Variscan": (50.0, 12.0),
    "Rhenohercynian": (51.0, 8.0),
    "Lahn Syncline": (50.6, 8.4),

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
    "Grenville Province": (47.0, -75.0),
    "Trans-Hudson Orogen": (55.0, -101.0),
    "Wopmay Orogen": (64.0, -116.0),
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
    # Southeast Asian tin belt 南北跨度大，按论文实际聚焦区分段：
    # 北段（云南/缅甸，NRR 论文集中区）
    "Southeast Asian tin belt": (23.0, 100.0),     # 云南/缅甸段中心（NRR论文集中区）
    "Southeast Asian tin belt northern": (23.0, 100.0),
    "Southeast Asian tin belt southern": (8.0, 101.0),  # 泰国/马来西亚段
    "Malay tin belt": (5.0, 103.0),
}


def _normalize(s):
    """标准化：全角破折号→半角，转小写"""
    return s.replace('–', '-').replace('—', '-').replace('‒', '-').lower()


def match_belt_coordinates(result):
    """从metallogenic_belt推断坐标，同时检索tectonic_setting"""
    belt = (result.get('metallogenic_belt') or '').strip()
    tectonic = (result.get('tectonic_setting') or '').strip()

    # 合并搜索文本
    search_text = f"{belt} {tectonic}".strip()
    if not search_text or result.get('coordinates'):
        return False

    search_norm = _normalize(search_text)

    # 精确匹配 belt
    if belt in BELT_COORDINATES:
        lat, lon = BELT_COORDINATES[belt]
        result['coordinates'] = {
            "latitude": lat, "longitude": lon,
            "precision": "成矿带级",
            "source": f"从成矿带{belt}推断",
            "confidence": 0.6,
            "extraction_method": "成矿带映射"
        }
        return True

    # 模糊匹配（标准化后对比）
    for known_belt, coords in BELT_COORDINATES.items():
        known_norm = _normalize(known_belt)
        if known_norm in search_norm or search_norm in known_norm:
            lat, lon = coords
            result['coordinates'] = {
                "latitude": lat, "longitude": lon,
                "precision": "成矿带级",
                "source": f"从成矿带{belt}推断（匹配{known_belt}）",
                "confidence": 0.5,
                "extraction_method": "成矿带模糊映射"
            }
            return True

    return False


def match_batch(results):
    """批量匹配"""
    matched = 0
    for result in results:
        if 'extracted' in result:
            if match_belt_coordinates(result['extracted']):
                matched += 1
        else:
            if match_belt_coordinates(result):
                matched += 1

    return matched


def main():
    if len(sys.argv) < 2:
        print("用法: python match_belt_coordinates.py <input.json> [output.json]")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else input_file.replace('.json', '_with_belt.json')

    print("=" * 80)
    print("Metallogenic Belt坐标映射")
    print("=" * 80)
    print()
    print(f"成矿带库规模: {len(BELT_COORDINATES)}个主要成矿带")
    print()

    # 读取
    with open(input_file) as f:
        data = json.load(f)

    total = len(data)
    before = sum(1 for r in data if (r.get('extracted') or r).get('coordinates'))

    print(f"输入样本: {total}篇")
    print(f"已有坐标: {before}篇 ({before/total*100:.1f}%)")
    print()

    # 匹配
    matched = match_batch(data)

    # 保存
    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    after = sum(1 for r in data if (r.get('extracted') or r).get('coordinates'))

    print(f"新增坐标: {matched}篇")
    print(f"现有坐标: {after}篇 ({after/total*100:.1f}%)")
    print(f"输出文件: {output_file}")
    print()
    print("✅ 完成")


if __name__ == "__main__":
    main()
