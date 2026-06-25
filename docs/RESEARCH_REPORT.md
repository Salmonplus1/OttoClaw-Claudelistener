# 嵌入式设备与大模型协作的实物状态反馈系统设计与实现

## 摘要

本文在 OttoClaw——一个功能完备的端侧 AI 桌面机器人平台——的基础上，设计并实现了一套 Claude Code 状态实物反馈系统。通过 RLE 压缩的序列帧动画在 LCD 上实时展示 AI 的工作状态（思考/编码/完成/出错），并通过 BOOT 按钮实现物理→数字反向控制。系统采用 Playwright 采样 SVG 关键帧后经调色板量化和游程编码将 17.7MB 动画数据压缩至 1.2MB，以 LVGL Canvas 直接写缓冲区的方案实现 15fps 流畅渲染，基于 WebSocket 双向协议完成 <80ms 的状态同步。实验表明系统在 4MB OTA 分区的资源约束下稳定运行，有效增强了人机交互的物理感知维度。

**关键词**：嵌入式系统；大模型人机交互；RLE 压缩；LVGL；WebSocket；实物反馈

---

## 1. 引言

### 1.1 研究背景

开发者使用 Claude Code 等终端工具与 AI 协作已成为日常编程的一部分，但 AI 的内在状态完全被封闭在屏幕文字中——思考时只能看到加载图标，完成后若不主动查看便无从知晓。这种"屏幕内"模式忽略了人类的多模态感知特性。同时，Cozmo、Vector、LOVOT 等商业化桌面机器人虽具备情感表达，却均为封闭系统，AI 依赖厂商云端服务，用户无法自定义行为或接入自选模型。

本文工作建立在 OttoClaw 平台之上——一个全栈开源的 AI 桌面人形机器人，在单块 ESP32-S3 上以纯 C/FreeRTOS 实现了完整的 ReAct Agent、22 种自主情绪、5 阶段关系成长、6 路 AI 控制舵机，以及 Anthropic/OpenAI 双格式兼容的开放架构。尽管 OttoClaw 已具备丰富的 AI 能力，但其与开发者最常用的 Claude Code 之间缺乏直接物理连接。本文的目标正是填补这一缺口。

### 1.2 相关工作

| 项目 | Agent 能力 | 反馈通道 | 开放度 |
|------|-----------|---------|--------|
| ClackClaw[1] | 无 | TFT + 电磁铁 + 蜂鸣器 | 开源 |
| Blink1[2] | 无 | USB LED | 开源 |
| Cozmo/Vector[7] | 云端闭源 | 面部动画 + 声音 + 运动 | 闭源 |
| LOVOT[8] | 云端闭源 | 全身动画 + 声音 + 热感 | 闭源 |
| OttoClaw 既有[9] | 端侧开源 ReAct Agent | LCD 22 情绪 + 6 舵机 | 全栈开源 |
| **OttoClaw + 本文** | **端侧 Agent + Claude Code 双向同步** | **+ 螃蟹动画 + BOOT→PC** | **全栈开源** |

ClackClaw[1] 最接近本文思路——通过串口驱动 TFT 螃蟹动画反映 Claude Code 状态，但为单向通信且不承载 AI Agent。本文在其基础上做了三方面扩展：（1）将 RLE 动画管线从 Arduino 移植到 ESP-IDF/LVGL 平台；（2）以 WebSocket 替代串口，支持多客户端双向通信；（3）增加 BOOT→PC 反向控制链路。

### 1.3 系统亮点

1. **零云端依赖**：单块 ESP32-S3 运行全部功能——Agent 推理、工具调用、记忆存取、动画渲染。0.5W 功耗，USB 供电 24/7 在线，不需要 GPU 服务器或云中转。
2. **数据安全**：对话记录、长期记忆、用户画像全部存储在设备本地 SPIFFS 文件系统。没有数据离开用户的房间。钉钉消息走 Stream 直连，不经过第三方服务器。
3. **DIY 自由度高**：硬件 PCB、3D 外壳 STL、固件源码、动画 SVG 源文件、构建管线全部开源。可改螃蟹造型（改 SVG→跑 build_assets.py→重编译→新动画），可换大模型（Anthropic/OpenAI 兼容格式随意切，Base URL 自定义），可加工具（tool_registry.c 注册，AI 自动学会调用）。
4. **AI 情绪自发**：22 种情绪由大模型根据对话语境自主决定，不是按钮触发的预设反应。聊到食物自发开心，被冷落了自己害羞——AI 有"性格"。
5. **AI 控制物理身体**：大模型自主设计每个舵机的角度。"做求婚动作"→AI 推理出单膝跪地+右手高举+左手放下，6 个关节角度全部实时计算。同样的话每次可能编排不同姿态。
6. **会成长的机器人**：5 阶段关系体系（陌生→认识→熟络→亲密→羁绊）。初次见面爱答不理，聊多了自然熟络。AI 自主推演关系走向，数据持久化，重启不丢。
7. **Claude Code 物理化**：LCD 实时显示 Claude 工作状态——思考冒气泡、写代码敲键盘、完成举花、出错冒烟。17.7MB 动画压缩至 1.2MB，15fps 流畅播放，<80ms 延迟。
8. **物理反向控制**：Claude 弹权限确认框→按 Otto 的 BOOT 按钮→PC 窗口自动激活+回车确认。从物理世界操控数字世界。

### 1.4 本文贡献

1. 提出大模型运行状态"物理化"的通用架构，不依赖特定硬件平台
2. 实现 SVG 动画到嵌入式 RLE 数据的完整自动化构建管线
3. 设计 WebSocket 双向协议，使嵌入式设备成为 Claude Code 的物理外设
4. 通过 BOOT 按钮实现物理→数字反向控制

---

## 2. 系统架构

### 2.1 总体架构

系统由 PC 端 Claude Code Hook、OttoClaw 固件、WebSocket 通道三部分构成。

```
┌─ PC (Windows) ────────────────────┐      ┌─ OttoClaw (ESP32-S3) ──────┐
│ Claude Code CLI                    │      │ ws_server.c                │
│   │ hook 事件                      │      │   ├ agent_state 处理        │
│   ▼                                │ WebSocket    ▼                  │
│ agent_state.py ─── thinking ──────┼──────┼─→ agent_anim.c             │
│                                     │      │   ├ RLE 解码器            │
│ boot_listener.py ◄── boot_button ──┼──────┼─ broadcast()             │
│   ├ win32gui 激活窗口              │      │   ├ LVGL Canvas 200×100   │
│   └ pyautogui 回车                 │      │   ├ 15fps Timer            │
└────────────────────────────────────┘      │   └ intro/loop 状态机     │
                                            │           ↓                │
                                            │ ST7789 LCD 螃蟹动画        │
                                            │ BOOT (GPIO0) → 广播        │
                                            └────────────────────────────┘
```

### 2.2 硬件平台

- **主控**：ESP32-S3 (Xtensa LX7 双核 240MHz)，512KB SRAM + 8MB Octal PSRAM
- **存储**：16MB Flash (QIO)，OTA 双分区各 4MB
- **显示**：ST7789 240×240 LCD (SPI, RGB565)
- **外设**：6 路舵机 (LEDC PWM)、MEMS 麦克风、I2S 功放+喇叭、电容触摸、BOOT 按钮
- **通信**：WiFi 2.4GHz、Bluetooth 5.0 BLE

### 2.3 软件栈

| 层次 | 技术 |
|------|------|
| OS | FreeRTOS (ESP-IDF v5.5)，双核调度 |
| 图形 | LVGL 9.2.2 (Canvas + 22 情绪 + 5 螃蟹动画) |
| AI Agent | 自研 ReAct 循环 (纯 C)，12 个工具，上下文拼接 |
| 存储 | SPIFFS：长期记忆、用户画像、每日笔记、会话历史 |
| 关系 | 5 阶段成长模型，消息计数驱动，持久化 |
| 通信 | WebSocket (18789)、钉钉 Stream Bot、HTTP 代理 |
| 动画 | RLE + 256 色调色板，~1.2MB .rodata |
| PC 端 | Python 3.12 + WebSocket + Windows API |

---

## 3. 动画系统设计

### 3.1 SVG → RLE 构建管线

动画素材为 7 个 SVG 文件，使用 CSS `@keyframes` 定义关键帧。构建管线分 5 步：

**① Playwright 帧采样**：无头 Chromium 加载 SVG，通过 Web Animations API 的 `pause()` + `currentTime` 逐帧截图。每帧时间戳由脚本精确控制，按 1/15 秒对齐，避免传统视频采样的时间漂移。

**② 调色板量化**：同状态所有帧拼为大图，PIL ADAPTIVE 量化得 256 色共享调色板。`Image.Dither.NONE` 是关键——关闭抖动避免纯色区引入噪点，噪点会严重损害 RLE 压缩效率。

**③ RGB565 转换**：调色板转 RGB565 大端格式（与 ST7789 一致），固定 512 字节。

**④ 游程编码**：逐帧做 `(count, index)` RLE，count ∈ [1,255]。对 20,000 像素/帧，平均压缩至 6.8%。

**⑤ C 源码生成**：输出 `crab_data.c`（7.5MB 源文件，独立编译为 1.2MB .rodata）+ `crab_data.h`（小型头文件，仅类型定义和 extern 声明）。

### 3.2 运行时渲染

```c
typedef struct {
    char id;                               // 'T'/'W'/'D'/'E'/'I'
    const uint8_t* palette;                // 512B RGB565 大端
    uint16_t intro_count, loop_count;      // 帧数
    const uint8_t* const* intro_frames;     // 每帧 RLE 数据
    const uint16_t *intro_sizes, *loop_sizes;
    const uint8_t* const* loop_frames;
} CrabState;
```

渲染采用直接写缓冲区方案：从 PSRAM 分配 40KB 帧缓冲区（200×100×2，64 字节对齐），解码时直接写入缓冲，完成后 `lv_obj_invalidate()` 一次性刷新整个 Canvas。将 20,000 次 API 调用减为 1 次，延迟从 ~200ms 降至 <5ms。15fps 定时器通过 `lv_timer_create(callback, 66, NULL)` 驱动，回调在 LVGL 任务上下文中执行。

### 3.3 线程安全

状态切换可能来自 WebSocket 回调（HTTP Server 任务）或 timer 回调（LVGL 任务）。使用 C11 `atomic_int` 实现无锁传递，避免跨任务互斥锁的优先级反转问题：

```c
void agent_anim_set_state(state) {
    atomic_store(&s_pending_state, (int)state);   // 任意线程写入
}
// LVGL timer 回调中：
int pending = atomic_exchange(&s_pending_state, -1);  // 原子读取+重置
```

---

## 4. 通信协议设计

### 4.1 WebSocket 协议

选用 WebSocket 的理由：全双工双向、多客户端并发、基于 ESP-IDF 内置 HTTP Server。

```
PC→Otto:  {"type": "agent_state", "state": "thinking|writing|done|error|idle"}
Otto→PC:  {"type": "boot_button", "action": "short_press"}
```

### 4.2 WebSocket Masking Bug

实现中遇到一个隐蔽的 bug：PC 端手工构造的 WebSocket 帧在 ESP32 端被静默丢弃。根源是 RFC 6455 规定客户端→服务器帧必须用 4 字节 mask key 对 payload 做 XOR 编码，初始实现遗漏了此步骤。ESP-IDF httpd 的 WebSocket 实现严格校验 mask 字段，不符合规范的帧直接断开连接，ESP32 侧无任何错误日志，PC 端仅表现为 "SENT_OK"，排查极其困难。

修复：帧头长度字节的 MASK bit (0x80) 置位，生成随机 mask key，payload 逐字节 XOR。此 bug 暴露了手工构造协议帧的高风险性——本地回环测试无法复现，必须在真实 ESP32 服务器上才能触发。

### 4.3 Claude Code Hook 集成

| Hook 事件 | 时机 | 动画 |
|-----------|------|------|
| UserPromptSubmit | 用户提交消息 | thinking |
| PreToolUse | 执行 Edit/Write | writing |
| Stop / Notification | 完成回答 | done |
| PermissionRequest | 权限弹窗 | done + 窗口标记 🔴 |

PermissionRequest 额外调用 `SetConsoleTitle("🔴 OTTO_WAIT")` 标记终端窗口。BOOT 反向控制链由 boot_listener 实现：收到广播→窗口类名白名单搜索（仅 `CASCADIA_HOSTING_WINDOW_CLASS` 和 `ConsoleWindowClass`，排除资源管理器等非终端窗口）→ `SetForegroundWindow` 激活→ `pyautogui.press("enter")` 回车。

---

## 5. 实验结果

### 5.1 动画数据压缩

| 状态 | 帧数 | 原始 | 压缩后 | 比 |
|------|------|------|--------|-----|
| T-thinking | 180 | 7.03MB | 560KB | 7.8% |
| W-writing | 48 | 1.88MB | 148KB | 7.7% |
| D-done | 48 | 1.88MB | 149KB | 7.8% |
| E-error | 60 | 2.34MB | 162KB | 6.8% |
| I-idle | 57+60 | 4.57MB | 213KB | 4.6% |
| **合计** | **453** | **17.7MB** | **1.2MB** | **6.8%** |

### 5.2 系统延迟与资源

| 环节 | 延迟 |
|------|------|
| Hook → WebSocket 到 Otto | <10ms |
| 帧解析 → 状态切换 | <1ms (atomic) |
| 下一帧渲染 | <66ms (15fps 最坏) |
| RLE 解码一帧 | <3ms |
| **总端到端** | **<80ms** |

| 资源 | 占用 |
|------|------|
| Flash (OTA 槽) | 3.2/4MB (77%) |
| PSRAM (帧缓冲) | 40KB/8MB (0.5%) |
| CPU | <1% |

---

## 6. 问题与讨论

### 6.1 关键技术问题

**窗口检测精确性**：初期用标题关键词匹配目标窗口，但 Claude Code 运行在 Windows Terminal 中时标题随当前命令动态变化（如显示为"写一个脚本"），且会误匹配资源管理器窗口（名为 ".claude" 的文件夹含 "claude" 子串）。最终采用窗口类名白名单——仅匹配 `CASCADIA_HOSTING_WINDOW_CLASS` 和 `ConsoleWindowClass`，从根源消除误匹配。

**RGB565 字节序**：RLE 调色板为 RGB565 大端，解码时 `(pal[0]<<8)|pal[1]` 构造 uint16_t。在 ESP32 小端平台上，此值在内存中的字节布局恰好与 LVGL RGB565 原生格式一致，无需额外转换。此"恰好正确"的特性在自底向上的验证中被确认，体现了嵌入式开发中字节序一致性的重要性。

### 6.2 局限性

1. boot_listener 依赖 Windows API，暂不支持 macOS/Linux
2. 动画数据以 const 数组编译进固件，修改需重建构建管线
3. BOOT 短按功能从"进入配置门户"变为"唤醒 PC"，需长按开机才能重新配网

---

## 7. 结论与展望

本文在 OttoClaw 端侧 AI 平台基础上，实现了 Claude Code 状态实物反馈系统：RLE 压缩管线（17.7MB→1.2MB）、LVGL Canvas 直接渲染、WebSocket 双向通信（<80ms）、C11 原子无锁状态传递、BOOT 反向控制。本文的核心价值在于提出"嵌入式 AI Agent + 大模型编程助手"的协同范式——OttoClaw 的端侧 Agent 负责日常交互，Claude Code 状态同步让它能感知编程助手的内在状态，从"被动响应"升级为"环境感知"。

未来方向：（1）SPIFFS 加载动画数据，支持不重编译更新；（2）板载喇叭实现蜂鸣器音效；（3）mDNS 零配置网络发现；（4）macOS/Linux 跨平台支持；（5）Claude Code 状态作为关系系统输入——Claude 频繁出错可能导致 Otto"心情变差"。

---

## 参考文献

[1] ClackClaw — AI 编程助手的实物状态指示器. https://github.com/FlashCat-Jordan/ClackClaw

[2] Blink1 — USB RGB LED Notification Light. https://blink1.thingm.com/

[3] ESP-IDF Programming Guide v5.5. Espressif Systems. https://docs.espressif.com/projects/esp-idf/

[4] LVGL v9.2 Documentation. https://docs.lvgl.io/

[5] Fette, I. & Melnikov, A. (2011). RFC 6455: The WebSocket Protocol. IETF.

[6] Claude Code — Hooks. Anthropic. https://docs.anthropic.com/en/docs/claude-code

[7] Anki Cozmo & Vector — Consumer Social Robots. Digital Dream Labs.

[8] GROOVE X LOVOT — 情感陪伴机器人. https://lovot.life/

[9] OttoClaw — 开源 AI 桌面人形机器人. https://github.com/FlashCat-Jordan/OttoClaw
