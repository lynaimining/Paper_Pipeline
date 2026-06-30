# Paper Pipeline Production

PDF → structured geological data → LLM fine-tuning dataset

Processes academic geology papers through MinerU (PDF parsing) → DeepSeek (structured extraction) → Qwen VL (image understanding) → LLaMA-Factory (training).

## Data Flow

```
PDF corpus
  ↓ [MinerU, offline]
auto/*.md + *_content_list.json
  ↓ [deepseek_extract.py]
trusted.json (25-field structured records, 109-type deposit vocabulary)
  ↓ [generate_qa.py]
_text_qa_all.jsonl (43 spatial-reasoning templates)
  ↓ [qwen_vl_hf.py + optimized_qa_pipeline.py, optional]
_image_qa.jsonl
  ↓ [process_paper.py × 16 workers]
unified/<paper_id>.jsonl (per-paper ShareGPT format)
  ↓ [build_global.py]
train.jsonl / val.jsonl / test.jsonl  →  LLaMA-Factory / ms-swift
```

## Scripts

| Script | Purpose |
|--------|---------|
| `deepseek_extract.py` | Async DeepSeek API extraction, checkpoint resume, cost tracking |
| `gate_lite.py` | Quality gate: 3-layer funnel (exact → alias normalize → FLAG) |
| `generate_qa.py` | 43-template spatial reasoning QA from trusted records |
| `process_paper.py` | Per-paper artifact assembly → unified ShareGPT JSONL |
| `pipeline_final.py` | End-to-end orchestrator, 16-worker parallel |
| `qwen_vl_hf.py` | Qwen2.5-VL image understanding via vLLM |
| `build_global.py` | Multi-machine merge + paper-level train/val/test split |
| `export.py` | Export structured DB (CSV / GeoJSON / JSONL) |
| `build_extractor_train.py` | Build extractor training set from splits |
| `build_benchmark.py` | Build evaluation benchmark |
| `build_corpus.py` | Build clean text corpus |

## Quick Start

```bash
# 1. Set API key
export DEEPSEEK_API_KEY=sk-xxx

# 2. Configure MinerU model path
# Edit config/magic-pdf.json: set "models-dir" to your MinerU models path

# 3. Extract structured data from corpus
python scripts/deepseek_extract.py /path/to/corpus /path/to/output

# 4. Build training dataset
python scripts/pipeline_final.py \
    --paper-ids-file paper_ids.txt \
    --trusted-json config/trusted_100_papers.json \
    --eg-root /path/to/corpus \
    --output-dir dataset_final
```

## Dependencies

- Python 3.12+
- CUDA GPU required for Qwen VL inference
- `pip install -r requirements.txt`
- MinerU installed separately (see requirements.txt comments)

## Tests

```bash
python -m pytest tests/ -q
```

70+ tests covering gate logic, QA generation, coordinate normalization, split anti-leakage, cost estimation, and end-to-end smoke test.
