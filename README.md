# OttoClaw — 一个不会开口说话的 AI 桌面人形机器人

**[中文](README.md) | [English](README_EN.md)**

<p align="center"><img src="assets/product_hero.jpg" width="800"></p>



## 🆕 Claude Code 螃蟹助手

> **新功能！** Otto LCD 实时显示 Claude Code 工作状态。Claude 思考时螃蟹冒气泡 💭，写代码时敲键盘 ⌨️，完成时举花 🌸，出错时冒烟 🔥。按 BOOT 按钮即可唤醒电脑端 Claude Code 窗口。

<p align="center"><img src="assets/crab_states.gif" width="600"></p>

### 5 种状态动画

| 状态 | 动画 | 触发 |
|------|------|------|
| 🦀 Idle | 哈欠 → 打盹循环 | Claude 空闲 / 完成 6 秒后自动切回 |
| 💭 Thinking | 思考气泡 (180帧) | 用户提交消息 |
| ⌨️ Writing | 敲键盘 + 数据粒子 | Claude 执行 Edit/Write 等工具 |
| 🌸 Done | 举花挥手 + 闪光 | Claude 完成回答 / 6s 后自动 idle |
| 🔥 Error | 冒烟 + X眼 | 出错时 |

### PC 端交互

```
Claude Code 状态变化 → hook 触发 → WebSocket → Otto LCD 自动切动画
按 Otto 的 BOOT 按钮 → WebSocket 广播 → PC 窗口激活 + 自动回车确认
```

### 快速配置 Claude Code

```bash
# 1. 安装依赖
pip install websocket-client pywin32 pyautogui pygetwindow

# 2. 启动 PC 监听（保持运行）
python tools/claude_hooks/boot_listener.py --otto-ip <Otto的IP>

# 3. 配置 Claude Code hooks（见 tools/claude_hooks/settings.example.json）
```

详见 [DEVLOG.md](DEVLOG.md) 了解完整开发过程和技术细节。

---

## 核心亮点

OttoClaw 与市面上其他 AI 玩具和桌面机器人不同：

- **真正运行在本地端侧的轻量 Agent** — 纯 C / FreeRTOS，单块 ESP32-S3 即可运行全部功能，不依赖云端服务器，记忆、会话、技能全部本地存储，0.5W 功耗 24/7 在线。
- **不会开口说话** — 不像其他机器人那样跟你说话打扰你。采用钉钉消息交互，忙碌时它安静等候，空闲时看一眼消息即可触发响应，安静如猫，始终在场。
- **AI 自主情绪表达** — 22 种情绪状态（+ 5 种 Claude Code 螃蟹状态），情绪随语境随机波动 — 开心时摇摆，害羞时低头掩面，思考时做出沉思姿态，情绪是自发的而非被动的。
- **性格与成长体系** — 它有自己的性格。初次见面可能对你爱答不理，随着互动增多逐渐熟络，感情自然升温。LCD右上角的红色爱心（1~5颗）是你们关系升温的见证。
- **真正的 AI 控制每一个关节** — 大模型自主决定 6 个舵机到达何种角度，创造任何它所想象的动作姿态，实现 AI 意识的物理化表达，而非依赖预设脚本。
- **全栈开源** — 硬件、软件、3D 模型全部开源
- **全开放架构** — 自选模型、自选交互通道、自选 MCP / Skill 等服务接入，阿里云百炼一键打通丰富生态。
- **功能模块母集** — 麦克风、显示屏、喇叭+功放、电源管理、电容触摸、6 路舵机、WiFi、蓝牙一板全集成。


---

## 快速上手

### 前置要求

1.  OttoRobot AI 版开发板或 DIY 套件
2. USB Type-C 数据线（须支持数据传输）
3. 大模型 API Key
4. 钉钉账号

### 步骤

**1. 下载固件** — 从 [Releases](https://github.com/FlashCat-Jordan/OttoClaw/releases) 下载对应板型的 `.bin` 文件

**2. 烧录** — [鹿戴马在线烧录](https://www.16302.com/localinit) 或 `esptool.py` 命令行：

```bash
esptool.py --chip esp32s3 --port COM3 --baud 460800 write_flash 0x0 ottoclaw.bin
```

**3. 配网** — 手机连接热点 `OttoClaw-XXXX`，浏览器打开 `192.168.4.1`，依次配置 WiFi、大模型、钉钉

**4. 开始使用** — 钉钉找到机器人，发消息即互动；LCD 右上角爱心显示关系等级

---

## 从源码编译

```bash
# 需要 ESP-IDF v5.5
git clone https://github.com/FlashCat-Jordan/OttoClaw.git
cd OttoClaw
cp main/ottoclaw_secrets.h.example main/ottoclaw_secrets.h
idf.py set-target esp32s3
idf.py build
idf.py -p PORT flash
```

### 烧录地址 (flash_download_tool)

| 文件 | 地址 |
|------|------|
| `build/bootloader/bootloader.bin` | `0x0` |
| `build/partition_table/partition-table.bin` | `0x8000` |
| `build/ota_data_initial.bin` | `0xf000` |
| `build/ottoclaw.bin` | `0x20000` |
| `build/spiffs.bin` | `0x820000` |

芯片: ESP32-S3 | SPI: 80MHz DIO | Flash: 128Mbit

### 生成动画数据

```bash
cd tools
pip install pillow playwright && playwright install chromium
python build_assets.py   # SVG → RLE
python build_h.py        # → crab_data.h + crab_data.c
```

---

## 交互方式

- **钉钉** — 主聊天入口。Stream 模式直连，安静不打扰
- **WebSocket** — 端口 18789。内置聊天页、API、Claude Code 状态同步
- **串口 CLI** — `oc>` 命令行，本地运维

### WebSocket 协议

**Claude Code → Otto**（状态同步）：
```json
{"type": "agent_state", "state": "thinking"}
```

**Otto → PC**（BOOT 广播）：
```json
{"type": "boot_button", "action": "short_press"}
```

---

## 项目结构

```
OttoClaw-main/
├── main/
│   ├── lcd/
│   │   ├── agent_anim.c/h      # 🆕 螃蟹动画驱动
│   │   ├── crab_data.c/h       # 🆕 RLE 动画数据 (1.2MB)
│   │   └── lcd_display.c/h     # LCD 显示 + 22 情绪动画
│   ├── gateway/ws_server.c/h   # WebSocket (含 agent_state)
│   ├── agent/agent_loop.c/h    # ReAct Agent 循环
│   ├── otto/                   # 舵机驱动 + 动作库
│   ├── tools/                  # 12 个 AI 工具
│   └── ...
├── tools/
│   ├── build_assets.py         # SVG → Playwright → RLE
│   ├── build_h.py              # RLE → C 源码
│   ├── assets/svg/             # 螃蟹 SVG 源文件
│   └── claude_hooks/           # Claude Code 集成脚本
├── partitions.csv              # OTA 4MB × 2
├── sdkconfig.defaults.esp32s3
├── DEVLOG.md                   # 开发日志
└── README.md
```

---

## 功能

### AI 自主情绪 — 22 种状态 + 5 种螃蟹动画

- **22 种情绪**：开心、害羞、思考、愤怒、惊讶、无聊、赛博、发晕、亢奋...
- **5 种螃蟹**：idle、thinking、writing、done、error — 通过 Claude Code hook 自动切换
- 情绪由 AI 根据语境自主触发，非被动预设

### 性格与成长 — 5 阶段关系

陌生 → 认识 → 熟络 → 亲密 → 羁绊。AI 自主推演关系走向。LCD 右上角 1~5 颗红心。

### AI 控制舵机 — 6 关节自主运动

22 个动作原语 + AI Servo Sequences。大模型根据语义自主设计姿态。

### 对话、搜索与记忆

钉钉交互，支持联网搜索、长期记忆、跨重启保留。

---

## 配置与 CLI

配置门户可完成所有配置。以下 CLI 命令供高级用户通过串口使用（115200）：

```
oc> wifi_set <ssid> <pass>        设置 WiFi
oc> set_api_key <key>             设置 API Key
oc> set_model <model>             设置模型名称
oc> set_model_provider <provider> 设置提供商
oc> config_show                   显示当前配置
oc> restart                       重启设备
oc> wifi_status                   显示 WiFi 状态与 IP
oc> heap_info                     显示可用堆内存
```

---

## 技术架构

- **纯 C / FreeRTOS** — 单块 ESP32-S3 运行全部功能
- **双核架构** — Core 0 网络 I/O，Core 1 Agent 循环
- **Anthropic tool use / ReAct** — AI 自主决定工具调用
- **LVGL 9.x** — 图形界面 + Canvas 动画
- **SPIFFS** — 本地存储记忆、会话、配置
- **WebSocket** — 状态同步 + BOOT 广播

详见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) 与 [DEVLOG.md](DEVLOG.md)（开发日志）

---

## 许可证

CC BY-NC-SA 4.0 — 署名、非商用、相同方式共享。个人学习与研究自由使用，商业用途需另行授权。

## 致谢

灵感源自 [OpenClaw](https://github.com/openclaw/openclaw)、[Nanobot](https://github.com/HKUDS/nanobot)、[mimiclaw](https://github.com/memovai/mimiclaw)、[OttoDIYLib](https://github.com/OttoDIY/OttoDIYLib) 与 [ClackClaw](https://github.com/FlashCat-Jordan/ClackClaw)。我们将 AI Agent 架构带入嵌入式硬件，并赋予其更具实体感的设备体验。

