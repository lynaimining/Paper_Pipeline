# Pipeline v4 — NRR矿床论文结构化提取

**版本**: v4.0.0  **日期**: 2026-06-21  **状态**: 定稿

---

## 架构

```
论文MD → DeepSeek提取(25字段) → 后处理(清洗+坐标匹配) → 三桶分流 → 结构化JSON
```

## 快速开始

### 1. 单次提取 + 后处理

```bash
cd /root/autodl-tmp/pipeline-v4

# 提取（使用scripts/deepseek_extract.py）
python3 scripts/deepseek_extract.py <corpus_dir> <output_dir> \
    --enhanced-dir <enhanced_md_dir> \
    --concurrency 20

# 后处理（清洗 + 坐标匹配 + 成矿带推断）
python3 scripts/postprocess.py <output_dir>/all_results.json <output_dir>/all_results_processed.json

# 三桶分流 + 对账
python3 run_v4_pipeline.py <output_dir>/all_results_processed.json <output_dir>/final/
```

### 2. 全量运行（1244篇）

```bash
# 参考 /root/autodl-tmp/run_full_qa_pipeline.sh
# OUTPUT_DIR 设为 pipeline_v4_outputs/
```

---

## Schema（25个字段）

### 基础分类
| 字段 | 类型 | 说明 |
|------|------|------|
| paper_id | str | 论文标识符 |
| deposit_type | str/null | 矿床类型（开放枚举） |
| deposit_type_conf | float | 置信度 0-1 |
| deposit_type_evidence | str/null | 类型判断依据 |
| deposit_class | str | 论文分类（6种） |
| is_primary_research | bool | 是否主研究 |
| is_primary_research_reason | str | 判断理由 |

### 空间信息
| 字段 | 类型 | 说明 |
|------|------|------|
| countries | list | 国家 |
| metallogenic_belt | str | 成矿带 |
| tectonic_setting | str | 构造背景 |
| coordinates | obj/null | 坐标（lat/lon/precision/confidence） |

### 矿物与商品
| 字段 | 类型 | 说明 |
|------|------|------|
| minerals | obj/null | 分类矿物（ore/gangue/alteration） |
| alteration | list | 蚀变类型 |
| commodities | obj/null | 分类商品（primary/byproduct/trace） |

### 规模与年代
| 字段 | 类型 | 说明 |
|------|------|------|
| host_rocks | list | 围岩 |
| structural_controls | list | 构造控制 |
| deposit_scale | obj/null | 品位吨位 |
| ages | list/null | 年龄（含method/material/citation） |

### 地球化学与成矿
| 字段 | 类型 | 说明 |
|------|------|------|
| geochemistry | obj/null | 微量元素/同位素/流体包裹体 |
| reference_deposits | list/null | 参考矿床 |
| mineral_system | obj/null | 矿物系统七要素（含evidence） |

---

## 后处理工具

```
scripts/
├── deepseek_extract.py      # 主提取（含完整25字段prompt）
├── postprocess.py           # 后处理一键脚本
│   ├── clean_geochemistry   # 清洗空结构
│   ├── build_global_db      # USGS MRDS坐标匹配（102,555个矿床）
│   └── match_belt_coordinates # 成矿带推断（225条）
├── gate_lite.py             # 质量门控（canonical版，开放枚举）
└── monitor_quality.py       # 分批监控

lib/
├── triage.py               # 三桶分流（pass→trusted/warn→review/fail→quarantine）
├── reconcile.py            # 对账（数据守恒证明）
├── dedup.py                # Content-hash去重
├── sanitize.py             # 路径消毒
└── verify_gate.py          # Gate版本锁定校验
```

---

## 坐标覆盖策略（三层）

| 层级 | 方法 | 准确率 | 精度 |
|------|------|--------|------|
| LLM提取 | 从论文图件/文本读取 | 高 | 矿区级~省级 |
| 矿床库匹配 | USGS MRDS 102,555个矿床 | 极高 | 矿区级 |
| 成矿带推断 | 225条全球成矿带库 | 中 | 成矿带级±50km |

实测：纯矿床论文100%覆盖，混合数据集有矿床类型论文86%覆盖

---

## 质量保障

### 数据工程守则
- **三桶分流**: pass→trusted / warn→review / fail→quarantine
- **对账机制**: input = trusted + review + quarantine + deduped
- **去重**: Content-hash去重（排除paper_id）
- **路径消毒**: 防路径穿越
- **Gate锁定**: Canonical版本验证

### 坐标质量
- 重名门控：同名多国矿床强制验证国家
- 停用词过滤：basin/extension等通用词不触发匹配
- 白名单机制：只匹配已知专有矿床名称

---

## 测试验证结果

| 数据集 | 样本 | 坐标覆盖 | 核心字段 | 成本/篇 |
|--------|------|---------|---------|---------|
| EG+MD 矿床论文 | 39篇 | 100% | 100% | $0.0016 |
| Lithos+AJES 混合 | 32篇 | 86%（矿床类型） | 100% | $0.0017 |
| 1244篇全量预计 | — | ~90% | ~100% | $2.08总计 |
