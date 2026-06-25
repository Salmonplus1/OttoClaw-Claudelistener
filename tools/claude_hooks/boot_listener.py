#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
boot_listener.py — 监听 Otto BOOT 按钮广播，激活 Claude Code 窗口
===================================================================

作为后台守护进程运行，连接 Otto 的 WebSocket 服务器，持续监听
BOOT 按钮短按事件。

收到 {"type":"boot_button","action":"short_press"} 后：
  1. 找到 Claude Code 终端窗口并激活（bring to foreground）
  2. 发送 Enter 键（确认权限请求）

Windows 实现：
  - 使用 win32gui 查找窗口
  - 使用 pygetwindow 激活窗口
  - 使用 pyautogui 发送按键

用法：
    python boot_listener.py [--otto-ip 192.168.4.1] [--otto-port 18789]

依赖：
    pip install websocket-client pygetwindow pyautogui pywin32
"""

import json
import os
import sys
import subprocess
import time
import threading
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
LOG_FILE   = SCRIPT_DIR / "boot_listener.log"


def log(msg: str) -> None:
    """写日志"""
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
        print(f"[{ts}] {msg}")
    except Exception:
        print(msg)


# ── Windows 窗口激活 ──

def find_claude_window() -> "int | None":
    """仅搜索终端窗口，避免误激活资源管理器等其他窗口"""
    try:
        import win32gui
    except ImportError:
        log("WARN: win32gui not available — pip install pywin32")
        return None

    # 终端窗口类名白名单
    TERMINAL_CLASSES = {
        "CASCADIA_HOSTING_WINDOW_CLASS",  # Windows Terminal
        "ConsoleWindowClass",             # 传统 cmd / PowerShell
    }

    # 标题关键词（在终端窗口内匹配）
    keywords = [
        "OTTO_WAIT", "Claude Code", "claude",
        "Windows PowerShell", "PowerShell", "Command Prompt",
        "cmd.exe", "bash", "zsh", "WSL",
    ]

    # 先收集所有终端窗口
    terminal_windows = []

    def collect_cb(hwnd, _):
        cls = win32gui.GetClassName(hwnd)
        if cls in TERMINAL_CLASSES:
            title = win32gui.GetWindowText(hwnd)
            terminal_windows.append((hwnd, cls, title))

    win32gui.EnumWindows(collect_cb, None)

    if not terminal_windows:
        log("No terminal windows found")
        return None

    log(f"Terminal windows: {[(h,c,t) for h,c,t in terminal_windows]}")

    # 在终端窗口中按关键词优先级匹配
    for kw in keywords:
        for hwnd, cls, title in terminal_windows:
            if title and kw.lower() in title.lower():
                log(f"Matched: '{kw}' in '{title}' hwnd={hwnd}")
                return hwnd

    # 无匹配 — 返回找到的第一个终端窗口作为兜底
    hwnd = terminal_windows[0][0]
    log(f"No keyword match, fallback to first terminal: hwnd={hwnd}")
    return hwnd


def activate_claude_window() -> bool:
    """激活 Claude Code 窗口并发送 Enter"""
    try:
        import win32gui
        import win32con
        import pyautogui
    except ImportError as e:
        log(f"IMPORT_ERR: {e}")
        return False

    hwnd = find_claude_window()
    if not hwnd:
        # 回退：尝试 FindWindow 模糊搜索
        for title_hint in ["PowerShell", "cmd", "claude", "Terminal"]:
            hwnd = win32gui.FindWindow(None, None)
            # 遍历所有窗口找模糊匹配
            def find_by_substring(hint):
                result = []
                def cb(h, _):
                    t = win32gui.GetWindowText(h)
                    if hint.lower() in t.lower():
                        result.append(h)
                win32gui.EnumWindows(cb, None)
                return result[0] if result else None
            hwnd = find_by_substring(title_hint)
            if hwnd:
                log(f"Fallback found: {title_hint} hwnd={hwnd}")
                break

    if not hwnd:
        log("No window to activate")
        return False

    try:
        # 如果窗口最小化，先恢复
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

        # 激活窗口
        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.3)

        # 发送 Enter
        pyautogui.press("enter")
        log(f"Activated + Enter sent to hwnd={hwnd}")
        return True
    except Exception as e:
        log(f"ACTIVATE_ERR: {e}")
        return False


# ── WebSocket 监听 ──

def listen_ws(otto_ip: str, otto_port: int) -> None:
    """连接 Otto WebSocket，持续监听 boot_button 事件"""
    try:
        from websocket import create_connection, WebSocketConnectionClosedException, WebSocketTimeoutException
    except ImportError:
        log("FATAL: websocket-client not installed — pip install websocket-client")
        sys.exit(1)

    ws_url = f"ws://{otto_ip}:{otto_port}/ws"
    log(f"Connecting to {ws_url} ...")

    reconnect_delay = 1

    while True:
        try:
            ws = create_connection(ws_url, timeout=5, ping_interval=20, ping_timeout=10)
            log(f"Connected to {ws_url}")

            # 重置重连延迟
            reconnect_delay = 1

            while True:
                try:
                    msg = ws.recv()
                except WebSocketTimeoutException:
                    # 无消息超时，正常情况（Otto 不发数据直到按 BOOT）
                    continue
                if not msg:
                    continue

                try:
                    data = json.loads(msg)
                except json.JSONDecodeError:
                    continue

                msg_type = data.get("type", "")
                if msg_type == "boot_button":
                    action = data.get("action", "")
                    log(f"BOOT_BUTTON  action={action}")

                    if action == "short_press":
                        # 在单独的线程中激活窗口，不阻塞 WS 连接
                        threading.Thread(
                            target=activate_claude_window,
                            daemon=True,
                        ).start()

        except WebSocketConnectionClosedException:
            log(f"Connection closed — reconnecting in {reconnect_delay}s")
            time.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, 30)
        except ConnectionRefusedError:
            log(f"Connection refused — Otto not ready? retry in {reconnect_delay}s")
            time.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, 30)
        except Exception as e:
            log(f"WS_ERR: {e} — reconnecting in {reconnect_delay}s")
            time.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, 30)


def main() -> None:
    otto_ip = "10.20.149.112"
    otto_port = 18789

    # 解析命令行参数
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--otto-ip" and i + 1 < len(args):
            otto_ip = args[i + 1]
            i += 2
        elif args[i] == "--otto-port" and i + 1 < len(args):
            otto_port = int(args[i + 1])
            i += 2
        else:
            i += 1

    # 也支持环境变量
    otto_ip = os.environ.get("OTTO_IP", otto_ip)
    otto_port = int(os.environ.get("OTTO_WS_PORT", otto_port))

    log(f"=== boot_listener starting ===")
    log(f"Otto: {otto_ip}:{otto_port}")
    log(f"Log:  {LOG_FILE}")

    listen_ws(otto_ip, otto_port)


if __name__ == "__main__":
    main()
