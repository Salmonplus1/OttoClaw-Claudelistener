#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_assets.py — OttoClaw 螃蟹动画资产构建脚本
==================================================
改编自 ClackClaw 的 build_assets.py，适配 OttoClaw 的 240x240 LCD。

SVG 源 → Playwright Chromium 加载并采样多帧
       → 缩放到 FRAME_W × FRAME_H
       → 每像素转 RGB565
       → 调色板量化（256 色）
       → RLE 压缩
       → 输出 tools/build/crab_data.py
"""

import os
import re
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

# === 项目路径 ===
PROJECT    = Path(__file__).resolve().parent
BUILD_DIR  = PROJECT / "build"

# SVG 源文件目录（使用 clackclack 项目的 SVG 资源）
CLACKCLACK_SVG_DIR = Path(__file__).resolve().parent.parent.parent / "clackclack-main" / "clackclack-main" / "assets" / "svg"
# 如果 clackclack SVGs 不在，检查本地 assets/svg/
LOCAL_SVG_DIR = PROJECT / "assets" / "svg"

def find_svg_dir():
    if CLACKCLACK_SVG_DIR.exists():
        return CLACKCLACK_SVG_DIR
    if LOCAL_SVG_DIR.exists():
        return LOCAL_SVG_DIR
    return None

# === 渲染参数 ===
FRAME_W, FRAME_H = 200, 100   # 2:1 比例，适配 OttoClaw 240x240 屏幕的 face_area
FPS              = 15          # 采样帧率（每秒 15 帧 → 间隔 66ms）
INTERVAL_MS      = 1000 // FPS
DEFAULT_DURATION_MS = 2000

# 采样比例
SAMPLE_DURATION_RATIO = 1.0

# 每状态有 intro（可选，进入时播放一次）和 loop（必须，无限循环）
# N（notify）移除，OttoClaw 不需要通知状态
STATES = {
    "E": {"loop":  ("E_error.svg", None)},        # 错误：冒烟 + X眼
    "I": {"intro": ("I_idle.svg",  None),         # idle intro：哈欠一次
          "loop":  ("I_doze.svg",  None)},        # idle loop：打盹循环
    "T": {"loop":  ("T_think.svg", None)},        # 思考：左右气泡
    "D": {"loop":  ("D_done.svg",  None)},        # 完成：举花挥手 + 闪光
    "W": {"loop":  ("W_write.svg", None)},        # 写代码：敲键盘 + 数据粒子
}


def rgb_to_rgb565(r: int, g: int, b: int) -> int:
    """24 位 RGB → 16 位 RGB565"""
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


def png_to_rgb_image(png_bytes: bytes) -> Image.Image:
    """PNG → RGB PIL Image，固定到 FRAME_W × FRAME_H"""
    img = Image.open(BytesIO(png_bytes)).convert("RGB")
    if img.size != (FRAME_W, FRAME_H):
        img = img.resize((FRAME_W, FRAME_H), Image.LANCZOS)
    return img


def build_state_palette(frame_imgs: list, n_colors: int = 256) -> Image.Image:
    """把一个状态的所有帧拼成大图，量化得到该状态专属调色板"""
    n = len(frame_imgs)
    if n == 0:
        return None
    combined = Image.new("RGB", (FRAME_W, FRAME_H * n))
    for i, im in enumerate(frame_imgs):
        combined.paste(im, (0, i * FRAME_H))
    return combined.convert("P", palette=Image.Palette.ADAPTIVE, colors=n_colors)


def palette_to_rgb565_bytes(pal_img: Image.Image) -> bytes:
    """从 P 模式图里取出调色板，转成 256×2 字节 RGB565（大端）"""
    pal = pal_img.getpalette() or []
    pal = (pal + [0] * (768 - len(pal)))[:768]
    out = bytearray(256 * 2)
    for i in range(256):
        r, g, b = pal[i * 3], pal[i * 3 + 1], pal[i * 3 + 2]
        c = rgb_to_rgb565(r, g, b)
        out[i * 2]     = (c >> 8) & 0xFF
        out[i * 2 + 1] = c & 0xFF
    return bytes(out)


def rgb_image_to_indices(rgb_img: Image.Image, pal_img: Image.Image) -> bytes:
    """把 RGB 图按给定调色板量化，返回 FRAME_W*FRAME_H 字节索引数组"""
    indexed = rgb_img.quantize(palette=pal_img, dither=Image.Dither.NONE)
    return bytes(indexed.getdata())


def rle_encode(indices: bytes) -> bytes:
    """简单 RLE：连续相同索引 → (count, index) 对。count ∈ [1, 255]"""
    if not indices:
        return b""
    out = bytearray()
    cur = indices[0]
    count = 1
    for b in indices[1:]:
        if b == cur and count < 255:
            count += 1
        else:
            out.append(count)
            out.append(cur)
            cur = b
            count = 1
    out.append(count)
    out.append(cur)
    return bytes(out)


def infer_duration_ms(svg_text: str) -> int:
    """扫 SVG 里所有 animation 声明，取最长时长作为采样窗口"""
    pattern = r'animation\s*:\s*[^;]*?(\d+(?:\.\d+)?)\s*(s|ms)'
    matches = re.findall(pattern, svg_text)
    if not matches:
        return DEFAULT_DURATION_MS
    durations_ms = [
        int(float(v) * 1000) if u == "s" else int(float(v))
        for v, u in matches
    ]
    return max(durations_ms)


def build_html(svg_text: str) -> str:
    """把 SVG inline 进 HTML，去掉 width/height 让其按 viewBox 自适应"""
    svg_inline = re.sub(
        r'(<svg\b[^>]*?)\s+(width|height)="[^"]*"',
        r'\1',
        svg_text,
        count=2,
    )
    return f"""<!DOCTYPE html>
<html><head><style>
  html, body, svg {{
    margin: 0; padding: 0;
    width: 100%; height: 100%;
    display: block;
    background: #ffffff;
  }}
  *, *::before, *::after {{ animation-fill-mode: both !important; }}
</style></head>
<body>{svg_inline}</body></html>"""


def sample_svg_pngs(svg_text: str, duration_ms: int) -> list:
    """精确采样 SVG 动画，用 Web Animations API 暂停 + currentTime 逐帧截图"""
    html = build_html(svg_text)
    n_frames = max(1, duration_ms * FPS // 1000)
    png_frames = []
    with sync_playwright() as p:
        # 自动检测已安装的 Chromium（版本号自动适配）
        import glob as _glob
        _shell_dirs = sorted(_glob.glob(
            os.path.expanduser("~/AppData/Local/ms-playwright/chromium_headless_shell-*")
        ))
        if _shell_dirs:
            _exe = _shell_dirs[-1] + "/chrome-headless-shell-win64/chrome-headless-shell.exe"
        else:
            _chrome_dirs = sorted(_glob.glob(
                os.path.expanduser("~/AppData/Local/ms-playwright/chromium-*")
            ))
            _exe = _chrome_dirs[-1] + "/chrome-win64/chrome.exe" if _chrome_dirs else None
        if _exe and Path(_exe).exists():
            browser = p.chromium.launch(executable_path=_exe)
        else:
            browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": FRAME_W, "height": FRAME_H})
        page.set_content(html, wait_until="networkidle")
        page.wait_for_timeout(100)

        page.evaluate("""() => {
            window.__anims = document.getAnimations();
            window.__anims.forEach(a => {
                a.pause();
                try { a.effect.updateTiming({ fill: 'both' }); } catch (e) {}
            });
        }""")

        for i in range(n_frames):
            t_ms = i * INTERVAL_MS
            page.evaluate("(t) => { window.__anims.forEach(a => { a.currentTime = t; }); }", t_ms)
            page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
            png = page.screenshot()
            png_frames.append(png)
        browser.close()
    return png_frames


def quantize_and_compress(png_frames: list, pal_img: Image.Image) -> list:
    """给定 PNG 帧和一个调色板，量化 + RLE 压缩"""
    out = []
    for png in png_frames:
        rgb = png_to_rgb_image(png)
        idx = rgb_image_to_indices(rgb, pal_img)
        out.append(rle_encode(idx))
    return out


def write_python_data(animations: dict, out_path: Path) -> None:
    """生成 crab_data.py"""
    lines = [
        "# AUTO-GENERATED by build_assets.py — DO NOT EDIT",
        "# OttoClaw 螃蟹动画数据",
        "# 格式：每状态 256 色调色板（512B 大端 RGB565）+ intro/loop 两段 RLE 帧流",
        "",
        f"FRAME_W = {FRAME_W}",
        f"FRAME_H = {FRAME_H}",
        f"FPS = {FPS}",
        f"MS_PER_FRAME = {INTERVAL_MS}",
        "",
        "ANIMATIONS = {",
    ]
    for state, (palette, segments) in animations.items():
        lines.append(f"    {state!r}: {{")
        lines.append(f'        "palette": {palette!r},')
        for seg_name in ("intro", "loop"):
            if seg_name not in segments:
                continue
            lines.append(f'        {seg_name!r}: [')
            for f in segments[seg_name]:
                lines.append(f"            {f!r},")
            lines.append("        ],")
        lines.append("    },")
    lines.append("}")
    lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    svg_dir = find_svg_dir()
    if svg_dir is None:
        print(f"[错误] 找不到 SVG 目录。检查过：\n  {CLACKCLACK_SVG_DIR}\n  {LOCAL_SVG_DIR}", file=sys.stderr)
        print("[提示] 请把 clackclack 的 assets/svg/ 复制到 tools/assets/svg/", file=sys.stderr)
        return 1

    print(f"[SVG 源] {svg_dir}")
    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    raw_bytes_per_frame = FRAME_W * FRAME_H * 2
    animations = {}
    for state, segments_config in STATES.items():
        # 第 1 步：采每个 segment 的 PNG 帧
        segments_pngs = {}
        for seg_name, (fname, duration_override) in segments_config.items():
            svg_path = svg_dir / fname
            if not svg_path.exists():
                print(f"[跳过] {state}.{seg_name}: {svg_path} 不存在")
                continue
            svg_text = svg_path.read_text(encoding="utf-8")
            raw_ms = duration_override or infer_duration_ms(svg_text)
            duration_ms = int(raw_ms * SAMPLE_DURATION_RATIO)
            source = "覆盖" if duration_override else "自动"
            print(f"[{state}.{seg_name}] 采样 {fname}  时长 {duration_ms}ms"
                  f"  ({raw_ms}ms × {SAMPLE_DURATION_RATIO}, {source})...")
            segments_pngs[seg_name] = sample_svg_pngs(svg_text, duration_ms)
            print(f"      → {len(segments_pngs[seg_name])} 帧")

        if not segments_pngs:
            continue

        # 第 2 步：合并所有帧构建统一 256 色调色板
        all_imgs = []
        for pngs in segments_pngs.values():
            all_imgs.extend([png_to_rgb_image(p) for p in pngs])
        pal_img = build_state_palette(all_imgs, n_colors=256)
        palette = palette_to_rgb565_bytes(pal_img)

        # 第 3 步：量化压缩每个 segment
        segments_out = {}
        for seg_name, pngs in segments_pngs.items():
            segments_out[seg_name] = quantize_and_compress(pngs, pal_img)
            seg_bytes = sum(len(f) for f in segments_out[seg_name])
            seg_raw   = len(segments_out[seg_name]) * raw_bytes_per_frame
            print(f"      [{seg_name}]  {len(segments_out[seg_name])} 帧 → {seg_bytes}B"
                  f" (压缩前 {seg_raw}B, 比 {seg_bytes/seg_raw*100:.1f}%)")

        animations[state] = (palette, segments_out)

    out = BUILD_DIR / "crab_data.py"
    write_python_data(animations, out)

    def state_size(palette, segments_out):
        return len(palette) + sum(sum(len(f) for f in fs) for fs in segments_out.values())
    def state_raw(segments_out):
        n = sum(len(fs) for fs in segments_out.values())
        return n * raw_bytes_per_frame
    total_compressed = sum(state_size(p, s) for p, s in animations.values())
    total_raw        = sum(state_raw(s)      for _, s in animations.values())
    print(f"\n输出: {out}")
    print(f"压缩前: {total_raw}  字节 ({total_raw/1024:.1f} KB)")
    print(f"压缩后: {total_compressed}  字节 ({total_compressed/1024:.1f} KB)  ←  {total_compressed/total_raw*100:.1f}% of 原大小")
    return 0


if __name__ == "__main__":
    sys.exit(main())
