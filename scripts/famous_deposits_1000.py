#!/usr/bin/env python3
"""
超大型著名矿床坐标库 - 目标1000+矿床
数据来源：USGS MRDS, 各国地质调查局, 上市公司年报, 教科书案例

组织方式：
1. 按矿床类型分类
2. 包含世界级矿床 + 大型矿床 + 区域重要矿床
3. 覆盖全球主要矿业国家
"""

# ============================================================================
# 造山型金矿 OROG-AU (~150个)
# ============================================================================
OROG_AU_DEPOSITS = {
    # 南非 Witwatersrand
    "Witwatersrand": {"lat": -26.2, "lon": 27.8, "country": "South Africa"},
    "Vaal Reef": {"lat": -26.9, "lon": 27.1, "country": "South Africa"},
    "Kloof": {"lat": -26.4, "lon": 27.5, "country": "South Africa"},
    "Driefontein": {"lat": -26.4, "lon": 27.5, "country": "South Africa"},
    "Western Deep": {"lat": -26.4, "lon": 27.5, "country": "South Africa"},
    "Tau Tona": {"lat": -26.4, "lon": 27.5, "country": "South Africa"},
    "Mponeng": {"lat": -26.4, "lon": 27.5, "country": "South Africa"},

    # 澳大利亚 Yilgarn
    "Kalgoorlie": {"lat": -30.7, "lon": 121.5, "country": "Australia"},
    "Golden Mile": {"lat": -30.75, "lon": 121.47, "country": "Australia"},
    "Super Pit": {"lat": -30.78, "lon": 121.50, "country": "Australia"},
    "St Ives": {"lat": -31.3, "lon": 121.3, "country": "Australia"},
    "Kambalda": {"lat": -31.2, "lon": 121.7, "country": "Australia"},
    "Granny Smith": {"lat": -28.7, "lon": 120.6, "country": "Australia"},
    "Sunrise Dam": {"lat": -29.2, "lon": 122.3, "country": "Australia"},
    "Wallaby": {"lat": -27.7, "lon": 120.6, "country": "Australia"},
    "Jundee": {"lat": -26.3, "lon": 120.5, "country": "Australia"},
    "Boddington": {"lat": -32.8, "lon": 116.5, "country": "Australia"},
    "Telfer": {"lat": -21.7, "lon": 122.2, "country": "Australia"},
    "Paddington": {"lat": -30.9, "lon": 121.6, "country": "Australia"},
    "Kanowna Belle": {"lat": -30.6, "lon": 121.6, "country": "Australia"},
    "Gruyere": {"lat": -28.5, "lon": 122.0, "country": "Australia"},

    # 加拿大 Abitibi
    "Kirkland Lake": {"lat": 48.15, "lon": -80.03, "country": "Canada"},
    "Timmins": {"lat": 48.47, "lon": -81.33, "country": "Canada"},
    "Dome": {"lat": 48.48, "lon": -81.22, "country": "Canada"},
    "Hollinger": {"lat": 48.48, "lon": -81.20, "country": "Canada"},
    "McIntyre": {"lat": 48.45, "lon": -81.28, "country": "Canada"},
    "Red Lake": {"lat": 51.0, "lon": -93.8, "country": "Canada"},
    "Campbell": {"lat": 51.03, "lon": -93.82, "country": "Canada"},
    "Val-d'Or": {"lat": 48.1, "lon": -77.8, "country": "Canada"},
    "Malartic": {"lat": 48.13, "lon": -78.13, "country": "Canada"},
    "Detour Lake": {"lat": 48.5, "lon": -81.8, "country": "Canada"},
    "Hemlo": {"lat": 48.7, "lon": -85.9, "country": "Canada"},
    "Musselwhite": {"lat": 52.6, "lon": -90.4, "country": "Canada"},
    "Meadowbank": {"lat": 65.1, "lon": -96.0, "country": "Canada"},
    "Lupin": {"lat": 65.8, "lon": -111.2, "country": "Canada"},

    # 中国
    "Jiaodong": {"lat": 37.5, "lon": 120.5, "country": "China"},
    "Linglong": {"lat": 37.3, "lon": 120.7, "country": "China"},
    "Sanshandao": {"lat": 37.4, "lon": 120.2, "country": "China"},
    "Xincheng": {"lat": 37.5, "lon": 120.6, "country": "China"},
    "Jiaojia": {"lat": 37.6, "lon": 120.4, "country": "China"},
    "Sizhuang": {"lat": 37.4, "lon": 120.5, "country": "China"},
    "Yangshan": {"lat": 37.3, "lon": 120.8, "country": "China"},
    "Rushan": {"lat": 36.9, "lon": 121.5, "country": "China"},

    # 西非
    "Ashanti": {"lat": 6.7, "lon": -1.6, "country": "Ghana"},
    "Obuasi": {"lat": 6.2, "lon": -1.7, "country": "Ghana"},
    "Bibiani": {"lat": 6.5, "lon": -2.3, "country": "Ghana"},
    "Ahafo": {"lat": 7.1, "lon": -2.5, "country": "Ghana"},
    "Akyem": {"lat": 6.3, "lon": -0.8, "country": "Ghana"},
    "Geita": {"lat": -2.9, "lon": 32.2, "country": "Tanzania"},
    "Bulyanhulu": {"lat": -3.5, "lon": 32.3, "country": "Tanzania"},
    "North Mara": {"lat": -1.5, "lon": 34.5, "country": "Tanzania"},
    "Buzwagi": {"lat": -3.6, "lon": 32.4, "country": "Tanzania"},
    "Loulo-Gounkoto": {"lat": 13.7, "lon": -10.7, "country": "Mali"},
    "Morila": {"lat": 12.6, "lon": -8.0, "country": "Mali"},
    "Sadiola": {"lat": 13.3, "lon": -11.0, "country": "Mali"},
    "Siguiri": {"lat": 11.4, "lon": -9.2, "country": "Guinea"},
    "Syama": {"lat": 11.3, "lon": -6.0, "country": "Mali"},

    # 中亚
    "Muruntau": {"lat": 41.5, "lon": 64.6, "country": "Uzbekistan"},
    "Kumtor": {"lat": 41.8, "lon": 78.2, "country": "Kyrgyzstan"},
    "Vasilkovskoye": {"lat": 50.3, "lon": 73.1, "country": "Kazakhstan"},

    # 美国
    "Homestake": {"lat": 44.4, "lon": -103.8, "country": "USA"},
    "Cripple Creek": {"lat": 38.7, "lon": -105.2, "country": "USA"},
    "Mother Lode": {"lat": 38.5, "lon": -120.5, "country": "USA"},

    # 巴西
    "Morro do Ouro": {"lat": -15.2, "lon": -43.5, "country": "Brazil"},
    "Cuiabá": {"lat": -20.3, "lon": -43.8, "country": "Brazil"},
    "Lamego": {"lat": -20.4, "lon": -43.5, "country": "Brazil"},

    # 其他
    "Porgera": {"lat": -5.5, "lon": 143.1, "country": "Papua New Guinea"},
    "Lihir": {"lat": -3.1, "lon": 152.6, "country": "Papua New Guinea"},
    "Hidden Valley": {"lat": -7.5, "lon": 147.0, "country": "Papua New Guinea"},
}

# ============================================================================
# Carlin型金矿 CARLIN-AU (~30个)
# ============================================================================
CARLIN_AU_DEPOSITS = {
    "Carlin": {"lat": 40.7, "lon": -116.3, "country": "USA"},
    "Goldstrike": {"lat": 40.9, "lon": -116.3, "country": "USA"},
    "Cortez": {"lat": 40.4, "lon": -116.6, "country": "USA"},
    "Turquoise Ridge": {"lat": 40.5, "lon": -117.2, "country": "USA"},
    "Pipeline": {"lat": 40.9, "lon": -116.3, "country": "USA"},
    "Meikle": {"lat": 40.9, "lon": -116.3, "country": "USA"},
    "Deep Star": {"lat": 40.8, "lon": -116.3, "country": "USA"},
    "Leeville": {"lat": 40.8, "lon": -116.4, "country": "USA"},
    "Gold Quarry": {"lat": 40.6, "lon": -116.2, "country": "USA"},
    "Lone Tree": {"lat": 40.3, "lon": -116.5, "country": "USA"},
    "Marigold": {"lat": 40.6, "lon": -116.9, "country": "USA"},
    "Phoenix": {"lat": 40.9, "lon": -116.4, "country": "USA"},
    "Emigrant": {"lat": 40.3, "lon": -116.7, "country": "USA"},
    "Twin Creeks": {"lat": 41.0, "lon": -117.3, "country": "USA"},
    "Getchell": {"lat": 40.9, "lon": -117.5, "country": "USA"},
    "Jerritt Canyon": {"lat": 41.2, "lon": -115.9, "country": "USA"},
    "Midas": {"lat": 41.2, "lon": -116.7, "country": "USA"},
    "Hollister": {"lat": 40.5, "lon": -116.7, "country": "USA"},
    "Hycroft": {"lat": 40.9, "lon": -118.7, "country": "USA"},
}

# ============================================================================
# 斑岩型 PORPHYRY (~200个)
# ============================================================================
PORPHYRY_DEPOSITS = {
    # 智利
    "Chuquicamata": {"lat": -22.3, "lon": -68.9, "country": "Chile"},
    "El Teniente": {"lat": -34.1, "lon": -70.4, "country": "Chile"},
    "Escondida": {"lat": -24.2, "lon": -69.1, "country": "Chile"},
    "Collahuasi": {"lat": -20.95, "lon": -68.7, "country": "Chile"},
    "Los Bronces": {"lat": -33.15, "lon": -70.3, "country": "Chile"},
    "Andina": {"lat": -32.8, "lon": -70.2, "country": "Chile"},
    "Los Pelambres": {"lat": -31.8, "lon": -70.5, "country": "Chile"},
    "El Salvador": {"lat": -26.2, "lon": -69.7, "country": "Chile"},
    "Centinela": {"lat": -23.3, "lon": -69.5, "country": "Chile"},
    "Radomiro Tomic": {"lat": -22.4, "lon": -68.8, "country": "Chile"},
    "Ministro Hales": {"lat": -22.3, "lon": -68.9, "country": "Chile"},
    "Gabriela Mistral": {"lat": -25.4, "lon": -69.5, "country": "Chile"},
    "Cerro Colorado": {"lat": -19.9, "lon": -69.1, "country": "Chile"},
    "Quebrada Blanca": {"lat": -21.0, "lon": -68.8, "country": "Chile"},
    "Zaldívar": {"lat": -24.1, "lon": -69.0, "country": "Chile"},
    "Candelaria": {"lat": -27.5, "lon": -70.2, "country": "Chile"},
    "Ojos del Salado": {"lat": -27.1, "lon": -69.0, "country": "Chile"},

    # 秘鲁
    "Antamina": {"lat": -9.3, "lon": -77.1, "country": "Peru"},
    "Cerro Verde": {"lat": -16.5, "lon": -71.6, "country": "Peru"},
    "Toromocho": {"lat": -11.4, "lon": -76.1, "country": "Peru"},
    "Las Bambas": {"lat": -14.2, "lon": -72.2, "country": "Peru"},
    "Toquepala": {"lat": -17.2, "lon": -70.6, "country": "Peru"},
    "Cuajone": {"lat": -17.0, "lon": -70.7, "country": "Peru"},
    "Quellaveco": {"lat": -17.1, "lon": -70.6, "country": "Peru"},
    "Constancia": {"lat": -14.3, "lon": -71.7, "country": "Peru"},
    "Mina Justa": {"lat": -15.4, "lon": -75.2, "country": "Peru"},

    # 美国
    "Bingham Canyon": {"lat": 40.5, "lon": -112.2, "country": "USA"},
    "Morenci": {"lat": 33.0, "lon": -109.3, "country": "USA"},
    "Bagdad": {"lat": 34.6, "lon": -113.2, "country": "USA"},
    "Sierrita": {"lat": 31.8, "lon": -111.0, "country": "USA"},
    "Ray": {"lat": 33.2, "lon": -110.9, "country": "USA"},
    "Mission": {"lat": 32.0, "lon": -111.1, "country": "USA"},
    "Safford": {"lat": 32.8, "lon": -109.7, "country": "USA"},
    "Pebble": {"lat": 59.5, "lon": -156.0, "country": "USA"},
    "Resolution": {"lat": 33.3, "lon": -111.1, "country": "USA"},
    "Butte": {"lat": 46.0, "lon": -112.5, "country": "USA"},
    "Yerington": {"lat": 39.0, "lon": -119.1, "country": "USA"},

    # 印尼
    "Grasberg": {"lat": -4.05, "lon": 137.1, "country": "Indonesia"},
    "Ertsberg": {"lat": -4.1, "lon": 137.1, "country": "Indonesia"},
    "Batu Hijau": {"lat": -8.9, "lon": 116.9, "country": "Indonesia"},

    # 蒙古
    "Oyu Tolgoi": {"lat": 43.0, "lon": 106.8, "country": "Mongolia"},
    "Erdenet": {"lat": 49.0, "lon": 104.1, "country": "Mongolia"},

    # 加拿大
    "Highland Valley": {"lat": 50.5, "lon": -121.0, "country": "Canada"},
    "Mount Milligan": {"lat": 55.2, "lon": -124.0, "country": "Canada"},
    "Red Chris": {"lat": 57.7, "lon": -129.8, "country": "Canada"},
    "Morrison": {"lat": 50.0, "lon": -120.9, "country": "Canada"},
    "Gibraltar": {"lat": 52.0, "lon": -122.3, "country": "Canada"},
    "Copper Mountain": {"lat": 49.3, "lon": -120.5, "country": "Canada"},

    # 墨西哥
    "Cananea": {"lat": 30.9, "lon": -110.3, "country": "Mexico"},
    "La Caridad": {"lat": 29.9, "lon": -109.6, "country": "Mexico"},
    "Buenavista": {"lat": 30.8, "lon": -109.6, "country": "Mexico"},

    # 巴拿马
    "Cobre Panama": {"lat": 8.5, "lon": -80.6, "country": "Panama"},
    "Petaquilla": {"lat": 8.6, "lon": -80.6, "country": "Panama"},

    # 澳大利亚
    "Northparkes": {"lat": -32.95, "lon": 148.15, "country": "Australia"},
    "Cadia": {"lat": -33.5, "lon": 149.0, "country": "Australia"},
    "Ridgeway": {"lat": -33.5, "lon": 149.0, "country": "Australia"},
    "Ernest Henry": {"lat": -20.4, "lon": 140.7, "country": "Australia"},
    "Red Dome": {"lat": -17.2, "lon": 144.9, "country": "Australia"},

    # 巴布亚新几内亚
    "Ok Tedi": {"lat": -5.2, "lon": 141.2, "country": "Papua New Guinea"},
    "Panguna": {"lat": -6.3, "lon": 155.5, "country": "Papua New Guinea"},
    "Wafi-Golpu": {"lat": -7.3, "lon": 146.5, "country": "Papua New Guinea"},
    "Frieda River": {"lat": -4.7, "lon": 141.9, "country": "Papua New Guinea"},

    # 菲律宾
    "Tampakan": {"lat": 6.4, "lon": 125.0, "country": "Philippines"},
    "Atlas": {"lat": 9.8, "lon": 125.5, "country": "Philippines"},

    # 中国
    "Yulong": {"lat": 31.4, "lon": 96.5, "country": "China"},
    "Qulong": {"lat": 29.6, "lon": 91.7, "country": "China"},
    "Jiama": {"lat": 30.1, "lon": 91.7, "country": "China"},
    "Pulang": {"lat": 28.0, "lon": 99.5, "country": "China"},
    "Dexing": {"lat": 29.0, "lon": 117.7, "country": "China"},

    # 伊朗
    "Sarcheshmeh": {"lat": 29.8, "lon": 55.7, "country": "Iran"},
    "Sungun": {"lat": 38.8, "lon": 46.4, "country": "Iran"},

    # 哈萨克斯坦
    "Kounrad": {"lat": 47.5, "lon": 74.9, "country": "Kazakhstan"},

    # 俄罗斯
    "Peschanka": {"lat": 65.8, "lon": 175.9, "country": "Russia"},
    "Malmyzh": {"lat": 50.6, "lon": 128.2, "country": "Russia"},

    # 土耳其
    "Çöpler": {"lat": 40.2, "lon": 39.4, "country": "Turkey"},
    "Kisladag": {"lat": 38.3, "lon": 31.3, "country": "Turkey"},

    # 阿根廷
    "Bajo de la Alumbrera": {"lat": -27.3, "lon": -66.6, "country": "Argentina"},
    "Agua Rica": {"lat": -27.4, "lon": -66.2, "country": "Argentina"},
    "Los Azules": {"lat": -31.7, "lon": -70.3, "country": "Argentina"},
    "San Jorge": {"lat": -28.5, "lon": -68.5, "country": "Argentina"},
}

# 续...
# (VMS, SEDEX, IOCG等其他类型...)

def combine_all_deposits():
    """合并所有矿床库"""
    all_deposits =

    # 添加类型标签
    for name, info in OROG_AU_DEPOSITS.items():
        info['type'] = 'OROG-AU'
        all_deposits[name] = info

    for name, info in CARLIN_AU_DEPOSITS.items():
        info['type'] = 'CARLIN-AU'
        all_deposits[name] = info

    for name, info in PORPHYRY_DEPOSITS.items():
        info['type'] = 'PORPHYRY'
        all_deposits[name] = info

    return all_deposits

# 导出主数据库
FAMOUS_DEPOSITS = combine_all_deposits()

if __name__ == "__main__":
    print("=" * 80)
    print("超大型矿床库统计（目标1000+）")
    print("=" * 80)
    print()
    print(f"当前矿床数: {len(FAMOUS_DEPOSITS)}个")
    print()
    print("按类型分布:")
    print(f"  OROG-AU:   {len(OROG_AU_DEPOSITS)}个")
    print(f"  CARLIN-AU: {len(CARLIN_AU_DEPOSITS)}个")
    print(f"  PORPHYRY:  {len(PORPHYRY_DEPOSITS)}个")
    print()
    print("进度: {:.1f}% (目标1000个)".format(len(FAMOUS_DEPOSITS)/1000*100))
    print()
    print("待补充类型:")
    print("  - VMS (目标100个)")
    print("  - SEDEX (目标80个)")
    print("  - IOCG (目标50个)")
    print("  - EPITHERMAL (目标150个)")
    print("  - SKARN (目标100个)")
    print("  - NI-CU-PGE (目标80个)")
    print("  - REE (目标30个)")
    print("  - 其他类型 (目标~300个)")
