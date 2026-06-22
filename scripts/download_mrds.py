#!/usr/bin/env python3
"""
从USGS MRDS构建大型矿床数据库
目标：1000+世界著名矿床
"""
import requests
import zipfile
import pandas as pd
import json
from pathlib import Path
import sys

def download_mrds():
    """下载USGS MRDS数据库"""
    print("=" * 80)
    print("下载USGS MRDS数据库")
    print("=" * 80)
    print()

    url = "https://mrdata.usgs.gov/mrds/mrds-csv.zip"
    output_file = "mrds.zip"

    print(f"下载地址: {url}")
    print("文件大小: ~50MB")
    print()

    try:
        print("开始下载...")
        response = requests.get(url, stream=True, timeout=300)
        response.raise_for_status()

        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0

        with open(output_file, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                downloaded += len(chunk)
                if total_size:
                    progress = downloaded / total_size * 100
                    print(f"\r进度: {progress:.1f}% ({downloaded//1024//1024}MB/{total_size//1024//1024}MB)", end='')

        print()
        print(f"✅ 下载完成: {output_file}")
        return output_file

    except Exception as e:
        print(f"❌ 下载失败: {e}")
        return None


def extract_mrds(zip_file):
    """解压MRDS数据"""
    print()
    print("=" * 80)
    print("解压数据")
    print("=" * 80)
    print()

    extract_dir = "mrds_data"
    Path(extract_dir).mkdir(exist_ok=True)

    try:
        with zipfile.ZipFile(zip_file, 'r') as z:
            print(f"解压到: {extract_dir}/")
            z.extractall(extract_dir)
            files = z.namelist()
            print(f"✅ 解压完成: {len(files)}个文件")

        return extract_dir

    except Exception as e:
        print(f"❌ 解压失败: {e}")
        return None


def parse_mrds(data_dir):
    """解析MRDS数据，提取著名矿床"""
    print()
    print("=" * 80)
    print("解析MRDS数据")
    print("=" * 80)
    print()

    csv_file = Path(data_dir) / "mrds.csv"
    if not csv_file.exists():
        print(f"❌ 找不到文件: {csv_file}")
        return None

    print(f"读取: {csv_file}")

    try:
        # 读取CSV（可能有编码问题）
        df = pd.read_csv(csv_file, encoding='latin1', low_memory=False)

        print(f"总记录数: {len(df):,}")
        print()

        # 过滤条件
        print("过滤条件:")
        print("  1. 有坐标（latitude + longitude）")
        print("  2. 生产状态（Producer或Past Producer）")
        print("  3. 有商品信息（commod1）")
        print()

        # 应用过滤
        filtered = df[
            (df['latitude'].notna()) &
            (df['longitude'].notna()) &
            (df['dev_stat'].isin(['Producer', 'Past Producer'])) &
            (df['commod1'].notna())
        ].copy()

        print(f"过滤后: {len(filtered):,}个矿床")
        print()

        # 转换为我们的格式
        print("转换为标准格式...")
        deposits = {}

        for idx, row in filtered.iterrows():
            name = str(row.get('site_name', f'MRDS_{idx}')).strip()

            # 跳过无效名称
            if not name or name == 'nan':
                continue

            # 构建矿床记录
            deposits[name] = {
                'lat': float(row['latitude']),
                'lon': float(row['longitude']),
                'country': str(row.get('country', 'Unknown')).strip(),
                'type': str(row.get('dep_type', 'Unknown')).strip(),
                'commodity': str(row.get('commod1', 'Unknown')).strip(),
                'dev_status': str(row.get('dev_stat', 'Unknown')).strip(),
            }

        print(f"✅ 转换完成: {len(deposits):,}个有效矿床")

        return deposits

    except Exception as e:
        print(f"❌ 解析失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def analyze_deposits(deposits):
    """分析矿床分布"""
    print()
    print("=" * 80)
    print("矿床分布分析")
    print("=" * 80)
    print()

    # 按国家统计
    countries = {}
    for info in deposits.values():
        country = info['country']
        countries[country] = countries.get(country, 0) + 1

    print("按国家分布（Top 20）:")
    for country, count in sorted(countries.items(), key=lambda x: -x[1])[:20]:
        print(f"  {country:30} {count:>5}个")

    print()

    # 按商品统计
    commodities = {}
    for info in deposits.values():
        comm = info['commodity']
        commodities[comm] = commodities.get(comm, 0) + 1

    print("按商品分布（Top 20）:")
    for comm, count in sorted(commodities.items(), key=lambda x: -x[1])[:20]:
        print(f"  {comm:30} {count:>5}个")

    print()

    # 按类型统计
    types = {}
    for info in deposits.values():
        dtype = info['type']
        types[dtype] = types.get(dtype, 0) + 1

    print("按类型分布（Top 20）:")
    for dtype, count in sorted(types.items(), key=lambda x: -x[1])[:20]:
        print(f"  {dtype:30} {count:>5}个")


def save_deposits(deposits, output_file):
    """保存为JSON格式"""
    print()
    print("=" * 80)
    print("保存数据")
    print("=" * 80)
    print()

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(deposits, f, indent=2, ensure_ascii=False)

    print(f"✅ 保存完成: {output_file}")
    print(f"   矿床数量: {len(deposits):,}个")


def main():
    print("=" * 80)
    print("USGS MRDS矿床数据库构建")
    print("=" * 80)
    print()

    # Step 1: 下载
    zip_file = download_mrds()
    if not zip_file:
        sys.exit(1)

    # Step 2: 解压
    data_dir = extract_mrds(zip_file)
    if not data_dir:
        sys.exit(1)

    # Step 3: 解析
    deposits = parse_mrds(data_dir)
    if not deposits:
        sys.exit(1)

    # Step 4: 分析
    analyze_deposits(deposits)

    # Step 5: 保存
    output_file = "mrds_deposits.json"
    save_deposits(deposits, output_file)

    print()
    print("=" * 80)
    print("完成！")
    print("=" * 80)
    print()
    print(f"✅ 成功构建 {len(deposits):,} 个矿床数据库")
    print(f"✅ 输出文件: {output_file}")
    print()
    print("下一步: 转换为famous_deposits_database.py格式")


if __name__ == "__main__":
    main()
