#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
同步 klines_1m 表和 klines_1m_macd_smooth_ma 表的数据。

功能：
1. 对比两个表的最后数据
2. 如果 klines_1m 中有数据但 klines_1m_macd_smooth_ma 中没有
3. 使用 compute_1m_macd_smooth_ma 的算法计算指标并追加写入

使用方法：
    python data/sync_macd_indicators.py          # 单次执行
    python data/sync_macd_indicators.py --loop   # 持续运行，每分钟多次执行
"""

import argparse
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

# 添加项目根目录到路径（确保能找到 core 与 data_module 等包）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import config
from core.logger import get_logger

logger = get_logger('sync_macd')

# 将 print 重定向到 logger
original_print = print
def print(*args, **kwargs):
    msg = " ".join(map(str, args))
    logger.info(msg)
    # original_print(*args, **kwargs) # 可选：同时也打印到控制台，但在后台运行时不需要

try:
    import db_compat
except ImportError:
    db_compat = None

# 每分钟执行的秒数
TRIGGER_SECONDS = [1, 3, 5, 13, 20, 23]


def get_engine():
    """获取数据库引擎"""
    db_uri = (config.DB_PATH or '').strip()

    # 如果未配置协议，按本地sqlite文件处理
    if '://' not in db_uri:
        db_uri = f"sqlite:///{os.path.abspath(db_uri or 'data/klines.db')}"

    return create_engine(db_uri)


def ensure_table_exists(engine):
    """确保目标表存在"""
    is_sqlite = engine.url.get_backend_name() == "sqlite"
    if is_sqlite:
        ddl = """
        CREATE TABLE IF NOT EXISTS klines_1m_macd_smooth_ma (
            open_time DATETIME PRIMARY KEY,
            close_time DATETIME,
            "open" REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL,
            macd15m REAL,
            macd4h REAL,
            dif15m REAL,
            dea15m REAL,
            dif4h REAL,
            dea4h REAL,
            macd1d REAL,
            dif1d REAL,
            dea1d REAL,
            macd1h REAL,
            dif1h REAL,
            dea1h REAL,
            k_15 REAL,
            d_15 REAL,
            j_15 REAL,
            k_1h REAL,
            d_1h REAL,
            j_1h REAL,
            k_4h REAL,
            d_4h REAL,
            j_4h REAL,
            vol_ma1 REAL,
            vol_ma5 REAL,
            vol_ma10 REAL,
            vol_ma30 REAL
        )
        """
    else:
        ddl = """
        CREATE TABLE IF NOT EXISTS `klines_1m_macd_smooth_ma` (
            `open_time` DATETIME NOT NULL,
            `close_time` DATETIME NULL,
            `open` DOUBLE NULL,
            `high` DOUBLE NULL,
            `low` DOUBLE NULL,
            `close` DOUBLE NULL,
            `volume` DOUBLE NULL,
            `macd15m` DOUBLE NULL,
            `macd4h` DOUBLE NULL,
            `dif15m` DOUBLE NULL,
            `dea15m` DOUBLE NULL,
            `dif4h` DOUBLE NULL,
            `dea4h` DOUBLE NULL,
            `macd1d` DOUBLE NULL,
            `dif1d` DOUBLE NULL,
            `dea1d` DOUBLE NULL,
            `macd1h` DOUBLE NULL,
            `dif1h` DOUBLE NULL,
            `dea1h` DOUBLE NULL,
            `k_15` DOUBLE NULL,
            `d_15` DOUBLE NULL,
            `j_15` DOUBLE NULL,
            `k_1h` DOUBLE NULL,
            `d_1h` DOUBLE NULL,
            `j_1h` DOUBLE NULL,
            `k_4h` DOUBLE NULL,
            `d_4h` DOUBLE NULL,
            `j_4h` DOUBLE NULL,
            `vol_ma1` DOUBLE NULL,
            `vol_ma5` DOUBLE NULL,
            `vol_ma10` DOUBLE NULL,
            `vol_ma30` DOUBLE NULL,
            PRIMARY KEY (`open_time`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
    with engine.begin() as conn:
        conn.execute(text(ddl))


def compute_strided_indicators(df, interval_minutes, calc_kdj=False):
    """
    计算分时指标（MACD/KDJ）
    
    Args:
        df: 包含 close, high, low 列的 DataFrame
        interval_minutes: 时间间隔（分钟）
        calc_kdj: 是否计算 KDJ
    
    Returns:
        包含 dif, dea, macd 以及可选 k, d, j 的 DataFrame
    """
    groups = np.arange(len(df)) % interval_minutes
    grouped_close = df["close"].groupby(groups)

    # MACD 计算
    ema12 = grouped_close.transform(lambda x: x.ewm(span=12, adjust=False).mean())
    ema26 = grouped_close.transform(lambda x: x.ewm(span=26, adjust=False).mean())
    dif = ema12 - ema26
    dea = dif.groupby(groups).transform(lambda x: x.ewm(span=9, adjust=False).mean())
    macd = dif - dea

    result = pd.DataFrame({"dif": dif, "dea": dea, "macd": macd}, index=df.index)

    # KDJ 计算
    if calc_kdj:
        grouped_low = df["low"].groupby(groups)
        grouped_high = df["high"].groupby(groups)
        low_min = grouped_low.transform(lambda x: x.rolling(window=9, min_periods=1).min())
        high_max = grouped_high.transform(lambda x: x.rolling(window=9, min_periods=1).max())
        denom = (high_max - low_min).replace(0, np.nan)
        rsv = ((df["close"] - low_min) / denom * 100).fillna(50)
        k = rsv.groupby(groups).transform(lambda x: x.ewm(alpha=1.0 / 3.0, adjust=False).mean())
        d = k.groupby(groups).transform(lambda x: x.ewm(alpha=1.0 / 3.0, adjust=False).mean())
        j = 3 * k - 2 * d
        result["k"] = k
        result["d"] = d
        result["j"] = j

    return result


def get_missing_times(engine):
    """
    获取 klines_1m 中有但 klines_1m_macd_smooth_ma 中没有的时间点
    
    优化：只查询 MACD 表最后时间之后的数据，避免全表扫描
    
    Returns:
        list: 缺失的 open_time 列表
    """
    with engine.connect() as conn:
        # 获取 klines_1m 的最后时间
        result = conn.execute(text(
            "SELECT MAX(open_time) as last_time FROM klines_1m"
        ))
        row = result.fetchone()
        klines_1m_last = row[0] if row else None
        
        # 获取 klines_1m_macd_smooth_ma 的最后时间
        result = conn.execute(text(
            "SELECT MAX(open_time) as last_time FROM klines_1m_macd_smooth_ma"
        ))
        row = result.fetchone()
        macd_last = row[0] if row else None
        
        print(f"klines_1m 最后时间: {klines_1m_last}")
        print(f"klines_1m_macd_smooth_ma 最后时间: {macd_last}")
        
        if klines_1m_last is None:
            print("klines_1m 表为空")
            return []
        
        if macd_last is None:
            # MACD 表为空，需要计算所有数据
            print("MACD表为空，将计算所有数据...")
            result = conn.execute(text(
                "SELECT open_time FROM klines_1m ORDER BY open_time ASC"
            ))
            return [row[0] for row in result.fetchall()]
        
        # 优化：只查询 MACD 表最后时间之后的数据
        # 这样避免了全表 LEFT JOIN 扫描
        result = conn.execute(text("""
            SELECT open_time 
            FROM klines_1m 
            WHERE open_time > :macd_last
            ORDER BY open_time ASC
        """), {"macd_last": macd_last})
        missing = [row[0] for row in result.fetchall()]
        
        return missing


def compute_and_insert_indicators(engine, missing_times):
    """
    计算缺失时间点的指标并插入数据库
    
    为了保证指标计算的准确性，需要加载足够的历史数据来预热指标
    """
    if not missing_times:
        print("没有需要同步的数据")
        return
    
    is_sqlite = engine.url.get_backend_name() == "sqlite"
    
    # 获取最早的缺失时间
    if isinstance(missing_times[0], str):
        earliest_missing = pd.to_datetime(missing_times[0])
    else:
        earliest_missing = pd.to_datetime(missing_times[0])
    
    # 为了准确计算1d MACD指标，需要加载足够的历史数据
    # 1d MACD 使用 EMA26，为了EMA收敛需要至少 26*3=78 天
    # 参考原始算法 compute_1m_macd_smooth_ma.py 使用 200 天预热
    # 200天 = 200 * 1440 = 288000 分钟
    warmup_days = 200
    warmup_minutes = 1440 * warmup_days
    start_time = earliest_missing - timedelta(minutes=warmup_minutes)
    # 转换为ISO格式字符串，SQLite需要字符串格式
    start_time_str = start_time.strftime("%Y-%m-%dT%H:%M:%S")
    
    print(f"加载从 {start_time} 开始的数据用于计算...")
    
    with engine.connect() as conn:
        query = text("""
            SELECT open_time, close, high, low, volume, `open` 
            FROM klines_1m 
            WHERE open_time >= :start 
            ORDER BY open_time ASC
        """)
        df = pd.read_sql(query, conn, params={"start": start_time_str})
    
    if df.empty:
        print("没有找到数据")
        return
    
    print(f"加载了 {len(df)} 条记录")
    
    # 转换时间格式
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    df = df.set_index("open_time").sort_index()
    # 去除重复
    df = df[~df.index.duplicated(keep="last")]
    
    # 重采样确保连续性
    print("重采样确保时间连续性...")
    df_resampled = df.resample("1min").ffill().dropna(subset=["close"])
    original_index = df.index
    
    print(f"重采样后: {len(df_resampled)} 条记录")
    
    # 计算各时间周期的指标
    print("计算 15m 指标...")
    res15 = compute_strided_indicators(df_resampled, 15, calc_kdj=True)
    
    print("计算 1h 指标...")
    res1h = compute_strided_indicators(df_resampled, 60, calc_kdj=True)
    
    print("计算 4h 指标...")
    res4h = compute_strided_indicators(df_resampled, 240, calc_kdj=True)
    
    print("计算 1d 指标...")
    res1d = compute_strided_indicators(df_resampled, 1440, calc_kdj=False)
    
    # 合并结果
    print("合并指标结果...")
    export_df = df_resampled.loc[original_index].copy()
    
    # 15m 指标
    subset15 = res15.loc[original_index]
    export_df["macd15m"] = subset15["macd"]
    export_df["dif15m"] = subset15["dif"]
    export_df["dea15m"] = subset15["dea"]
    export_df["k_15"] = subset15.get("k")
    export_df["d_15"] = subset15.get("d")
    export_df["j_15"] = subset15.get("j")
    
    # 4h 指标
    subset4h = res4h.loc[original_index]
    export_df["macd4h"] = subset4h["macd"]
    export_df["dif4h"] = subset4h["dif"]
    export_df["dea4h"] = subset4h["dea"]
    export_df["k_4h"] = subset4h.get("k")
    export_df["d_4h"] = subset4h.get("d")
    export_df["j_4h"] = subset4h.get("j")
    
    # 1d 指标
    subset1d = res1d.loc[original_index]
    export_df["macd1d"] = subset1d["macd"]
    export_df["dif1d"] = subset1d["dif"]
    export_df["dea1d"] = subset1d["dea"]
    
    # 1h 指标
    subset1h = res1h.loc[original_index]
    export_df["macd1h"] = subset1h["macd"]
    export_df["dif1h"] = subset1h["dif"]
    export_df["dea1h"] = subset1h["dea"]
    export_df["k_1h"] = subset1h.get("k")
    export_df["d_1h"] = subset1h.get("d")
    export_df["j_1h"] = subset1h.get("j")
    
    # 成交量均线
    vol = df_resampled["volume"]
    export_df["vol_ma1"] = vol.rolling(window=1, min_periods=1).mean().loc[original_index]
    export_df["vol_ma5"] = vol.rolling(window=5, min_periods=1).mean().loc[original_index]
    export_df["vol_ma10"] = vol.rolling(window=10, min_periods=1).mean().loc[original_index]
    export_df["vol_ma30"] = vol.rolling(window=30, min_periods=1).mean().loc[original_index]
    
    # 只保留缺失的时间点数据
    missing_times_set = set()
    for t in missing_times:
        if isinstance(t, str):
            missing_times_set.add(pd.to_datetime(t).tz_localize("UTC"))
        else:
            ts = pd.to_datetime(t)
            if ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
            missing_times_set.add(ts)
    
    # 过滤只保留缺失的数据
    export_df = export_df[export_df.index.isin(missing_times_set)]
    
    if export_df.empty:
        print("过滤后没有需要插入的数据")
        return
    
    print(f"需要插入 {len(export_df)} 条记录")
    
    # 写入数据库
    columns = "(open_time, close_time, `open`, `high`, `low`, `close`, `volume`, macd15m, macd4h, dif15m, dea15m, dif4h, dea4h, macd1d, dif1d, dea1d, macd1h, dif1h, dea1h, k_15, d_15, j_15, k_1h, d_1h, j_1h, k_4h, d_4h, j_4h, vol_ma1, vol_ma5, vol_ma10, vol_ma30)"
    placeholders = ("?," * 32).rstrip(',') if is_sqlite else ("%s," * 32).rstrip(',')
    
    if is_sqlite:
        insert_sql = f"INSERT OR REPLACE INTO klines_1m_macd_smooth_ma {columns} VALUES ({placeholders})"
    else:
        insert_sql = (
            "INSERT INTO `klines_1m_macd_smooth_ma` "
            f"{columns} "
            f"VALUES ({placeholders}) "
            "ON DUPLICATE KEY UPDATE "
            "macd15m=VALUES(macd15m), macd4h=VALUES(macd4h), "
            "dif15m=VALUES(dif15m), dea15m=VALUES(dea15m), "
            "dif4h=VALUES(dif4h), dea4h=VALUES(dea4h), "
            "macd1d=VALUES(macd1d), dif1d=VALUES(dif1d), dea1d=VALUES(dea1d), "
            "macd1h=VALUES(macd1h), dif1h=VALUES(dif1h), dea1h=VALUES(dea1h), "
            "k_15=VALUES(k_15), d_15=VALUES(d_15), j_15=VALUES(j_15), "
            "k_1h=VALUES(k_1h), d_1h=VALUES(d_1h), j_1h=VALUES(j_1h), "
            "k_4h=VALUES(k_4h), d_4h=VALUES(d_4h), j_4h=VALUES(j_4h), "
            "vol_ma1=VALUES(vol_ma1), vol_ma5=VALUES(vol_ma5), "
            "vol_ma10=VALUES(vol_ma10), vol_ma30=VALUES(vol_ma30)"
        )
    
    export_df = export_df.replace({np.nan: None})
    batch = []
    count = 0
    batch_size = 1000
    
    raw_conn = engine.raw_connection()
    cursor = raw_conn.cursor()
    
    try:
        for row in export_df.itertuples():
            ot = row.Index.to_pydatetime()
            ct = ot + timedelta(seconds=59, microseconds=999000)
            # 避免 sqlite 默认 datetime 适配器弃用警告，显式转为字符串
            ot_str = ot.strftime('%Y-%m-%d %H:%M:%S')
            ct_str = ct.strftime('%Y-%m-%d %H:%M:%S')
            params = (
                ot_str, ct_str,
                row.open, row.high, row.low, row.close, row.volume,
                row.macd15m, row.macd4h, row.dif15m, row.dea15m, row.dif4h, row.dea4h,
                row.macd1d, row.dif1d, row.dea1d,
                row.macd1h, row.dif1h, row.dea1h,
                row.k_15, row.d_15, row.j_15,
                row.k_1h, row.d_1h, row.j_1h,
                row.k_4h, row.d_4h, row.j_4h,
                row.vol_ma1, row.vol_ma5, row.vol_ma10, row.vol_ma30,
            )
            batch.append(params)
            
            if len(batch) >= batch_size:
                if db_compat:
                    db_compat.execute_many_compatible(raw_conn, insert_sql, batch)
                else:
                    cursor.executemany(insert_sql, batch)
                raw_conn.commit()
                count += len(batch)
                print(f"已插入 {count} 条记录...")
                batch = []
        
        if batch:
            if db_compat:
                db_compat.execute_many_compatible(raw_conn, insert_sql, batch)
            else:
                cursor.executemany(insert_sql, batch)
            raw_conn.commit()
            count += len(batch)
        
        print(f"同步完成，共插入 {count} 条记录")
        
    finally:
        cursor.close()
        raw_conn.close()


def verify_sync(engine):
    """验证同步结果"""
    with engine.connect() as conn:
        # 获取两表的记录数
        result = conn.execute(text("SELECT COUNT(*) FROM klines_1m"))
        klines_count = result.fetchone()[0]
        
        result = conn.execute(text("SELECT COUNT(*) FROM klines_1m_macd_smooth_ma"))
        macd_count = result.fetchone()[0]
        
        # 获取两表的最后时间
        result = conn.execute(text("SELECT MAX(open_time) FROM klines_1m"))
        klines_last = result.fetchone()[0]
        
        result = conn.execute(text("SELECT MAX(open_time) FROM klines_1m_macd_smooth_ma"))
        macd_last = result.fetchone()[0]
        
        print("\n=== 同步验证 ===")
        print(f"klines_1m 记录数: {klines_count}")
        print(f"klines_1m_macd_smooth_ma 记录数: {macd_count}")
        print(f"klines_1m 最后时间: {klines_last}")
        print(f"klines_1m_macd_smooth_ma 最后时间: {macd_last}")
        
        if klines_count == macd_count and klines_last == macd_last:
            print("✅ 两表数据已完全同步")
        else:
            diff = klines_count - macd_count
            print(f"⚠️ 数据差异: {diff} 条记录")


def check_last_time_match(engine):
    """
    检查两个表的最后一条数据 open_time 是否一致
    
    Returns:
        (bool, str, str): (是否一致, klines_1m最后时间, macd表最后时间)
    """
    with engine.connect() as conn:
        # 获取 klines_1m 的最后时间
        result = conn.execute(text(
            "SELECT MAX(open_time) as last_time FROM klines_1m"
        ))
        row = result.fetchone()
        klines_1m_last = row[0] if row else None
        
        # 获取 klines_1m_macd_smooth_ma 的最后时间
        result = conn.execute(text(
            "SELECT MAX(open_time) as last_time FROM klines_1m_macd_smooth_ma"
        ))
        row = result.fetchone()
        macd_last = row[0] if row else None
        
        # 标准化时间格式进行比较
        if klines_1m_last is not None and macd_last is not None:
            # 统一转换为 pandas Timestamp 再比较
            # 处理不同格式: "2026-01-09T14:01:00" vs "2026-01-09 14:01:00+00:00"
            try:
                k_time = pd.to_datetime(klines_1m_last)
                m_time = pd.to_datetime(macd_last)
                # 移除时区信息进行比较（两者都是UTC）
                if k_time.tzinfo is not None:
                    k_time = k_time.tz_localize(None)
                if m_time.tzinfo is not None:
                    m_time = m_time.tz_localize(None)
                is_match = (k_time == m_time)
            except Exception:
                # 降级到字符串比较
                k_str = str(klines_1m_last).replace('T', ' ')[:19]
                m_str = str(macd_last).replace('T', ' ')[:19]
                is_match = (k_str == m_str)
        else:
            is_match = False
        
        return is_match, klines_1m_last, macd_last


def run_sync():
    """执行一次同步"""
    now_utc = datetime.now(timezone.utc)
    print(f"\n[{now_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC] 开始同步...")
    
    engine = get_engine()
    
    # 确保目标表存在
    ensure_table_exists(engine)
    
    # 先检查最后一条数据的 open_time 是否一致
    is_match, klines_last, macd_last = check_last_time_match(engine)
    
    if is_match:
        print(f"✓ 两表最后数据一致: {klines_last}")
        return
    
    print(f"klines_1m 最后: {klines_last}")
    print(f"macd 表最后: {macd_last}")
    
    # 获取缺失的时间点
    missing_times = get_missing_times(engine)
    
    if missing_times:
        print(f"发现 {len(missing_times)} 条缺失记录")
        if len(missing_times) <= 5:
            for t in missing_times:
                print(f"  - {t}")
        else:
            print(f"  首条: {missing_times[0]}, 末条: {missing_times[-1]}")
        
        # 计算并插入指标
        compute_and_insert_indicators(engine, missing_times)
        verify_sync(engine)
    else:
        print("✓ 两表数据已同步")
    
    now_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{now_str} UTC] 同步完成")


def wait_for_next_trigger():
    """等待下一个触发时间点"""
    while True:
        now = datetime.now(timezone.utc)
        current_second = now.second
        
        # 找到下一个触发秒数
        next_trigger = None
        for s in TRIGGER_SECONDS:
            if s > current_second:
                next_trigger = s
                break
        
        if next_trigger is None:
            # 当前秒数已超过所有触发点，等到下一分钟的第一个触发点
            wait_seconds = (60 - current_second) + TRIGGER_SECONDS[0]
        else:
            wait_seconds = next_trigger - current_second
        
        # 减去当前的毫秒部分以更精确
        wait_seconds -= now.microsecond / 1_000_000
        
        if wait_seconds > 0:
            time.sleep(wait_seconds)
        
        return datetime.now(timezone.utc).second


def run_loop():
    """持续运行模式"""
    print("=" * 50)
    print("MACD 指标同步工具 - 持续运行模式")
    print("=" * 50)
    print(f"启动时间: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"触发秒数: {TRIGGER_SECONDS}")
    print("按 Ctrl+C 停止")
    print("=" * 50)
    
    last_run_minute = -1
    last_run_second = -1
    
    try:
        while True:
            now = datetime.now(timezone.utc)
            current_minute = now.minute
            current_second = now.second
            
            # 检查是否在触发秒数，并且这个(分钟,秒)组合还没执行过
            if current_second in TRIGGER_SECONDS:
                run_key = (current_minute, current_second)
                if (current_minute, current_second) != (last_run_minute, last_run_second):
                    last_run_minute = current_minute
                    last_run_second = current_second
                    try:
                        run_sync()
                    except Exception as e:
                        print(f"❌ 同步出错: {e}")
            
            # 等待下一个触发点
            wait_for_next_trigger()
            
    except KeyboardInterrupt:
        print("\n\n停止运行")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="MACD 指标同步工具")
    parser.add_argument(
        "--loop", 
        action="store_true", 
        help="持续运行模式，每分钟在指定秒数执行"
    )
    args = parser.parse_args()
    
    if args.loop:
        run_loop()
    else:
        # 单次执行模式
        print("=" * 50)
        print("MACD 指标同步工具")
        print("=" * 50)
        run_sync()


if __name__ == "__main__":
    main()
