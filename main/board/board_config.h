#pragma once

#include "driver/gpio.h"

/*
 * OttoClaw Board Configuration
 *
 * CONFIG_OTTOCLAW_BOARD_VARIANT selects the PCB version:
 *   1 = OttoRobot AI (non-camera) — default
 *   2 = OttoCam519 (camera version, different GPIO routing)
 *
 * Set via: idf.py menuconfig → OttoClaw Board → Board Variant
 */

/* ── Servo GPIO pins ───────────────────────────────────────── */
#if CONFIG_OTTOCLAW_BOARD_VARIANT == 2
  #define OTTO_PIN_LEFT_LEG    5
  #define OTTO_PIN_RIGHT_LEG   43
  #define OTTO_PIN_LEFT_FOOT   6
  #define OTTO_PIN_RIGHT_FOOT  44
  #define OTTO_PIN_LEFT_HAND   4
  #define OTTO_PIN_RIGHT_HAND  7
#else
  #define OTTO_PIN_LEFT_LEG    17
  #define OTTO_PIN_RIGHT_LEG   39
  #define OTTO_PIN_LEFT_FOOT   18
  #define OTTO_PIN_RIGHT_FOOT  38
  #define OTTO_PIN_LEFT_HAND   8
  #define OTTO_PIN_RIGHT_HAND  12
#endif

/* ── LCD GPIO pins ─────────────────────────────────────────── */
#if CONFIG_OTTOCLAW_BOARD_VARIANT == 2
  #define OTTO_PIN_LCD_BL      38
  #define OTTO_PIN_LCD_MOSI    45
  #define OTTO_PIN_LCD_SCLK    48
  #define OTTO_PIN_LCD_DC      47
  #define OTTO_PIN_LCD_RST     1
  #define OTTO_PIN_LCD_CS      (-1)
#else
  #define OTTO_PIN_LCD_BL      3
  #define OTTO_PIN_LCD_MOSI    10
  #define OTTO_PIN_LCD_SCLK    9
  #define OTTO_PIN_LCD_DC      46
  #define OTTO_PIN_LCD_RST     11
  #define OTTO_PIN_LCD_CS      12
#endif

/* ── LCD hardware config ──────────────────────────────────── */
#define OTTO_LCD_SPI_HOST     SPI3_HOST
#define OTTO_LCD_PIXEL_CLK    (40 * 1000 * 1000)
#define OTTO_LCD_H_RES        240
#define OTTO_LCD_V_RES        240

/* ── Boot button (same on both boards) ─────────────────────── */
#define OTTO_PIN_BOOT_BUTTON  GPIO_NUM_0