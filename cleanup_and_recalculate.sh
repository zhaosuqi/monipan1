#!/bin/bash
# 清理并重新计算指标数据

echo "========================================="
echo "清理并重新计算指标数据"
echo "========================================="
echo ""

echo "⚠️  警告：此操作将："
echo "1. 删除 2024-12-20 之后的所有指标数据"
echo "2. 从数据库重新获取K线数据"
echo "3. 重新计算所有技术指标"
echo ""
echo "预计耗时：10-30分钟（取决于数据量）"
echo ""

read -p "确认继续？(yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "操作已取消"
    exit 0
fi

echo ""
echo "开始处理..."
echo ""

python cleanup_and_recalculate.py

echo ""
echo "========================================="
echo "处理完成"
echo "========================================="
