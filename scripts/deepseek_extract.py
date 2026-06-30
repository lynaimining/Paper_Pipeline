#!/usr/bin/env python3
"""
DeepSeek 批量地质论文结构化抽取
用法:
  export DEEPSEEK_API_KEY="sk-xxx"
  python deepseek_extract.py <corpus_root> <output_dir> [--max N] [--concurrency 20] [--truncate 0]

输入: MinerU 解析后的目录结构 (每篇论文目录下有 auto/*.md)
输出: JSON 文件,每篇一条结构化记录
"""
import logging
import os, sys, json, glob, asyncio, time, argparse, hashlib, random
from pathlib import Path
from openai import AsyncOpenAI

_log = logging.getLogger("deepseek_extract")  # 模块级 logger，extract_one 等函数可用

# ── 费率常量（DeepSeek Chat，按需更新）─────────────────────────────────────
_PRICE_INPUT_PER_M  = 0.14   # USD per 1M input tokens (cache miss)
_PRICE_OUTPUT_PER_M = 0.28   # USD per 1M output tokens


def _estimate_cost_usd(acc: dict) -> float:
    """根据 usage_acc 估算 API 费用（USD）。费率常量在文件顶部按需更新。"""
    return (acc.get('prompt_tokens', 0) / 1_000_000 * _PRICE_INPUT_PER_M
            + acc.get('completion_tokens', 0) / 1_000_000 * _PRICE_OUTPUT_PER_M)


def _prompt_hash() -> str:
    """SYSTEM_PROMPT + USER_TEMPLATE 内容哈希——任一变更时旧 checkpoint 自动失效"""
    return hashlib.sha256((SYSTEM_PROMPT + USER_TEMPLATE).encode()).hexdigest()[:16]


def _setup_logging(output_dir: str, run_id: str) -> logging.Logger:
    """配置日志：同时写到 stderr 和 output_dir/run_<id>.log。"""
    log_path = os.path.join(output_dir, f'run_{run_id}.log')
    fmt = f'[%(asctime)s run={run_id}] %(levelname)s %(message)s'
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        datefmt='%H:%M:%S',
        handlers=[
            logging.StreamHandler(sys.stderr),
            logging.FileHandler(log_path, encoding='utf-8'),
        ],
    )
    return logging.getLogger('deepseek_extract')

# ── 配置 ──
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
MODEL = "deepseek-chat"  # DeepSeek V3/V4-Flash

# ── 快速前置分类 prompt（P0-A：仅消耗约150 tokens，过滤无空间推理价值的论文）──
PRESCREEN_SYSTEM = "你是地质学专家。仅根据论文前1500字符判断该论文是否包含对空间推理训练有价值的地质空间信息。"
PRESCREEN_USER = """论文ID: {paper_id}

论文摘要/开头（前1500字符）:
{head}

判断：该论文是否包含**地质空间实体**信息，即满足以下任一条件：
1. 涉���矿床/矿化/矿产勘探（金属矿、能源矿产包括煤、油气、煤层气、地热、可燃冰均算）
2. 包含构造单元的空间关系（断层走向、剪切带分布、造山带、盆地边界、克拉通）
3. 包含岩体空间关系（侵入体接触关系、地层序列、岩相分布、岩石单元的方位与范围）
4. 包含地球物理异常的空间分布（磁异常、重力异常、地震剖面构造）

**跳过条件**（满足任一则跳过）：
- 纯软件工具/算法/统计方法/程序代码（无真实地质案例）
- 期刊书评、编辑注记、会议通知类短文
- 纯海洋生物/土壤农业/生态/非地质主题

只输出一个JSON: {{"has_geo_spatial": true/false, "confidence": 0.0-1.0, "reason": "一句话"}}"""

SYSTEM_PROMPT = """你是一个矿床地质学专家。你的任务是从学术论文全文中提取结构化信息。

## 核心原则

1. **属性归属**: 只提取论文**主要研究对象/案例矿床**的属性，不要从文献综述、对比讨论中归纳。
2. **覆盖面原则**: 方法学/ML/地球物理论文，若用真实矿床作为案例，仍填写 deposit_type 等字段，is_primary_research 设 false。
3. **细节优先**: 矿物、岩性尽量写具体名称（如 "dunite, lherzolite" 而非 "ultramafic"）。
4. **年龄提取**: 优先带 ± 不确定度的放射性年龄，不提取温度、百分比等非年龄数字。
5. **无数据填null**: 没有相关数据时填 null，不要填空数组 [] 或空对象 {}。

## 输出格式

严格输出一个 JSON 对象，字段如下：

### 基础分类
- paper_id: 论文标识符
- deposit_type: 矿床类型。**必须从以下受控词表中选一个**，或填 null（不涉及任何矿床时）。不在列表中的类型选最接近的父级，并在 deposit_type_evidence 末尾注明原文术语（如"原文: porphyry Au-Cu"）。

  ━━ 词表使用规则 ━━
  · 优先选最具体的子类（如 PORPHYRY-CU 优于 PORPHYRY）
  · 若论文研究多类型矿床但有主研究对象，选主研究对象的类型
  · 确实无法归入任一类型时用 POLYMETALLIC，并在 evidence 说明

  【A. 斑岩型 Porphyry】
  PORPHYRY-CU         — 斑岩铜矿（Chuquicamata, Qulong型）
  PORPHYRY-CU-AU      — 斑岩铜金矿（Grasberg, Pebble型）
  PORPHYRY-CU-MO      — 斑岩铜钼矿（Bingham Canyon型）
  PORPHYRY-MO         — 斑岩钼矿（Climax, Henderson型）
  PORPHYRY-AU         — 斑岩金矿（低铜，Donlin Creek型）
  PORPHYRY-SN         — 斑岩锡矿（玻利维亚型，如Llallagua）
  PORPHYRY-W          — 斑岩钨矿
  PORPHYRY-SKARN      — 斑岩-矽卡岩过渡型（长江中下游型，porphyry-skarn系统）
  PORPHYRY            — 斑岩型，商品不明或多商品均等

  【B. 浅成热液 Epithermal】
  EPITHERMAL-HS       — 高硫化型（HS），明矾石-硫磺-冰长石蚀变（Yanacocha型）
  EPITHERMAL-IS       — 中硫化型（IS），冰长石-绢云母蚀变（Waihi型）
  EPITHERMAL-LS       — 低硫化型（LS），冰长石-方解石-白云石（Hishikari型）
  EPITHERMAL-AU       — 浅成热液金矿，硫化度不明
  EPITHERMAL-AG       — 浅成热液银矿（Fresnillo型）
  EPITHERMAL-AG-AU    — 浅成热液银金矿
  EPITHERMAL          — 浅成热液，类型不明或多金属

  【C. 造山型/古砂矿金矿 Orogenic & Placer Au】
  OROG-AU             — 造山型金矿（Kalgoorlie, Jiaodong型，中温石英脉+绿泥石化）
  OROG-AU-PALEO       — 古砂矿金矿（paleoplacer Au），太古代砾岩型（Witwatersrand型）
  CARLIN-AU           — 卡林型金矿，碳酸盐岩容矿，纳米级金（Nevada型）
  JACUTINGA-AU        — Jacutinga型金-钯矿，BIF容矿（巴西Quadrilátero Ferrífero）

  【D. 铁氧化物铜金/矽卡岩 IOCG & Skarn】
  IOCG                — 铁氧化物铜金矿（Olympic Dam, Candelária型）
  KIRUNA-FE           — 基律纳型磁铁矿-磷灰石矿（Kiruna, El Laco型）
  SKARN-CU-AU         — 铜金矽卡岩（Daye, Ertsberg型）
  SKARN-CU            — 铜矽卡岩
  SKARN-PB-ZN         — 铅锌矽卡岩
  SKARN-FE            — 铁矽卡岩（磁铁矿型）
  SKARN-W             — 钨矽卡岩（Cantung型）
  SKARN-W-SN          — 钨锡矽卡岩
  SKARN-SN            — 锡矽卡岩
  SKARN-AU            — 金矽卡岩
  SKARN-MN            — 锰矽卡岩
  SKARN               — 矽卡岩，商品不明或复合商品

  【E. 块状硫化物/沉积喷流 VMS & SEDEX】
  VMS                 — 火山成因块状硫化物（Kidd Creek, Neves-Corvo型）
  SMS                 — 海底热液硫化物（现代，TAG, Logatchev型）
  SEDEX               — 沉积喷流型（Sullivan, Broken Hill型）
  MVT                 — 密西西比河谷型Pb-Zn（Pine Point, Viburnum Trend型）
  IRISH-PB-ZN         — 爱尔兰型碳酸盐岩容矿Pb-Zn（Navan, Lisheen型）

  【F. 岩浆硫化物/铂族/铬铁矿 Magmatic Sulfide & PGE & Cr】
  NI-CU-PGE           — 镍铜铂族岩浆硫化物（Noril'sk, Jinchuan, Voisey's Bay型）
  NI-CU               — 镍铜岩浆硫化物（无显著PGE）
  NI-LATERITE         — 红土型镍矿（Nickel Laterite，风化型，区别于岩浆型）
  PGE-REEF            — 铂族层状矿床（Merensky Reef, Stillwater型）
  PGE-CR              — 铂族-铬铁矿（UG2, Critical Zone型）
  CR-OPHIOLITE        — 蛇绿岩豆荚状铬铁矿（podiform chromitite）
  CR-STRATIFORM       — 层状侵入体铬铁矿（Bushveld Cr）

  【G. 碳酸岩/伟晶岩 Carbonatite & Pegmatite】
  CARBONATITE-REE     — 碳酸岩稀土矿（Mountain Pass, Bayan Obo型）
  CARBONATITE-NB      — 碳酸岩铌矿（Araxa, Catalão型）
  CARBONATITE-P       — 碳酸岩磷矿（Phalaborwa型）
  CARBONATITE         — 碳酸岩，商品不明或多商品
  PEGMATITE-LCT       — LCT型伟晶岩（Li-Cs-Ta，Greenbushes, Kings Mountain型）
  PEGMATITE-NYF       — NYF型伟晶岩（Nb-Y-F，Strange Lake型）
  PEGMATITE-REE       — REE伟晶岩
  PEGMATITE           — 伟晶岩，未分类

  【H. 铀矿 Uranium】
  U-UNCONFORMITY      — 不整合面型铀矿（Athabasca盆地，Cigar Lake型）
  U-SANDSTONE         — 砂岩型铀矿（卷状矿体，Wyoming型）
  U-ALBITITE          — 钠长岩型铀矿（Olympic Dam关联型）
  U-VEIN              — 热液脉型铀矿（Shinkolobwe型）
  U-PHOSPHATE         — 磷酸盐岩型铀矿

  【I. 风化壳/红土型 Laterite & Residual】
  LATERITE-NI         — 红土型镍矿（氧化带+腐泥土带，Goro, Cerro Matoso型）
  LATERITE-REE        — 离子吸附型稀土矿（华南风化壳型）
  BAUXITE             — 铝土矿（红土型或沉积型）
  LATERITE-AU         — 红土型金矿（lateritic gold）
  RESIDUAL-MN         — 残余型锰矿

  【J. 沉积型 Sedimentary（含铜/铁/锰/磷/煤）】
  KUPFERSCHIEFER      — 铜页岩型（Kupferschiefer型）：黑色沥青质页岩叠覆红层的氧化还原界面，Cu-Ag-Pb-Zn共生，Zechstein盆地（波兰KGHM、德国Mansfeld）
  SANDSTONE-CU        — 红层型砂岩铜矿（Red-bed Cu）：铜在陆相**氧化性**红色砂岩/页岩的氧化还原界面富集，低温，常与蒸发岩/石膏伴生；辉铜矿/斑铜矿交代植物化石；无海相证据。典型：Colorado Plateau、Coro-Coro(Bolivia)、Newark系红层
  SEDIMENT-CU         — 还原型沉积层控铜矿（SSC/Sediment-hosted Stratiform Cu）：铜在**还原性**海相或大陆裂谷沉积岩（砂页岩/碳酸盐岩）中层状富集，盆地卤水成矿，规模大；典型：**Central African Copperbelt（赞比亚Chambishi/Mufulira/Nchanga，刚果Tenke-Fungurume/Kamoa）**、White Pine(Michigan)、Spar Lake(Montana)、Belt Basin、Dongchuan(中国)
  BIF-FE              — 条带状铁建造铁矿（BIF-hosted iron ore）：前寒武纪化学沉积铁建造，硅铁互层；含两个亚类——**Superior型**（元古宙克拉通陆架盆地，超大型，Hamersley/Carajás/Transvaal/Lake Superior）和**Algoma型**（太古代绿岩带，与火山岩互层，规模较小）；亦涵盖BIF风化富集的河道铁矿（CID，Pilbara Robe River型）和高品位表生富集矿体（martite-goethite型）
  SEDIMENTARY-FE     — 显生宙沉积铁矿：浅海鲕状/豆状铁岩（oolitic/pisolitic ironstone）或碳酸盐岩容矿铁矿；**区别BIF-FE**（前寒武纪，硅铁互层）；典型：Jurassic ironstones（英国Northampton/Cleveland）、Clinton型（北美）、西非白垩纪鲕铁岩（尼日利亚Agbaja、伊拉克Ga'ara）
  SEDIMENTARY-MN      — 沉积型锰矿（Kalahari, Groote Eylandt型）
  SEDIMENTARY-P       — 沉积磷矿（磷块岩，Phosphoria型）
  EVAPORITE           — 蒸发岩及卤水型矿产（盐、钾盐、石膏、硼酸盐）；**含Salar型锂矿**（盐湖卤水Li，Atacama/Uyuni型）和溴/碘/锶卤水矿床；若论文主商品为Li且来自盐湖/卤水，优先选此类型而非POLYMETALLIC
  BENTONITE          — 膨润土（火山凝灰岩蒙脱石化蚀变型；钻井/铸造工业矿物）
  KAOLIN             — 高岭土矿（长石风化壳型或热液蚀变型；陶瓷/造纸工业矿产）
  GRAPHITE            — 石墨矿

  【K. 砂矿 Placer】
  PLACER-AU           — 冲积砂金矿（现代）
  PLACER-AU-PALEO     — 古砂金矿（古砾岩型，Witwatersrand型）
  PLACER-TI-ZR        — 海滨钛铁矿-锆英砂矿（Richards Bay型）
  PLACER-PGE          — 铂族砂矿（Ural型）
  PLACER-TIN          — 砂锡矿（马来西亚型）
  PLACER              — 砂矿，未分类

  【L. 云英岩/热液脉型 Greisen & Vein】
  GREISEN-W-SN        — 云英岩型钨锡矿（Erzgebirge型）
  GREISEN-SN          — 云英岩型锡矿（Devon型）
  GREISEN-W           — 云英岩型钨矿（Panasqueira型）
  GREISEN             — 云英岩型，未分类
  INTRUSION-RELATED-AU — 还原性侵入体相关金矿（IRAU/ILG）：与还原性（低氧逸度）长英质岩浆热液直接相关；双峰式成矿、近岩体分布、富Bi-Te-W；**区别OROG-AU**（区域变质流体，远离岩体）；典型：Fort Knox/Dublin Gulch(Yukon)、Pogo(Alaska)
  VEIN-AU             — 金石英脉（含造山型之外的热液脉型）
  VEIN-AG             — 银脉矿（Coeur d'Alene型）
  VEIN-CU             — 铜脉矿（Butte铜脉段，角砾管型）
  VEIN-PB-ZN          — 铅锌脉矿（东田型）
  VEIN-SN-W           — 锡钨石英脉
  VEIN-SN             — 锡石英脉
  VEIN-SB            — 造山型锑矿脉（辉锑矿stibnite，受断裂控制，碳酸盐岩容矿；中国锡矿山/Xikuangshan型、土耳其型）
  VEIN-MN            — 热液锰脉矿（菱锰矿/软锰矿脉，区别于沉积型SEDIMENTARY-MN；常与热液多金属矿床共生）
  VEIN-HG            — 汞脉矿（辰砂HgS脉，低温热液，Almadén型；与EPITHERMAL低温端元相关）
  VEIN-F             — 萤石脉矿（CaF₂，热液裂隙充填型，与花岗岩侵入体热液有关）
  FIVE-ELEMENT        — 五元素脉（Ni-Co-As-Ag-Bi，Cobalt型）
  ALUNITE-AU          — 明矾石型金矿

  【M. 金刚石/特种矿产及工业矿物】
  TALC               — 滑石矿（超基性岩蚀变或碳酸盐岩-硅质岩热液交代，工业矿物；与SKARN/蛇纹岩化超基性岩常见）
  SERPENTINE-ASBESTOS — 蛇纹岩型石棉（纤维状蛇纹石chrysotile，超基性岩水化蚀变；与IOCG/NI-CU-PGE伴生的超基性岩体）
  KIMBERLITE          — 金伯利岩型金刚石（Kimberley型）
  LAMPROITE-DIAMOND   — 钾镁煌斑岩型金刚石（Argyle型）

  【O. 能源矿产 Energy】
  COAL                — 煤矿（含煤层气、褐煤、无烟煤）
  COAL-CBM            — 煤层气（coalbed methane）为主研究对象
  OIL-GAS             — 常规油气（砂岩/碳酸盐岩储层）
  SHALE-GAS           — 页岩气/致密气（非常规）
  OIL-SANDS           — 油砂（加拿大Athabasca型）
  GEOTHERMAL          — 地热资源（干热岩/水热型）
  GAS-HYDRATE         — 天然气水合物（可燃冰）

  【N. 兜底/复合】
  SKARN-MO           — 钼矽卡岩（花岗岩-碳酸盐岩接触带，Climax型斑岩系统外带；与PORPHYRY-MO伴生）
  POLYMETALLIC        — 多金属（≥3种主商品，类型不明确）

- deposit_type_conf: 置信度 0.0-1.0
- deposit_type_alternative: 副类型，仅在矿床**确实**属于过渡/混合/争议情形时填写，否则填 null。格式：
  {"type": "受控词表中的类型", "relation": "关系代码", "evidence": "一句话说明"}
  relation 受控值（只能用这5个）：
    "synonymous"       — 两个术语描述同一现象，行业用法不同（如 VMS/SMS，VEIN-AU/OROG-AU）
    "transitional"     — 矿床处于两类型连续体的过渡位置（如斑岩-矽卡岩接触带）
    "zoned"            — 同一矿床不同空间域属不同类型（如内带skarn + 外带vein）
    "co-hosted"        — 同一地区两种独立成因矿床共存（如IOCG旁有PORPHYRY-CU）
    "genetic_spectrum" — 同一成矿系统的不同端员（如SEDEX/MVT/IRISH-PB-ZN同族）
  **不填的情形**（绝大多数论文）：矿床类型清晰无争议时填 null，不要为了填而填。
- deposit_type_evidence: 判断依据（字符串）。说明为何是该矿床类型，包括：论文明确描述、关键诊断特征（围岩/矿物/蚀变）、排除其他类型理由。
  **关键规则：只写主研究矿床的证据，不要从"对比讨论"或"文献引用"中抽证据。**
  例如：论文研究A矿床，但引用了B矿床和C矿床作为类比 → deposit_type 只反映A矿床，evidence 只引用论文对A的直接描述。
  若原文术语不在受控词表中，在此末尾注明（如"原文: porphyry Cu"）。deposit_type=null 时填 null。
- deposit_type_null_reason: 当 deposit_type=null 时，必须填以下之一；deposit_type 非 null 时填 null。
  - "no_deposit" — 论文完全不涉及矿床/矿化（如纯构造、岩石学、方法学论文）
  - "insufficient_evidence" — 论文涉及矿化迹象但证据不足以分类
  - "multi_deposit_study" — 论文对比多种不同类型矿床，无单一主研究矿床
  - "exploration_stage" — 早期勘探阶段，矿床类型尚未确定
- deposit_class: 论文分类，从以下选一个: mineral_deposit / structural_tectonic / geochemical_petrology / methodological / energy / none
- is_primary_research: true/false
- is_primary_research_reason: 判断理由（字符串），说明为何是主研究或辅助研究

### 空间信息
- countries: 研究区所在国家数组，或 null
- metallogenic_belt: 成矿带/大地构造单元名称（包含所属克拉通/造山带），或 null
- tectonic_setting: 构造背景，或 null
- coordinates: 矿床/研究区坐标，或 null。格式：
  {"latitude": 35.5, "longitude": 115.2, "precision": "矿区级", "source": "Figure 1", "confidence": 0.9, "extraction_method": "图件坐标网格"}
  precision 选项：矿区级（误差<5km）/ 省级（误差10-100km）/ 国家级（误差>100km）
  extraction_method 选项：图件坐标网格 / 明确经纬度 / 地名推断
  置��度标准：0.9-1.0=论文明确经纬度或清晰坐标网格；0.7-0.9=图件坐标轴可读；0.5-0.7=地名推断；<0.5=仅国家名猜测
  如论文完全无位置信息，填 null

### 矿物信息（必须分类）
- minerals: 矿物分类对象，或 null。格式：
  {"ore_minerals": ["sphalerite","galena"], "gangue_minerals": ["quartz","calcite"], "alteration_minerals": ["tremolite","chlorite"]}
  ore_minerals: 含经济元素的矿物；gangue_minerals: 不含经济元素的脉石；alteration_minerals: 蚀变产物
- alteration: 蚀变类型数组（如 ["potassic","phyllic","silicification"]），或 null

### 商品信息（必须分类）
- commodities: 商品分类对象，或 null。格式：
  {"primary": ["Pb","Zn"], "byproduct": ["Ag","Cd"], "trace": ["As","Se"]}
  primary 根据 deposit_type 的主商品判断（OROG-AU→Au，SKARN Pb-Zn→Pb和Zn）
  byproduct: 有经济价值但不是重点；trace: 仅科学意义的微量元素

### 地质信息
- host_rocks: 围岩数组（具体岩性名称），或 null
- structural_controls: 构造控制数组，或 null

### 规模信息
- deposit_scale: 矿床规模，或 null。格式：
  {"tonnage": {"value": 5.2, "unit": "Mt", "resource_type": "proven+probable"}, "grade": {"Au_ppm": 3.5, "Cu_percent": 0.8}, "scale_class": "large", "production_status": "producing", "citation": "Table 2"}
  只提取论文明确的数字，没有则填 null

### 年代信息
- ages: 年龄数组，或 null。格式：
  [{"age_ma": 125.3, "uncertainty": 1.2, "method": "U-Pb zircon", "material": "granite", "interpretation": "侵入年龄", "citation": "Figure 5"}]
  只提取论文明确的测年数据

### 地球化学
- geochemistry: 地球化学数据，或 null。格式：
  {"trace_elements": {"enriched": ["REE","Y"], "depleted": ["Sr","Ba"]}, "isotopes": {"sulfur_delta34s": "+5.2 to +8.5‰"}, "fluid_inclusion": {"temperature_c": "250-350", "salinity_wt_nacl": "5-15"}, "citation": "Figure 7"}
  如论文无地球化学数据，整个字段填 null（不填空对象）

### 参考矿床
- reference_deposits: 参考矿床数组，或 null。格式：
  [{"name": "Carlin", "relation": "类型对比", "similarity": "相似碳酸盐岩容矿"}]

### 成矿系统
- mineral_system: Mineral System七要素，涉及矿床时填写，否则 null。格式：
  {"source": {"score": 1-5, "evidence": "..."}, "transport": {"score": 1-5, "evidence": "..."}, "trap": {"score": 1-5, "evidence": "..."}, "reservoir": {"score": 1-5, "evidence": "..."}, "seal": {"score": 1-5, "evidence": "..."}, "timing": {"score": 1-5, "evidence": "..."}, "preservation": {"score": 1-5, "evidence": "..."}}
  评分：5=充分证据 4=较好 3=间接 2=推测 1=无证据

只输出一个 JSON 对象，不要输出任何其他文字。"""

USER_TEMPLATE = """论文ID: {paper_id}

以下是论文全文:

{body}"""


def find_papers(corpus_root: str, enhanced_dir: str = '') -> list[dict]:
    """递归查找所有 .md 文件。若指定 enhanced_dir, 优先用增强版(含 Qwen 视觉内容)"""
    papers = []
    for md in sorted(glob.glob(os.path.join(corpus_root, '**', 'auto', '*.md'), recursive=True)):
        # 排除非论文 md (layout等)
        if '_layout' in md or '_middle' in md or '_model' in md or '_spans' in md:
            continue
        paper_id = Path(md).stem.strip()  # 文件名末尾可能有空格（Linux 允许），strip 防止 lookup 失败
        # 优先使用增强版 .md (inject_visual.py 产出, 含图表识别结果)
        if enhanced_dir:
            enhanced_path = os.path.join(enhanced_dir, f'{paper_id}.md')
            if os.path.exists(enhanced_path):
                papers.append({'paper_id': paper_id, 'md_path': enhanced_path})
                continue
        papers.append({'paper_id': paper_id, 'md_path': md})
    return papers


def load_body(md_path: str, truncate: int = 0) -> str:
    """读取 MD 正文，可选截断。使用 with 确保文件描述符及时释放（高并发场景）。"""
    with open(md_path, encoding='utf-8-sig') as f:  # utf-8-sig 自动剥离 BOM
        text = f.read()
    # 去掉 References 之后的部分 (节省 tokens)
    for marker in ['# References', '# REFERENCES', '## References', '## REFERENCES']:
        idx = text.find(marker)
        if idx > 0:
            text = text[:idx]
            break
    if truncate > 0:
        text = text[:truncate]
    return text


async def prescreen_paper(client: AsyncOpenAI, paper: dict, semaphore: asyncio.Semaphore) -> bool:
    """P0-A: 快速前置筛选——只读前1500字符，判断是否矿床论文。非矿床直接跳过。"""
    body = load_body(paper['md_path'], truncate=1500)
    head = body
    async with semaphore:
        try:
            resp = await asyncio.wait_for(
                client.chat.completions.create(
                    model=MODEL,
                    messages=[
                        {"role": "system", "content": PRESCREEN_SYSTEM},
                        {"role": "user", "content": PRESCREEN_USER.format(
                            paper_id=paper['paper_id'], head=head)}
                    ],
                    temperature=0.0,
                    max_tokens=80,
                    response_format={"type": "json_object"},
                ),
                timeout=15.0,  # 单次 prescreen 最多等 15s
            )
            result = json.loads(resp.choices[0].message.content)
            return result.get('has_geo_spatial', True)  # 不确定时默认保留
        except Exception:
            return True  # 超时或解析失败时保留，宁可多跑不漏


async def extract_one(client: AsyncOpenAI, paper: dict, truncate: int, semaphore: asyncio.Semaphore,
                      usage_acc: dict, retries: int = 3) -> dict | None:
    """单篇抽取,带重试"""
    body = load_body(paper['md_path'], truncate)

    for attempt in range(retries):
        try:
            async with semaphore:
                resp = await asyncio.wait_for(
                    client.chat.completions.create(
                        model=MODEL,
                        messages=[
                            # P1-A: system prompt 完全静态，DeepSeek 会自动缓存相同前缀
                            # 论文正文放在 user message 最后，区分动态/静态部分
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": USER_TEMPLATE.format(
                                paper_id=paper['paper_id'], body=body
                            )}
                        ],
                        temperature=0.1,
                        max_tokens=2000,
                        response_format={"type": "json_object"},
                    ),
                    timeout=120.0,  # 防止单篇挂起占住 semaphore 导致整批死锁
                )
            # P2: 累计 usage
            if resp.usage:
                usage_acc['prompt_tokens']     += resp.usage.prompt_tokens
                usage_acc['completion_tokens'] += resp.usage.completion_tokens
                usage_acc['total_tokens']      += resp.usage.total_tokens
                usage_acc['api_calls']         += 1
            text = resp.choices[0].message.content.strip()
            result = json.loads(text)
            result['paper_id'] = paper['paper_id']  # 确保 paper_id 正确
            return result
        except json.JSONDecodeError:
            # 尝试修复常见 JSON 问题
            try:
                # 有时模型输出 ```json ... ```
                if '```json' in text:
                    text = text.split('```json')[1].split('```')[0]
                    result = json.loads(text)
                    result['paper_id'] = paper['paper_id']
                    return result
            except (KeyboardInterrupt, SystemExit):
                raise   # 只放行真正的中断信号
            except Exception:
                pass    # JSON 修复也失败，继续走 retry 逻辑
            if attempt < retries - 1:
                await asyncio.sleep(2 ** attempt + random.uniform(0, 1))
            else:
                print(f"  [FAIL] {paper['paper_id']}: JSONDecodeError (JSON修复失败，已重试{retries}次)", file=sys.stderr)
        except Exception as e:
            err_str = str(e).lower()
            # 429 限流：尊重窗口时间，不烧完重试次数
            is_rate_limit = '429' in str(e) or 'rate limit' in err_str or 'too many requests' in err_str
            if is_rate_limit:
                wait = 60.0
                _log.warning(f"[RATE LIMIT] {paper['paper_id']}: 触发限流，等待 {wait}s 后重试 (attempt {attempt+1}/{retries})")
                await asyncio.sleep(wait)
            elif attempt < retries - 1:
                await asyncio.sleep(2 ** attempt + random.uniform(0, 1))
            else:
                print(f"  [FAIL] {paper['paper_id']}: {type(e).__name__}: {e}", file=sys.stderr)
                return None
    return None


async def run(corpus_root: str, output_dir: str, max_papers: int = 0,
              concurrency: int = 20, truncate: int = 0, enhanced_dir: str = '',
              prescreen: bool = True):
    """主流程。费用实时显示在进度日志，不设硬上限（retries=3 已兜底异常场景）。"""
    import datetime, secrets
    run_id = datetime.datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + secrets.token_hex(2)
    os.makedirs(output_dir, exist_ok=True)
    log = _setup_logging(output_dir, run_id)

    # ── 启动前预检 ──────────────────────────────────────────────────────────────
    if not os.path.isdir(corpus_root):
        log.error(f"corpus_root 不存在或不是目录: {corpus_root}")
        sys.exit(1)
    try:
        _probe = os.path.join(output_dir, '.write_probe')
        open(_probe, 'w').close()
        os.remove(_probe)
    except OSError as e:
        log.error(f"output_dir 不可写: {output_dir} — {e}")
        sys.exit(1)
    # 磁盘空间粗估（每篇约 4KB 结果 + 4KB 文本）
    import shutil
    free_gb = shutil.disk_usage(output_dir).free / 1024**3
    if free_gb < 1.0:
        log.warning(f"磁盘空间不足 1GB（剩余 {free_gb:.1f}GB），大批量跑可能中途失败")

    api_key = os.environ.get('DEEPSEEK_API_KEY')
    if not api_key:
        log.error("请设置 DEEPSEEK_API_KEY 环境变量")
        sys.exit(1)

    client = AsyncOpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)
    semaphore = asyncio.Semaphore(concurrency)

    # 查找论文
    papers = find_papers(corpus_root, enhanced_dir)
    if max_papers > 0:
        papers = papers[:max_papers]
    enhanced_count = sum(1 for p in papers if enhanced_dir and enhanced_dir in p['md_path'])
    log.info(f"找到 {len(papers)} 篇论文, 并发={concurrency}, 截断={truncate or '不截断'}")
    # 启动时显示预估费用（供参考，不干预流程）
    est_input_tokens = len(papers) * (truncate if truncate > 0 else 6000)
    est_output_tokens = len(papers) * 2000
    est_cost = _estimate_cost_usd({'prompt_tokens': est_input_tokens, 'completion_tokens': est_output_tokens})
    log.info(f"预估费用: ¥{est_cost*7.2:.1f} (${est_cost:.2f})，单篇约 ¥{est_cost*7.2/max(len(papers),1)*100:.2f}分")
    if enhanced_dir:
        log.info(f"  其中 {enhanced_count} 篇使用 Qwen 增强版 .md")

    # 检查已完成的 (支持断点续跑，P6: prompt-hash 幂等校验)
    os.makedirs(output_dir, exist_ok=True)
    done_file = os.path.join(output_dir, '_done.json')
    done_ids = set()
    current_hash = _prompt_hash()
    if os.path.exists(done_file):
        with open(done_file, encoding='utf-8') as f:
            done_meta = json.load(f)
        if isinstance(done_meta, dict):
            saved_hash = done_meta.get('prompt_hash', '')
            if saved_hash != current_hash:
                print(f"⚠️  SYSTEM_PROMPT 已变更 (hash: {saved_hash[:8]}→{current_hash[:8]})")
                print(f"   已完成的 {len(done_meta.get('ids',[]))} 篇将被标记为 needs_rerun，重新提取")
                done_ids = set()  # prompt 变了，全部重跑
                # 清理旧 chunk 文件，防止旧数据被 glob 合并进本次结果
                old_chunks = glob.glob(os.path.join(output_dir, 'results_*.json'))
                for cf in old_chunks:
                    os.remove(cf)
                if old_chunks:
                    print(f"   已清理 {len(old_chunks)} 个旧 chunk 文件")
            else:
                done_ids = set(done_meta.get('ids', []))
                print(f"已完成 {len(done_ids)} 篇 (断点续跑, prompt_hash={current_hash[:8]})")
        else:
            # 兼容旧格式（list）
            done_ids = set(done_meta)
            print(f"已完成 {len(done_ids)} 篇 (旧格式 checkpoint, 升级中...)")

    todo = [p for p in papers if p['paper_id'] not in done_ids]
    # 续跑时跳过已被 prescreen 拒绝的论文（避免每次续跑重复筛选）
    rejected_ids: set = set()
    if os.path.exists(done_file):
        with open(done_file, encoding='utf-8') as f:
            _meta = json.load(f)
        if isinstance(_meta, dict):
            rejected_ids = set(_meta.get('rejected_ids', []))
    todo = [p for p in todo if p['paper_id'] not in rejected_ids]
    log.info(f"待处理: {len(todo)} 篇 (已完成={len(done_ids)}, 已拒绝={len(rejected_ids)})")

    if not todo:
        log.info("全部完成!")
        return

    # P0-A: 前置筛选
    if prescreen and len(todo) > 5:
        log.info(f"[P0-A] 前置筛选: 并发检查 {len(todo)} 篇是否矿床论文...")
        ps_batch = 500
        ps_results = []
        for i in range(0, len(todo), ps_batch):
            chunk = todo[i:i + ps_batch]
            chunk_results = await asyncio.gather(
                *[prescreen_paper(client, p, semaphore) for p in chunk],
                return_exceptions=True,
            )
            # 异常对象 → 保留（fail-open），同时记录异常率
            exc_count = sum(1 for r in chunk_results if isinstance(r, BaseException))
            if exc_count:
                log.warning(f"  P0-A 本批 {exc_count}/{len(chunk)} 条 prescreen 异常（已 fail-open 保留）")
            ps_results.extend(
                True if isinstance(r, BaseException) else r
                for r in chunk_results
            )
            done_so_far = min(i + ps_batch, len(todo))
            log.info(f"  P0-A 进度: {done_so_far}/{len(todo)}")
        before = len(todo)
        original_todo = todo
        todo = [p for p, keep in zip(original_todo, ps_results) if keep]
        skipped = before - len(todo)
        rejected = [p['paper_id'] for p, keep in zip(original_todo, ps_results) if not keep]
        rejected_ids.update(rejected)  # 累积到当前 rejected_ids，连同原有的一起写回 checkpoint
        rejected_path = os.path.join(output_dir, 'rejected_paper_ids.json')
        with open(rejected_path, 'w', encoding='utf-8') as f:
            json.dump({"count": len(rejected_ids), "paper_ids": sorted(rejected_ids)},
                      f, ensure_ascii=False, indent=2)
        log.info(f"  → 保留 {len(todo)} 篇, 本次跳过 {skipped} 篇 (累计已拒绝 {len(rejected_ids)} 篇) → {rejected_path}")

    # usage 累计器
    usage_acc = {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0, 'api_calls': 0}
    # _estimate_cost_usd 已在模块级定义，删除局部重复定义

    results = []
    batch_size = 500
    t0 = time.time()

    for batch_start in range(0, len(todo), batch_size):
        batch = todo[batch_start:batch_start + batch_size]
        tasks = [extract_one(client, p, truncate, semaphore, usage_acc) for p in batch]
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        # 异常对象降级为 None
        processed_results = []
        for p, r in zip(batch, batch_results):
            if isinstance(r, BaseException):
                log.error(f"[FAIL] {p['paper_id']}: gather exception: {type(r).__name__}: {r}")
                processed_results.append(None)
            else:
                processed_results.append(r)
        batch_results = processed_results

        failed_ids = []
        for p, r in zip(batch, batch_results):
            if r is not None:
                results.append(r)
                done_ids.add(r['paper_id'])
            else:
                failed_ids.append(p['paper_id'])
                log.warning(f"[LOST] {p['paper_id']}: 抽取失败（3次重试后返回 None）")

        if failed_ids:
            failed_path = os.path.join(output_dir, 'failed_paper_ids.json')
            existing = []
            if os.path.exists(failed_path):
                with open(failed_path, encoding='utf-8') as f:
                    existing = json.load(f).get('paper_ids', [])
            with open(failed_path, 'w', encoding='utf-8') as f:
                all_failed = list(dict.fromkeys(existing + failed_ids))
                json.dump({'count': len(all_failed), 'paper_ids': all_failed}, f, ensure_ascii=False, indent=2)

        # 进度 + 实时费用 + 批次门控快报（早发现质量问题，不等 10 小时后）
        elapsed = time.time() - t0
        rate = len(results) / elapsed if elapsed > 0 else 0
        eta = (len(todo) - len(results)) / rate / 3600 if rate > 0 else 0
        cost_usd = _estimate_cost_usd(usage_acc)
        cost_rmb = cost_usd * 7.2
        log.info(f"进度: {len(results)}/{len(todo)} ({len(results)/len(todo)*100:.1f}%) "
                 f"| {rate:.1f} 篇/秒 | ETA: {eta:.1f}h | 累计: ¥{cost_rmb:.2f} (${cost_usd:.3f})")

        # 每批跑一次门控快照（仅统计，不写文件，给运维人员质量信号）
        if batch_results:
            batch_valid = [r for r in batch_results if r]
            if batch_valid:
                from gate_lite import gate_check as _gc
                _, batch_report = _gc(batch_valid, dedup=False)
                pass_rate = batch_report['pass'] / max(batch_report['total'], 1)
                fail_rate = batch_report['fail'] / max(batch_report['total'], 1)
                level = "⚠ " if fail_rate > 0.1 else ""
                log.info(f"  {level}本批门控: pass={batch_report['pass']} "
                         f"warn={batch_report['warn']} fail={batch_report['fail']} "
                         f"(pass率={pass_rate:.0%})"
                         + (f"  问题: {dict(list(batch_report['flag_counts'].items())[:3])}"
                            if batch_report['flag_counts'] else ""))

        # 每批写磁盘
        chunk_file = os.path.join(output_dir, f'results_{batch_start:06d}.json')
        with open(chunk_file, 'w', encoding='utf-8') as f:
            json.dump([r for r in batch_results if r], f, ensure_ascii=False, indent=1)
        done_file_tmp = done_file + '.tmp'
        with open(done_file_tmp, 'w', encoding='utf-8') as f:
            json.dump({'prompt_hash': current_hash,
                       'ids': list(done_ids),
                       'rejected_ids': sorted(rejected_ids)}, f)
        os.replace(done_file_tmp, done_file)

    # usage.json
    usage_file = os.path.join(output_dir, 'usage.json')
    final_cost = _estimate_cost_usd(usage_acc)
    with open(usage_file, 'w', encoding='utf-8') as f:
        json.dump({**usage_acc, 'estimated_cost_usd': round(final_cost, 4)}, f, indent=2)
    log.info(f"usage: {usage_acc['total_tokens']:,} tokens ({usage_acc['api_calls']} calls) "
             f"≈ ${final_cost:.3f} → {usage_file}")

    # 最终汇总
    all_results_file = os.path.join(output_dir, 'all_results.json')
    all_data = []
    chunk_files = sorted(glob.glob(os.path.join(output_dir, 'results_*.json')))
    for chunk_path in chunk_files:
        try:
            with open(chunk_path, encoding='utf-8') as f:
                all_data.extend(json.load(f))
        except (json.JSONDecodeError, OSError) as e:
            log.warning(f"跳过损坏的 chunk 文件 {os.path.basename(chunk_path)}: {e}")

    # ── 门控检查 ──
    from gate_lite import gate_check
    gated_data, gate_report = gate_check(all_data)

    # 分流: pass/warn → trusted, fail → quarantine
    trusted = [r for r in gated_data if r['_gate_status'] != 'fail']
    quarantine = [r for r in gated_data if r['_gate_status'] == 'fail']

    # 写入结果
    with open(all_results_file, 'w', encoding='utf-8') as f:
        json.dump(gated_data, f, ensure_ascii=False, indent=1)
    with open(os.path.join(output_dir, 'trusted.json'), 'w', encoding='utf-8') as f:
        json.dump(trusted, f, ensure_ascii=False, indent=1)
    if quarantine:
        with open(os.path.join(output_dir, 'quarantine.json'), 'w', encoding='utf-8') as f:
            json.dump(quarantine, f, ensure_ascii=False, indent=1)

    elapsed = time.time() - t0
    log.info('=' * 60)
    log.info(f"完成! {len(all_data)} 篇, 耗时 {elapsed/60:.1f} 分钟, "
             f"实际费用 ≈ ¥{final_cost*7.2:.2f} (${final_cost:.3f})")
    log.info(f"  门控: pass={gate_report['pass']} warn={gate_report['warn']} fail={gate_report['fail']}")
    log.info(f"  trusted: {len(trusted)} 篇 → {output_dir}/trusted.json")
    if quarantine:
        log.info(f"  quarantine: {len(quarantine)} 篇 → {output_dir}/quarantine.json")
    if gate_report['flag_counts']:
        log.info(f"  问题明细: {gate_report['flag_counts']}")
    log.info(f"  全量(含标记): {all_results_file}")
    log.info('=' * 60)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='DeepSeek 地质论文结构化抽取')
    parser.add_argument('corpus_root', help='MinerU 输出根目录')
    parser.add_argument('output_dir', help='输出目录')
    parser.add_argument('--max', type=int, default=0, help='最多处理N篇 (0=全部)')
    parser.add_argument('--concurrency', type=int, default=20, help='并发数 (默认20)')
    parser.add_argument('--truncate', type=int, default=0, help='截断字符数 (0=不截断)')
    parser.add_argument('--enhanced-dir', default='', help='inject_visual.py 输出目录 (含 Qwen 增强 .md)')
    parser.add_argument('--no-prescreen', action='store_true', help='跳过前置矿床筛选（默认开启）')
    args = parser.parse_args()

    asyncio.run(run(args.corpus_root, args.output_dir, args.max, args.concurrency, args.truncate,
                    args.enhanced_dir, prescreen=not args.no_prescreen))
