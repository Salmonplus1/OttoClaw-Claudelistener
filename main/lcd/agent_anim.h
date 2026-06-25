#pragma once

#include <stdbool.h>
#include "esp_err.h"

/**
 * agent_anim.h — Claude Code 状态同步螃蟹动画驱动
 * ==================================================
 *
 * 用法：
 *   1. agent_anim_init()   — 初始化 LVGL canvas + 15fps 定时器，默认显示 idle
 *   2. agent_anim_set_state(state) — 切换动画状态（可在任意上下文调用，线程安全）
 *   3. agent_anim_stop()   — 停止动画并销毁 canvas
 *
 * 状态对应关系：
 *   AGENT_ANIM_IDLE     ← Claude Code 空闲
 *   AGENT_ANIM_THINKING  ← Claude Code 思考中（LLM 推理）
 *   AGENT_ANIM_WRITING   ← Claude Code 写代码中（Edit/Write 工具）
 *   AGENT_ANIM_DONE      ← Claude Code 完成回答
 *   AGENT_ANIM_ERROR     ← Claude Code 出错
 *
 * 动画结构：
 *   每个状态有 intro（入场，播一次）和 loop（稳态，无限循环）两段。
 *   例如 idle: intro=哈欠一次 → loop=打盹循环。
 */

typedef enum {
    AGENT_ANIM_IDLE,       // 空闲打盹
    AGENT_ANIM_THINKING,   // 思考中（气泡）
    AGENT_ANIM_WRITING,    // 写代码（敲键盘）
    AGENT_ANIM_DONE,       // 完成（举花）
    AGENT_ANIM_ERROR,      // 出错（冒烟）
} agent_anim_state_t;

/**
 * 初始化动画模块。
 * - 创建 LVGL canvas 对象（200×100，居中在 face_area）
 * - 分配帧缓冲区（PSRAM）
 * - 启动 15fps 定时器
 * - 默认显示 idle 状态
 *
 * 必须在 LVGL 初始化完成后调用。
 */
esp_err_t agent_anim_init(void);

/**
 * 切换动画状态。
 * 线程安全——可在 WebSocket 回调、agent loop 等任意上下文调用。
 */
void agent_anim_set_state(agent_anim_state_t state);

/**
 * 停止动画并释放资源。
 * 隐藏 canvas，删除定时器，释放帧缓冲区。
 */
void agent_anim_stop(void);
