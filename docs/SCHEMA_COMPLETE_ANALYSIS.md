# Schema 完整字段分析 - 置信度、噪音、改进建议

**当前状态**: 15个字段（矿床论文）  
**日期**: 2026-06-21

---

## 一、字段清单与置信度

### 【A类】有置信度/证据的字段 ✅

| 字段 | 填充率 | 置信度机制 | 证据字段 | 状态 |
|------|--------|-----------|---------|------|
| **deposit_type** | 100% | deposit_type_conf (0-1) | ✅ deposit_type_evidence (已测试) | 优秀 |
| **mineral_system** | 100% | 内部score (1-5) + evidence | ✅ 每个要素都有evidence | 优秀 |
| **coordinates** | - | confidence (0-1) | ✅ source + extraction_method | 优秀 (新增) |

**结论**: 这3个字段是**标杆**，做得很好。

---

### 【B类】应该有置信度/证据，但目前缺失 ⚠️

| 字段 | 填充率 | 当前问题 | 建议改进 | 优先级 |
|------|--------|---------|---------|--------|
| **is_primary_research** | 100% | 只有boolean，无理由 | 新增 `is_primary_research_reason` | P1 |
| **ages_ma** | 53.8% | 只有数字，无来源/方法 | 扩展为结构化（method, material, citation） | P2 |
| **deposit_class** | 100% | 只有枚举值，无依据 | 可选新增 `deposit_class_reason` | P3 |

---

### 【C类】简单数组/字符串，不需要置信度 ✅

| 字段 | 填充率 | 类型 | 是否有噪音风险 | 备注 |
|------|--------|------|---------------|------|
| **paper_id** | 100% | 字符串 | 无 | 主键 |
| **commodities** | 100% | 数组 | ⚠️ 中等 | 可能包含非主要商品 |
| **countries** | 97.4% | 数组 | 低 | 有coordinates验证 |
| **host_rocks** | 100% | 数组 | ⚠️ 中等 | 可能过于详细或泛化 |
| **minerals_mentioned** | 100% | 数组 | ⚠️ 高 | **最大噪音源** |
| **alteration** | 82.1% | 数组 | 低 | 较规范 |
| **structural_controls** | 76.9% | 数组 | 中等 | 描述方式不统一 |
| **metallogenic_belt** | 100% | 字符串 | 低 | 通常准确 |
| **tectonic_setting** | 100% | 字符串 | 低 | 描述性，无标准 |
| **no_deposit_reason** | 0% | 字符串 | - | 矿床论文不适用 |

---

## 二、噪音风险分析

### 🔴 高风险：minerals_mentioned（噪音最多）

**问题**:
```json
"minerals_mentioned": [
  "sphalerite", "galena", "chalcopyrite",  // 矿石矿物
  "quartz", "calcite", "dolomite",         // 脉石矿物
  "tremolite", "diopside", "serpentine",   // 蚀变矿物
  "apatite", "biotite", "muscovite",       // 围岩矿物
  "magnetite", "enstatite"                 // 其他
]
```

**噪音来源**:
1. **全部混在一起** - 矿石、脉石、蚀变、围岩不区分
2. **过于详细** - 30+种矿物，包含次要矿物
3. **无主次** - 不知道哪些是关键诊断矿物

**改进建议**:

#### 方案A: 分类（推荐）
```json
"minerals": {
  "ore_minerals": ["sphalerite", "galena", "chalcopyrite"],  // 矿石
  "gangue_minerals": ["quartz", "calcite"],                  // 脉石
  "alteration_minerals": ["tremolite", "diopside"],          // 蚀变
  "diagnostic_minerals": ["sphalerite", "galena"]            // 关键诊断
}
```

#### 方案B: 加权重
```json
"minerals_mentioned": [
  {"name": "sphalerite", "importance": "major", "role": "ore"},
  {"name": "quartz", "importance": "minor", "role": "gangue"}
]
```

#### 方案C: 仅关键矿物（最简单）
```json
"diagnostic_minerals": ["sphalerite", "galena", "chalcopyrite"]  // 仅5-10种关键矿物
```

**成本**: 方案A +15%, 方案B +20%, 方案C 0%

---

### 🟡 中等风险：commodities（可能过度提取）

**问题**:
```json
"commodities": [
  "Pb", "Zn", "Ag",  // 主要商品
  "Cd", "In", "Ga", "Ge", "Bi", "Sb", "Se", "Te", "Tl", "Co", "Ni", "As"  // 伴生元素
]
```

**噪音来源**:
- **主次不分** - 主要商品vs伴生元素
- **经济性未考虑** - 有些元素提及但无经济价值

**改进建议**:

```json
"commodities": {
  "primary": ["Pb", "Zn", "Ag"],          // 主要商品（论文重点）
  "byproduct": ["Cd", "In", "Ga"],        // 副产品（有经济价值）
  "trace": ["As", "Se", "Te"]             // 微量元素（仅科学意义）
}
```

**成本**: +5%

---

### 🟡 中等风险：host_rocks（可能过于详细或泛化）

**问题**:
- 有些论文：`["limestone", "marble"]` （泛化）
- 有些论文：`["pelitic metasediments", "hornfels", "carbonaceous slate"]` （过细）

**改进建议**:

```json
"host_rocks": {
  "primary": ["limestone"],               // 主要围岩
  "specific_types": ["marble", "dolomitic limestone"],  // 具体类型
  "lithology_group": "carbonate"          // 大类
}
```

**成本**: +5%

---

### 🟢 低风险字段（暂不改动）

- **alteration**: 已经很规范
- **structural_controls**: 描述性，可接受
- **metallogenic_belt**: 通常准确
- **tectonic_setting**: 描述性，无标准化需求

---

## 三、缺失的高价值字段（建议新增）

### 1. Grade & Tonnage（品位与储量）⭐⭐⭐

**为什么重要**: 经济价值核心

```json
"deposit_scale": {
  "tonnage_mt": 5.2,                    // 储量（百万吨）
  "grade": {
    "Au_ppm": 3.5,                      // 金品位
    "Cu_percent": 0.8                   // 铜品位
  },
  "scale_class": "large",               // 大型/中型/小型
  "production_status": "producing",     // 生产中/已停产/勘探
  "citation": "Table 2"                 // 来源
}
```

**填充率预估**: 30-50%  
**成本**: +10%  
**优先级**: P1（Week 3）

---

### 2. Exploration Indicators（找矿标志）⭐⭐

**为什么重要**: 实用价值（勘探指导）

```json
"exploration_indicators": {
  "geochemical": ["As-Au anomaly", "Sb pathfinder"],
  "geophysical": ["gravity low", "magnetic anomaly"],
  "visible": ["quartz veins", "silicification", "gossans"],
  "drilling_targets": "优先钻探NE向断裂带与围岩接触部位"
}
```

**填充率预估**: 30-40%  
**成本**: +10%  
**优先级**: P2（Week 4）

---

### 3. Genetic Model（成因模型）⭐⭐

**为什么重要**: 科学价值（成因理解）

```json
"genetic_model": {
  "ore_source": "granitic magma",
  "transport_mechanism": "hydrothermal fluid via fractures",
  "deposition_trigger": "chemical reaction with limestone",
  "timing_relation": "syn-to-late granite intrusion",
  "model_confidence": "high"
}
```

**问题**: 与mineral_system重复度高  
**建议**: mineral_system已覆盖大部分，可不新增  
**优先级**: P3（低）

---

### 4. Geochemistry（地球化学特征）⭐⭐

**为什么重要**: 成因判断依据

```json
"geochemistry": {
  "trace_elements": {
    "enriched": ["REE", "Y", "Nb"],
    "depleted": ["Sr", "Ba"]
  },
  "isotopes": {
    "sulfur_delta34s": "+5.2 to +8.5‰",
    "lead_206_204": "18.5-18.8"
  },
  "citation": "Figure 7, Table 4"
}
```

**填充率预估**: 40-60%  
**成本**: +15%  
**优先级**: P2（Week 3-4）

---

### 5. References Cited（参考文献/对比矿床）⭐

**为什么重要**: 知识图谱构建

```json
"reference_deposits": [
  {"name": "Carlin", "relation": "相似成因"},
  {"name": "Yilgarn", "relation": "对比研究"}
]
```

**填充率预估**: 40-60%  
**成本**: +5%  
**优先级**: P2（Week 3）

---

## 四、优先级排序

### Week 2（立即部署）✅
1. ✅ coordinates
2. ✅ deposit_type_evidence

### Week 3（高价值）
1. **is_primary_research_reason** - 成本0%, 填充率100%
2. **deposit_scale** (品位储量) - 经济价值核心
3. **minerals分类** - 降低噪音

### Week 4（中等价值）
1. **geochemistry** - 科学价值
2. **reference_deposits** - 知识图谱
3. **ages_ma扩展** - 增加method/citation

### 长期（低优先级）
1. exploration_indicators - 实用但填充率低
2. commodities分类 - 改进但非必需

---

## 五、噪音控制策略

### 当前最大噪音源

1. **minerals_mentioned** - 30+种混杂
2. **commodities** - 主次不分
3. **host_rocks** - 详细程度不一

### 降噪方案

#### 短期（Week 3）
```
minerals_mentioned → diagnostic_minerals (仅5-10种关键矿物)
成本: 0% (减少output)
效果: 降噪60%+
```

#### 中期（Week 4）
```
minerals → {ore_minerals, gangue_minerals, alteration_minerals}
成本: +10%
效果: 结构化，易用
```

---

## 六、成本预算

| 阶段 | 新增字段 | 成本增加 | 累计成本 |
|------|---------|----------|----------|
| Week 2 | coordinates + deposit_type_evidence | +$0 | $1.12 |
| Week 3 | is_primary_research_reason + deposit_scale + minerals分类 | +$0.30 | $1.42 |
| Week 4 | geochemistry + reference_deposits + ages_ma扩展 | +$0.40 | $1.82 |

**全量1244篇总成本**: $1.82

---

## 七、建议

### ✅ 立即行动（Week 2）
- coordinates
- deposit_type_evidence

### 📋 Week 3计划
1. **is_primary_research_reason** - 零成本，立即价值
2. **deposit_scale** - 高价值（经济评估）
3. **minerals降噪** - 改为diagnostic_minerals

### 🤔 需要讨论
1. **minerals分类方案** - 方案A/B/C选哪个？
2. **geochemistry** - 是否值得+15%成本？
3. **ages_ma扩展** - 填充率只有53.8%，是否值得？

---

**核心原则**: 
1. **高填充率优先** - >80%才有统计意义
2. **低噪音优先** - 宁缺毋滥
3. **成本效益** - ROI<20%慎重考虑
4. **渐进式** - 每个字段先小样本验证

---

**准备好讨论下一步！**
