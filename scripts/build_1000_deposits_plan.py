"""
从公开数据源构建1000+矿床库的策略

问题：手动添加太慢（目前300个，需要1000+）

解决方案：从公开数据源批量导入
"""

# ============================================================================
# 方案1：USGS MRDS (Mineral Resources Data System) - 最佳方案
# ============================================================================

"""
USGS MRDS包含：
- 全球180,000+个矿床记录
- 包含坐标、矿床类型、商品、国家
- 完全公开，可免费下载

下载地址：
https://mrdata.usgs.gov/mrds/

文件格式：CSV / Shapefile

实施步骤：
1. 下载MRDS数据库
2. 过滤出著名矿床（根据产量、储量、文献引用）
3. 标准化字段名称
4. 转换为我们的格式
"""

USGS_MRDS_SCRIPT = '''
import pandas as pd
import requests

# 下载USGS MRDS
url = "https://mrdata.usgs.gov/mrds/mrds-csv.zip"
response = requests.get(url)
with open("mrds.zip", "wb") as f:
    f.write(response.content)

# 解压并读取
import zipfile
with zipfile.ZipFile("mrds.zip") as z:
    z.extractall("mrds_data")

# 读取CSV
df = pd.read_csv("mrds_data/mrds.csv", encoding='latin1')

# 过滤条件：
# 1. 有坐标
# 2. 主要矿床类型
# 3. 大型矿床（根据吨位/品位）

famous = df[
    (df['latitude'].notna()) &
    (df['longitude'].notna()) &
    (df['dev_stat'].isin(['Producer', 'Past Producer'])) &
    (df['commod1'].notna())
]

# 转换为我们的格式
deposits = {}
for idx, row in famous.iterrows():
    name = row['site_name']
    deposits[name] = {
        'lat': row['latitude'],
        'lon': row['longitude'],
        'country': row['country'],
        'type': row['dep_type']  # 需要映射到我们的类型
    }

print(f"从USGS MRDS提取了 {len(deposits)} 个矿床")
'''

# ============================================================================
# 方案2：MinDat.org API
# ============================================================================

"""
MinDat包含：
- 50,000+个矿物产地
- 包括著名矿床的type locality
- 有API可用

API文档：
https://api.mindat.org/

需要：免费注册获取API key
"""

MINDAT_SCRIPT = '''
import requests

API_KEY = "your_mindat_api_key"
headers = {"Authorization": f"Token {API_KEY}"}

# 获取矿床列表
url = "https://api.mindat.org/localities"
params = {
    "fields": "name,latitude,longitude,country",
    "page_size": 1000,
    "locality_type": "mining"
}

response = requests.get(url, headers=headers, params=params)
data = response.json()

deposits = {}
for loc in data['results']:
    if loc.get('latitude') and loc.get('longitude'):
        deposits[loc['name']] = {
            'lat': loc['latitude'],
            'lon': loc['longitude'],
            'country': loc['country']
        }
'''

# ============================================================================
# 方案3：上市公司矿山清单
# ============================================================================

"""
主要矿业公司：
- BHP (20+个主要矿山)
- Rio Tinto (30+个)
- Glencore (50+个)
- Freeport (10+个)
- Newmont (20+个)
- Barrick (30+个)
- Anglo American (30+个)
- Vale (40+个)
- Southern Copper (5+个)
- First Quantum (10+个)
- Antofagasta (5+个)
- Teck (10+个)

数据来源：
- 公司年报（Operations页面）
- 公司网站（Assets页面）
- 通常包含精确坐标
"""

MAJOR_COMPANIES_MINES = '''
BHP_MINES = {
    # Copper
    "Escondida": {"lat": -24.2, "lon": -69.1, "country": "Chile"},
    "Spence": {"lat": -22.9, "lon": -69.1, "country": "Chile"},
    "Pampa Norte": {"lat": -22.3, "lon": -68.9, "country": "Chile"},
    "Olympic Dam": {"lat": -30.4, "lon": 136.9, "country": "Australia"},
    "Antamina": {"lat": -9.3, "lon": -77.1, "country": "Peru"},
    "Resolution": {"lat": 33.3, "lon": -111.1, "country": "USA"},

    # Iron Ore
    "Mount Whaleback": {"lat": -23.3, "lon": 119.7, "country": "Australia"},
    "Jimblebar": {"lat": -23.3, "lon": 119.7, "country": "Australia"},
    "Yandi": {"lat": -22.7, "lon": 119.0, "country": "Australia"},
    "Area C": {"lat": -22.8, "lon": 118.8, "country": "Australia"},
    "South Flank": {"lat": -23.0, "lon": 119.6, "country": "Australia"},

    # Coal
    "Goonyella": {"lat": -21.8, "lon": 148.2, "country": "Australia"},
    "Peak Downs": {"lat": -22.3, "lon": 148.3, "country": "Australia"},
    "Saraji": {"lat": -22.1, "lon": 148.5, "country": "Australia"},

    # Nickel
    "Nickel West": {"lat": -31.2, "lon": 121.7, "country": "Australia"},
}

# 类似地添加其他公司...
'''

# ============================================================================
# 方案4：S&P Global市场情报数据
# ============================================================================

"""
S&P Global (原SNL Metals & Mining)
- 最全面的商业矿床数据库
- 需要付费订阅
- 包含详细的产量、储量、坐标

替代：可以从免费报告中提取
"""

# ============================================================================
# 推荐实施顺序
# ============================================================================

IMPLEMENTATION_PLAN = """
第1步（今天，2小时）：
  - 下载USGS MRDS数据库
  - 解析并转换为我们的格式
  - 预期：500-1000个矿床

第2步（明天，1小时）：
  - 补充上市公司矿山（BHP/Rio/Glencore等）
  - 预期：+200个矿床

第3步（本周，2小时）：
  - MinDat API提取著名矿床
  - 预期：+300个矿床

总计：1000-1500个矿床

质量控制：
  - 去重（同一矿床不同名称）
  - 坐标验证（范围检查）
  - 国家一致性检查
"""

print(__doc__)
print("\n" + "=" * 80)
print("推荐方案：USGS MRDS")
print("=" * 80)
print(IMPLEMENTATION_PLAN)
print("\n下一步：下载并解析USGS MRDS数据")
