/**
 * agent_anim.c — Claude Code 状态同步螃蟹动画驱动
 * =================================================
 *
 * RLE 解码 + LVGL canvas + 15fps 定时器。
 *
 * 动画结构：
 *   每个状态有 intro 段（播一次，如哈欠）和 loop 段（无限循环，如打盹）。
 *   set_state 时先播 intro（如果有），intro 结束自动切入 loop。
 *
 * RLE 格式：
 *   每帧 = (count, palette_index) 对序列，count ∈ [1, 255]。
 *   解码：取 count 和 index → 查 palette 得 RGB565 → 画 count 个像素。
 *   palette 是 512 字节，256 色 RGB565 大端。
 *
 * 线程安全：
 *   - 定时器回调在 LVGL 任务中执行，无需额外加锁
 *   - set_state 可在任意线程调用，使用原子标志 + LVGL 锁
 */

#include "agent_anim.h"
#include "crab_data.h"
#include "esp_log.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include <string.h>
#include <stdatomic.h>

/* LVGL 头文件 */
#include "lvgl.h"

/* esp_lvgl_port 锁（LVGL 9.x 线程安全） */
#include "esp_lvgl_port.h"

static const char *TAG = "agent_anim";

/* ── Canvas 尺寸与布局 ── */
#define CANVAS_W  CRAB_FRAME_W   /* 200 */
#define CANVAS_H  CRAB_FRAME_H   /* 100 */
/* 在 240x240 屏幕上居中（face_area 是 y=0~132） */
#define CANVAS_X  ((240 - CANVAS_W) / 2)   /* 20 */
#define CANVAS_Y  ((132 - CANVAS_H) / 2)   /* 16 */

/* DONE→IDLE 自动超时：完成后 6 秒自动回到空闲（与 clackclack 一致） */
#define DONE_AUTO_IDLE_MS  6000

/* ── 动画片段 ── */
typedef enum {
    SEG_INTRO = 0,   /* 入场动画：播一次后切 loop */
    SEG_LOOP  = 1,   /* 循环动画：无限循环 */
} anim_segment_t;

/* ── 运行时变量 ── */
static lv_obj_t      *s_canvas       = NULL;   /* LVGL canvas 对象 */
static lv_timer_t    *s_timer        = NULL;   /* 15fps 定时器 */
static uint16_t      *s_frame_buf    = NULL;   /* 帧缓冲区（PSRAM，CANVAS_W*CANVAS_H*2 字节）*/
static const CrabState *s_crab       = NULL;   /* 当前状态的 CrabState */
static anim_segment_t s_segment      = SEG_LOOP;
static uint16_t       s_frame_idx    = 0;
static volatile atomic_int s_pending_state = -1;  /* 待切换状态（-1=无） */
static agent_anim_state_t s_current_state = AGENT_ANIM_IDLE;
static uint32_t s_state_enter_ms = 0;             /* 进入当前状态的 tick（用于 DONE 超时） */

/* ── 状态 → crab_data char 映射 ── */
static char state_to_char(agent_anim_state_t st)
{
    switch (st) {
        case AGENT_ANIM_IDLE:     return 'I';
        case AGENT_ANIM_THINKING: return 'T';
        case AGENT_ANIM_WRITING:  return 'W';
        case AGENT_ANIM_DONE:     return 'D';
        case AGENT_ANIM_ERROR:    return 'E';
        default:                  return 'I';
    }
}

/* ── RLE 解码到帧缓冲区 ── */
static void decode_rle_frame(const CrabState *crab, anim_segment_t seg,
                              uint16_t frame_idx, uint16_t *buf)
{
    const uint8_t *rle;
    uint16_t sz;

    if (seg == SEG_INTRO && crab->intro_count > 0 && frame_idx < crab->intro_count) {
        rle = crab->intro_frames[frame_idx];
        sz  = crab->intro_sizes[frame_idx];
    } else if (seg == SEG_LOOP && crab->loop_count > 0) {
        rle = crab->loop_frames[frame_idx];
        sz  = crab->loop_sizes[frame_idx];
    } else {
        /* 无数据 — 清空 buffer 为黑色 */
        memset(buf, 0, CANVAS_W * CANVAS_H * 2);
        return;
    }

    const uint8_t *pal = crab->palette;
    uint16_t *out = buf;
    uint16_t remaining = CANVAS_W * CANVAS_H;   /* 总像素数 */
    uint16_t rle_i = 0;

    while (remaining > 0 && rle_i < sz) {
        uint8_t count = rle[rle_i];
        uint8_t idx   = rle[rle_i + 1];
        rle_i += 2;

        /* 查调色板：RGB565 大端 */
        uint16_t color = ((uint16_t)pal[idx * 2] << 8) | pal[idx * 2 + 1];

        /* 写 count 个像素（不超过剩余） */
        uint16_t n = (count <= remaining) ? count : remaining;
        for (uint16_t k = 0; k < n; k++) {
            *out++ = color;
        }
        remaining -= n;
    }

    /* 剩余像素填黑 */
    while (remaining > 0) {
        *out++ = 0x0000;
        remaining--;
    }
}

/* ── 获取当前 segment 的帧数 ── */
static uint16_t segment_frame_count(const CrabState *crab, anim_segment_t seg)
{
    if (!crab) return 0;
    return (seg == SEG_INTRO) ? crab->intro_count : crab->loop_count;
}

/* ── 15fps 定时器回调 ── */
static void anim_timer_cb(lv_timer_t *timer)
{
    /* 处理待切换的状态 */
    int pending = atomic_exchange(&s_pending_state, -1);
    if (pending >= 0) {
        agent_anim_state_t new_st = (agent_anim_state_t)pending;
        char c = state_to_char(new_st);
        const CrabState *new_crab = crab_get_state(c);

        if (new_crab) {
            s_crab = new_crab;
            s_current_state = new_st;
            s_state_enter_ms = esp_timer_get_time() / 1000;
            /* 有 intro 就从 intro 开始，否则直接 loop */
            if (new_crab->intro_count > 0) {
                s_segment = SEG_INTRO;
            } else {
                s_segment = SEG_LOOP;
            }
            s_frame_idx = 0;
            ESP_LOGI(TAG, "State → %c (intro=%d, loop=%d)",
                     c, new_crab->intro_count, new_crab->loop_count);
        } else {
            ESP_LOGW(TAG, "No crab data for state %c", c);
        }
    }

    if (!s_crab) return;

    /* DONE→IDLE 自动超时（6 秒后回到空闲打盹） */
    if (s_current_state == AGENT_ANIM_DONE) {
        uint32_t elapsed = esp_timer_get_time() / 1000 - s_state_enter_ms;
        if (elapsed >= DONE_AUTO_IDLE_MS) {
            ESP_LOGI(TAG, "DONE timeout → IDLE");
            const CrabState *idle = crab_get_state('I');
            if (idle) {
                s_crab = idle;
                s_current_state = AGENT_ANIM_IDLE;
                s_segment = (idle->intro_count > 0) ? SEG_INTRO : SEG_LOOP;
                s_frame_idx = 0;
                s_state_enter_ms = esp_timer_get_time() / 1000;
            }
        }
    }

    /* 推进帧 */
    uint16_t total = segment_frame_count(s_crab, s_segment);
    if (total == 0) return;

    /* 解码当前帧 */
    decode_rle_frame(s_crab, s_segment, s_frame_idx, s_frame_buf);

    /* 刷新 canvas */
    lv_obj_invalidate(s_canvas);

    /* 推进帧索引 */
    s_frame_idx++;
    if (s_frame_idx >= total) {
        if (s_segment == SEG_INTRO && s_crab->loop_count > 0) {
            /* intro 播完 → 进入 loop */
            s_segment = SEG_LOOP;
            s_frame_idx = 0;
        } else {
            /* loop 播完 → 回到 loop 开头 */
            s_frame_idx = 0;
        }
    }
}

/* ── 公开 API ── */

esp_err_t agent_anim_init(void)
{
    if (s_canvas) {
        ESP_LOGW(TAG, "Already initialized");
        return ESP_ERR_INVALID_STATE;
    }

    /* 分配帧缓冲区（PSRAM，64 字节对齐以满足 LVGL draw buffer 要求） */
    size_t buf_size = CANVAS_W * CANVAS_H * sizeof(uint16_t);
    s_frame_buf = (uint16_t *)heap_caps_aligned_alloc(64, buf_size,
                        MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!s_frame_buf) {
        ESP_LOGE(TAG, "Failed to alloc frame buffer (%d bytes)", (int)buf_size);
        return ESP_ERR_NO_MEM;
    }
    memset(s_frame_buf, 0, buf_size);

    /* 创建 LVGL canvas */
    lvgl_port_lock(0);
    s_canvas = lv_canvas_create(lv_screen_active());
    lv_canvas_set_buffer(s_canvas, s_frame_buf, CANVAS_W, CANVAS_H, LV_COLOR_FORMAT_RGB565);
    lv_obj_set_pos(s_canvas, CANVAS_X, CANVAS_Y);
    lv_obj_set_size(s_canvas, CANVAS_W, CANVAS_H);
    /* 去除 canvas 默认样式，干净叠加 */
    lv_obj_set_style_border_width(s_canvas, 0, 0);
    lv_obj_set_style_bg_opa(s_canvas, LV_OPA_TRANSP, 0);
    lv_obj_set_style_pad_all(s_canvas, 0, 0);
    lvgl_port_unlock();

    /* 加载默认 idle 状态 */
    const CrabState *idle = crab_get_state('I');
    if (idle) {
        s_crab = idle;
        s_current_state = AGENT_ANIM_IDLE;
        s_segment = (idle->intro_count > 0) ? SEG_INTRO : SEG_LOOP;
        s_frame_idx = 0;
        /* 立即画第一帧 */
        decode_rle_frame(s_crab, s_segment, 0, s_frame_buf);
    }

    /* 启动 15fps 定时器 */
    s_timer = lv_timer_create(anim_timer_cb, CRAB_MS_PER_FRAME, NULL);
    if (!s_timer) {
        ESP_LOGE(TAG, "Failed to create timer");
        heap_caps_free(s_frame_buf);
        s_frame_buf = NULL;
        lvgl_port_lock(0);
        lv_obj_del(s_canvas);
        lvgl_port_unlock();
        s_canvas = NULL;
        return ESP_FAIL;
    }

    ESP_LOGI(TAG, "Initialized: %dx%d canvas at (%d,%d), %dfps",
             CANVAS_W, CANVAS_H, CANVAS_X, CANVAS_Y, CRAB_FPS);
    return ESP_OK;
}

void agent_anim_set_state(agent_anim_state_t state)
{
    /* 原子写入待切换状态，定时器回调中实际切换 */
    atomic_store(&s_pending_state, (int)state);
    ESP_LOGI(TAG, "set_state: %d → pending", state);
}

void agent_anim_stop(void)
{
    /* 删除定时器必须在 LVGL 锁内，避免与 LVGL 任务并发 */
    lvgl_port_lock(0);
    if (s_timer) {
        lv_timer_del(s_timer);
        s_timer = NULL;
    }
    if (s_canvas) {
        lv_obj_del(s_canvas);
        s_canvas = NULL;
    }
    lvgl_port_unlock();

    if (s_frame_buf) {
        heap_caps_free(s_frame_buf);
        s_frame_buf = NULL;
    }

    s_crab = NULL;
    atomic_store(&s_pending_state, -1);
    ESP_LOGI(TAG, "Stopped");
}
