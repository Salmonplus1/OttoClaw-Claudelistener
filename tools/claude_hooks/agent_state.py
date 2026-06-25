#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
agent_state.py — Claude Code Hook → OttoClaw WebSocket 状态同步
=================================================================

被 Claude Code hooks 调用，把事件映射为状态，通过 WebSocket 发给 Otto。

事件 → 状态映射：
    user_prompt        → thinking   (用户提交输入，AI 开始思考)
    pre_write_tool     → writing    (AI 即将写代码)
    stop               → done       (AI 完成回答)
    notification       → done       (弹窗通知)
    error              → error      (出错)

用法（一般由 Claude Code 自动调用）：
    python agent_state.py <event_type>

依赖：Python 标准库 + websockets (pip install websockets)

配置：
    环境变量 OTTO_IP — OttoClaw 的 IP 地址（默认 192.168.4.1）
    环境变量 OTTO_WS_PORT — WebSocket 端口（默认 18789）
"""

import asyncio
import ctypes
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# ── 终端窗口标题标记（Windows SetConsoleTitle） ──
WAIT_MARK = "🔴 OTTO_WAIT"

def set_console_title(title: str) -> None:
    """设置当前控制台窗口标题，用于 boot_listener 精确定位"""
    try:
        ctypes.windll.kernel32.SetConsoleTitleW(title)
    except Exception:
        pass

# ── 配置 ──
OTTO_IP   = os.environ.get("OTTO_IP", "10.20.149.112")
OTTO_PORT = int(os.environ.get("OTTO_WS_PORT", "18789"))
OTTO_WS_URL = f"ws://{OTTO_IP}:{OTTO_PORT}/ws"

SCRIPT_DIR = Path(__file__).resolve().parent
LOG_FILE   = SCRIPT_DIR / "agent_state.log"

# 事件 → agent_state
EVENT_TO_STATE = {
    "user_prompt":        "thinking",
    "pre_write_tool":     "writing",
    "stop":               "done",
    "notification":       "done",
    "permission_request": "done",     # 权限弹窗 → 完成态（提示用户互动）
    "error":              "error",
}


def log(msg: str) -> None:
    """写日志到文件"""
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


async def send_state(state: str) -> bool:
    """通过 WebSocket 发送 agent_state 消息到 Otto"""
    try:
        # 使用标准库 asyncio 的 WebSocket 客户端（Python 3.8+ 无内置 WebSocket）
        # 回退到简单的 TCP socket 发送
        import socket

        ws_msg = json.dumps({"type": "agent_state", "state": state})
        log(f"SEND → {OTTO_WS_URL} : {ws_msg}")

        # 先用快速 TCP 连接试试
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        sock.connect((OTTO_IP, OTTO_PORT))

        # 发送 HTTP Upgrade 请求建立 WebSocket
        http_request = (
            f"GET /ws HTTP/1.1\r\n"
            f"Host: {OTTO_IP}:{OTTO_PORT}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
            f"Sec-WebSocket-Version: 13\r\n"
            f"\r\n"
        )
        sock.sendall(http_request.encode())

        # 读服务器响应
        response = sock.recv(4096)
        if b"101" not in response:
            log(f"HANDSHAKE_FAIL: {response[:200]}")
            sock.close()
            return False

        # 构造 WebSocket 文本帧（客户端→服务器 必须 mask）
        payload = ws_msg.encode("utf-8")
        import random as _random
        mask_key = bytes([_random.randint(0, 255) for _ in range(4)])

        frame = bytearray()
        frame.append(0x81)  # FIN + text opcode
        if len(payload) < 126:
            frame.append(0x80 | len(payload))   # MASK bit set
        elif len(payload) < 65536:
            frame.append(0x80 | 126)
            frame.extend(len(payload).to_bytes(2, "big"))
        else:
            frame.append(0x80 | 127)
            frame.extend(len(payload).to_bytes(8, "big"))
        frame.extend(mask_key)

        # XOR payload with mask key
        masked = bytearray()
        for i, b in enumerate(payload):
            masked.append(b ^ mask_key[i % 4])
        frame.extend(masked)

        sock.sendall(frame)
        sock.close()
        log(f"SENT_OK  state={state}")
        return True

    except socket.timeout:
        log(f"TIMEOUT   state={state}  host={OTTO_IP}:{OTTO_PORT}")
        return False
    except ConnectionRefusedError:
        log(f"REFUSED   state={state}  host={OTTO_IP}:{OTTO_PORT} (Otto not connected?)")
        return False
    except Exception as e:
        log(f"FAIL      state={state}  err={e}")
        return False


def main() -> None:
    event = sys.argv[1].lower() if len(sys.argv) > 1 else "unknown"
    state = EVENT_TO_STATE.get(event)

    if state is None:
        log(f"WARN  unknown event: {event!r}")
        return

    log(f"EVENT {event} → {state}")

    # 权限弹窗时标记终端窗口标题，boot_listener 据此精确激活
    if event == "permission_request":
        set_console_title(WAIT_MARK)
        log(f"MARK  {WAIT_MARK}")
    elif event in ("stop", "user_prompt"):
        set_console_title("")
        log("MARK  cleared")

    try:
        asyncio.run(send_state(state))
    except Exception as e:
        log(f"ASYNC_ERR  {e}")


if __name__ == "__main__":
    main()
