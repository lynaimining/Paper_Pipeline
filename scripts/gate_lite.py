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
    'none',
    'sedimentary_geology',   # 沉积/地层/古气候研究
    'geomorphology',         # 地貌/第四纪
    'paleontology',          # 古生物
]

# 未知 deposit_class → 最近邻归一化映射（防止 LLM 造词污染 B 层数据库）
_DEPOSIT_CLASS_REMAP = {
    'sedimentary':          'sedimentary_geology',
    'stratigraphy':         'sedimentary_geology',
    'paleoclimate':         'sedimentary_geology',
    'geomorphic':           'geomorphology',
    'quaternary':           'geomorphology',
    'paleobiology':         'paleontology',
    'structural':           'structural_tectonic',
    'tectonics':            'structural_tectonic',
    'petrology':            'geochemical_petrology',
    'geochemistry':         'geochemical_petrology',
    'isotope':              'geochemical_petrology',
    'geochronology':        'geochemical_petrology',
    'hydrocarbon':          'energy',
    'coal':                 'energy',
    'oil':                  'energy',
    'method':               'methodological',
    'modeling':             'methodological',
    'remote_sensing':       'methodological',
}

# ── deposit_type 别名归一化映射（第二层兜底）──
# 目的：LLM 输出命名漂移时自动映射到词表标准项，不丢数据、不误杀
# 规则：key 统一小写+连字符，value 为词表正式项
# 来源：从金标 8/30 不合规标签 + 常见文献别名归纳
_DEPOSIT_TYPE_ALIASES: dict[str, str] = {
    # Epithermal 命名变体
    'hs-epith':             'EPITHERMAL-HS',
    'epithermal-hs':        'EPITHERMAL-HS',   # 防大小写
    'high-sulfidation':     'EPITHERMAL-HS',
    'high-s':               'EPITHERMAL-HS',
    'ls-epith':             'EPITHERMAL-LS',
    'low-sulfidation':      'EPITHERMAL-LS',
    'low-s':                'EPITHERMAL-LS',
    'is-epith':             'EPITHERMAL-IS',
    'intermediate-sulfidation': 'EPITHERMAL-IS',
    # PGE/Ni 命名变体
    'mum-nicu':             'NI-CU-PGE',
    'ni-cu-pge-mum':        'NI-CU-PGE',
    'mafic-ultramafic-nicu':'NI-CU-PGE',
    'magmatic-ni-cu':       'NI-CU-PGE',
    'magmatic-sulfide':     'NI-CU-PGE',
    # PGE 层状岩浆矿床（有明确亚类特征时才映射）
    'pge-layered':          'PGE-REEF',
    # Pegmatite/Li 命名变体
    'lct-li':               'PEGMATITE-LCT',
    'li-pegmatite':         'PEGMATITE-LCT',
    'pegmatite-li':         'PEGMATITE-LCT',
    'lct-pegmatite':        'PEGMATITE-LCT',
    # 散浸型银 → 最近邻
    'diss-ag':              'EPITHERMAL-AG',
    'disseminated-ag':      'EPITHERMAL-AG',
    'disseminated-silver':  'EPITHERMAL-AG',
    # 铅银脉 → Pb-Zn 脉（Ag 在 evidence 保留）
    'vein-pbag':            'VEIN-PB-ZN',
    'vein-pb-ag':           'VEIN-PB-ZN',
    'pb-ag-vein':           'VEIN-PB-ZN',
    # 铜脉/角砾岩管
    'breccia-pipe-cu':      'VEIN-CU',
    # Carlin 别名
    'carlin':               'CARLIN-AU',
    'carlin-type':          'CARLIN-AU',
    # Orogenic Au 别名
    'orogenic-gold':        'OROG-AU',
    'lode-gold':            'OROG-AU',
    'greenstone-au':        'OROG-AU',
    # SEDEX 别名
    'sedex-pb-zn':          'SEDEX',
    'shale-hosted-pb-zn':   'SEDEX',
    # MVT 别名
    'mvt-pb-zn':            'MVT',
    'carbonate-hosted-pb-zn':'MVT',
    # IOCG 别名
    'iron-oxide-cu-au':     'IOCG',
    'iocg-u':               'IOCG',
    # VMS 别名
    'kuroko':               'VMS',
    'besshi':               'VMS',
    'cyprus-type':          'VMS',
    # Skarn 别名
    'contact-metasomatic':  'SKARN',
    'skarn-cu-au-ag':       'SKARN-CU-AU',
    # 能源 别名
    'cbm':                  'COAL-CBM',
    'coal-bed-methane':     'COAL-CBM',
    'unconventional-gas':   'SHALE-GAS',
    'tight-gas':            'SHALE-GAS',
    # 锂/蒸发岩 变体 → EVAPORITE（Salar型锂已明确纳入EVAPORITE描述）
    'salar-li':             'EVAPORITE',
    'salar_li':             'EVAPORITE',
    'sedimentary-li':       'EVAPORITE',
    'sedimentary-brine-li': 'EVAPORITE',
    'brine-li':             'EVAPORITE',
    'lacustrine-li':        'EVAPORITE',
    # 宽泛 SEDIMENTARY → POLYMETALLIC 兜底（过于笼统，不独立成类）
    'sedimentary':          'POLYMETALLIC',
    # 顺序/写法变体
    'pge-ree':              'CARBONATITE-REE',  # 若commodities含REE则近邻是碳酸岩REE
    'polymetallic-vein':    'POLYMETALLIC',
    'sedimentary-cu':       'SEDIMENT-CU',      # 语义等价，统一到SEDIMENT-CU
    'vein-w-sn':            'VEIN-SN-W',
    'greisen-sn-w':         'GREISEN-W-SN',
    'epithermal-au-ag':     'EPITHERMAL-AU',
    'porphyry-cu-au-mo':    'PORPHYRY-CU-AU',
    'porphyry-cu-mo-au':    'PORPHYRY-CU-MO',
    'skarn-cu-zn':          'SKARN-CU',
    'skarn-cu-mo':          'SKARN-CU',
    'vein-fe':              'SKARN-FE',
}

# ── deposit_type 不再用闭合枚举（改为开放，第三层兜底）──
# 旧版闭合枚举会误杀51.3%矿床论文（KUPFERSCHIEFER, JACUTINGA-AU等新矿种）
# 新版策略：词表外的类型自动走三层漏斗
#   1. 精确匹配词表 → 直接通过
#   2. 别名映射 → 归一化到最近邻词表项 + WARN:deposit_type_normalized
#   3. 词表外且无别名 → FLAG:unknown_deposit_type，但保留入库
#      原文术语保留在 deposit_type_evidence 末尾，供后续扩词表参考


def _check_one(record: dict) -> tuple[str, list[str], dict]:
    """
    检查单条记录, 返回 (status, flags, record)
    record 可能因归一化被修改（deposit_class remap）
    status: 'pass' | 'warn' | 'fail'
    flags: 问题列表 (空=通过)
    """
    flags = []

    # 1. 主键存在
    pid = record.get('paper_id')
    if not pid or not str(pid).strip():
        flags.append('FAIL:no_paper_id')
        return 'fail', flags, record

    # 2. deposit_class 合法值；未知值先尝试归一化，再 WARN
    dc = record.get('deposit_class')
    if dc is not None and dc not in VALID_DEPOSIT_CLASSES:
        normalized = _DEPOSIT_CLASS_REMAP.get(dc.lower().replace('-', '_'))
        if normalized:
            record = record.copy()
            record['deposit_class'] = normalized
            record['_deposit_class_remapped_from'] = dc
        else:
            flags.append(f'WARN:unknown_deposit_class={dc}')

    # 2b. deposit_type 三层漏斗（开放枚举 + 别名归一化 + 未知保留）
    dt = record.get('deposit_type')
    if dt is not None:
        # 层1: 精确匹配词表（词表项全大写+连字符，视为已知）
        dt_upper = dt.upper()
        dt_key = dt.lower().replace('_', '-').strip()
        alias_target = _DEPOSIT_TYPE_ALIASES.get(dt_key)
        if alias_target and dt_upper != alias_target:
            # 层2: 命中别名映射 → 归一化，保留原始值在 evidence 末尾
            record = record.copy()
            record['deposit_type'] = alias_target
            record['_deposit_type_normalized_from'] = dt
            # 把原文术语追加到 evidence（若 evidence 已有内容，用分号拼接）
            ev = record.get('deposit_type_evidence') or ''
            suffix = f'原始词表外术语: {dt}'
            if suffix not in ev:
                record['deposit_type_evidence'] = (ev.rstrip(';').rstrip() + '; ' + suffix).lstrip('; ')
            flags.append(f'WARN:deposit_type_normalized:{dt}→{alias_target}')
        elif not alias_target and not dt.isupper():
            # 层3: 非全大写 + 不在别名表 → 可能是词表外新类型，FLAG 但保留
            # 全大写的词表项（如 KUPFERSCHIEFER、MY-NEW-TYPE）不触发此分支
            flags.append(f'FLAG:unknown_deposit_type={dt}')

    # 3. 坐标值域（deepseek 输出 coordinates: {lat, lon}）
    coords = record.get('coordinates')
    if isinstance(coords, dict):
        # 用 is not None 避免 0.0（赤道/本初子午线）被 or 短路成 None
        lat = coords.get('lat') if coords.get('lat') is not None else coords.get('latitude')
        lon = coords.get('lon') if coords.get('lon') is not None else coords.get('longitude')
    else:
        lat = lon = None
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

    # 4. 年龄值域（deepseek 输出 ages: [{age_ma: float, ...}]）
    ages = record.get('ages')
    if ages and isinstance(ages, list):
        for a in ages:
            age_val = a.get('age_ma') if isinstance(a, dict) else a
            try:
                age_val = float(age_val)
                if not (AGE_MIN <= age_val <= AGE_MAX):
                    flags.append(f'WARN:age_out_of_range={age_val}')
            except (TypeError, ValueError):
                flags.append(f'WARN:age_not_numeric={age_val}')

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
                         'minerals',
                         'commodities', 'ages',
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

    return status, flags, record


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
            pid = str(r.get('paper_id', ''))  # 统一为 str，避免 int/str 混用漏判重复
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
        status, flags, r = _check_one(r)
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


# ── CLI 入口 ──
if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("用法: python gate_lite.py <results.json>")
        sys.exit(1)

    with open(sys.argv[1], encoding='utf-8') as f:
        data = json.load(f)
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
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(checked, f, ensure_ascii=False, indent=1)
    print(f"\n  结果: {out}")
