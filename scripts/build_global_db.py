#!/usr/bin/env python3
"""
全球矿床数据库 + 重名门控（修复版）

修复问题：
1. 扩大停用词表（地质通用词不能作为矿床名匹配）
2. 加强国家验证（无国家匹配→拒绝）
3. 提高分数阈值
4. 只匹配已知的具体矿床/成矿带名称
"""
import json
import sys
import re
import requests
from pathlib import Path
from collections import defaultdict


# ============================================================
# 全局停用词：这些词出现在paper_id/belt中不能作为矿床名匹配
# ============================================================
STOPWORDS = {
    # 方向/位置词
    "northern", "southern", "eastern", "western", "central", "upper", "lower",
    "north", "south", "east", "west", "inner", "outer",
    # 地貌词
    "basin", "valley", "river", "creek", "mountain", "range", "ridge",
    "plateau", "plain", "coast", "shelf", "margin", "slope", "arch",
    "belt", "zone", "province", "region", "district", "area",
    "block", "terrane", "domain", "sector", "field",
    # 地质术语
    "extension", "compression", "rifting", "subduction", "collision",
    "continental", "oceanic", "intrusion", "pluton", "batholith",
    "formation", "group", "series", "complex", "suite",
    "sandstone", "limestone", "granite", "basalt", "schist", "gneiss",
    "fault", "thrust", "shear", "fold", "anticline", "syncline",
    # 通用矿业词
    "mine", "mining", "miner", "mineral", "mineralization", "deposit",
    "prospect", "occurrence", "showing", "exploration", "project",
    "gold", "silver", "copper", "iron", "zinc", "lead", "nickel",
    # 地名通用词（非专有名词）
    "england", "france", "america", "africa", "asia", "europe",
    "pacific", "atlantic", "mediterranean", "francisco",
    "cycle", "model", "system", "process", "mechanism",
    # 太短的词
    "r", "x", "a", "b", "c", "d", "e", "f",
}

# 已知的可信矿床/成矿带关键词白名单（只有这些词才能触发匹配）
# 格式：{关键词: [可能的国家列表]}  None表示全球唯一
TRUSTED_DEPOSIT_KEYWORDS = {
    # 南非
    "bushveld": ["south africa"],
    "witwatersrand": ["south africa"],
    "merensky": ["south africa"],
    "sishen": ["south africa"],
    "palabora": ["south africa"],
    "jwaneng": ["botswana"],
    "orapa": ["botswana"],

    # 澳大利亚
    "kalgoorlie": ["australia"],
    "kambalda": ["australia"],
    "olympic dam": ["australia"],
    "mount isa": ["australia"],
    "broken hill": ["australia"],
    "mcarthur river": ["australia"],
    "century mine": ["australia"],
    "northparkes": ["australia"],
    "telfer": ["australia"],
    "jundee": ["australia"],
    "sunrise dam": ["australia"],
    "cadia": ["australia"],
    "prominent hill": ["australia"],

    # 中国
    "jiaodong": ["china"],
    "linglong": ["china"],
    "sanshandao": ["china"],
    "dexing": ["china"],
    "bayan obo": ["china"],
    "yulong": ["china"],
    "qulong": ["china"],
    "jiama": ["china"],
    "daye": ["china"],
    "jinchuan": ["china"],

    # 俄罗斯/中亚
    "norilsk": ["russia"],
    "muruntau": ["uzbekistan"],
    "kumtor": ["kyrgyzstan"],

    # 非洲
    "geita": ["tanzania"],
    "obuasi": ["ghana"],
    "ahafo": ["ghana"],
    "akyem": ["ghana"],
    "kibali": ["dr congo", "democratic republic of the congo"],
    "kamoa": ["dr congo", "democratic republic of the congo"],
    "kansanshi": ["zambia"],
    "lumwana": ["zambia"],
    "tenke": ["dr congo"],
    "loulo": ["mali"],
    "tasiast": ["mauritania"],

    # 加拿大
    "sudbury": ["canada"],
    "voisey": ["canada"],
    "kidd creek": ["canada"],
    "hemlo": ["canada"],
    "red lake": ["canada"],
    "malartic": ["canada"],
    "detour": ["canada"],

    # 蒙古
    "oyu tolgoi": ["mongolia"],
    "erdenet": ["mongolia"],
    "tavan tolgoi": ["mongolia"],

    # 南美（智利/秘鲁等斑岩矿床名称高度特化，不会重名）
    "chuquicamata": ["chile"],
    "escondida": ["chile"],
    "collahuasi": ["chile"],
    "los pelambres": ["chile"],
    "antamina": ["peru"],
    "yanacocha": ["peru"],
    "cerro verde": ["peru"],
    "las bambas": ["peru"],
    "grasberg": ["indonesia"],
    "batu hijau": ["indonesia"],
    "porgera": ["papua new guinea"],
    "lihir": ["papua new guinea"],

    # 欧洲
    "kiruna": ["sweden"],
    "boliden": ["sweden"],
    "neves-corvo": ["portugal"],
    "lubin": ["poland"],
    "kupferschiefer": ["poland", "germany"],
    "sarcheshmeh": ["iran"],
    "sungun": ["iran"],
    "fore-sudetic": ["poland"],
    "pine creek": ["australia"],
    "kibaran": ["dr congo", "rwanda", "burundi", "tanzania"],
    "quadrilatero": ["brazil"],
    "carajas": ["brazil"],
    "witwatersrand": ["south africa"],
}


def load_manual_global_deposits():
    """已知的高质量矿床坐标（只包含专有名词矿床）"""
    return {
        "Kalgoorlie": {"lat": -30.75, "lon": 121.47, "country": "Australia"},
        "Olympic Dam": {"lat": -30.44, "lon": 136.89, "country": "Australia"},
        "Mount Isa": {"lat": -20.73, "lon": 139.49, "country": "Australia"},
        "Broken Hill": {"lat": -31.96, "lon": 141.47, "country": "Australia"},
        "McArthur River": {"lat": -16.44, "lon": 136.08, "country": "Australia"},
        "Ernest Henry": {"lat": -20.38, "lon": 140.74, "country": "Australia"},
        "Bushveld Complex": {"lat": -25.00, "lon": 28.50, "country": "South Africa"},
        "Witwatersrand": {"lat": -26.20, "lon": 27.80, "country": "South Africa"},
        "Jiaodong": {"lat": 37.50, "lon": 120.50, "country": "China"},
        "Bayan Obo": {"lat": 41.80, "lon": 109.97, "country": "China"},
        "Norilsk": {"lat": 69.33, "lon": 88.22, "country": "Russia"},
        "Muruntau": {"lat": 41.52, "lon": 64.58, "country": "Uzbekistan"},
        "Kumtor": {"lat": 41.83, "lon": 78.22, "country": "Kyrgyzstan"},
        "Obuasi": {"lat": 6.20, "lon": -1.68, "country": "Ghana"},
        "Geita": {"lat": -2.87, "lon": 32.23, "country": "Tanzania"},
        "Kamoa-Kakula": {"lat": -10.73, "lon": 25.78, "country": "DR Congo"},
        "Kansanshi": {"lat": -12.07, "lon": 25.85, "country": "Zambia"},
        "Loulo-Gounkoto": {"lat": 13.67, "lon": -10.72, "country": "Mali"},
        "Oyu Tolgoi": {"lat": 43.00, "lon": 106.85, "country": "Mongolia"},
        "Grasberg": {"lat": -4.05, "lon": 137.12, "country": "Indonesia"},
        "Batu Hijau": {"lat": -8.97, "lon": 116.87, "country": "Indonesia"},
        "Porgera": {"lat": -5.47, "lon": 143.13, "country": "Papua New Guinea"},
        "Lihir": {"lat": -3.12, "lon": 152.63, "country": "Papua New Guinea"},
        "Neves-Corvo": {"lat": 37.60, "lon": -7.93, "country": "Portugal"},
        "Kiruna": {"lat": 67.85, "lon": 20.25, "country": "Sweden"},
        "Lubin": {"lat": 51.40, "lon": 16.20, "country": "Poland"},
        "Fore-Sudetic Monocline": {"lat": 51.30, "lon": 16.50, "country": "Poland"},
        "Sarcheshmeh": {"lat": 29.76, "lon": 55.74, "country": "Iran"},
        "Yanacocha": {"lat": -7.00, "lon": -78.50, "country": "Peru"},
        "Antamina": {"lat": -9.33, "lon": -77.07, "country": "Peru"},
        "Las Bambas": {"lat": -14.20, "lon": -72.20, "country": "Peru"},
        "Cerro Verde": {"lat": -16.53, "lon": -71.56, "country": "Peru"},
        "Carajas": {"lat": -6.06, "lon": -50.28, "country": "Brazil"},
        "Quadrilátero Ferrífero": {"lat": -20.00, "lon": -43.50, "country": "Brazil"},
        "Dexing": {"lat": 29.01, "lon": 117.68, "country": "China"},
        "Jinchuan": {"lat": 38.50, "lon": 102.17, "country": "China"},
    }


class DepositMatcher:
    """
    矿床坐标匹配器 - 修复版
    
    核心改进：
    1. 停用词过滤（地质通用词不能作为匹配词）
    2. 白名单机制（只匹配已知的专有矿床/成矿带名称）
    3. 强制国家验证（无论是否重名都要验证）
    4. 提高阈值
    """
    
    def __init__(self, mrds_db_path: str, manual_global: dict = None):
        print("构建匹配索引（修复版）...")
        
        # 只使用手动整理的高质量数据 + MRDS中与白名单匹配的数据
        self.known_deposits = dict(manual_global or {})
        
        # 从MRDS中提取白名单矿床
        if Path(mrds_db_path).exists():
            with open(mrds_db_path) as f:
                mrds = json.load(f)
            
            extracted = 0
            for name, info in mrds.items():
                name_lower = name.lower()
                # 只保留名称在白名单中的
                for keyword in TRUSTED_DEPOSIT_KEYWORDS:
                    if keyword in name_lower:
                        if name not in self.known_deposits:
                            self.known_deposits[name] = info
                            extracted += 1
                        break
            
            print(f"  从MRDS提取白名单矿床: {extracted}个")
        
        print(f"  已知矿床总数: {len(self.known_deposits)}个")
        
        # 构建索引
        self.index = defaultdict(list)
        for deposit_name, info in self.known_deposits.items():
            # 完整名称
            self.index[deposit_name.lower()].append((deposit_name, info))
            
            # 多词短语的子集
            words = deposit_name.lower().split()
            for i in range(len(words)):
                for j in range(i+1, min(i+4, len(words)+1)):
                    phrase = " ".join(words[i:j])
                    if len(phrase) >= 5 and phrase not in STOPWORDS:
                        self.index[phrase].append((deposit_name, info))
    
    def match(self, result: dict) -> bool:
        """匹配单条记录（修复版：严格验证）"""
        if result.get("coordinates"):
            return False
        
        paper_id = (result.get("paper_id") or "").lower()
        belt = (result.get("metallogenic_belt") or "").lower()
        tectonic = (result.get("tectonic_setting") or "").lower()
        deposit_evidence = (result.get("deposit_type_evidence") or "").lower()
        
        claimed_countries = {
            c.lower().strip()
            for c in (result.get("countries") or [])
        }
        
        # 搜索文本池
        text = f"{paper_id} {belt} {tectonic} {deposit_evidence}"
        
        # 提取候选词（优先长短语）
        candidates = set()
        
        # 先尝试完整的已知矿床名称
        for keyword in TRUSTED_DEPOSIT_KEYWORDS:
            if keyword in text:
                candidates.add(keyword)
        
        # 再尝试index中的短语
        words = re.split(r'[\s\-_/\.\(\),;:]+', text)
        words = [w for w in words if len(w) >= 5 and w not in STOPWORDS]
        
        for i in range(len(words)):
            for length in range(3, 0, -1):  # 优先长短语
                if i + length <= len(words):
                    phrase = " ".join(words[i:i+length])
                    if phrase not in STOPWORDS and phrase in self.index:
                        candidates.add(phrase)
        
        # 按长度排序（优先长匹配）
        candidates = sorted(candidates, key=len, reverse=True)
        
        best_score = 0
        best_entry = None
        best_token = None
        
        for token in candidates:
            if token in STOPWORDS:
                continue
            
            entries = self.index.get(token, [])
            
            for deposit_name, info in entries:
                dep_country = (info.get("country") or "").lower()
                
                # ★ 必须验证国家（核心门控）
                if claimed_countries:
                    country_ok = any(
                        c in dep_country or dep_country in c
                        for c in claimed_countries
                    )
                    if not country_ok:
                        continue  # 国家不匹配，直接跳过
                else:
                    # 没有国家信息→只接受全球唯一的矿床（白名单中无重名）
                    # 对于白名单中已知是某国独有的，可以接受
                    global_unique = TRUSTED_DEPOSIT_KEYWORDS.get(token.lower())
                    if global_unique is None:
                        continue  # 未知是否唯一，拒绝
                
                score = len(token) / max(len(deposit_name), 1)
                if token == deposit_name.lower():
                    score += 0.3
                
                if score > best_score:
                    best_score = score
                    best_entry = (deposit_name, info)
                    best_token = token
        
        # 严格阈值：0.6
        if best_entry is None or best_score < 0.6:
            return False
        
        deposit_name, info = best_entry
        confidence = min(0.95, best_score)
        
        result["coordinates"] = {
            "latitude": info["lat"],
            "longitude": info["lon"],
            "precision": "矿区级" if confidence >= 0.85 else "省级",
            "source": f"Global DB-{deposit_name}",
            "confidence": round(confidence, 3),
            "extraction_method": "矿床数据库匹配",
            "matched_token": best_token,
        }
        return True
    
    def batch_match(self, results: list) -> dict:
        matched = 0
        for result in results:
            r = result.get("extracted") or result
            if self.match(r):
                matched += 1
        return {"matched": matched}


def main():
    print("=" * 80)
    print("全球矿床数据库匹配（修复版）")
    print("=" * 80)
    print()
    
    manual = load_manual_global_deposits()
    mrds_path = Path(__file__).parent / "mrds_deposits.json"
    matcher = DepositMatcher(str(mrds_path), manual)
    
    # 测试
    test_file = Path(__file__).parent.parent / "complete_pilot_results_cleaned.json"
    with open(test_file) as f:
        test_data = json.load(f)
    
    total = len(test_data)
    before = sum(1 for r in test_data if (r.get("extracted") or r).get("coordinates"))
    
    print(f"\n输入: {total}篇, 已有坐标: {before}篇 ({before/total*100:.1f}%)")
    
    stats = matcher.batch_match(test_data)
    
    after = sum(1 for r in test_data if (r.get("extracted") or r).get("coordinates"))
    
    print(f"新增坐标: {stats['matched']}篇")
    print(f"最终: {after}篇 ({after/total*100:.1f}%)")
    print()
    
    # 展示新匹配的结果
    print("新匹配详情（全部验证）:")
    for r in test_data:
        rec = r.get("extracted") or r
        coords = rec.get("coordinates")
        if not coords or coords.get("extraction_method") != "矿床数据库匹配":
            continue
        
        paper_id = str(rec.get("paper_id", ""))[:55]
        countries = rec.get("countries") or []
        matched_token = coords.get("matched_token", "")
        lat, lon = coords["latitude"], coords["longitude"]
        conf = coords["confidence"]
        
        print(f"  ✅ {paper_id}")
        print(f"     国家: {countries} | 匹配词: '{matched_token}' | 置信度: {conf}")
        print(f"     坐标: ({lat:.2f}, {lon:.2f}) | 来源: {coords['source']}")
    
    # 保存
    output = test_file.parent / "complete_pilot_with_global_v2.json"
    with open(output, "w") as f:
        json.dump(test_data, f, indent=2, ensure_ascii=False)
    print(f"\n✅ 保存: {output}")

if __name__ == "__main__":
    main()
