#!/bin/bash
# 安装Web监控系统所需依赖

echo "正在检查Web监控系统依赖..."

# 激活conda环境
source /Users/zhaosuqi/miniforge3/bin/activate bigtree

echo "当前环境:"
python --version
echo ""

echo "已安装的Flask相关包:"
pip list | grep -i flask
echo ""

echo "检查是否需要安装Flask-SocketIO..."
python -c "import flask_socketio" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✓ Flask-SocketIO 已安装"
else
    echo "✗ Flask-SocketIO 未安装"
    echo ""
    echo "正在安装 Flask-SocketIO..."
    pip install flask-socketio

    if [ $? -eq 0 ]; then
        echo "✓ Flask-SocketIO 安装成功"
    else
        echo "✗ Flask-SocketIO 安装失败"
        exit 1
    fi
fi

echo ""
echo "所有依赖检查完成!"
echo ""
echo "启动Web监控系统:"
echo "  python web_app.py"
echo ""
echo "或使用测试脚本:"
echo "  ./test_web_app.sh"
