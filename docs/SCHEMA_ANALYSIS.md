# Schema 字段价值分析与优化建议

**基于**: Pipeline v4 测试数据（39篇矿床论文）  
**日期**: 2026-06-21

---

## 当前字段填充率分析

### ✅ 核心字段（填充率100%，必须保留）

| 字段 | 填充率 | 价值 | 建议 |
|------|--------|------|------|
| **paper_id** | 100% | 主键 | ✅ 保留 |
| **deposit_class** | 100% | 论文分类（mineral_deposit/structural_tectonic等） | ✅ 保留，用于过滤 |
| **deposit_type** | 100% | 矿床类型（OROG-AU/SKARN等） | ✅ 保留，核心业务字段 |
| **deposit_type_conf** | 100% | 置信度 | ✅ 保留，质量评估 |
| **is_primary_research** | 100% | 是否主研究 | ✅ 保留，区分主/辅研究 |
| **host_rocks** | 100% | 围岩 | ✅ 保留，地质核心属性 |
| **minerals_mentioned** | 100% | 矿物列表 | ✅ 保留，矿床特征关键 |
| **commodities** | 100% | 商品金属 | ✅ 保留，经济价值核心 |
| **metallogenic_belt** | 100% | 成矿带 | ✅ 保留，空间推理关键 |
| **tectonic_setting** | 100% | 构造背景 | ✅ 保留，成因分析核心 |
| **mineral_system** | 100% | 矿物系统七要素 | ✅ 保留，成矿系统分析 |

### ✅ 高价值字段（填充率≥80%）

| 字段 | 填充率 | 价值 | 建议 |
|------|--------|------|------|
| **countries** | 97.4% | 国家 | ✅ 保留，地理定位 |
| **alteration** | 82.1% | 蚀变类型 | ✅ 保留，找矿指示 |

### ⚠️ 中等价值字段（50-80%）

| 字段 | 填充率 | 价值 | 建议 |
|------|--------|------|------|
| **structural_controls** | 76.9% | 构造控制 | ⚠️ 保留但降低权重 |
| **ages_ma** | 53.8% | 年龄 | ⚠️ 保留，但非所有论文都有测年 |

### ❌ 低价值/冗余字段

| 字段 | 填充率 | 问题 | 建议 |
|------|--------|------|------|
| **no_deposit_reason** | 0% (矿床论文) | 仅用于非矿床论文 | ❌ 删除，改用deposit_class判断 |

---

## 缺失的高价值字段（建议新增）

### 1. 空间坐标（Coordinates）

**当前问题**: 只有 `countries` 和 `metallogenic_belt`（文本描述），缺少精确坐标

**建议新增**:
```python
"coordinates": {
    "latitude": 35.5,        # 纬度
    "longitude": 115.2,      # 经度
    "coord_precision": "矿区级",  # 精度：矿区级/省级/国家级
    "coord_source": "论文图1"     # 来源
}
```

**价值**:
- ✅ 空间推理训练的核心（LLM地理定位）
- ✅ 可视化（地图展示）
- ✅ 空间聚类分析

**填充率预估**: 60-80%（很多论文有位置图）

---

### 2. 矿床规模（Deposit Scale）

**当前问题**: 只有 `commodities`，不知道储量/品位

**建议新增**:
```python
"deposit_scale": {
    "tonnage_mt": 5.2,           # 吨位（百万吨）
    "grade_au_ppm": 3.5,         # 金品位（ppm）
    "grade_cu_percent": 0.8,     # 铜品位（%）
    "scale_class": "large",      # 规模：large/medium/small
    "production_status": "producing"  # 开采状态：producing/past producer/prospect
}
```

**价值**:
- ✅ 经济价值评估
- ✅ 区分世界级矿床 vs 小矿点
- ✅ 训练"矿床规模 vs 地质特征"关联

**填充率预估**: 30-50%（不是所有论文都报储量）

---

### 3. 参考矿床（Reference Deposits）

**当前问题**: 论文常对比典型矿床，但未抽取

**建议新增**:
```python
"reference_deposits": [
    {"name": "Carlin", "relation": "相似成因"},
    {"name": "Yilgarn", "relation": "对比研究"}
]
```

**价值**:
- ✅ 矿床类比推理
- ✅ 构建矿床知识图谱
- ✅ 发现隐含相似性

**填充率预估**: 40-60%

---

### 4. 地球化学特征（Geochemistry）

**当前问题**: `minerals_mentioned` 有矿物，但缺少地球化学签名

**建议新增**:
```python
"geochemistry": {
    "trace_elements": ["REE", "Y", "Nb", "Ta"],  # 微量元素富集
    "isotope_signatures": {
        "sulfur_delta34s": "+5.2 to +8.5",       # 硫同位素
        "lead_206_204": "18.5-18.8"              # 铅同位素
    },
    "fluid_inclusion": {
        "salinity_wt_nacl": "5-15",              # 盐度
        "temperature_c": "250-350"               # 均一温度
    }
}
```

**价值**:
- ✅ 成因判断（岩浆 vs 沉积 vs 变质）
- ✅ 矿源追踪
- ✅ 训练地球化学推理

**填充率预估**: 40-60%（地球化学论文多，但不是全部论文都测）

---

### 5. 图件信息（Figures）

**当前问题**: Qwen已经读图，但图片信息未结构化保存

**建议新增**:
```python
"figures": [
    {
        "figure_id": "Fig. 3",
        "type": "geological_map",       # 类型：地质图/剖面图/柱状图
        "caption": "Geological map...",
        "spatial_entities": [           # 从图中提取的空间实体
            {"type": "fault", "name": "Main Fault", "orientation": "NE-SW"},
            {"type": "orebody", "name": "Orebody #1", "location": "north"}
        ],
        "has_coordinates": true         # 是否有坐标系
    }
]
```

**价值**:
- ✅ 视觉-文本对齐训练
- ✅ 空间关系理解
- ✅ 图件检索

**填充率预估**: 80%+（几乎所有矿床论文都有图）

---

### 6. 找矿模型（Exploration Model）

**当前问题**: 缺少"如何找这类矿"的知识

**建议新增**:
```python
"exploration_model": {
    "target_indicators": [              # 找矿标志
        "羽状石英脉", 
        "黄铁绢英岩化",
        "As-Au地球化学异常"
    ],
    "geophysical_signatures": [         # 地球物理特征
        "重力低",
        "磁异常"
    ],
    "drilling_recommendations": "优先钻探NE向断裂带与围岩接触部位"
}
```

**价值**:
- ✅ 勘探指导
- ✅ 训练"找矿标志 → 矿床类型"推理
- ✅ 构建找矿知识库

**填充率预估**: 30-40%（有些论文明确讨论找矿，有些不涉及）

---

## Schema 优化建议总结

### 📋 调整方案

#### 方案A：保守（推荐Week 2）
```python
# 保留所有现有字段
# 新增2个高优先级字段
+ coordinates         # 空间坐标（填充率60-80%）
+ figures            # 图件信息（填充率80%+）
```

#### 方案B：激进（Week 3-4考虑）
```python
# 在方案A基础上新增
+ deposit_scale              # 矿床规模
+ reference_deposits         # 参考矿床
+ geochemistry              # 地球化学
+ exploration_model         # 找矿模型
```

#### 删除/简化
```python
- no_deposit_reason          # 删除，用deposit_class判断
? structural_controls        # 考虑合并到 mineral_system.trap
```

---

## 字段优先级（按业务价值）

### P0 - 核心字段（已有，必须保留）
1. paper_id
2. deposit_type
3. deposit_class
4. commodities
5. host_rocks
6. minerals_mentioned
7. metallogenic_belt
8. tectonic_setting

### P1 - 高价值扩展（建议Week 2新增）
1. **coordinates** - 空间定位核心
2. **figures** - 视觉信息结构化

### P2 - 中等价值（Week 3-4考虑）
1. **deposit_scale** - 经济价值
2. **reference_deposits** - 知识图谱
3. **geochemistry** - 成因判断

### P3 - 低优先级（长期考虑）
1. **exploration_model** - 勘探指导
2. **mining_history** - 开采历史
3. **environmental_impact** - 环境影响

---

## 实施建议

### Week 2（立即行动）

1. **新增 coordinates 字段**
   - 修改 deepseek_extract.py 的 SYSTEM_PROMPT
   - 指导LLM从论文中提取 lat/lon（从图、文本、矿区名）
   - 填充率目标：60%+

2. **新增 figures 字段**
   - 利用现有 Qwen 视觉识别结果
   - 结构化保存图件类型、caption、空间实体
   - 填充率目标：80%+

3. **删除 no_deposit_reason**
   - 用 deposit_class 替代
   - 简化schema

### Week 3-4（视Week 2效果）

- 评估 deposit_scale / geochemistry 的投入产出比
- 小样本测试（50篇）验证填充率
- 决定是否全量采纳

---

## 附：字段填充率与训练价值的关系

| 填充率 | 训练价值 | 策略 |
|--------|----------|------|
| 80%+ | 可作为强特征 | 必须保留 |
| 50-80% | 可作为辅助特征 | 保留但降权 |
| 30-50% | 仅少数样本有 | 视业务需求，可选 |
| <30% | 噪声大于信号 | 删除或改为可选 |

**核心原则**：填充率低的字段不是"没用"，而是"不适合作为必填项"。可以改为可选字段，让LLM在有把握时才填。

EOF
cat > /root/autodl-tmp/pipeline-v4/docs/SCHEMA_ANALYSIS.md << 'DOCEOF'
# Schema 字段价值分析与优化建议

**基于**: Pipeline v4 测试数据（39篇矿床论文）  
**日期**: 2026-06-21

---

## 当前字段填充率分析

### ✅ 核心字段（填充率100%，必须保留）

| 字段 | 填充率 | 价值 | 建议 |
|------|--------|------|------|
| **paper_id** | 100% | 主键 | ✅ 保留 |
| **deposit_class** | 100% | 论文分类（mineral_deposit/structural_tectonic等） | ✅ 保留，用于过滤 |
| **deposit_type** | 100% | 矿床类型（OROG-AU/SKARN等） | ✅ 保留，核心业务字段 |
| **deposit_type_conf** | 100% | 置信度 | ✅ 保留，质量评估 |
| **is_primary_research** | 100% | 是否主研究 | ✅ 保留，区分主/辅研究 |
| **host_rocks** | 100% | 围岩 | ✅ 保留，地质核心属性 |
| **minerals_mentioned** | 100% | 矿物列表 | ✅ 保留，矿床特征关键 |
| **commodities** | 100% | 商品金属 | ✅ 保留，经济价值核心 |
| **metallogenic_belt** | 100% | 成矿带 | ✅ 保留，空间推理关键 |
| **tectonic_setting** | 100% | 构造背景 | ✅ 保留，成因分析核心 |
| **mineral_system** | 100% | 矿物系统七要素 | ✅ 保留，成矿系统分析 |

### ✅ 高价值字段（填充率≥80%）

| 字段 | 填充率 | 价值 | 建议 |
|------|--------|------|------|
| **countries** | 97.4% | 国家 | ✅ 保留，地理定位 |
| **alteration** | 82.1% | 蚀变类型 | ✅ 保留，找矿指示 |

### ⚠️ 中等价值字段（50-80%）

| 字段 | 填充率 | 价值 | 建议 |
|------|--------|------|------|
| **structural_controls** | 76.9% | 构造控制 | ⚠️ 保留但降低权重 |
| **ages_ma** | 53.8% | 年龄 | ⚠️ 保留，但非所有论文都有测年 |

### ❌ 低价值/冗余字段

| 字段 | 填充率 | 问题 | 建议 |
|------|--------|------|------|
| **no_deposit_reason** | 0% (矿床论文) | 仅用于非矿床论文 | ❌ 删除，改用deposit_class判断 |

---

## 缺失的高价值字段（建议新增）

### 1. 空间坐标（Coordinates）⭐⭐⭐

**当前问题**: 只有文本描述，缺少精确坐标

**建议新增**:
```python
"coordinates": {
    "latitude": 35.5,
    "longitude": 115.2,
    "coord_precision": "矿区级",  # 矿区级/省级/国家级
    "coord_source": "论文图1"
}
```

**价值**: 空间推理训练核心，可视化，空间聚类  
**预估填充率**: 60-80%

### 2. 图件信息（Figures）⭐⭐⭐

**当前问题**: Qwen已读图，但信息未结构化

**建议新增**:
```python
"figures": [{
    "figure_id": "Fig. 3",
    "type": "geological_map",
    "spatial_entities": [
        {"type": "fault", "orientation": "NE-SW"}
    ]
}]
```

**价值**: 视觉-文本对齐，空间关系理解  
**预估填充率**: 80%+

### 3. 矿床规模（Deposit Scale）⭐⭐

**建议新增**:
```python
"deposit_scale": {
    "tonnage_mt": 5.2,
    "grade_au_ppm": 3.5,
    "scale_class": "large"
}
```

**价值**: 经济价值评估，规模-特征关联  
**预估填充率**: 30-50%

### 4. 地球化学特征（Geochemistry）⭐⭐

**建议新增**:
```python
"geochemistry": {
    "trace_elements": ["REE", "Y"],
    "isotope_signatures": {"sulfur_delta34s": "+5.2 to +8.5"}
}
```

**价值**: 成因判断，矿源追踪  
**预估填充率**: 40-60%

---

## Schema 优化方案

### 方案A：保守（推荐Week 2）
```
+ coordinates        ⭐⭐⭐ 高价值，填充率高
+ figures           ⭐⭐⭐ 高价值，填充率高
- no_deposit_reason  冗余字段
```

### 方案B：激进（Week 3-4）
```
方案A +
+ deposit_scale
+ reference_deposits
+ geochemistry
+ exploration_model
```

---

## 实施建议

### Week 2
1. 新增 coordinates（目标填充率60%+）
2. 新增 figures（目标填充率80%+）
3. 删除 no_deposit_reason

### Week 3-4
- 小样本测试deposit_scale/geochemistry
- 评估投入产出比后决定

---

**核心原则**: 填充率<30%的字段改为可选，而非强制必填。
DOCEOF
cat /root/autodl-tmp/pipeline-v4/docs/SCHEMA_ANALYSIS.md
