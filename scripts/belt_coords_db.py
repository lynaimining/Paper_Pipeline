"""
地质带/盆地坐标质心数据库
来源：USGS、各国地质调查局、学术文献
精度：地质带级（约50-200km误差）
"""

BELT_COORDS = {
    # ─── 中国成矿带 ───
    "闽西南成矿带": {"lat": 25.5, "lon": 116.5, "country": "China", "alias": ["福建西南部铁多金属成矿带", "Southwestern Fujian metallogenic belt", "SFMB", "华夏地块，闽西南", "永安-梅州坳陷带"]},
    "沁水盆地": {"lat": 36.0, "lon": 112.5, "country": "China", "alias": ["沁水盆地南部", "Qinshui Basin", "Qinshui Coalfield"]},
    "鄂尔多斯盆地": {"lat": 38.0, "lon": 108.0, "country": "China", "alias": ["Ordos Basin", "鄂尔多斯盆地", "四川盆地川西坳陷"]},
    "四川盆地": {"lat": 30.0, "lon": 104.5, "country": "China", "alias": ["Sichuan Basin", "四川盆地西部", "川西坳陷"]},
    "渤海湾盆地": {"lat": 38.5, "lon": 118.0, "country": "China", "alias": ["黄骅坳陷", "Huanghua Depression", "Bohai Bay Basin", "黄骅坳陷，渤海湾盆地"]},
    "松辽盆地": {"lat": 47.0, "lon": 125.0, "country": "China", "alias": ["Songliao Basin", "松辽盆地北部", "徐家围子断陷"]},
    "准噶尔盆地": {"lat": 44.5, "lon": 86.5, "country": "China", "alias": ["Junggar Basin", "准噶尔盆地南缘"]},
    "胶东金矿带": {"lat": 37.0, "lon": 121.0, "country": "China", "alias": ["胶东金矿成矿带", "Jiaodong Gold Belt", "华北克拉通东南缘"]},
    "南岭成矿带": {"lat": 25.0, "lon": 113.0, "country": "China", "alias": ["Nanling metallogenic belt", "华南地区"]},
    "长江中下游成矿带": {"lat": 30.5, "lon": 117.0, "country": "China", "alias": ["Middle-Lower Yangtze River Valley", "中下游成矿带", "Yangtze River Valley metallogenic belt"]},
    "大兴安岭成矿带": {"lat": 46.0, "lon": 119.5, "country": "China", "alias": ["大兴安岭中南部", "Ag多金属成矿带", "大兴安岭"]},
    "西昆仑造山带": {"lat": 37.0, "lon": 79.0, "country": "China", "alias": ["Western Kunlun Orogenic Belt", "Dahongliutan"]},
    "义敦岛弧带": {"lat": 30.0, "lon": 99.0, "country": "China", "alias": ["Yidun-Zhongdian", "Ganze-Litang", "义敦-中甸岛弧带"]},
    "阿尔泰成矿带": {"lat": 47.0, "lon": 89.0, "country": "China", "alias": ["Fuyun", "Altai", "southern Altai region", "Siberian Plate"]},
    "江南造山带": {"lat": 27.0, "lon": 112.0, "country": "China", "alias": ["雪峰山造山带", "Xuefengshan Orogen", "Jiangnan Orogenic Belt"]},
    "莺歌海盆地": {"lat": 18.0, "lon": 109.5, "country": "China", "alias": ["Yinggehai Basin", "莺歌海"]},
    "贵州西部成矿区": {"lat": 26.5, "lon": 104.5, "country": "China", "alias": ["Eastern Yunnan and Western Guizhou", "贵州西部", "土城向斜", "滇黔桂", "盘关向斜"]},

    # ─── 伊朗成矿带 ───
    "乌尔米耶-多赫塔尔岩浆弧": {"lat": 35.5, "lon": 48.5, "country": "Iran", "alias": ["Urumieh-Dokhtar magmatic arc", "UDMA", "Ahar-Arasbaran porphyry copper belt", "Ahar-Arasbaran"]},
    "莫阿勒曼-托巴特带": {"lat": 35.5, "lon": 59.0, "country": "Iran", "alias": ["Moaleman–Torbat-e-Heydaryeh belt", "NE Iran", "Moaleman"]},
    "扎格罗斯褶皱冲断带": {"lat": 31.0, "lon": 48.5, "country": "Iran", "alias": ["Zagros Folded and Thrusted Belt", "ZFTB", "Zagros fold-thrust belt", "Abadan Plain", "Mesopotamian Basin", "Gavbendi High"]},
    "马拉叶尔-伊斯法罕带": {"lat": 33.0, "lon": 51.0, "country": "Iran", "alias": ["Malayer-Esfahan metallogenic belt", "Sanandaj-Sirjan zone", "Sanandaj-Sirjan"]},
    "巴夫克成矿带": {"lat": 32.0, "lon": 55.5, "country": "Iran", "alias": ["Bafq metallogenic belt", "Central Iran", "Bafq"]},

    # ─── 北美成矿带 ───
    "麦古马地体": {"lat": 44.5, "lon": -64.0, "country": "Canada", "alias": ["Meguma Terrane", "Nova Scotia", "Meguma"]},
    "阿比蒂比绿岩带": {"lat": 49.0, "lon": -79.0, "country": "Canada", "alias": ["Abitibi Subprovince", "Superior Province", "Wabigoon Subprovince", "Matheson"]},
    "跨哈德森造山带": {"lat": 58.0, "lon": -98.0, "country": "Canada", "alias": ["Trans-Hudson Orogen", "Churchill Province", "Trans-Hudson"]},
    "格伦维尔省": {"lat": 57.0, "lon": -104.0, "country": "Canada", "alias": ["Grenville Province", "Athabasca Basin", "Athabasca"]},
    "威利斯顿盆地": {"lat": 47.0, "lon": -102.0, "country": "USA", "alias": ["Williston Basin", "Bakken Formation", "Williston"]},

    # ─── 欧洲成矿带 ───
    "伊比利亚黄铁矿带": {"lat": 37.5, "lon": -8.0, "country": "Spain", "alias": ["Iberian Pyrite Belt", "South Portuguese Zone", "Hercynian Iberian Massif", "Iberian Variscan Belt", "Iberian"]},
    "上莱茵地堑": {"lat": 49.0, "lon": 8.0, "country": "Germany", "alias": ["Upper Rhine Graben", "Rhine Graben"]},
    "芬诺斯坎的亚地盾": {"lat": 65.0, "lon": 26.0, "country": "Finland", "alias": ["Fennoscandian Shield", "Fennoscandian"]},

    # ─── 非洲成矿带 ───
    "苏伊士湾裂谷盆地": {"lat": 29.0, "lon": 33.0, "country": "Egypt", "alias": ["Gulf of Suez Rift basin", "Gulf of Suez"]},
    "依利兹盆地": {"lat": 28.0, "lon": 9.0, "country": "Algeria", "alias": ["Illizi Basin", "Illizi"]},
    "尼日尔三角洲": {"lat": 5.0, "lon": 6.0, "country": "Nigeria", "alias": ["Niger Delta"]},
    "伏尔塔盆地": {"lat": 9.0, "lon": -1.0, "country": "Ghana", "alias": ["Volta Basin", "West African Craton"]},
    "曼达瓦盆地": {"lat": -9.0, "lon": 39.0, "country": "Tanzania", "alias": ["Mandawa Basin", "Tanga盆地", "Tanga Basin"]},
    "布雷达斯多普盆地": {"lat": -34.5, "lon": 21.0, "country": "South Africa", "alias": ["Bredasdorp Basin", "Outeniqua Basin"]},
    "卡拉哈里盆地": {"lat": -22.0, "lon": 26.0, "country": "Botswana", "alias": ["Kalahari Karoo Basin", "Karoo Supergroup", "Kalahari"]},
    "卡普瓦尔克拉通": {"lat": -26.0, "lon": 28.0, "country": "South Africa", "alias": ["Kaapvaal Craton", "Kaapvaal"]},
    "中非元古代造山带": {"lat": -2.0, "lon": 30.0, "country": "Rwanda", "alias": ["Mesoproterozoic orogenic belts of Central Africa", "Central Africa orogenic"]},

    # ─── 中东/中亚 ───
    "萨永-马西拉盆地": {"lat": 15.5, "lon": 48.5, "country": "Yemen", "alias": ["Sayun-Masila Rift Basin", "Sayun-Masila"]},
    "楚-萨雷苏盆地": {"lat": 45.0, "lon": 66.0, "country": "Kazakhstan", "alias": ["Chu-Sarysu Basin", "Ustyurt–Buzachi Basin", "Ustyurt-Buzachi", "Ustyurt"]},

    # ─── 南亚 ───
    "印度河盆地": {"lat": 27.0, "lon": 68.0, "country": "Pakistan", "alias": ["Middle Indus Basin", "Lower Indus Basin", "Indus Basin", "Southern Indus Basin", "Upper Indus Basin", "Potwar Plateau", "Dargai Complex", "Indus Suture Zone"]},
    "孟买近海盆地": {"lat": 19.0, "lon": 72.0, "country": "India", "alias": ["Mumbai offshore basin", "Heera–Panna–Bassein", "Heera-Panna-Bassein"]},
    "坎贝盆地": {"lat": 22.0, "lon": 73.0, "country": "India", "alias": ["Cambay Basin", "Jambusar–Broach block", "Jambusar-Broach"]},
    "克里希纳-戈达瓦里盆地": {"lat": 16.0, "lon": 81.0, "country": "India", "alias": ["Krishna-Godavari Basin", "Krishna-Godavari"]},

    # ─── 大洋洲 ───
    "鲍恩盆地": {"lat": -23.0, "lon": 148.0, "country": "Australia", "alias": ["Bowen Basin", "Central Queensland"]},
    "拉赫兰造山带": {"lat": -35.0, "lon": 148.0, "country": "Australia", "alias": ["Lachlan Orogen", "Lachlan"]},
    "塔拉纳基盆地": {"lat": -39.0, "lon": 174.0, "country": "New Zealand", "alias": ["Taranaki Basin", "Taranaki"]},

    # ─── 南美 ───
    "圭亚那地盾绿岩带": {"lat": 4.0, "lon": -56.0, "country": "Suriname", "alias": ["Guiana Shield", "圭亚那地盾"]},
}
