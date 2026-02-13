#!/bin/bash

# check if service is running
if pgrep -f "scripts/main.py" > /dev/null; then
    echo "Opening Dashboard..."
    # 使用 127.0.0.1 以确保连接稳定
    open "http://127.0.0.1:7860"
else
    echo "⚠️  Service is not running."
    echo "Run 'bash start.sh' to start the service."
fi
