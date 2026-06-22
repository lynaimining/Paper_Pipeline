#!/usr/bin/env python3
"""
优化的图像QA生成Pipeline
集成今天所有的改进：
1. Ground Truth驱动（从Caption反向设计问题）
2. 空间等价性支持
3. Gold/Silver分级扩增
"""

import json
import os
import hashlib
import asyncio
from pathlib import Path
from openai import AsyncOpenAI
from typing import List, Dict, Optional
from figure_classifier import load_qwen_spatial_images, classify_figure

# ==================== 配置 ====================

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
MODEL = "deepseek-chat"

# ==================== 成本追踪（全局累加） ====================

class UsageTracker:
    """累加API token使用"""
    def __init__(self):
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.calls = 0

    def add(self, usage):
        if usage:
            self.prompt_tokens += getattr(usage, 'prompt_tokens', 0)
            self.completion_tokens += getattr(usage, 'completion_tokens', 0)
            self.calls += 1

    def to_dict(self):
        return {
            'api_calls': self.calls,
            'prompt_tokens': self.prompt_tokens,
            'completion_tokens': self.completion_tokens,
            'total_tokens': self.prompt_tokens + self.completion_tokens,
        }

USAGE = UsageTracker()

# ==================== 分类型空间推理Prompt ====================

# 各类图的空间推理聚焦点
_SPATIAL_FOCUS = {
    "geo_map": """This is a GEOLOGICAL MAP. Ask about PLANAR spatial relationships:
- Directional distribution (e.g. "deposits aligned NE-SW")
- Structural control (e.g. fault-mineralization spatial relationship)
- Relative position (which side of a fault is a body on)
- Scale-bridging (what a local pattern implies regionally)""",

    "cross_section": """This is a CROSS-SECTION. Ask about VERTICAL spatial relationships:
- Dip direction (which way does an orebody/fault dip)
- Depth sequence (top-to-bottom stratigraphic order)
- Cross-cutting (which units a fault cuts through)
- Thickness variation along strike""",

    "geophys_map": """This is a GEOPHYSICAL figure (magnetic/gravity/IP/EM/seismic).
Ask about ANOMALY spatial relationships:
- Anomaly location & geometry (where is the high/low, its shape)
- Spatial coupling with structures (anomaly aligned with a fault?)
- For sections: depth & velocity/reflector structure, reflector geometry
- What subsurface body the anomaly likely represents""",
}

GROUND_TRUTH_PROMPT = """You are a geology expert creating training data for VLM SPATIAL REASONING.

Figure Caption (EXPERT ANNOTATION - This is Ground Truth):
"{caption}"

Figure type: {figure_type}
Text in figure: {text_in_figure}
Legend items: {legend}

{spatial_focus}

Your task: Generate {n_qa} SPATIAL question-answer pairs.

**CRITICAL RULES**:

1. **Answers MUST come from the caption** (it's the expert ground truth):
   - Quote or paraphrase caption content, preserve precise directions/positions

2. **Questions MUST require SPATIAL reasoning** — about WHERE / WHICH DIRECTION /
   relative position / geometry. The answer should require LOOKING at the figure's
   spatial layout, not just reading text.

3. **STRICTLY FORBIDDEN** (these are OCR/classification, NOT spatial reasoning):
   - "What does the figure show?" / "What is shown in this figure?"
   - "What is the range of values / the unit / measured in?"
   - "What type of figure / map is this?"
   - "What items are in the legend?"
   If the caption only contains a title/unit with no spatial content,
   generate FEWER questions rather than asking non-spatial ones.

4. **Spatial equivalence is natural** (both forms correct):
   - "A west of B" = "B east of A"
   - "NW-SE trend" = "SE-NW trend"
   - "A overlies B" = "B underlies A"

5. Answer format: 40-150 chars, include specific terms from caption.

**GOOD examples** (spatial):
- Q: In which direction do the faults trend? A: NW-SE trending.
- Q: Which unit overlies the Silurian strata? A: Lower Cretaceous unit F.
- Q: Where is the magnetic high located relative to the fault? A: East of the fault.

**BAD examples** (forbidden — OCR/classification):
- Q: What does the figure show? A: Total magnetic intensity. ← FORBIDDEN
- Q: What is the unit? A: nT. ← FORBIDDEN

Generate {n_qa} SPATIAL QA pairs. If caption lacks spatial content, generate fewer.

Output JSON:
[
  {{"question": "...", "answer": "..."}},
  ...
]
"""

# ==================== 等价QA生成规则 ====================

class EquivalenceGenerator:
    """Gold和Silver级等价QA生成器"""

    @staticmethod
    def generate_gold_equivalents(qa: Dict) -> List[Dict]:
        """
        Gold级：完全等价（置信度100%）
        - 线性构造双向趋势
        - 上下关系互换
        """
        gold_eqs = []
        answer = qa['answer']

        # Gold规则1: 双向趋势
        trend_pairs = [
            ('NW-SE', 'SE-NW'),
            ('NE-SW', 'SW-NE'),
            ('N-S', 'S-N'),
            ('E-W', 'W-E'),
            ('northwest-southeast', 'southeast-northwest'),
            ('northeast-southwest', 'southwest-northeast'),
        ]

        for t1, t2 in trend_pairs:
            if t1 in answer:
                gold_eqs.append({
                    **qa,
                    'question': qa['question'].replace('trend', 'strike direction'),
                    'answer': answer.replace(t1, t2),
                    'tier': 'gold',
                    'equivalence_type': 'bidirectional_trend',
                    'confidence': 1.0,
                    'original_id': qa['id']
                })
                break

        # Gold规则2: 上下关系互换
        if ' overlies ' in answer.lower():
            parts = answer.lower().split(' overlies ')
            if len(parts) == 2:
                entity_a = parts[0].strip().title()
                entity_b = parts[1].strip().rstrip('.').title()

                gold_eqs.append({
                    'image': qa['image'],
                    'question': f"What underlies the {entity_a}?",
                    'answer': f"The {entity_b} underlies the {entity_a}.",
                    'tier': 'gold',
                    'equivalence_type': 'vertical_inverse',
                    'confidence': 1.0,
                    'original_id': qa['id'],
                    'caption': qa.get('caption', ''),
                    'has_ground_truth': True,
                    'generation_method': 'gold_augmentation'
                })

        return gold_eqs

    @staticmethod
    def generate_silver_equivalents(qa: Dict) -> List[Dict]:
        """
        Silver级：部分等价（置信度75%）
        - 分布方向的反向问题
        - 位置-内容反向
        """
        silver_eqs = []
        question = qa['question'].lower()
        answer = qa['answer'].lower()

        # Silver规则: 方向分布反向
        if ('trend' in question or 'distribution' in question):
            direction = None
            trend_directions = ['nw-se', 'ne-sw', 'n-s', 'e-w']

            for direction_key in trend_directions:
                if direction_key in answer:
                    direction = direction_key.upper()
                    break

            if direction:
                # 提取实体类型
                entity = 'features'
                if 'fault' in answer:
                    entity = 'faults'
                elif 'deposit' in answer:
                    entity = 'deposits'
                elif 'mineralization' in answer:
                    entity = 'mineralization'

                silver_eqs.append({
                    'image': qa['image'],
                    'question': f"What geological features are aligned in the {direction} direction?",
                    'answer': f"{entity.capitalize()} are aligned in the {direction} direction.",
                    'tier': 'silver',
                    'equivalence_type': 'reverse_distribution',
                    'confidence': 0.75,
                    'caveat': 'Other features may also be present in this direction',
                    'original_id': qa['id'],
                    'caption': qa.get('caption', ''),
                    'has_ground_truth': True,
                    'generation_method': 'silver_augmentation'
                })

        return silver_eqs

# ==================== 主Pipeline ====================

class OptimizedQAPipeline:
    """优化的QA生成Pipeline"""

    def __init__(self, api_key: str, concurrency: int = 5):
        self.client = AsyncOpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)
        self.semaphore = asyncio.Semaphore(concurrency)
        self.eq_generator = EquivalenceGenerator()

    async def generate_ground_truth_qa(
        self,
        image_record: Dict,
        n_qa: int = 3
    ) -> List[Dict]:
        """
        为单张图生成Ground Truth驱动的QA

        Args:
            image_record: 包含image_path, caption, figure_type等
            n_qa: 每张图生成的QA数量

        Returns:
            QA列表
        """
        # 完整ground truth = caption + 正文(Fig.X)引用句（Part E）
        caption = image_record.get('full_groundtruth') or image_record.get('caption', '')
        category = image_record.get('category', 'geo_map')

        if not caption or len(caption) < 20:
            print(f"  ⚠️  No ground truth, skipping: {image_record.get('image_path', '')[-60:]}")
            return []

        # 按图类型选择空间推理聚焦点
        spatial_focus = _SPATIAL_FOCUS.get(category, _SPATIAL_FOCUS['geo_map'])

        # 构建prompt
        prompt = GROUND_TRUTH_PROMPT.format(
            caption=caption,
            figure_type=image_record.get('figure_type', 'geological figure'),
            text_in_figure='; '.join(str(t) for t in (image_record.get('text_in_figure') or [])[:8]) or 'N/A',
            legend='; '.join(str(l) for l in (image_record.get('legend') or [])[:5]) or 'N/A',
            spatial_focus=spatial_focus,
            n_qa=n_qa
        )

        async with self.semaphore:
            try:
                response = await self.client.chat.completions.create(
                    model=MODEL,
                    messages=[
                        {"role": "system", "content": "You are a precision geology expert specializing in spatial reasoning."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.2,
                    max_tokens=600
                )

                USAGE.add(response.usage)
                result_text = response.choices[0].message.content

                # 解析JSON
                import re
                json_match = re.search(r'\[[\s\S]*?\]', result_text)
                if not json_match:
                    return []

                qa_list = json.loads(json_match.group())

                # 添加元数据
                qa_records = []
                for qa in qa_list:
                    qa_id = hashlib.md5(
                        f"{image_record['image_path']}{qa['question']}".encode()
                    ).hexdigest()[:10]

                    qa_records.append({
                        'id': f'imgqa_{qa_id}',
                        'image': image_record['image_path'],
                        'question': qa['question'],
                        'answer': qa['answer'],
                        'caption': image_record.get('caption', ''),
                        'groundtruth': caption,  # 完整ground truth(caption+正文引用)，供监控
                        'figure_type': image_record.get('figure_type'),
                        'category': category,
                        'n_body_refs': image_record.get('n_body_refs', 0),
                        'paper_id': image_record.get('paper_id', ''),
                        'has_ground_truth': True,
                        'generation_method': 'ground_truth_driven'
                    })

                return qa_records

            except Exception as e:
                print(f"  ❌ Error: {e}")
                return []

    def augment_with_equivalents(
        self,
        qa_list: List[Dict],
        include_silver: bool = True
    ) -> List[Dict]:
        """
        使用Gold/Silver等价扩增QA

        Args:
            qa_list: 原始QA列表
            include_silver: 是否包含Silver级扩增

        Returns:
            扩增后的QA列表
        """
        augmented = list(qa_list)

        for qa in qa_list:
            # Gold级扩增
            gold_eqs = self.eq_generator.generate_gold_equivalents(qa)
            for eq in gold_eqs:
                eq['id'] = f"imgqa_gold_{hashlib.md5(eq['question'].encode()).hexdigest()[:10]}"
            augmented.extend(gold_eqs)

            # Silver级扩增
            if include_silver:
                silver_eqs = self.eq_generator.generate_silver_equivalents(qa)
                for eq in silver_eqs:
                    eq['id'] = f"imgqa_silver_{hashlib.md5(eq['question'].encode()).hexdigest()[:10]}"
                augmented.extend(silver_eqs)

        return augmented

    async def process_batch(
        self,
        image_records: List[Dict],
        n_qa_per_image: int = 3,
        include_silver: bool = True
    ) -> List[Dict]:
        """
        批量处理图像生成QA

        Args:
            image_records: 图像记录列表
            n_qa_per_image: 每张图生成的QA数
            include_silver: 是否包含Silver级扩增

        Returns:
            最终QA列表（包含原始+扩增）
        """
        print(f"Processing {len(image_records)} images...")

        # 并发生成Ground Truth QA
        tasks = [
            self.generate_ground_truth_qa(img, n_qa_per_image)
            for img in image_records
        ]

        results = await asyncio.gather(*tasks)

        # 展平
        all_qa = []
        for qa_list in results:
            all_qa.extend(qa_list)

        print(f"Generated {len(all_qa)} Ground Truth QA")

        # 等价扩增
        augmented = self.augment_with_equivalents(all_qa, include_silver)

        gold_count = len([qa for qa in augmented if qa.get('tier') == 'gold'])
        silver_count = len([qa for qa in augmented if qa.get('tier') == 'silver'])

        print(f"Augmented: {len(augmented)} total")
        print(f"  - Original: {len(all_qa)}")
        print(f"  - Gold: {gold_count}")
        print(f"  - Silver: {silver_count}")

        # 只保留 Tier A：问题含至少1个空间推理关键词
        _SPATIAL_KW = [
            'from north to south', 'from south to north', 'from east to west', 'from west to east',
            'where', 'location', 'located', 'position', 'spatial', 'extent',
            'extend', 'extension', 'direction', 'directional', 'arrangement',
            'distribution', 'boundary', 'border', 'contact', 'relative to',
            'between', 'east of', 'west of', 'north of', 'south of',
            'strike', 'dip', 'depth', 'zone', 'relationship', 'adjacent',
            'proximal', 'distal', 'corridor', 'domain', 'belt', 'region',
        ]
        before = len(augmented)
        augmented = [
            qa for qa in augmented
            if any(kw in qa.get('question', '').lower() for kw in _SPATIAL_KW)
        ]
        print(f"  → Tier A filter: {before} → {len(augmented)} (dropped {before - len(augmented)} non-spatial)")

        # P1-B: Blind Test 视觉依赖性验证
        # 不看图就能答的 → 降级为文本QA（source改为text_from_image），不丢弃
        augmented, text_demoted = await self._blind_test_filter(augmented)

        return augmented, text_demoted

    async def _blind_test_filter(self, qa_list: List[Dict]):
        """P1-B: Blind Test — 不看图就能答的条目降级为文本QA，需要看图的保留为图QA"""
        if not qa_list:
            return qa_list, []

        BLIND_PROMPT = (
            "Answer the following geology question WITHOUT any image. "
            "If you can give a confident specific answer from general knowledge, do so. "
            "If you cannot answer without seeing a specific figure, reply EXACTLY: NEEDS_IMAGE\n\n"
            "Question: {question}"
        )

        async def check_one(qa: Dict) -> bool:
            """返回 True 表示保留为图QA（需要看图），False 表示降级为文本QA（不看图也能答）"""
            async with self.semaphore:
                try:
                    resp = await self.client.chat.completions.create(
                        model=MODEL,
                        messages=[{"role": "user", "content":
                                   BLIND_PROMPT.format(question=qa['question'])}],
                        temperature=0.0,
                        max_tokens=60,
                    )
                    USAGE.add(resp.usage)
                    reply = resp.choices[0].message.content.strip()
                    return 'NEEDS_IMAGE' in reply.upper()
                except Exception:
                    return True  # 出错时保留为图QA

        tasks = [check_one(qa) for qa in qa_list]
        keep_flags = await asyncio.gather(*tasks)

        image_qa = []
        text_demoted = []
        for qa, keep in zip(qa_list, keep_flags):
            if keep:
                image_qa.append(qa)
            else:
                # 降级为文本QA：去���image字段，标记来源
                text_qa = {k: v for k, v in qa.items() if k != 'image'}
                text_qa['source'] = 'text_from_image'
                text_qa['blind_test'] = 'text_answerable'
                text_demoted.append(text_qa)

        print(f"  → Blind Test: {len(qa_list)} image QA → {len(image_qa)} keep + {len(text_demoted)} demoted to text QA")
        return image_qa, text_demoted

async def run_optimized_pipeline(
    qwen_results_path: str,
    output_path: str,
    api_key: str,
    max_images: int = 0,
    n_qa_per_image: int = 3,
    include_silver: bool = False,
    groundtruth_path: str = ""
):
    """
    运行完整的优化pipeline

    Args:
        qwen_results_path: Qwen VL识别结果路径
        output_path: 输出路径
        api_key: DeepSeek API key
        max_images: 最多处理多少张图（0=全部）
        n_qa_per_image: 每张图生成QA数
        include_silver: 是否包含Silver级扩增
    """
    print("=" * 70)
    print("优化的图像QA生成Pipeline")
    print("=" * 70)

    # 读取Qwen VL结果，用分类器筛选「空间推理图」（已排除photomicrograph/table/噪声）
    caption_images, class_stats = load_qwen_spatial_images(qwen_results_path)

    print(f"\n图像分类统计:")
    print(f"  geo_map: {class_stats['geo_map']} | cross_section: {class_stats['cross_section']} | geophys_map: {class_stats['geophys_map']}")
    print(f"  丢弃junk: {class_stats['junk']} | table任务: {class_stats['table_task']}")
    print(f"  → 空间推理图: {len(caption_images)} 张")

    # 加载正文引用ground truth（caption + 正文(Fig.X)引用句），合并到每张图
    gt_map = {}
    if groundtruth_path and os.path.exists(groundtruth_path):
        gt_map = json.load(open(groundtruth_path, encoding='utf-8'))
        print(f"  加载正文ground truth: {len(gt_map)} 图")

    for img in caption_images:
        # 用图片hash匹配ground truth
        img_hash = Path(img['image_path']).stem
        gt = gt_map.get(img_hash, {})
        body_refs = gt.get('body_refs', [])
        # 完整ground truth = caption + 正文引用句
        full_gt = img.get('caption', '')
        if body_refs:
            full_gt = (full_gt + '\n' + '\n'.join(f"(body) {r}" for r in body_refs))[:1500]
        img['full_groundtruth'] = full_gt
        img['n_body_refs'] = len(body_refs)

    # 保留条件：有caption 或 有正文引用句（任一即可生成QA）
    before = len(caption_images)
    caption_images = [img for img in caption_images
                      if (img.get('caption') and len(str(img['caption'])) > 20)
                      or img.get('n_body_refs', 0) > 0]
    with_body = sum(1 for img in caption_images if img.get('n_body_refs', 0) > 0)
    print(f"  → 可生成QA(有caption或正文引用): {len(caption_images)}/{before} 张 (其中{with_body}张有正文引用)")

    if max_images > 0:
        caption_images = caption_images[:max_images]
        print(f"限制处理: {max_images} 张")

    # 运行pipeline
    pipeline = OptimizedQAPipeline(api_key, concurrency=5)

    image_qa_results, text_demoted = await pipeline.process_batch(
        caption_images,
        n_qa_per_image=n_qa_per_image,
        include_silver=include_silver
    )

    # 保存图QA
    with open(output_path, 'w') as f:
        for qa in image_qa_results:
            f.write(json.dumps(qa, ensure_ascii=False) + '\n')

    # 保存降级文本QA（blind test判定不需要看图的）到单独文件供合并
    text_demoted_path = output_path.replace('.jsonl', '_text_demoted.jsonl')
    if text_demoted:
        with open(text_demoted_path, 'w') as f:
            for qa in text_demoted:
                f.write(json.dumps(qa, ensure_ascii=False) + '\n')
        print(f"✅ 降级文本QA: {text_demoted_path} ({len(text_demoted)} 条)")

    print(f"\n✅ 保存到: {output_path}")

    # 统计
    stats = {
        'total': len(image_qa_results),
        'text_demoted': len(text_demoted),
        'original': len([qa for qa in image_qa_results if qa.get('generation_method') == 'ground_truth_driven']),
        'gold': len([qa for qa in image_qa_results if qa.get('tier') == 'gold']),
        'silver': len([qa for qa in image_qa_results if qa.get('tier') == 'silver']),
        'usage': USAGE.to_dict(),
    }

    print(f"\n📊 统计:")
    print(f"  图QA: {stats['total']} 条")
    print(f"  降级为文本QA: {stats['text_demoted']} 条 (blind test: 不需要看图)")
    print(f"  原始Ground Truth: {stats['original']} 条")
    print(f"  Gold扩增: {stats['gold']} 条 (置信度100%)")
    print(f"  Silver扩增: {stats['silver']} 条 (置信度75%)")
    print(f"  Token: {stats['usage']['total_tokens']} ({stats['usage']['api_calls']}次调用)")

    # 保存usage到同目录（供成本聚合用）
    usage_path = output_path.replace('.jsonl', '_usage.json')
    with open(usage_path, 'w') as f:
        json.dump(stats['usage'], f, indent=2)

    return image_qa_results, text_demoted

# ==================== 主入口 ====================

def main():
    import argparse

    parser = argparse.ArgumentParser(description='优化的图像QA生成Pipeline')
    parser.add_argument('--qwen-results', required=True, help='Qwen VL识别结果JSONL文件')
    parser.add_argument('--output', required=True, help='输出JSONL文件')
    parser.add_argument('--groundtruth', default='', help='figure_groundtruth.json(caption+正文引用)，可选但推荐')
    parser.add_argument('--max', type=int, default=0, help='最多处理N张图（0=全部）')
    parser.add_argument('--n-qa', type=int, default=3, help='每张图生成N个QA')
    parser.add_argument('--silver', action='store_true', help='开启Silver级反向扩增(默认关闭,有噪声)')

    args = parser.parse_args()

    # 从环境变量获取API key
    api_key = os.environ.get('DEEPSEEK_API_KEY')
    if not api_key:
        print("错误: 请设置 DEEPSEEK_API_KEY 环境变量")
        return

    # 运行
    asyncio.run(run_optimized_pipeline(
        qwen_results_path=args.qwen_results,
        output_path=args.output,
        api_key=api_key,
        max_images=args.max,
        n_qa_per_image=args.n_qa,
        include_silver=args.silver,
        groundtruth_path=args.groundtruth
    ))

if __name__ == '__main__':
    main()
