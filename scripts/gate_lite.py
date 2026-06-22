#!/usr/bin/env python3
"""
gate_lite.py — LLM 抽取后的轻量门控
职责: catch 幻觉 + 数据工程基本面, 不再纠正抽取逻辑

用法:
    from gate_lite import gate_check
    results, report = gate_check(raw_results)
    # results: 带 _gate_status 和 _gate_flags 的结果列表
    # report: 门控统计摘要
"""
import hashlib
import json
from typing import Any

# ── 值域红线 ──
AGE_MIN, AGE_MAX = 0.0, 4600.0
LAT_MIN, LAT_MAX = -90.0, 90.0
LON_MIN, LON_MAX = -180.0, 180.0

# ── deposit_class 允许值（开放枚举）──
VALID_DEPOSIT_CLASSES = [
    'mineral_deposit',
    'structural_tectonic',
    'geochemical_petrology',
    'methodological',
    'energy',
    'none'
]

# ── deposit_type 不再用闭合枚举（改为开放） ──
# 旧版闭合枚举会误杀51.3%矿床论文（KUPFERSCHIEFER, JACUTINGA-AU等新矿种）
# 新版：只要有deposit_class即可，deposit_type允许任意值


def _check_one(record: dict) -> tuple[str, list[str]]:
    """
    检查单条记录, 返回 (status, flags)
    status: 'pass' | 'warn' | 'fail'
    flags: 问题列表 (空=通过)
    """
    flags = []

    # 1. 主键存在
    pid = record.get('paper_id')
    if not pid or not str(pid).strip():
        flags.append('FAIL:no_paper_id')
        return 'fail', flags

    # 2. deposit_class 合法值（开放deposit_type，只检查deposit_class）
    dc = record.get('deposit_class')
    if dc is not None and dc not in VALID_DEPOSIT_CLASSES:
        flags.append(f'WARN:unknown_deposit_class={dc}')  # WARN而非FAIL，允许新类别

    # 3. 坐标值域
    lat = record.get('coord_lat')
    lon = record.get('coord_lon')
    if lat is not None:
        try:
            lat = float(lat)
            if not (LAT_MIN <= lat <= LAT_MAX):
                flags.append(f'FAIL:lat_out_of_range={lat}')
        except (TypeError, ValueError):
            flags.append(f'FAIL:lat_not_numeric={lat}')
    if lon is not None:
        try:
            lon = float(lon)
            if not (LON_MIN <= lon <= LON_MAX):
                flags.append(f'FAIL:lon_out_of_range={lon}')
        except (TypeError, ValueError):
            flags.append(f'FAIL:lon_not_numeric={lon}')

    # 4. 年龄值域
    ages = record.get('ages_ma')
    if ages and isinstance(ages, list):
        for a in ages:
            try:
                a = float(a)
                if not (AGE_MIN <= a <= AGE_MAX):
                    flags.append(f'WARN:age_out_of_range={a}')
                    break
            except (TypeError, ValueError):
                flags.append(f'WARN:age_not_numeric={a}')
                break

    # 5. 置信度范围
    conf = record.get('deposit_type_conf')
    if conf is not None:
        try:
            conf = float(conf)
            if not (0.0 <= conf <= 1.0):
                flags.append(f'WARN:conf_out_of_range={conf}')
            elif conf < 0.5 and record.get('deposit_type') is not None:
                flags.append('FLAG:low_confidence')
        except (TypeError, ValueError):
            pass

    # 6. 有 deposit_type 但所���细节全空 → 可疑
    if record.get('deposit_type') is not None:
        detail_fields = ['host_rocks', 'alteration', 'structural_controls',
                         'minerals_mentioned', 'commodities', 'ages_ma',
                         'metallogenic_belt', 'tectonic_setting']
        all_empty = all(
            not record.get(f) or record.get(f) == [] or str(record.get(f)).lower() in ('null', 'none', '')
            for f in detail_fields
        )
        if all_empty:
            flags.append('FLAG:deposit_type_but_no_details')

    # Determine status
    if any(f.startswith('FAIL:') for f in flags):
        status = 'fail'
    elif any(f.startswith('WARN:') or f.startswith('FLAG:') for f in flags):
        status = 'warn'
    else:
        status = 'pass'

    return status, flags


def gate_check(results: list[dict], dedup: bool = True) -> tuple[list[dict], dict]:
    """
    对 LLM 抽取结果做门控检查。

    参数:
        results: LLM 抽取的原始结果列表
        dedup: 是否去重 (按 paper_id, 保留第一条)

    返回:
        (checked_results, report)
        - checked_results: 每条加了 _gate_status, _gate_flags 字段
        - report: 门控统计
    """
    # 去重
    if dedup:
        seen = set()
        deduped = []
        dup_count = 0
        for r in results:
            pid = r.get('paper_id', '')
            if pid in seen:
                dup_count += 1
                continue
            seen.add(pid)
            deduped.append(r)
        results = deduped
    else:
        dup_count = 0

    # 逐条检查
    checked = []
    counts = {'pass': 0, 'warn': 0, 'fail': 0}
    flag_counts = {}

    for r in results:
        status, flags = _check_one(r)
        r = r.copy()
        r['_gate_status'] = status
        r['_gate_flags'] = flags
        checked.append(r)
        counts[status] += 1
        for f in flags:
            flag_counts[f] = flag_counts.get(f, 0) + 1

    # 汇总报告
    report = {
        'total': len(checked),
        'duplicates_removed': dup_count,
        'pass': counts['pass'],
        'warn': counts['warn'],
        'fail': counts['fail'],
        'pass_rate': round(counts['pass'] / len(checked), 4) if checked else 0,
        'flag_counts': dict(sorted(flag_counts.items(), key=lambda x: -x[1])),
    }

    return checked, report


def content_hash(text: str) -> str:
    """生成内容哈希, 用于增量判断"""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


# ── CLI 入口 ──
if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("用法: python gate_lite.py <results.json>")
        sys.exit(1)

    data = json.load(open(sys.argv[1], encoding='utf-8'))
    checked, report = gate_check(data)

    print(f"门控结果:")
    print(f"  总数: {report['total']}")
    print(f"  通过: {report['pass']} ({report['pass_rate']:.1%})")
    print(f"  警告: {report['warn']}")
    print(f"  失败: {report['fail']}")
    print(f"  去重: {report['duplicates_removed']}")
    if report['flag_counts']:
        print(f"  问题明细:")
        for flag, cnt in report['flag_counts'].items():
            print(f"    {flag}: {cnt}")

    # 写入带门控标记的结果
    out = sys.argv[1].replace('.json', '_gated.json')
    json.dump(checked, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f"\n  结果: {out}")
