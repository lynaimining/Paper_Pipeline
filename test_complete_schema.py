#!/usr/bin/env python3
"""
完整Schema提取 - 一次性全上版本
包含所有高价值字段：
- coordinates (空间坐标)
- deposit_type_evidence (类型证据)
- minerals分类 (ore/gangue/alteration)
- deposit_scale (品位吨位)
- commodities分类 (primary/byproduct/trace)
- is_primary_research_reason (判断理由)
- geochemistry (地球化学)
- reference_deposits (参考矿床)
- ages扩展 (method/material/citation)
"""
import os, sys, json, asyncio
from pathlib import Path
from openai import AsyncOpenAI

# 完整版 SYSTEM_PROMPT
SYSTEM_PROMPT_COMPLETE = """你是一个矿床地质学专家。从学术论文中提取结构化信息。

## 输出格式

严格输出JSON对象，字段如下：

### 基础分类
- paper_id: 论文标识符
- deposit_type: 矿床类型（OROG-AU/SKARN/VMS等）或null
- deposit_type_conf: 置信度 0.0-1.0
- deposit_type_evidence: 判断依据（字符串），包括：论文明确描述、关键特征、排除其他类型理由
- is_primary_research: true/false
- is_primary_research_reason: 判断理由（字符串），说明为何是主研究或辅助研究

### 空间信息
- countries: 国家数组
- metallogenic_belt: 成矿带名称
- coordinates: 坐标对象或null，格式：
  {
    "latitude": 35.50417,
    "longitude": 115.2125,
    "precision": "矿区级",  // 矿区级/省级/国家级
    "source": "Figure 1地质图坐标网格",
    "confidence": 0.95,
    "extraction_method": "图件坐标网格"  // 图件坐标网格/明确经纬度/地名推断
  }

### 矿物信息（重要：分类）
- minerals: 矿物分类对象，格式：
  {
    "ore_minerals": ["sphalerite", "galena", "chalcopyrite"],  // 矿石矿物
    "gangue_minerals": ["quartz", "calcite", "dolomite"],       // 脉石矿物
    "alteration_minerals": ["tremolite", "diopside"]            // 蚀变矿物
  }
  不要把所有矿物混在一起！ore是成矿的，gangue是脉石，alteration是蚀变产物。

- alteration: 蚀变类型数组

### 商品信息（重要：分类）
- commodities: 商品分类对象，格式：
  {
    "primary": ["Pb", "Zn", "Ag"],     // 主要商品（论文重点）
    "byproduct": ["Cd", "In"],         // 副产品（有经济价值）
    "trace": ["As", "Se"]              // 微量元素（仅科学意义）
  }

### 规模信息（新增，重要）
- deposit_scale: 矿床规模对象或null，格式：
  {
    "tonnage": {
      "value": 5.2,
      "unit": "Mt",  // Mt/kt/t
      "resource_type": "proven+probable"  // proven/probable/inferred/measured+indicated
    },
    "grade": {
      "Au_ppm": 3.5,
      "Cu_percent": 0.8,
      "Ag_ppm": 25
    },
    "scale_class": "large",  // world-class/large/medium/small/prospect
    "production_status": "producing",  // producing/past producer/prospect/exploration
    "citation": "Table 2"
  }
  只提取论文明确提到的数字，不要猜测。如果论文没有储量/品位数据，填null。

### 地质信息
- host_rocks: 围岩数组
- structural_controls: 构造控制数组
- tectonic_setting: 构造背景

### 年代信息（扩展）
- ages: 年龄数组或null，格式：
  [
    {
      "age_ma": 125.3,
      "uncertainty": 1.2,
      "method": "U-Pb zircon",
      "material": "granite",
      "interpretation": "侵入年龄",
      "citation": "Figure 5"
    }
  ]
  只提取论文明确的测年数据，包括方法和材料。

### 地球化学（新增）
- geochemistry: 地球化学对象或null，格式：
  {
    "trace_elements": {
      "enriched": ["REE", "Y", "Nb"],
      "depleted": ["Sr", "Ba"]
    },
    "isotopes": {
      "sulfur_delta34s": "+5.2 to +8.5‰",
      "lead_206_204": "18.5-18.8"
    },
    "fluid_inclusion": {
      "temperature_c": "250-350",
      "salinity_wt_nacl": "5-15"
    },
    "citation": "Figure 7, Table 4"
  }
  只提取论文明确提到的地球化学数据，不要编造。

### 参考矿床（新增）
- reference_deposits: 参考矿床数组或null，格式：
  [
    {
      "name": "Carlin (Nevada)",
      "relation": "类型对比",
      "similarity": "相似的碳酸盐岩容矿"
    }
  ]
  提取论文中明确对比的其他矿床。

### 成矿系统
- mineral_system: 七要素评估，每个要素包含score(1-5)和evidence

只输出JSON，不输出其他文字。"""

USER_TEMPLATE = """论文ID: {paper_id}

论文全文:

{body}"""


async def extract_complete(paper_id: str, md_path: str, client: AsyncOpenAI) -> dict:
    """完整提取（所有字段）"""
    with open(md_path, encoding='utf-8') as f:
        body = f.read()[:30000]  # 保留30k字符

    try:
        resp = await client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_COMPLETE},
                {"role": "user", "content": USER_TEMPLATE.format(paper_id=paper_id, body=body)}
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
        )

        result = json.loads(resp.choices[0].message.content)
        usage = resp.usage

        return {
            "result": result,
            "tokens": {
                "input": usage.prompt_tokens,
                "output": usage.completion_tokens
            }
        }

    except Exception as e:
        print(f"  ❌ 错误: {e}")
        return None


async def run_complete_pilot(num_samples: int = 20):
    """运行完整提取试点（20篇）"""

    # 加载样本
    trusted_path = Path("test_output/trusted.json")
    with open(trusted_path) as f:
        trusted = json.load(f)

    mineral_deposits = [r for r in trusted
                       if r.get("deposit_class") == "mineral_deposit"][:num_samples]

    print("=" * 80)
    print(f"完整Schema提取试点 - {num_samples}篇样本")
    print("=" * 80)
    print()
    print("提取字段：")
    print("  1. coordinates (坐标)")
    print("  2. deposit_type_evidence (类型证据)")
    print("  3. minerals分类 (ore/gangue/alteration)")
    print("  4. deposit_scale (品位吨位)")
    print("  5. commodities分类 (primary/byproduct/trace)")
    print("  6. is_primary_research_reason (判断理由)")
    print("  7. geochemistry (地球化学)")
    print("  8. reference_deposits (参考矿床)")
    print("  9. ages扩展 (method/material/citation)")
    print()

    # 准备样本
    test_samples = []
    for record in mineral_deposits:
        paper_id = record.get("paper_id")
        md_path = f"/root/autodl-tmp/corpus/pipeline-v3/400test-outputs/enhanced_md/{paper_id}.md"

        if Path(md_path).exists():
            test_samples.append({
                "paper_id": paper_id,
                "md_path": md_path
            })

    print(f"找到 {len(test_samples)} 篇样本\n")

    # 提取
    client = AsyncOpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com"
    )

    results = []
    total_tokens = {"input": 0, "output": 0}

    for i, sample in enumerate(test_samples, 1):
        print(f"[{i}/{len(test_samples)}] {sample['paper_id'][:50]}...")

        result_data = await extract_complete(
            sample['paper_id'],
            sample['md_path'],
            client
        )

        if result_data:
            result = result_data["result"]
            tokens = result_data["tokens"]

            total_tokens["input"] += tokens["input"]
            total_tokens["output"] += tokens["output"]

            # 快速展示关键字段
            coords = result.get("coordinates")
            minerals = result.get("minerals")
            scale = result.get("deposit_scale")
            geochem = result.get("geochemistry")

            print(f"  坐标: {'✅' if coords else '❌'}", end="")
            print(f" | 矿物分类: {'✅' if minerals and isinstance(minerals, dict) else '❌'}", end="")
            print(f" | 规模: {'✅' if scale else '❌'}", end="")
            print(f" | 地化: {'✅' if geochem else '❌'}")
            print(f"  Tokens: {tokens['input']}/{tokens['output']}")

            results.append({
                "paper_id": sample['paper_id'],
                "extracted": result,
                "tokens": tokens
            })

        print()

        # 每5篇休息
        if i % 5 == 0:
            await asyncio.sleep(1)

    # 分析
    analyze_complete_results(results, total_tokens)

    # 保存
    with open("complete_pilot_results.json", "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n详细结果: complete_pilot_results.json")

    return results


def analyze_complete_results(results, total_tokens):
    """分析完整提取结果"""

    print("\n" + "=" * 80)
    print("完整Schema提取分析")
    print("=" * 80)
    print()

    total = len(results)

    # 统计各字段填充率
    fields_to_check = {
        "coordinates": "空间坐标",
        "deposit_type_evidence": "类型证据",
        "minerals": "矿物分类",
        "deposit_scale": "品位吨位",
        "commodities": "商品分类",
        "is_primary_research_reason": "判断理由",
        "geochemistry": "地球化学",
        "reference_deposits": "参考矿床",
        "ages": "年龄详情"
    }

    print("【字段填充率】")
    print("-" * 80)

    for field, name in fields_to_check.items():
        count = 0
        for r in results:
            value = r['extracted'].get(field)
            if value not in [None, [], "", {}]:
                # 特殊检查minerals和commodities是否是dict
                if field in ["minerals", "commodities"]:
                    if isinstance(value, dict) and any(value.values()):
                        count += 1
                else:
                    count += 1

        rate = count / total * 100
        status = "✅" if rate >= 80 else "⚠️" if rate >= 50 else "❌"
        print(f"  {status} {name:20} {rate:5.1f}% ({count}/{total})")

    print()

    # 成本分析
    avg_input = total_tokens["input"] / total
    avg_output = total_tokens["output"] / total
    cost_per_paper = (avg_input * 0.14 / 1_000_000) + (avg_output * 0.28 / 1_000_000)
    cost_1244 = cost_per_paper * 1244

    print("【成本分析】")
    print("-" * 80)
    print(f"  平均 input tokens: {avg_input:.0f}")
    print(f"  平均 output tokens: {avg_output:.0f}")
    print(f"  单篇成本: ${cost_per_paper:.4f}")
    print(f"  1244篇总成本: ${cost_1244:.2f}")
    print()

    # 质量抽查
    print("【质量抽查】")
    print("-" * 80)

    # 检查minerals是否正确分类
    minerals_ok = 0
    for r in results:
        minerals = r['extracted'].get('minerals')
        if isinstance(minerals, dict):
            if 'ore_minerals' in minerals or 'gangue_minerals' in minerals:
                minerals_ok += 1

    print(f"  矿物正确分类: {minerals_ok}/{total} ({minerals_ok/total*100:.0f}%)")

    # 检查commodities是否正确分类
    commodities_ok = 0
    for r in results:
        commodities = r['extracted'].get('commodities')
        if isinstance(commodities, dict):
            if 'primary' in commodities:
                commodities_ok += 1

    print(f"  商品正确分类: {commodities_ok}/{total} ({commodities_ok/total*100:.0f}%)")

    print()

    # 结论
    print("=" * 80)
    print("结论")
    print("=" * 80)

    # 计算平均填充率
    avg_fill_rate = sum(
        1 for field in fields_to_check.keys()
        for r in results
        if r['extracted'].get(field) not in [None, [], "", {}]
    ) / (len(fields_to_check) * total) * 100

    print(f"平均字段填充率: {avg_fill_rate:.1f}%")
    print(f"1244篇总成本: ${cost_1244:.2f}")
    print()

    if avg_fill_rate >= 70:
        print("✅ 填充率优秀，可以全量部署")
    elif avg_fill_rate >= 50:
        print("⚠️  填充率中等，需要优化prompt")
    else:
        print("❌ 填充率偏低，需要重新设计")


if __name__ == "__main__":
    if not os.getenv("DEEPSEEK_API_KEY"):
        print("❌ 缺少 DEEPSEEK_API_KEY")
        sys.exit(1)

    asyncio.run(run_complete_pilot(20))
