#!/usr/bin/env python3
# 数据写入器
from typing import List, Dict, Any
from datetime import datetime

from core.database import get_db
from core.logger import get_logger

class DataWriter:
    def __init__(self):
        self.logger = get_logger('data_module.writer')
        self.db = get_db()
    
    def write_klines(self, klines: List[Dict]) -> bool:
        """写入K线数据"""
        try:
            with self.db.transaction() as conn:
                for kline in klines:
                    conn.execute("""
                        INSERT OR REPLACE INTO klines_1m 
                        (open_time, open, high, low, close, volume, close_time, 
                         quote_volume, trades, taker_buy_base, taker_buy_quote, ignore)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        kline['open_time'],
                        kline['open'],
                        kline['high'],
                        kline['low'],
                        kline['close'],
                        kline['volume'],
                        kline['close_time'],
                        kline['quote_volume'],
                        kline['trades'],
                        kline['taker_buy_base'],
                        kline['taker_buy_quote'],
                        kline.get('ignore', '')
                    ))
            
            self.logger.debug(f"写入{len(klines)}条K线")
            return True
        except Exception as e:
            self.logger.error(f"写入K线失败: {e}")
            return False
    
    def write_indicators(self, indicators: Dict) -> bool:
        """写入指标数据"""
        try:
            with self.db.transaction() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO klines_1m_macd_smooth_ma
                    (open_time, close, macd15m, dif15m, dea15m, j_15)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    indicators['open_time'],
                    indicators['close'],
                    indicators.get('macd15m'),
                    indicators.get('dif15m'),
                    indicators.get('dea15m'),
                    indicators.get('j_15')
                ))
            
            return True
        except Exception as e:
            self.logger.error(f"写入指标失败: {e}")
            return False
