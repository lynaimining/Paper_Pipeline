# 打分字段改进方案 - 增加事实依据

**问题**: deposit_type_conf只有数字（0.0-1.0），缺少判断依据  
**目标**: 所有打分字段都应包含事实依据（evidence/citation/comment）

---

## 当前状态分析

### ✅ 做得好的字段

#### 1. mineral_system（七要素）
```json
{
  "source": {
    "score": 3,
    "evidence": "Metals sourced from granitic magmatism (Cullen Supersuite) and/or sedimentary rocks"
  }
}
```
**优点**: 
- score + evidence结构
- evidence是具体事实，可追溯
- 从论文中直接引用

#### 2. coordinates
```json
{
  "latitude": -13.58,
  "longitude": 131.83,
  "confidence": 0.7,
  "source": "论文描述：Mount Evelyn deposit位于Pine Creek Orogen...",
  "extraction_method": "地名推断"
}
```
**优点**:
- confidence + source结构
- source说明了坐标来源
- extraction_method说明了提取方法

---

### ❌ 需要改进的字段

#### 1. deposit_type_conf（核心问题）

**当前**:
```json
{
  "deposit_type": "SKARN",
  "deposit_type_conf": 0.9
}
```

**问题**:
- 只有0.9这个数字
- 不知道为什么是SKARN而不是其他类型
- 无法追溯判断依据

**改进方案**:
```json
{
  "deposit_type": "SKARN",
  "deposit_type_conf": 0.9,
  "deposit_type_evidence": {
    "keywords": ["skarn", "limestone", "granite intrusion", "exoskarn"],
    "minerals": ["magnetite", "pyrrhotite", "chalcopyrite", "pyrite"],
    "alteration": ["potassic", "calc-silicate"],
    "citation": "论文明确提到'Pb-Zn-Ag skarn deposit'，围岩limestone，侵入体granite",
    "alternative_types": [
      {"type": "IOCG", "score": 0.3, "reason": "有magnetite但缺少典型IOCG特征"}
    ]
  }
}
```

---

## 改进方案

### 方案A: 最小改动（推荐Week 2）

**仅新增deposit_type_evidence字段**

```json
{
  "deposit_type": "SKARN",
  "deposit_type_conf": 0.9,
  "deposit_type_evidence": "论文标题和正文明确提到'skarn deposit'，围岩limestone，蚀变calc-silicate，矿物assemblage典型skarn特征"
}
```

**优点**:
- 改动最小，只加一个字段
- 立即可实施
- 成本增加<10%（~20 output tokens）

**缺点**:
- 不如方案B结构化

---

### 方案B: 结构化evidence（推荐Week 3）

```json
{
  "deposit_type": "SKARN",
  "deposit_type_conf": 0.9,
  "deposit_type_evidence": {
    "primary_indicators": [
      "论文标题含'skarn deposit'",
      "围岩limestone与granite接触",
      "calc-silicate蚀变"
    ],
    "supporting_evidence": [
      "矿物组合: magnetite, pyrrhotite, chalcopyrite",
      "构造位置: granite接触带"
    ],
    "citation": "论文第3页：'Pb-Zn-Ag skarn deposit formed at the contact between Cullen Granite and Koolpin Formation limestone'",
    "alternative_considered": [
      {"type": "IOCG", "rejected_because": "缺少典型Na-Ca蚀变"}
    ]
  }
}
```

**优点**:
- 结构化，可机器解析
- 包含排除推理（alternative_considered）
- 可引用原文（citation）

**缺点**:
- 改动较大
- 成本增加~30%（~50 output tokens）

---

### 方案C: 引用原文（最全面，Week 4）

```json
{
  "deposit_type": "SKARN",
  "deposit_type_conf": 0.9,
  "deposit_type_evidence": {
    "direct_citations": [
      {
        "quote": "Pb-Zn-Ag skarn deposit formed at the contact between granite and limestone",
        "location": "Abstract, line 3",
        "confidence_contribution": 0.7
      }
    ],
    "inferred_from": [
      {
        "observation": "calc-silicate alteration assemblage",
        "reasoning": "典型skarn蚀变",
        "confidence_contribution": 0.2
      }
    ],
    "diagnostic_features": ["limestone host", "granite contact", "skarn minerals"],
    "ruling_out": {
      "IOCG": "缺少Na-Ca蚀变",
      "VMS": "无火山岩"
    }
  }
}
```

**优点**:
- 最全面，可完整重现推理过程
- 包含原文引用
- 支持置信度拆解

**缺点**:
- 改动最大
- 成本增加~50%（~100 output tokens）
- 复杂度高

---

## 推荐实施路线

### Week 2: 方案A（最小改动）✅

**立即可做**，与coordinates全量部署一起：

```python
# 修改SYSTEM_PROMPT
"""
- deposit_type_conf: 置信度 0.0-1.0
- deposit_type_evidence: 判断依据（字符串），说明为什么是这个矿床类型。
  包括：
  1. 论文中的明确描述（如"skarn deposit"）
  2. 关键特征（围岩、矿物、蚀变）
  3. 排除其他类型的理由（可选）
  
  示例: "论文标题明确'skarn deposit'，围岩limestone与granite接触，蚀变calc-silicate，矿物magnetite+chalcopyrite典型skarn组合"
"""
```

**测试**:
```bash
# 在test_coordinates_deep.py基础上
# 新增deposit_type_evidence字段
# 测试5篇样本，验证填充率和质量
```

---

### Week 3: 方案B（结构化）

**在方案A验证成功后**，升级为结构化：

```python
"deposit_type_evidence": {
  "primary_indicators": [str],      # 主要证据
  "supporting_evidence": [str],     # 支持证据
  "citation": str,                  # 原文引用
  "alternative_considered": [       # 考虑过的其他类型
    {"type": str, "rejected_because": str}
  ]
}
```

---

### Week 4: 方案C（引用原文）

**可选**，如果需要完整可追溯性。

---

## 其他打分字段建议

### 1. is_primary_research（当前是boolean）

**当前**:
```json
{"is_primary_research": true}
```

**改进**:
```json
{
  "is_primary_research": true,
  "is_primary_research_reason": "论文主要目的是研究Mount Evelyn矿床的地质特征和成因，而非方法学验证"
}
```

---

### 2. ages_ma（当前只有数字）

**当前**:
```json
{"ages_ma": [125.3, 121.0]}
```

**改进**:
```json
{
  "ages_ma": [
    {
      "age": 125.3,
      "uncertainty": 1.2,
      "method": "U-Pb zircon",
      "material": "granite",
      "interpretation": "intrusion age",
      "citation": "Figure 5, sample MTE-01"
    }
  ]
}
```

---

## 成本分析

| 方案 | 新增tokens | 成本增加 | 填充率预估 | 推荐 |
|------|-----------|----------|-----------|------|
| 方案A（字符串） | ~20 | +10% | 95%+ | ✅ Week 2 |
| 方案B（结构化） | ~50 | +30% | 90%+ | Week 3 |
| 方案C（引用） | ~100 | +50% | 80%+ | Week 4 |

**全量成本**（1244篇）:
- 方案A: $1.64 → $1.80（+$0.16）
- 方案B: $1.64 → $2.13（+$0.49）
- 方案C: $1.64 → $2.46（+$0.82）

---

## 立即行动（Week 2）

### 测试方案A

```python
# 创建 test_deposit_type_evidence.py
# 基于 test_coordinates_deep.py
# 新增 deposit_type_evidence 字段
# 测试5篇样本
```

**测试目标**:
1. 填充率≥90%
2. evidence质量：包含关键特征描述
3. 成本增加<15%

**如果测试通过**:
- 与coordinates一起全量部署
- 总成本: $1.80（$1.64 + $0.16）

---

## 总结

**核心思想**: **所有打分都应有事实依据**

**已经做好的**:
- ✅ mineral_system: score + evidence
- ✅ coordinates: confidence + source

**需要改进的**:
- ❌ deposit_type_conf: 只有数字，需加evidence

**推荐路线**:
- Week 2: 方案A（+$0.16，立即可做）
- Week 3: 方案B（结构化）
- Week 4: 方案C（引用原文，可选）

---

**立即可测试方案A，成本增加仅$0.16！**
