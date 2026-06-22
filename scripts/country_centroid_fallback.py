#!/usr/bin/env python3
"""
国家质心兜底：对无坐标且只有国家信息的记录，用国家质心补充低精度坐标
"""
import json, sys

# 国家质心（主要陆地重心，不含领海）
COUNTRY_CENTROIDS = {
    "China": (35.86, 104.19),
    "USA": (37.09, -95.71),
    "United States": (37.09, -95.71),
    "Canada": (56.13, -106.35),
    "Australia": (-25.27, 133.78),
    "Russia": (61.52, 105.32),
    "Brazil": (-14.24, -51.93),
    "India": (20.59, 78.96),
    "Argentina": (-38.42, -63.62),
    "Chile": (-35.68, -71.54),
    "Peru": (-9.19, -75.02),
    "Mexico": (23.63, -102.55),
    "South Africa": (-30.56, 22.94),
    "Iran": (32.43, 53.69),
    "Kazakhstan": (48.02, 66.92),
    "Mongolia": (46.86, 103.85),
    "Turkey": (38.96, 35.24),
    "Spain": (40.46, -3.75),
    "Portugal": (39.40, -8.22),
    "Germany": (51.17, 10.45),
    "France": (46.23, 2.21),
    "Finland": (61.92, 25.75),
    "Sweden": (60.13, 18.64),
    "Norway": (60.47, 8.47),
    "UK": (55.38, -3.44),
    "United Kingdom": (55.38, -3.44),
    "Japan": (36.20, 138.25),
    "South Korea": (35.91, 127.77),
    "North Korea": (40.34, 127.51),
    "Philippines": (12.88, 121.77),
    "Indonesia": (-0.79, 113.92),
    "Malaysia": (4.21, 101.98),
    "Thailand": (15.87, 100.99),
    "Vietnam": (14.06, 108.28),
    "Myanmar": (21.91, 95.96),
    "Pakistan": (30.38, 69.35),
    "Afghanistan": (33.94, 67.71),
    "Uzbekistan": (41.38, 64.59),
    "Kyrgyzstan": (41.20, 74.77),
    "Tajikistan": (38.86, 71.28),
    "Ghana": (7.95, -1.02),
    "Nigeria": (9.08, 8.67),
    "Tanzania": (-6.37, 34.89),
    "Kenya": (-0.02, 37.91),
    "Ethiopia": (9.15, 40.49),
    "Democratic Republic of Congo": (-4.04, 21.76),
    "DRC": (-4.04, 21.76),
    "Zambia": (-13.13, 27.85),
    "Zimbabwe": (-19.02, 29.15),
    "Botswana": (-22.33, 24.68),
    "Morocco": (31.79, -7.09),
    "Algeria": (28.03, 1.66),
    "Egypt": (26.82, 30.80),
    "Tunisia": (33.89, 9.54),
    "Sudan": (12.86, 30.22),
    "Cameroon": (3.85, 11.50),
    "Rwanda": (-1.94, 29.87),
    "Mozambique": (-18.67, 35.53),
    "Suriname": (3.92, -56.03),
    "Colombia": (4.57, -74.30),
    "Bolivia": (-16.29, -63.59),
    "Ecuador": (-1.83, -78.18),
    "Venezuela": (6.42, -66.59),
    "Cuba": (21.52, -77.78),
    "Yemen": (15.55, 48.52),
    "Saudi Arabia": (23.89, 45.08),
    "Oman": (21.51, 55.92),
    "UAE": (23.42, 53.85),
    "Iraq": (33.22, 43.68),
    "Syria": (34.80, 38.99),
    "Jordan": (30.59, 36.24),
    "Lebanon": (33.85, 35.86),
    "Israel": (31.05, 34.85),
    "Greece": (39.07, 21.82),
    "Italy": (41.87, 12.57),
    "Poland": (51.92, 19.14),
    "Romania": (45.94, 24.97),
    "Serbia": (44.02, 21.01),
    "Bulgaria": (42.73, 25.49),
    "Czech Republic": (49.82, 15.47),
    "Slovakia": (48.67, 19.70),
    "Hungary": (47.16, 19.50),
    "Austria": (47.52, 14.55),
    "Switzerland": (46.82, 8.23),
    "Belgium": (50.50, 4.47),
    "Netherlands": (52.13, 5.29),
    "New Zealand": (-40.90, 174.89),
    "Papua New Guinea": (-6.31, 143.96),
    "Fiji": (-17.71, 178.07),
    "Cuba": (21.52, -77.78),
    "Jamaica": (18.11, -77.30),
    "Latin America": (-15.0, -65.0),
    "South America": (-15.0, -65.0),
    "Africa": (0.0, 25.0),
    "Asia": (35.0, 85.0),
    "Europe": (52.0, 15.0),
    "Greenland": (71.71, -42.60),
    "Iceland": (64.96, -19.02),
}


def apply_country_centroid(result):
    """用国家质心兜底，精度标记为国家级"""
    if result.get("coordinates"):
        return False
    countries = result.get("countries") or []
    if not countries:
        return False
    # 用第一个能匹配的国家
    for country in countries:
        if country in COUNTRY_CENTROIDS:
            lat, lon = COUNTRY_CENTROIDS[country]
            result["coordinates"] = {
                "latitude": lat,
                "longitude": lon,
                "precision": "国家级",
                "source": f"国家质心-{country}",
                "confidence": 0.3,
                "extraction_method": "国家质心兜底",
            }
            return True
    return False


def main():
    if len(sys.argv) < 2:
        print("用法: python country_centroid_fallback.py <input.json> [output.json]")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else input_file.replace(".json", "_with_country.json")

    with open(input_file) as f:
        data = json.load(f)

    total = len(data)
    before = sum(1 for r in data if (r.get("extracted") or r).get("coordinates"))

    matched = 0
    for r in data:
        rec = r.get("extracted") or r
        if apply_country_centroid(rec):
            matched += 1

    with open(output_file, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    after = sum(1 for r in data if (r.get("extracted") or r).get("coordinates"))
    no_country = total - after
    print(f"输入: {total} | 原有: {before} | 新增(国家质心): {matched} | 现有: {after} ({after/total*100:.1f}%)")
    print(f"仍无坐标(连国家都没有): {no_country}篇")
    print(f"输出: {output_file}")


if __name__ == "__main__":
    main()
