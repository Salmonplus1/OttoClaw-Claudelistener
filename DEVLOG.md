# OttoClaw Claude Code Crab Animation — 开发日志

## 项目背景

ClackClaw 项目已经实现了 Claude Code 状态 → ESP32-C3 螃蟹动画的完整管线（SVG → RLE → TFT 屏幕），但它是独立硬件（Arduino + 160×80 TFT）。OttoClaw 有更大的 240×240 LCD、LVGL 图形框架、WebSocket 服务，具备移植条件。

**目标**：在 Otto 上实现 Claude Code 工作时 LCD 自动显示螃蟹动态表情，BOOT 按钮能唤醒电脑端 Claude Code 窗口。

---

## 2026-06-23：架构设计与初始实现

### 设计决策

| 决策 | 选择 | 原因 |
|------|------|------|
| 帧渲染方式 | LVGL canvas + 直接写缓冲区 | 20K 像素/帧，逐像素 `lv_canvas_set_px` 太慢；直接写 buffer 后 `lv_obj_invalidate` 一次刷新 |
| 帧缓冲区位置 | PSRAM (40KB) | ESP32-S3 内部 SRAM 有限，40KB 应放 PSRAM |
| 数据格式 | `crab_data.c` 独立编译 | 原方案是把 7.5MB 数据塞进头文件，会导致每个 include 的翻译单元都重新编译。拆成 `.c` 后仅编译一次 |
| RLE 调色板字节序 | 大端（与 ST7789 一致） | 解码时 `(pal[0]<<8)|pal[1]` 转为 uint16_t，LVGL 按原生字节序读取，验证通过 |
| OTA 分区 | 2MB → 4MB | 原有 2MB 不够装 1.2MB 螃蟹数据 + 固件代码 |

### 遇到的问题

#### 1. ESP-IDF 工具链版本不匹配
**现象**：`Tool doesn't match supported version from list ['esp-14.2.0_20251107']`
**原因**：安装了两个版本的工具链 (20251107 和 20260121)，ESP-IDF v5.5 只认前者。
**解决**：在 build_otto.ps1 中显式指定 `esp-14.2.0_20251107` 路径。

#### 2. MSYS 环境污染
**现象**：在 Git Bash 中运行 `idf.py` 报 `MSys/Mingw is not supported`
**原因**：VSCode 的 bash 终端继承 `MSYSTEM=MINGW64` 环境变量，ESP-IDF 检测后拒绝运行。
**解决**：写 PowerShell 构建脚本，通过 `env -u MSYSTEM -u MSYS -u SHELL` 清除 MSYS 环境后调用 PowerShell，PowerShell 内部再 `Remove-Item Env:MSYSTEM`。

#### 3. Playwright Chromium 版本不匹配
**现象**：`Executable doesn't exist at .../chromium_headless_shell-1223/...`
**原因**：Python 包是 playwright 1.60.0（要求 chromium-1223），但系统装的是 chromium-1228。
**解决**：`build_assets.py` 中自动 `glob` 匹配已安装的 Chromium 版本号。

#### 4. WebSocket 帧未 mask
**现象**：PC hook 脚本发送 WebSocket 帧后 Otto 无反应。
**原因**：RFC 6455 规定客户端→服务器帧必须 XOR mask，ESP-IDF httpd 拒绝未 mask 帧。
**解决**：手动构造 mask key 并对 payload 逐字节 XOR。这是本项目中修得最隐蔽的 bug。

---

## 2026-06-24：调试与完善

### 5. Claude Code 路径转义问题
**现象**：hook 报错 `can't open file 'C:\\Users\\qq482\\Usersqq482.claudehooks...'`
**原因**：JSON 中 `C:\\Users\\...\\.claude\\hooks\\...` 的反斜杠被 JSON parser 当作转义序列吃掉。
**解决**：正斜杠 `C:/Users/qq482/.claude/hooks/agent_state.py` 在 Windows 上完全可用，JSON 无需转义。

### 6. lv_timer_del 竞态条件
**现象**：`agent_anim_stop()` 中先 `lv_timer_del` 再 `lvgl_port_lock`。
**风险**：如果在 timer 回调执行期间调用 stop，timer 和 LVGL 任务可能并发访问 canvas。
**解决**：把 timer 删除和 canvas 删除合并到同一个 `lvgl_port_lock(0)` 块内。

### 7. DONE 状态无自动超时
**现象**：进入 DONE（完成）状态后螃蟹一直循环举花动画，不回 idle。
**原因**：ClackClaw Arduino 版有 `D_AUTO_TO_I_MS = 6000`，移植时遗漏。
**解决**：添加 `esp_timer_get_time()` 计时，6 秒后自动切回 idle。

### 8. BOOT 按钮窗口激活误匹配
**现象**：按 BOOT 后激活了一个名为 `.claude` 的资源管理器窗口。
**原因**：窗口标题 `.claude` 包含关键词 `claude`，且 `EnumWindows` 枚举了所有窗口。
**解决**：
- 第一版：黑名单过滤 `CabinetWClass`（治标）
- 最终版：白名单模式，只搜索 `CASCADIA_HOSTING_WINDOW_CLASS` (Windows Terminal) 和 `ConsoleWindowClass` (传统终端)，其他窗口类一概忽略

### 9. WebSocket 连接反复超时断开
**现象**：`boot_listener` 连接后约 10 秒即超时重连。
**原因**：Otto 在无事件时不发任何数据，`ws.recv()` 超时抛出异常被当做连接断开。
**解决**：捕获 `WebSocketTimeoutException` 视为正常、添加 `ping_interval=20` 保活、`ping_timeout=10` 检测断连。

### 10. 分区表 OTA 扩容
**现象**：`crab_data.c` 编译后固件 3.2MB，原有 2MB OTA 槽不够。
**解决**：
```
ota_0:  0x20000,  2MB → 4MB
ota_1:  0x220000, 2MB → 4MB  → 0x420000
spiffs: 0x420000, 12MB → 0x820000, 8MB
```

### 11. sdkconfig 缺少 LVGL Canvas 支持
**现象**：编译时 `lv_canvas_create` 等函数未定义。
**原因**：sdkconfig 没有 `CONFIG_LV_USE_CANVAS=y`。
**解决**：添加到 `sdkconfig.defaults.esp32s3`。

### 12. 帧缓冲区对齐
**现象**：LVGL canvas 在 PSRAM 上可能因对齐问题导致花屏。
**预防**：使用 `heap_caps_aligned_alloc(64, ...)` 而非 `heap_caps_malloc`，确保 64 字节对齐。

---

## 技术要点

### RLE 解码算法
```
每帧 = (count, palette_index) 对序列，count ∈ [1, 255]
解码：while (剩余像素 > 0) {
    count, idx = 取下一对
    color = (palette[idx*2] << 8) | palette[idx*2+1]  // 大端 RGB565
    画 count 个 color 像素
}
剩余像素填黑 (0x0000)
```

### 文件大小管理
| 阶段 | 大小 | 说明 |
|------|------|------|
| 原始帧 (200×100×2B×453帧) | 17.7 MB | 未压缩 |
| RLE 压缩 + 调色板 | 1.2 MB | 6.8% 压缩比 |
| C 源码表示 (`0xAB, 0xCD, ...`) | 7.5 MB | 文本膨胀 6x |
| 编译后 `.rodata` | 1.2 MB | 存储在 Flash |

### 线程模型
- LVGL 定时器回调在 LVGL 任务中运行（已持锁）
- WebSocket handler 在 HTTP server 任务中运行
- `agent_anim_set_state()` 用 `atomic_int` 传递状态，避免跨任务竞态
- canvas 创建/销毁在 `lvgl_port_lock(0)` 保护下进行

---

## 后续改进方向

- [ ] 使用 SPIFFS 存储动画数据而非编译进固件（简化更新）
- [ ] WiFi 断连时自动切换到错误动画
- [ ] 添加蜂鸣器音效（与 ClackClaw 的电磁铁/蜂鸣器一致）
- [ ] 支持自定义 SVG 动画（用户可自行设计螃蟹造型）
- [ ] OTA 远程更新动画数据
- [ ] 支持 Linux/macOS 的 boot_listener（目前仅 Windows）
