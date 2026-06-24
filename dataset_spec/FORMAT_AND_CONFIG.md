# Paper_Pipeline_Final — 数据格式规范 & 最优配置

## 数据格式：ShareGPT（LLaMA-Factory 标准）

### 文本 QA 条目

```json
{
  "id": "qa_e21792ede586",
  "paper_id": "2123",
  "qa_type": "text",
  "source": "template",
  "dimension": "spatial_location",
  "quality_score": 0.7,
  "split": "train",
  "conversations": [
    {"from": "system", "value": "You are a geology expert specializing in metallic mineral deposits..."},
    {"from": "human", "value": "What is the metallogenic belt hosting the orogenic gold?"},
    {"from": "gpt",   "value": "The deposit is situated within the Pine Creek inlier, northern Australia."}
  ]
}
```

### 图 QA 条目（多轮）

```json
{
  "id": "imggrp_abc123",
  "paper_id": "1172",
  "qa_type": "image",
  "source": "ground_truth_driven",
  "dimension": "visual_spatial",
  "figure_category": "geo_map",
  "quality_score": 0.8,
  "split": "train",
  "images": ["images/1172/<hash>.jpg"],
  "conversations": [
    {"from": "system", "value": "You are a geology expert..."},
    {"from": "human", "value": "<image>\nIn which direction are the tungsten deposits aligned?"},
    {"from": "gpt",   "value": "NE-SW, following the Hercynian structural trend."},
    {"from": "human", "value": "Where are the skarn deposits relative to the granitoids?"},
    {"from": "gpt",   "value": "At the boundaries of the Upper Westphalian Granitoids."}
  ]
}
```

### 规则

| 规则 | 说明 |
|---|---|
| 字段 `from` | 只能是 `system` / `human` / `gpt` |
| 字段 `value` | 字符串 |
| 图像路径 | 顶层 `images: [...]`，相对于 `image_dir`（LLaMA-Factory 配置项） |
| `<image>` token | 第一个 `human` turn 的 value 开头插入 `<image>\n` |
| 多轮图 QA | 同一张图的多条 QA 聚合进一条记录，后续 human turn 无 `<image>` |
| `split` 字段 | `train` / `val` / `test`，由 `build_global.py` paper 级别切分（8:1:1, seed=42）填写 |

---

## 最优运行配置（30 篇实测）

### GPU 环境修复（每次新实例必做）

```bash
# 修复 libcuda.so.1 指向错误版本
ln -sfn libcuda.so.580.95.05 /usr/lib/x86_64-linux-gnu/libcuda.so.1
ln -sfn libcuda.so.580.95.05 /usr/lib/x86_64-linux-gnu/libcuda.so

# 建 /dev/nvidia0 映射（容器设备是 nvidia6）
mknod /dev/nvidia0 c 195 6 2>/dev/null || true
chmod a+rw /dev/nvidia0

# 验证
python3 -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

### MinerU GPU 配置（/root/magic-pdf.json）

```json
{
  "bucket_info": {"bucket-name-1": ["ak","sk","endpoint"]},
  "models-dir": "/root/models/MinerU/models",
  "device-mode": "cuda",
  "layoutreader-model-dir": "/root/models/MinerU/models/layoutreader",
  "layout-config": {"model": "doclayout_yolo"},
  "formula-config": {"mfd_model": "yolo_v8_mfd", "mfr_model": "unimernet_small", "enable": false},
  "table-config": {"model": "rapid_table", "is_table_recog_enable": false}
}
```

- GPU vs CPU 速度：0.69 page/s vs 0.21 page/s（3.3×）
- 公式识别关掉：unimernet 与 transformers 5.10 不兼容，后续流程有兜底

### Qwen VL 图像识别（qwen_vl_hf.py）

| 参数 | 值 | 原因 |
|---|---|---|
| `batch` | 4 | 实测最优（batch=8 反而慢，GPU compute 已饱和） |
| `tasks` | `image` | table 任务暂不需要 |
| `padding_side` | `left` | 必须！不加会输出乱码"addCriterion" |
| 速度 | 0.35 img/s | RTX PRO 6000 Blackwell 94GB 实测 |
| vLLM | ❌ 不可用 | sm_120 (Blackwell) FlashInfer 不支持，等 vLLM ≥ 0.25 |

```bash
python3 scripts/qwen_vl_hf.py \
    --corpus /tmp/eg_corpus \
    --out /tmp/qwen_out \
    --tasks image \
    --batch 4
```

### image QA 生成（optimized_qa_pipeline.py）

- DeepSeek API，concurrency=5
- `img_caption` 需从 content_list.json 注入（MinerU caption 字段），否则只有 7/99 张有 caption
- blind-test 降级：约 35% 图 QA 被判定无需看图，降级为文本 QA

### process_paper + build_global

```bash
python3 scripts/pipeline_v5.py \
    --paper-ids <ids...> \
    --trusted-json <trusted.json> \
    --eg-root "<EG root>" \
    --output-dir dataset \
    --with-image-qa \
    --qwen-results <qwen_vl_results.jsonl> \
    --workers 16

python3 scripts/build_global.py \
    --dataset-dir dataset \
    --split-ratio 0.8 0.1 0.1 \
    --seed 42
```

---

## 单篇论文耗时（30 篇实测均值）

| 阶段 | 耗时 | 资源 |
|---|---|---|
| MinerU PDF 解析 | 26s/篇 | GPU |
| Qwen VL 图像识别 | 37s/篇（12.7 img avg） | GPU |
| DeepSeek 25字段抽取 | 1.7s/篇 | API |
| Image QA 生成 | 1.1s/篇 | API |
| process_paper（CPU） | <1s/篇 | CPU 16 workers |
| **合计** | **~67s/篇** | |

### 100k 篇估算（5% pass rate → 5,000 篇需完整跑）

```
GPU total: ~3.9 天（单卡）
横向扩：2 卡 ≈ 2 天，4 卡 ≈ 1 天
```

---

## LLaMA-Factory 配置

### dataset_info.json 关键字段

```json
{
  "geo_spatial_train": {
    "file_name": "train.jsonl",
    "formatting": "sharegpt",
    "columns": {"messages": "conversations", "images": "images"},
    "tags": {
      "role_tag": "from", "content_tag": "value",
      "user_tag": "human", "assistant_tag": "gpt", "system_tag": "system"
    }
  }
}
```

### LoRA 关键超参

| 参数 | 值 |
|---|---|
| 底座 | Qwen2.5-VL-7B-Instruct |
| `lora_rank` | 16 |
| `lora_alpha` | 32 |
| `lora_target` | all |
| `image_max_pixels` | 1254400（1120²） |
| `bf16` | true |
| `gradient_checkpointing` | true |
| effective batch | 16（batch=2 × grad_acc=8） |
| lr | 1e-4，cosine，warmup 5% |

---

## 已知问题 & 注意事项

1. **vLLM 不支持 Blackwell (sm_120)**：等官方支持，当前用 transformers 版本
2. **公式识别关掉**：unimernet 与 transformers 5.10 API 不兼容
3. **img_caption 必须从 content_list.json 注入**：Qwen 本身对老论文扫描图 title_or_caption 几乎全为 null
4. **commodities 字段归一化**：新 trusted records 可能是 dict（含 primary/byproduct/trace），generate_qa.py 已处理
5. **CUDA 803 修复命令**：每次新实例挂卡后必须执行（见上方"GPU 环境修复"）
