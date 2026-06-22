#!/usr/bin/env python3
"""
扩充版著名矿床坐标库
目标：100+世界著名矿床
数据来源：USGS, 各国地质调查局, 教科书案例, 上市公司年报
"""

# 世界著名矿床坐标库（按矿床类型分类）
FAMOUS_DEPOSITS = {
    # ============ OROG-AU (造山型金矿) ============
    "Witwatersrand": {"lat": -26.2, "lon": 27.8, "country": "South Africa", "type": "OROG-AU"},
    "Kalgoorlie": {"lat": -30.7, "lon": 121.5, "country": "Australia", "type": "OROG-AU"},
    "Golden Mile": {"lat": -30.75, "lon": 121.47, "country": "Australia", "type": "OROG-AU"},
    "Homestake": {"lat": 44.4, "lon": -103.8, "country": "USA", "type": "OROG-AU"},
    "Kirkland Lake": {"lat": 48.15, "lon": -80.03, "country": "Canada", "type": "OROG-AU"},
    "Val-d'Or": {"lat": 48.1, "lon": -77.8, "country": "Canada", "type": "OROG-AU"},
    "Timmins": {"lat": 48.47, "lon": -81.33, "country": "Canada", "type": "OROG-AU"},
    "Red Lake": {"lat": 51.0, "lon": -93.8, "country": "Canada", "type": "OROG-AU"},
    "Muruntau": {"lat": 41.5, "lon": 64.6, "country": "Uzbekistan", "type": "OROG-AU"},
    "Kumtor": {"lat": 41.8, "lon": 78.2, "country": "Kyrgyzstan", "type": "OROG-AU"},
    "Jiaodong": {"lat": 37.5, "lon": 120.5, "country": "China", "type": "OROG-AU"},
    "Ashanti": {"lat": 6.7, "lon": -1.6, "country": "Ghana", "type": "OROG-AU"},
    "Obuasi": {"lat": 6.2, "lon": -1.7, "country": "Ghana", "type": "OROG-AU"},
    "Geita": {"lat": -2.9, "lon": 32.2, "country": "Tanzania", "type": "OROG-AU"},
    "Loulo-Gounkoto": {"lat": 13.7, "lon": -10.7, "country": "Mali", "type": "OROG-AU"},

    # ============ CARLIN-AU (卡林型金矿) ============
    "Carlin": {"lat": 40.7, "lon": -116.3, "country": "USA", "type": "CARLIN-AU"},
    "Goldstrike": {"lat": 40.9, "lon": -116.3, "country": "USA", "type": "CARLIN-AU"},
    "Cortez": {"lat": 40.4, "lon": -116.6, "country": "USA", "type": "CARLIN-AU"},
    "Turquoise Ridge": {"lat": 40.5, "lon": -117.2, "country": "USA", "type": "CARLIN-AU"},

    # ============ PORPHYRY (斑岩型) ============
    "Chuquicamata": {"lat": -22.3, "lon": -68.9, "country": "Chile", "type": "PORPHYRY-CU"},
    "El Teniente": {"lat": -34.1, "lon": -70.4, "country": "Chile", "type": "PORPHYRY-CU"},
    "Escondida": {"lat": -24.2, "lon": -69.1, "country": "Chile", "type": "PORPHYRY-CU"},
    "Collahuasi": {"lat": -20.95, "lon": -68.7, "country": "Chile", "type": "PORPHYRY-CU"},
    "Los Bronces": {"lat": -33.15, "lon": -70.3, "country": "Chile", "type": "PORPHYRY-CU"},
    "Grasberg": {"lat": -4.05, "lon": 137.1, "country": "Indonesia", "type": "PORPHYRY-CU-AU"},
    "Oyu Tolgoi": {"lat": 43.0, "lon": 106.8, "country": "Mongolia", "type": "PORPHYRY-CU-AU"},
    "Bingham Canyon": {"lat": 40.5, "lon": -112.2, "country": "USA", "type": "PORPHYRY-CU-MO"},
    "Morenci": {"lat": 33.0, "lon": -109.3, "country": "USA", "type": "PORPHYRY-CU"},
    "Resolution": {"lat": 33.3, "lon": -111.1, "country": "USA", "type": "PORPHYRY-CU"},
    "Pebble": {"lat": 59.5, "lon": -156.0, "country": "USA", "type": "PORPHYRY-CU-AU"},
    "Northparkes": {"lat": -32.95, "lon": 148.15, "country": "Australia", "type": "PORPHYRY-CU-AU"},
    "Cadia": {"lat": -33.5, "lon": 149.0, "country": "Australia", "type": "PORPHYRY-CU-AU"},
    "Ok Tedi": {"lat": -5.2, "lon": 141.2, "country": "Papua New Guinea", "type": "PORPHYRY-CU-AU"},
    "Panguna": {"lat": -6.3, "lon": 155.5, "country": "Papua New Guinea", "type": "PORPHYRY-CU-AU"},
    "Butte": {"lat": 46.0, "lon": -112.5, "country": "USA", "type": "PORPHYRY-CU"},

    # ============ VMS (火山块状硫化物) ============
    "Kidd Creek": {"lat": 48.6, "lon": -81.4, "country": "Canada", "type": "VMS"},
    "Noranda": {"lat": 48.3, "lon": -79.0, "country": "Canada", "type": "VMS"},
    "Horne": {"lat": 48.25, "lon": -79.03, "country": "Canada", "type": "VMS"},
    "Bathurst": {"lat": 47.7, "lon": -65.7, "country": "Canada", "type": "VMS"},
    "Flin Flon": {"lat": 54.8, "lon": -101.9, "country": "Canada", "type": "VMS"},
    "Rosebery": {"lat": -41.8, "lon": 145.5, "country": "Australia", "type": "VMS"},
    "Hellyer": {"lat": -41.6, "lon": 145.4, "country": "Australia", "type": "VMS"},
    "Neves-Corvo": {"lat": 37.6, "lon": -7.9, "country": "Portugal", "type": "VMS"},
    "Rio Tinto": {"lat": 37.7, "lon": -6.6, "country": "Spain", "type": "VMS"},
    "Aljustrel": {"lat": 37.9, "lon": -8.2, "country": "Portugal", "type": "VMS"},

    # ============ SEDEX (沉积喷流型) ============
    "Mount Isa": {"lat": -20.7, "lon": 139.5, "country": "Australia", "type": "SEDEX"},
    "McArthur River": {"lat": -16.4, "lon": 136.1, "country": "Australia", "type": "SEDEX"},
    "Century": {"lat": -18.7, "lon": 138.7, "country": "Australia", "type": "SEDEX"},
    "Broken Hill": {"lat": -31.9, "lon": 141.5, "country": "Australia", "type": "SEDEX"},
    "Red Dog": {"lat": 68.1, "lon": -162.8, "country": "USA", "type": "SEDEX"},
    "Sullivan": {"lat": 49.5, "lon": -116.2, "country": "Canada", "type": "SEDEX"},
    "Rammelsberg": {"lat": 51.9, "lon": 10.4, "country": "Germany", "type": "SEDEX"},
    "Copperbelt": {"lat": -12.8, "lon": 28.2, "country": "Zambia", "type": "SEDEX"},
    "Kamoa-Kakula": {"lat": -10.7, "lon": 25.8, "country": "DR Congo", "type": "SEDEX"},
    "Kipushi": {"lat": -11.8, "lon": 27.3, "country": "DR Congo", "type": "SEDEX"},

    # ============ IOCG (铁氧化物铜金) ============
    "Olympic Dam": {"lat": -30.4, "lon": 136.9, "country": "Australia", "type": "IOCG"},
    "Ernest Henry": {"lat": -20.4, "lon": 140.7, "country": "Australia", "type": "IOCG"},
    "Prominent Hill": {"lat": -29.7, "lon": 135.5, "country": "Australia", "type": "IOCG"},
    "Carajás": {"lat": -6.0, "lon": -50.3, "country": "Brazil", "type": "IOCG"},
    "Salobo": {"lat": -5.8, "lon": -50.5, "country": "Brazil", "type": "IOCG"},
    "Sossego": {"lat": -6.4, "lon": -50.1, "country": "Brazil", "type": "IOCG"},
    "Candelaria": {"lat": -27.5, "lon": -70.2, "country": "Chile", "type": "IOCG"},

    # ============ SKARN (矽卡岩) ============
    "Antamina": {"lat": -9.3, "lon": -77.1, "country": "Peru", "type": "SKARN-CU-ZN"},
    "Mina Justa": {"lat": -15.4, "lon": -75.2, "country": "Peru", "type": "SKARN-CU"},
    "Palabora": {"lat": -24.0, "lon": 31.1, "country": "South Africa", "type": "CARBONATITE-SKARN"},
    "Big Gossan": {"lat": 34.7, "lon": -114.7, "country": "USA", "type": "SKARN"},
    "Daye": {"lat": 30.1, "lon": 114.9, "country": "China", "type": "SKARN"},

    # ============ NI-CU-PGE (镍铜铂族) ============
    "Bushveld": {"lat": -25.5, "lon": 28.5, "country": "South Africa", "type": "PGE-CR"},
    "Sudbury": {"lat": 46.5, "lon": -81.0, "country": "Canada", "type": "NI-CU-PGE"},
    "Norilsk": {"lat": 69.3, "lon": 88.2, "country": "Russia", "type": "NI-CU-PGE"},
    "Voisey's Bay": {"lat": 56.3, "lon": -62.0, "country": "Canada", "type": "NI-CU"},
    "Kambalda": {"lat": -31.2, "lon": 121.7, "country": "Australia", "type": "NI"},
    "Thompson": {"lat": 55.7, "lon": -97.9, "country": "Canada", "type": "NI"},
    "Jinchuan": {"lat": 38.5, "lon": 102.2, "country": "China", "type": "NI-CU"},

    # ============ EPITHERMAL (浅成低温热液) ============
    "Fresnillo": {"lat": 23.2, "lon": -102.9, "country": "Mexico", "type": "EPITHERMAL-AG"},
    "Cerro Rico": {"lat": -19.6, "lon": -65.8, "country": "Bolivia", "type": "EPITHERMAL-AG"},
    "Hishikari": {"lat": 31.6, "lon": 130.7, "country": "Japan", "type": "EPITHERMAL-AU"},
    "Lihir": {"lat": -3.1, "lon": 152.6, "country": "Papua New Guinea", "type": "EPITHERMAL-AU"},
    "Porgera": {"lat": -5.5, "lon": 143.1, "country": "Papua New Guinea", "type": "EPITHERMAL-AU"},
    "Pueblo Viejo": {"lat": 19.0, "lon": -70.2, "country": "Dominican Republic", "type": "EPITHERMAL-AU"},
    "Yanacocha": {"lat": -7.0, "lon": -78.5, "country": "Peru", "type": "EPITHERMAL-AU"},
    "Comstock": {"lat": 39.3, "lon": -119.6, "country": "USA", "type": "EPITHERMAL-AG-AU"},
    "Round Mountain": {"lat": 38.7, "lon": -117.1, "country": "USA", "type": "EPITHERMAL-AU"},

    # ============ REE (稀土) ============
    "Bayan Obo": {"lat": 41.8, "lon": 109.9, "country": "China", "type": "CARBONATITE-REE"},
    "Mountain Pass": {"lat": 35.5, "lon": -115.5, "country": "USA", "type": "CARBONATITE-REE"},
    "Mount Weld": {"lat": -28.9, "lon": 122.4, "country": "Australia", "type": "CARBONATITE-REE"},

    # ============ 铁矿 ============
    "Pilbara": {"lat": -22.5, "lon": 118.5, "country": "Australia", "type": "BIF-FE"},
    "Hamersley": {"lat": -22.8, "lon": 117.5, "country": "Australia", "type": "BIF-FE"},
    "Carajás Iron": {"lat": -6.1, "lon": -50.4, "country": "Brazil", "type": "BIF-FE"},
    "Sishen": {"lat": -27.7, "lon": 23.0, "country": "South Africa", "type": "BIF-FE"},
    "Kiruna": {"lat": 67.9, "lon": 20.2, "country": "Sweden", "type": "KIRUNA-FE"},

    # ============ 其他重要矿床 ============
    "Cerro de Pasco": {"lat": -10.7, "lon": -76.3, "country": "Peru", "type": "POLYMETALLIC"},
    "Tsumeb": {"lat": -19.2, "lon": 17.7, "country": "Namibia", "type": "POLYMETALLIC"},
    "Leadville": {"lat": 39.2, "lon": -106.3, "country": "USA", "type": "POLYMETALLIC"},

    # ============ 西藏/三江 斑岩铜矿 (Tibetan Porphyry Belt) ============
    "Qulong": {"lat": 29.5, "lon": 91.6, "country": "China", "type": "PORPHYRY-CU"},
    "Jiama": {"lat": 29.7, "lon": 92.0, "country": "China", "type": "PORPHYRY-CU-AU"},
    "Yulong": {"lat": 29.2, "lon": 96.4, "country": "China", "type": "PORPHYRY-CU"},
    "Machangqing": {"lat": 26.0, "lon": 100.3, "country": "China", "type": "PORPHYRY-CU-AU"},
    "Pulang": {"lat": 28.5, "lon": 99.3, "country": "China", "type": "PORPHYRY-CU"},
    "Nuri": {"lat": 29.5, "lon": 94.5, "country": "China", "type": "PORPHYRY-CU-AU"},
    "Chongmuda": {"lat": 29.6, "lon": 91.8, "country": "China", "type": "PORPHYRY-CU-AU"},

    # ============ 中国其他重要矿床 ============
    "Dexing": {"lat": 28.9, "lon": 117.7, "country": "China", "type": "PORPHYRY-CU"},
    "Duobaoshan": {"lat": 49.1, "lon": 125.7, "country": "China", "type": "PORPHYRY-CU"},
    "Luming": {"lat": 47.5, "lon": 133.8, "country": "China", "type": "PORPHYRY-MO"},
    "Jiurui": {"lat": 29.8, "lon": 115.8, "country": "China", "type": "SKARN-CU-AU"},

    # ============ 中国钨锡矿（南岭）============
    "Shizhuyuan": {"lat": 25.7, "lon": 113.5, "country": "China", "type": "SKARN-W-SN"},
    "Dajishan": {"lat": 24.9, "lon": 114.7, "country": "China", "type": "GREISEN-W-SN"},
    "Xihuashan": {"lat": 25.5, "lon": 114.5, "country": "China", "type": "GREISEN-W-SN"},
    "Piaotang": {"lat": 25.2, "lon": 114.3, "country": "China", "type": "GREISEN-W-SN"},
    "Nanling": {"lat": 25.0, "lon": 113.0, "country": "China", "type": "GREISEN-W-SN"},
    "Dachang": {"lat": 24.5, "lon": 107.6, "country": "China", "type": "SEDEX"},
    "Huize": {"lat": 26.4, "lon": 103.3, "country": "China", "type": "MVT"},

    # ============ 中国金矿（胶东/秦岭）============
    "Jiaojia": {"lat": 37.5, "lon": 120.4, "country": "China", "type": "OROG-AU"},
    "Linglong": {"lat": 37.4, "lon": 120.4, "country": "China", "type": "OROG-AU"},
    "Sanshandao": {"lat": 37.2, "lon": 120.0, "country": "China", "type": "OROG-AU"},
    "Wenyu": {"lat": 34.5, "lon": 110.0, "country": "China", "type": "OROG-AU"},
    "Yangshan": {"lat": 33.8, "lon": 104.2, "country": "China", "type": "CARLIN-AU"},

    # ============ 中国铁矿 ============
    "Meishan": {"lat": 31.8, "lon": 120.3, "country": "China", "type": "KIRUNA-FE"},
    "Aoshan": {"lat": 31.5, "lon": 119.0, "country": "China", "type": "SKARN-FE"},
    "Makeng": {"lat": 26.0, "lon": 117.3, "country": "China", "type": "SKARN-FE"},

    # ============ 中国稀土/铌 ============
    "Bayan Obo": {"lat": 41.8, "lon": 109.9, "country": "China", "type": "CARBONATITE-REE"},
    "Weishan": {"lat": 27.2, "lon": 100.3, "country": "China", "type": "CARBONATITE-REE"},
    "Ion Adsorption REE": {"lat": 26.0, "lon": 115.0, "country": "China", "type": "LATERITE-REE"},

    # ============ 伊朗/中东 斑岩铜矿 ============
    "Sar Cheshmeh": {"lat": 29.97, "lon": 55.86, "country": "Iran", "type": "PORPHYRY-CU"},
    "Meiduk": {"lat": 30.0, "lon": 55.4, "country": "Iran", "type": "PORPHYRY-CU"},
    "Sungun": {"lat": 38.75, "lon": 46.75, "country": "Iran", "type": "PORPHYRY-CU"},
    "Chah-Firuzeh": {"lat": 30.5, "lon": 56.0, "country": "Iran", "type": "PORPHYRY-CU"},
    "Sarkuh": {"lat": 30.2, "lon": 55.7, "country": "Iran", "type": "PORPHYRY-CU"},

    # ============ 加拿大 铀矿 ============
    "Cigar Lake": {"lat": 58.08, "lon": -104.97, "country": "Canada", "type": "U-UNCONFORMITY"},
    "McArthur River": {"lat": 57.75, "lon": -105.08, "country": "Canada", "type": "U-UNCONFORMITY"},
    "Key Lake": {"lat": 57.22, "lon": -105.6, "country": "Canada", "type": "U-UNCONFORMITY"},
    "Rabbit Lake": {"lat": 58.23, "lon": -103.68, "country": "Canada", "type": "U-UNCONFORMITY"},

    # ============ 加拿大 SEDEX/VMS ============
    "Sullivan": {"lat": 49.78, "lon": -116.2, "country": "Canada", "type": "SEDEX"},
    "Faro": {"lat": 62.2, "lon": -133.4, "country": "Canada", "type": "SEDEX"},
    "Tom": {"lat": 62.5, "lon": -133.5, "country": "Canada", "type": "SEDEX"},
    "Kidd Creek": {"lat": 48.7, "lon": -81.4, "country": "Canada", "type": "VMS"},
    "Brunswick No.12": {"lat": 47.47, "lon": -65.77, "country": "Canada", "type": "VMS"},

    # ============ 澳大利亚 补充 ============
    "Broken Hill": {"lat": -31.95, "lon": 141.47, "country": "Australia", "type": "SEDEX"},
    "McArthur River Zn": {"lat": -16.4, "lon": 136.1, "country": "Australia", "type": "SEDEX"},
    "Cannington": {"lat": -22.0, "lon": 140.8, "country": "Australia", "type": "SEDEX"},
    "Olympic Dam": {"lat": -30.44, "lon": 136.87, "country": "Australia", "type": "IOCG"},
    "Prominent Hill": {"lat": -29.73, "lon": 135.52, "country": "Australia", "type": "IOCG"},
    "Carrapateena": {"lat": -31.9, "lon": 137.9, "country": "Australia", "type": "IOCG"},
    "Mount Tom Price": {"lat": -22.7, "lon": 117.8, "country": "Australia", "type": "BIF-FE"},
    "Hamersley": {"lat": -22.5, "lon": 117.5, "country": "Australia", "type": "BIF-FE"},

    # ============ 欧洲 补充 ============
    "KGHM": {"lat": 51.5, "lon": 16.5, "country": "Poland", "type": "KUPFERSCHIEFER"},
    "Kupferschiefer Poland": {"lat": 51.3, "lon": 16.5, "country": "Poland", "type": "KUPFERSCHIEFER"},
    "Lisheen": {"lat": 52.9, "lon": -7.8, "country": "Ireland", "type": "IRISH-PB-ZN"},
    "Navan": {"lat": 53.7, "lon": -6.7, "country": "Ireland", "type": "IRISH-PB-ZN"},
    "Tara": {"lat": 53.6, "lon": -6.6, "country": "Ireland", "type": "IRISH-PB-ZN"},
    "Bodmin Moor": {"lat": 50.5, "lon": -4.6, "country": "UK", "type": "GREISEN-SN"},
    "Cornish": {"lat": 50.2, "lon": -5.2, "country": "UK", "type": "GREISEN-SN"},
    "Panasqueira": {"lat": 40.2, "lon": -7.7, "country": "Portugal", "type": "GREISEN-W"},

    # ============ 非洲 补充 ============
    "Kamoa-Kakula": {"lat": -10.8, "lon": 25.0, "country": "DRC", "type": "SEDIMENT-CU"},
    "Tenke Fungurume": {"lat": -10.5, "lon": 26.1, "country": "DRC", "type": "SEDIMENT-CU"},
    "Konkola": {"lat": -12.4, "lon": 27.8, "country": "Zambia", "type": "KUPFERSCHIEFER"},
    "Lumwana": {"lat": -12.1, "lon": 25.8, "country": "Zambia", "type": "SEDIMENT-CU"},
    "Oyu Tolgoi": {"lat": 43.0, "lon": 106.8, "country": "Mongolia", "type": "PORPHYRY-CU-AU"},

    # ============ 岩浆硫化物 补充 ============
    "Noril'sk": {"lat": 69.33, "lon": 88.2, "country": "Russia", "type": "NI-CU-PGE"},
    "Voisey's Bay": {"lat": 56.27, "lon": -62.77, "country": "Canada", "type": "NI-CU-PGE"},
    "Sudbury": {"lat": 46.5, "lon": -81.0, "country": "Canada", "type": "NI-CU-PGE"},
    "Kambalda": {"lat": -31.2, "lon": 121.6, "country": "Australia", "type": "NI-CU"},
    "Bushveld PGE": {"lat": -25.5, "lon": 29.0, "country": "South Africa", "type": "PGE-REEF"},
    "Stillwater": {"lat": 45.4, "lon": -109.9, "country": "USA", "type": "PGE-REEF"},
    "Lac des Iles": {"lat": 49.8, "lon": -90.0, "country": "Canada", "type": "PGE-REEF"},

    # ============ 伟晶岩/锂矿 补充 ============
    "Greenbushes": {"lat": -33.8, "lon": 116.1, "country": "Australia", "type": "PEGMATITE-LCT"},
    "Tanco": {"lat": 50.0, "lon": -95.2, "country": "Canada", "type": "PEGMATITE-LCT"},
    "Bikita": {"lat": -20.1, "lon": 31.9, "country": "Zimbabwe", "type": "PEGMATITE-LCT"},
    "Manono": {"lat": -7.3, "lon": 27.4, "country": "DRC", "type": "PEGMATITE-LCT"},
    "Kings Mountain": {"lat": 35.2, "lon": -81.3, "country": "USA", "type": "PEGMATITE-LCT"},

    # ============ 碳酸岩 补充 ============
    "Araxa": {"lat": -19.6, "lon": -46.9, "country": "Brazil", "type": "CARBONATITE-NB"},
    "Catalao": {"lat": -18.2, "lon": -47.9, "country": "Brazil", "type": "CARBONATITE-NB"},
    "Mountain Pass": {"lat": 35.5, "lon": -115.5, "country": "USA", "type": "CARBONATITE-REE"},
    "Phalaborwa": {"lat": -23.9, "lon": 31.1, "country": "South Africa", "type": "CARBONATITE-P"},

    # ============ 砂矿 ============
    "Witwatersrand": {"lat": -26.2, "lon": 27.8, "country": "South Africa", "type": "OROG-AU-PALEO"},
    "Richards Bay": {"lat": -28.8, "lon": 32.1, "country": "South Africa", "type": "PLACER-TI-ZR"},
    "Trail Ridge": {"lat": 30.0, "lon": -82.0, "country": "USA", "type": "PLACER-TI-ZR"},

    # ============ BIF 铁矿 补充 ============
    "Carajas": {"lat": -6.0, "lon": -50.3, "country": "Brazil", "type": "BIF-FE"},
    "Itabira": {"lat": -20.25, "lon": -43.22, "country": "Brazil", "type": "BIF-FE"},
    "Sishen": {"lat": -27.8, "lon": 22.97, "country": "South Africa", "type": "BIF-FE"},

    # ============ 金刚石 ============
    "Orapa": {"lat": -21.32, "lon": 25.36, "country": "Botswana", "type": "KIMBERLITE"},
    "Jwaneng": {"lat": -24.6, "lon": 24.7, "country": "Botswana", "type": "KIMBERLITE"},
    "Argyle": {"lat": -16.7, "lon": 128.4, "country": "Australia", "type": "LAMPROITE-DIAMOND"},

    # ============ IOCG 补充 ============
    "Candelaria": {"lat": -27.5, "lon": -70.1, "country": "Chile", "type": "IOCG"},
    "Ernest Henry": {"lat": -20.44, "lon": 140.7, "country": "Australia", "type": "IOCG"},
    "Salobo": {"lat": -5.8, "lon": -50.5, "country": "Brazil", "type": "IOCG"},
    "Kirunavaara": {"lat": 67.9, "lon": 20.2, "country": "Sweden", "type": "KIRUNA-FE"},
}

def get_deposits_by_type(deposit_type):
    """按类型获取矿床"""
    return {name: info for name, info in FAMOUS_DEPOSITS.items()
            if deposit_type in info['type']}

def get_deposits_by_country(country):
    """按国家获取矿床"""
    return {name: info for name, info in FAMOUS_DEPOSITS.items()
            if info['country'] == country}

if __name__ == "__main__":
    print("=" * 80)
    print("扩充版著名矿床库统计")
    print("=" * 80)
    print()
    print(f"总矿床数: {len(FAMOUS_DEPOSITS)}个")
    print()

    # 按类型统计
    types = {}
    for info in FAMOUS_DEPOSITS.values():
        dtype = info['type'].split('-')[0]
        types[dtype] = types.get(dtype, 0) + 1

    print("按类型分布:")
    for dtype, count in sorted(types.items(), key=lambda x: -x[1]):
        print(f"  {dtype:15} {count}个")

    print()

    # 按国家统计
    countries = {}
    for info in FAMOUS_DEPOSITS.values():
        country = info['country']
        countries[country] = countries.get(country, 0) + 1

    print("按国家分布（Top 10）:")
    for country, count in sorted(countries.items(), key=lambda x: -x[1])[:10]:
        print(f"  {country:20} {count}个")
