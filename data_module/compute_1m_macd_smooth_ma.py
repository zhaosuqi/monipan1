#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compute 1m MACD (15m/1h/4h/1d) plus volume moving averages and write to `klines_1m_macd_smooth_ma`.

This is adapted from compute_1m_macd_vectorized.py with added volume MA fields:
- vol_ma1, vol_ma5, vol_ma10, vol_ma30 (simple moving averages on volume across resampled 1m data).
"""

import argparse
import os
from datetime import datetime, timedelta

import db_compat
import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text


def ensure_table_exists(engine):
    """Create target table if missing for both SQLite and MySQL."""
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


def get_engine():
    """Return SQLAlchemy engine; default to local SQLite if DB_URI unset."""
    db_uri = os.environ.get("DB_URI") or "sqlite:///../data/klines.db"
    return create_engine(db_uri)


def compute_strided_indicators(df, interval_minutes, calc_atr=False, ma_windows=None, calc_kdj=False):
    if ma_windows is None:
        ma_windows = []

    groups = np.arange(len(df)) % interval_minutes
    grouped_close = df["close"].groupby(groups)

    ema12 = grouped_close.transform(lambda x: x.ewm(span=12, adjust=False).mean())
    ema26 = grouped_close.transform(lambda x: x.ewm(span=26, adjust=False).mean())
    dif = ema12 - ema26
    dea = dif.groupby(groups).transform(lambda x: x.ewm(span=9, adjust=False).mean())
    macd = dif - dea

    result = pd.DataFrame({"dif": dif, "dea": dea, "macd": macd}, index=df.index)

    for w in ma_windows:
        ma = grouped_close.transform(lambda x: x.rolling(window=w, min_periods=1).mean())
        result[f"ma{w}"] = ma

    if calc_atr:
        prev_close = grouped_close.shift(1)
        h = df["high"]
        l = df["low"]
        c_prev = prev_close
        tr1 = h - l
        tr2 = (h - c_prev).abs()
        tr3 = (l - c_prev).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).fillna(tr1)
        atr = tr.groupby(groups).transform(lambda x: x.rolling(window=15, min_periods=1).mean())
        result["atr15"] = atr

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


def main():
    parser = argparse.ArgumentParser(description="Compute MACD smooth with volume MA (vectorized)")
    parser.add_argument("--days", type=int, default=0, help="Number of days to process (0 for all)")
    parser.add_argument("--batch-size", type=int, default=2000, help="Batch size for DB inserts")
    args = parser.parse_args()

    engine = get_engine()
    is_sqlite = engine.url.get_backend_name() == "sqlite"

    ensure_table_exists(engine)

    print("Fetching data range...")
    with engine.connect() as conn:
        if args.days > 0:
            start_dt = datetime.utcnow() - timedelta(days=args.days + 200)
            query = text("SELECT open_time, close, high, low, volume, `open` FROM `klines_1m` WHERE open_time >= :start ORDER BY open_time ASC")
            df = pd.read_sql(query, conn, params={"start": start_dt})
        else:
            print("Reading full klines_1m table (this may take a while)...")
            query = text("SELECT open_time, close, high, low, volume, `open` FROM `klines_1m` ORDER BY open_time ASC")
            df = pd.read_sql(query, conn)
            print("Truncating target table...")
            if is_sqlite:
                conn.execute(text("DELETE FROM klines_1m_macd_smooth_ma"))
            else:
                conn.execute(text("TRUNCATE TABLE `klines_1m_macd_smooth_ma`"))
            conn.commit()

    if df.empty:
        print("No data found.")
        return

    print(f"Loaded {len(df)} rows.")
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    df = df.set_index("open_time").sort_index()
    # guard against duplicate timestamps that break resample
    df = df[~df.index.duplicated(keep="last")]

    print("Resampling to ensure continuity...")
    df_resampled = df.resample("1min").ffill().dropna(subset=["close"])
    original_index = df.index
    print(f"Resampled size: {len(df_resampled)} rows.")

    print("Computing 15m indicators...")
    res15 = compute_strided_indicators(df_resampled, 15, calc_atr=False, ma_windows=[], calc_kdj=True)
    print("Computing 1h indicators...")
    res1h = compute_strided_indicators(df_resampled, 60, calc_atr=False, ma_windows=[], calc_kdj=True)
    print("Computing 4h indicators...")
    res4h = compute_strided_indicators(df_resampled, 240, calc_atr=False, ma_windows=[], calc_kdj=True)
    print("Computing 1d indicators...")
    res1d = compute_strided_indicators(df_resampled, 1440, calc_atr=False, ma_windows=[])

    print("Merging results...")
    export_df = df_resampled.loc[original_index].copy()

    subset15 = res15.loc[original_index]
    export_df["macd15m"] = subset15["macd"]
    export_df["dif15m"] = subset15["dif"]
    export_df["dea15m"] = subset15["dea"]
    export_df["k_15"] = subset15.get("k")
    export_df["d_15"] = subset15.get("d")
    export_df["j_15"] = subset15.get("j")

    subset4h = res4h.loc[original_index]
    export_df["macd4h"] = subset4h["macd"]
    export_df["dif4h"] = subset4h["dif"]
    export_df["dea4h"] = subset4h["dea"]
    export_df["k_4h"] = subset4h.get("k")
    export_df["d_4h"] = subset4h.get("d")
    export_df["j_4h"] = subset4h.get("j")

    subset1d = res1d.loc[original_index]
    export_df["macd1d"] = subset1d["macd"]
    export_df["dif1d"] = subset1d["dif"]
    export_df["dea1d"] = subset1d["dea"]

    subset1h = res1h.loc[original_index]
    export_df["macd1h"] = subset1h["macd"]
    export_df["dif1h"] = subset1h["dif"]
    export_df["dea1h"] = subset1h["dea"]
    export_df["k_1h"] = subset1h.get("k")
    export_df["d_1h"] = subset1h.get("d")
    export_df["j_1h"] = subset1h.get("j")

    # Volume moving averages on resampled series
    vol = df_resampled["volume"]
    export_df["vol_ma1"] = vol.rolling(window=1, min_periods=1).mean().loc[original_index]
    export_df["vol_ma5"] = vol.rolling(window=5, min_periods=1).mean().loc[original_index]
    export_df["vol_ma10"] = vol.rolling(window=10, min_periods=1).mean().loc[original_index]
    export_df["vol_ma30"] = vol.rolling(window=30, min_periods=1).mean().loc[original_index]

    if args.days > 0:
        cutoff = datetime.utcnow() - timedelta(days=args.days)
        cutoff = pd.Timestamp(cutoff).tz_localize("UTC")
        export_df = export_df[export_df.index >= cutoff]
        print(f"Filtered to last {args.days} days: {len(export_df)} rows.")

    print("Writing to database...")
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
            "vol_ma1=VALUES(vol_ma1), vol_ma5=VALUES(vol_ma5), vol_ma10=VALUES(vol_ma10), vol_ma30=VALUES(vol_ma30)"
        )

    export_df = export_df.replace({np.nan: None})
    count = 0
    batch = []

    raw_conn = engine.raw_connection()
    try:
        for row in export_df.itertuples():
            ot = row.Index.to_pydatetime()
            ct = ot + timedelta(seconds=59, microseconds=999000)
            params = (
                ot, ct,
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
            if len(batch) >= args.batch_size:
                db_compat.execute_many_compatible(raw_conn, insert_sql, batch)
                raw_conn.commit()
                count += len(batch)
                print(f"Inserted {count} rows...")
                batch = []
        if batch:
            db_compat.execute_many_compatible(raw_conn, insert_sql, batch)
            raw_conn.commit()
            count += len(batch)
            print(f"Inserted {count} rows. Done.")
    finally:
        raw_conn.close()


if __name__ == "__main__":
    main()
