#!/usr/bin/env python3
"""news-image-20261125 — front page of THE WORLD TODAY,
Wednesday 25 November 2026.

A pure-stdlib Python program (no Pillow, no network) that draws a
1024x1024 broadsheet front page and writes it to /output/entry.png.
It paints on a flat RGB canvas with a small set of primitives, sets
type with a 5x7 dot font stored as strings of '#' and ' ', and encodes
the PNG by hand (zlib + struct).

Deterministic: no clock, no randomness, fixed iteration order, so two
runs write byte-identical files.

Stories, each checked against reporting published on 25 November 2026:
- Lead: Zelensky confirms Ukraine hit a Russian cargo ship in the Gulf
  of Finland; Russia calls the sea-drone campaign "terrorism"; Norway
  urges caution. (Reuters world news summary, 25 Nov; Kyiv Independent)
- Riyadh: Houthi drones hit the Saudi capital's tallest tower, 11
  wounded — the second strike on it in under a week. (Reuters, 25 Nov)
- NATO: early-warning aircraft to be deployed in Poland after missiles
  landed there during an attack on Ukraine. (25 Nov headlines)
- Hormuz: Iran says three oil tankers were hit by naval mines in the
  Strait of Hormuz. (25 Nov headlines)
- USA: Trump awards the Medal of Freedom to Rudy Giuliani in a private
  Oval Office ceremony. (Reuters / AP, 24-25 Nov)
- Climate: COP31 ends with no deal — the first UN climate summit since
  Copenhagen 2009 to close without an agreement. (Reuters, 24 Nov)
- Cricket: England beat Australia by eight wickets in the 2nd T20I to
  level the five-match series. (25 Nov headlines)
- By the numbers: 700,000 Russian troops killed (new analysis); 11
  wounded in Riyadh; 3 tankers hit; Houthis 60 km from Aden.
"""
import math
import os
import struct
import tempfile
import zlib

W = 1024
H = 1024
MARGIN = 40
INNER = W - 2 * MARGIN

# ---- palette -------------------------------------------------------
PAPER = (248, 244, 233)
INK = (18, 18, 18)
RED = (164, 32, 36)
NAVY = (46, 74, 104)
GREY = (96, 110, 124)
CREAM = (234, 228, 212)
SKY = (176, 196, 210)
SEA = (52, 96, 128)
DEEP = (34, 58, 82)
COAL = (40, 48, 58)
ASH = (128, 128, 120)
GOLD = (200, 148, 0)
GREEN = (48, 126, 52)
ORANGE = (216, 112, 32)
FLAME = (234, 198, 66)
SNOW = (250, 248, 242)
GRID = (198, 204, 208)
EUBLUE = (36, 54, 118)


# ---- canvas --------------------------------------------------------
class Canvas:
    """Flat RGB buffer with a handful of drawing verbs."""

    def __init__(self, w, h, bg):
        self.w = w
        self.h = h
        self.buf = bytearray(bytes(bg) * (w * h))

    def px(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            o = (y * self.w + x) * 3
            self.buf[o:o + 3] = bytes(c)

    def box(self, x, y, w, h, c):
        x0 = max(x, 0)
        y0 = max(y, 0)
        x1 = min(x + w, self.w)
        y1 = min(y + h, self.h)
        if x1 <= x0 or y1 <= y0:
            return
        row = bytes(c) * (x1 - x0)
        for yy in range(y0, y1):
            o = (yy * self.w + x0) * 3
            self.buf[o:o + len(row)] = row

    def frame(self, x, y, w, h, c, t=1):
        self.box(x, y, w, t, c)
        self.box(x, y + h - t, w, t, c)
        self.box(x, y, t, h, c)
        self.box(x + w - t, y, t, h, c)

    def hline(self, x, y, n, c):
        self.box(x, y, n, 1, c)

    def vline(self, x, y, n, c):
        self.box(x, y, 1, n, c)

    def seg(self, x0, y0, x1, y1, c, t=1):
        """Bresenham line, stamped as t x t squares."""
        dx, dy = x1 - x0, y1 - y0
        sx = 1 if dx > 0 else -1
        sy = 1 if dy > 0 else -1
        dx, dy = abs(dx), abs(dy)
        half = t // 2
        if dx >= dy:
            err = 2 * dy - dx
            x, y = x0, y0
            for _ in range(dx + 1):
                self.box(x - half, y - half, t, t, c)
                if err >= 0:
                    y += sy
                    err -= 2 * dx
                err += 2 * dy
                x += sx
        else:
            err = 2 * dx - dy
            x, y = x0, y0
            for _ in range(dy + 1):
                self.box(x - half, y - half, t, t, c)
                if err >= 0:
                    x += sx
                    err -= 2 * dy
                err += 2 * dx
                y += sy

    def circle(self, cx, cy, r, c):
        for dy in range(-r, r + 1):
            half = int(math.sqrt(max(0, r * r - dy * dy)))
            self.hline(cx - half, cy + dy, 2 * half + 1, c)

    def ring(self, cx, cy, r, c, t=2):
        for i in range(360):
            a = 2.0 * math.pi * i / 360
            for k in range(t):
                rr = r - k
                self.px(int(cx + rr * math.cos(a)), int(cy + rr * math.sin(a)), c)

    def poly(self, pts, c):
        """Scanline fill of a simple polygon."""
        edges = []
        n = len(pts)
        for i in range(n):
            ax, ay = pts[i]
            bx, by = pts[(i + 1) % n]
            if ay != by:
                edges.append((ax, ay, bx, by))
        top = min(p[1] for p in pts)
        bot = max(p[1] for p in pts)
        for y in range(top, bot + 1):
            cuts = []
            for ax, ay, bx, by in edges:
                if (ay <= y < by) or (by <= y < ay):
                    cuts.append(ax + (y - ay) * (bx - ax) / (by - ay))
            cuts.sort()
            for j in range(0, len(cuts) - 1, 2):
                xa, xb = int(cuts[j]), int(cuts[j + 1])
                self.hline(xa, y, xb - xa + 1, c)

    def triangle(self, x0, y0, x1, y1, x2, y2, c):
        self.poly([(x0, y0), (x1, y1), (x2, y2)], c)


# ---- 5x7 dot font --------------------------------------------------
# Each glyph is seven strings of five cells; '1' is ink, '0' is blank.
FONT = {
    'A': ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    'B': ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    'C': ("01110", "10001", "10000", "10000", "10000", "10001", "01110"),
    'D': ("11100", "10010", "10001", "10001", "10001", "10010", "11100"),
    'E': ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    'F': ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    'G': ("01110", "10001", "10000", "10111", "10001", "10001", "01111"),
    'H': ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    'I': ("01110", "00100", "00100", "00100", "00100", "00100", "01110"),
    'J': ("00111", "00010", "00010", "00010", "00010", "10010", "01100"),
    'K': ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    'L': ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    'M': ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    'N': ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    'O': ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    'P': ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    'Q': ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    'R': ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    'S': ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    'T': ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    'U': ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    'V': ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    'W': ("10001", "10001", "10001", "10101", "10101", "10101", "01010"),
    'X': ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    'Y': ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    'Z': ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    'a': ("00000", "00000", "01110", "00001", "01111", "10001", "01111"),
    'b': ("10000", "10000", "11110", "10001", "10001", "10001", "11110"),
    'c': ("00000", "00000", "01110", "10000", "10000", "10001", "01110"),
    'd': ("00001", "00001", "01111", "10001", "10001", "10001", "01111"),
    'e': ("00000", "00000", "01110", "10001", "11111", "10000", "01110"),
    'f': ("00110", "01001", "01000", "11110", "01000", "01000", "01000"),
    'g': ("00000", "01111", "10001", "10001", "01111", "00001", "01110"),
    'h': ("10000", "10000", "11110", "10001", "10001", "10001", "10001"),
    'i': ("00100", "00000", "01100", "00100", "00100", "00100", "01110"),
    'j': ("00010", "00000", "00110", "00010", "00010", "10010", "01100"),
    'k': ("10000", "10000", "10010", "10100", "11000", "10100", "10010"),
    'l': ("01100", "00100", "00100", "00100", "00100", "00100", "01110"),
    'm': ("00000", "00000", "11010", "10101", "10101", "10101", "10101"),
    'n': ("00000", "00000", "11110", "10001", "10001", "10001", "10001"),
    'o': ("00000", "00000", "01110", "10001", "10001", "10001", "01110"),
    'p': ("00000", "00000", "11110", "10001", "10001", "11110", "10000"),
    'q': ("00000", "00000", "01111", "10001", "10001", "01111", "00001"),
    'r': ("00000", "00000", "10110", "11001", "10000", "10000", "10000"),
    's': ("00000", "00000", "01111", "10000", "01110", "00001", "11110"),
    't': ("01000", "01000", "11110", "01000", "01000", "01001", "00110"),
    'u': ("00000", "00000", "10001", "10001", "10001", "10011", "01101"),
    'v': ("00000", "00000", "10001", "10001", "10001", "01010", "00100"),
    'w': ("00000", "00000", "10001", "10101", "10101", "10101", "01010"),
    'x': ("00000", "00000", "10001", "01010", "00100", "01010", "10001"),
    'y': ("00000", "00000", "10001", "10001", "01111", "00001", "01110"),
    'z': ("00000", "00000", "11111", "00010", "00100", "01000", "11111"),
    '0': ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    '1': ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    '2': ("01110", "10001", "00001", "00110", "01000", "10000", "11111"),
    '3': ("11111", "00010", "00100", "00010", "00001", "10001", "01110"),
    '4': ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    '5': ("11111", "10000", "11110", "00001", "00001", "10001", "01110"),
    '6': ("00110", "01000", "10000", "11110", "10001", "10001", "01110"),
    '7': ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    '8': ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    '9': ("01110", "10001", "10001", "01111", "00001", "00010", "01100"),
    ' ': ("00000", "00000", "00000", "00000", "00000", "00000", "00000"),
    '.': ("00000", "00000", "00000", "00000", "00000", "01100", "01100"),
    ',': ("00000", "00000", "00000", "00000", "01100", "00100", "01000"),
    ';': ("00000", "01100", "01100", "00000", "01100", "00100", "01000"),
    "'": ("00100", "00100", "01000", "00000", "00000", "00000", "00000"),
    '-': ("00000", "00000", "00000", "01110", "00000", "00000", "00000"),
    ':': ("00000", "01100", "01100", "00000", "01100", "01100", "00000"),
    '!': ("00100", "00100", "00100", "00100", "00100", "00000", "00100"),
    '?': ("01110", "10001", "00001", "00110", "00100", "00000", "00100"),
    '(': ("00010", "00100", "01000", "01000", "01000", "00100", "00010"),
    ')': ("01000", "00100", "00010", "00010", "00010", "00100", "01000"),
    '/': ("00001", "00010", "00010", "00100", "01000", "01000", "10000"),
    '%': ("11001", "11010", "00010", "00100", "01000", "01011", "10011"),
    '+': ("00000", "00100", "00100", "01110", "00100", "00100", "00000"),
    '=': ("00000", "00000", "11111", "00000", "11111", "00000", "00000"),
    '"': ("01010", "01010", "00000", "00000", "00000", "00000", "00000"),
}
EMPTY = ("00000", "00000", "00000", "00000", "00000", "00000", "00000")
ADV = 6   # cell advance in font units (5 dots + 1 gap)
ROWS = 7


def text_w(s, scale):
    """Width in pixels of `s` at `scale`, no trailing gap."""
    return len(s) * ADV * scale - scale if s else 0


def draw_text(cv, x, y, s, scale, c, bold=False):
    """Set `s` with its top-left corner at (x, y)."""
    pen = x
    for ch in s:
        rows = FONT.get(ch, EMPTY)
        for r in range(ROWS):
            row = rows[r]
            for col in range(5):
                if row[col] == '1':
                    cv.box(pen + col * scale, y + r * scale, scale, scale, c)
                    if bold:
                        cv.box(pen + col * scale + 1, y + r * scale,
                               scale, scale, c)
        pen += ADV * scale
    return pen - x - scale


def draw_centred(cv, cx, y, s, scale, c, bold=False):
    draw_text(cv, cx - text_w(s, scale) // 2, y, s, scale, c, bold)


def wrap(s, scale, maxw):
    """Greedy word wrap of `s` to lines no wider than maxw."""
    lines = []
    for para in s.split('\n'):
        words = para.split(' ')
        cur = ''
        for word in words:
            trial = word if not cur else cur + ' ' + word
            if text_w(trial, scale) <= maxw or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
    return lines


def draw_para(cv, x, y, s, scale, maxw, c, leading, bold=False):
    """Set a wrapped paragraph; return the y just below its last line."""
    for line in wrap(s, scale, maxw):
        draw_text(cv, x, y, line, scale, c, bold)
        y += leading
    return y


# ---- small scene helpers -------------------------------------------
def flame(cv, x, y, w, h):
    cv.triangle(x, y + h, x + w // 2, y, x + w, y + h, ORANGE)
    cv.triangle(x + w // 4, y + h, x + w // 2, y + h // 3,
                x + 3 * w // 4, y + h, FLAME)


def smoke(cv, x, y, r, c=ASH):
    cv.circle(x, y, r, c)
    cv.circle(x + r, y - r // 2, int(r * 0.8), c)
    cv.circle(x - r, y - r // 2, int(r * 0.7), c)


def tile(cv, x, y, s, c):
    cv.box(x, y, s, s, c)
    cv.frame(x, y, s, s, INK, 2)


# ---- 72x72 story pictures ------------------------------------------
def pic_tower(cv, x, y, s):
    tile(cv, x, y, s, SKY)
    # Riyadh's tallest tower: stepped shaft, crown, antenna
    cv.box(x + 26, y + 18, 20, 44, COAL)
    cv.box(x + 30, y + 12, 12, 6, COAL)
    cv.vline(x + 35, y + 4, 8, INK)
    cv.circle(x + 35, y + 3, 2, RED)
    for wy in (24, 32, 40, 48):
        cv.box(x + 30, y + wy, 12, 3, FLAME)
    # fire and smoke at the crown
    flame(cv, x + 24, y + 2, 12, 14)
    smoke(cv, x + 48, y + 8, 5)
    # neighbouring blocks
    cv.box(x + 6, y + 44, 14, 18, GREY)
    cv.box(x + 52, y + 48, 14, 14, GREY)
    cv.box(x, y + 62, s, 10, DEEP)


def pic_awacs(cv, x, y, s):
    tile(cv, x, y, s, SKY)
    # early-warning jet seen from the side, radar disc on its back
    cv.circle(x + 36, y + 22, 9, SNOW)
    cv.frame(x + 27, y + 13, 18, 18, INK, 1)
    cv.vline(x + 36, y + 31, 4, INK)
    cv.poly([(x + 8, y + 40), (x + 62, y + 38), (x + 66, y + 44),
             (x + 10, y + 48)], SNOW)
    cv.frame(x + 8, y + 40, 58, 8, INK, 1)
    cv.poly([(x + 30, y + 40), (x + 44, y + 40), (x + 38, y + 56),
             (x + 30, y + 56)], SNOW)
    cv.poly([(x + 56, y + 38), (x + 62, y + 38), (x + 62, y + 28),
             (x + 58, y + 28)], SNOW)
    cv.circle(x + 14, y + 43, 2, RED)
    cv.circle(x + 20, y + 43, 2, RED)
    # contrail
    cv.hline(x + 2, y + 52, 12, SNOW)
    cv.hline(x + 2, y + 56, 8, SNOW)
    # ground line
    cv.box(x, y + 62, s, 10, CREAM)


def pic_mine(cv, x, y, s):
    tile(cv, x, y, s, SEA)
    cv.box(x + 3, y + s - 22, s - 6, 19, DEEP)
    cv.hline(x + 6, y + s - 14, s - 12, SNOW)
    cv.hline(x + 10, y + s - 8, s - 24, SNOW)
    # tanker hull with stacked boxes
    cv.poly([(x + 8, y + 38), (x + s - 8, y + 38),
             (x + s - 16, y + 54), (x + 16, y + 54)], COAL)
    cv.box(x + 12, y + 26, 12, 12, RED)
    cv.box(x + 26, y + 26, 12, 12, GOLD)
    cv.box(x + 40, y + 26, 12, 12, SNOW)
    cv.box(x + 52, y + 16, 8, 10, COAL)
    flame(cv, x + 14, y + 6, 12, 18)
    smoke(cv, x + 56, y + 8, 5)
    # naval mine: spiked disc riding low in the water
    mx, my = x + 58, y + s - 26
    cv.circle(mx, my, 6, INK)
    for dx, dy in ((-7, 0), (7, 0), (0, -7), (0, 7), (-5, -5), (5, -5),
                   (-5, 5), (5, 5)):
        cv.seg(mx, my, mx + dx, my + dy, INK, 2)


def pic_medal(cv, x, y, s):
    tile(cv, x, y, s, CREAM)
    # ribbon
    cv.poly([(x + 26, y + 8), (x + 46, y + 8), (x + 40, y + 30),
             (x + 32, y + 30)], RED)
    cv.poly([(x + 32, y + 8), (x + 40, y + 8), (x + 36, y + 30)], NAVY)
    # the medal itself
    cv.circle(x + 36, y + 46, 16, GOLD)
    cv.ring(x + 36, y + 46, 16, INK, 2)
    cv.ring(x + 36, y + 46, 11, INK, 1)
    draw_centred(cv, x + 36, y + 40, "1", 2, INK, bold=True)
    # sparkle
    cv.seg(x + 58, y + 8, x + 62, y + 12, GOLD, 2)
    cv.seg(x + 62, y + 8, x + 58, y + 12, GOLD, 2)


def pic_globe(cv, x, y, s):
    tile(cv, x, y, s, EUBLUE)
    cx, cy = x + s // 2, y + s // 2
    cv.circle(cx, cy, 24, GREEN)
    cv.ring(cx, cy, 24, SNOW, 2)
    # meridians and equator
    cv.ring(cx, cy, 12, SNOW, 1)
    cv.hline(cx - 24, cy, 48, SNOW)
    cv.vline(cx, cy - 24, 48, SNOW)
    # the crack: no deal
    cv.seg(cx - 18, cy + 20, cx + 20, cy - 18, RED, 4)


def pic_bat(cv, x, y, s):
    tile(cv, x, y, s, CREAM)
    # cricket bat, angled, with a red ball
    cv.poly([(x + 22, y + 14), (x + 34, y + 10), (x + 52, y + 46),
             (x + 40, y + 50)], NAVY)
    cv.seg(x + 22, y + 14, x + 14, y + 8, INK, 3)
    cv.box(x + 12, y + 4, 6, 6, INK)
    cv.circle(x + 54, y + 58, 9, RED)
    cv.ring(x + 54, y + 58, 9, INK, 1)
    cv.seg(x + 48, y + 54, x + 60, y + 62, SNOW, 1)
    # stumps
    for sx in (14, 20, 26):
        cv.vline(x + sx, y + 56, 12, GOLD)
    cv.hline(x + 14, y + 54, 14, GOLD)


# ---- lead picture ----------------------------------------------------
def lead_art(cv, x, y, w, h):
    """A Russian cargo ship burning in the Gulf of Finland, a Ukrainian
    sea drone closing in, caption strip below."""
    cv.box(x, y, w, h, SKY)
    cv.frame(x, y, w, h, INK, 2)
    # sun
    cv.circle(x + w - 90, y + 30, 16, FLAME)
    cv.ring(x + w - 90, y + 30, 16, GOLD, 2)
    # sea
    sea_top = y + 62
    cv.box(x, sea_top, w, h - 62 - 26, SEA)
    for wy in (sea_top + 12, sea_top + 30, sea_top + 48):
        cv.hline(x + 8, wy, w - 16, SNOW)
    cv.hline(x + 40, sea_top + 66, w - 80, SNOW)

    # --- the cargo ship, centre-left
    sx, sy = x + 60, sea_top - 8
    cv.poly([(sx, sy + 34), (sx + 330, sy + 34), (sx + 310, sy + 58),
             (sx + 20, sy + 58)], COAL)
    cv.frame(sx, sy + 34, 330, 24, INK, 1)
    for i, c in enumerate((RED, GOLD, SNOW, NAVY, RED, GOLD)):
        cv.box(sx + 16 + i * 52, sy + 8, 46, 26, c)
        cv.frame(sx + 16 + i * 52, sy + 8, 46, 26, INK, 1)
    cv.box(sx + 330, sy + 6, 26, 28, COAL)
    cv.box(sx + 338, sy - 4, 10, 10, COAL)
    # fire amidships and smoke
    flame(cv, sx + 150, sy - 22, 34, 40)
    flame(cv, sx + 210, sy - 12, 22, 28)
    smoke(cv, sx + 170, sy - 30, 12)
    smoke(cv, sx + 230, sy - 34, 9)

    # --- the sea drone, low and fast on the right
    dx, dy = x + w - 260, sea_top + 44
    cv.box(dx, dy, 46, 10, INK)
    cv.triangle(dx + 46, dy, dx + 62, dy + 5, dx + 46, dy + 10, INK)
    cv.vline(dx + 22, dy - 10, 10, INK)
    cv.circle(dx + 22, dy - 12, 3, RED)
    cv.hline(dx - 60, dy + 4, 56, SNOW)
    cv.hline(dx - 40, dy + 12, 36, SNOW)
    draw_text(cv, dx - 8, dy - 26, "DRONE", 2, SNOW, bold=True)

    # --- caption strip
    cv.box(x, y + h - 26, w, 26, INK)
    draw_centred(cv, x + w // 2, y + h - 21,
                 "A Russian cargo ship burns in the Gulf of Finland.",
                 2, SNOW)


# ---- stories ----------------------------------------------------------
# (kicker, body, picture painter)
CARDS = [
    ("RIYADH: TOWER HIT",
     "Houthi drones strike the Saudi capital's tallest tower, wounding 11 - the second hit in a week.",
     pic_tower),
    ("NATO: EYES ON POLAND",
     "NATO to deploy early-warning aircraft in Poland after missiles land in an attack on Ukraine.",
     pic_awacs),
    ("HORMUZ: THREE TANKERS HIT",
     "Iran says three oil tankers were struck by naval mines in the Strait of Hormuz.",
     pic_mine),
    ("USA: MEDAL FOR GIULIANI",
     "Trump gives the Medal of Freedom to Rudy Giuliani in a private Oval Office ceremony.",
     pic_medal),
    ("CLIMATE: COP31 ENDS IN FAILURE",
     "The UN climate summit closes with no deal - the first failed COP since 2009.",
     pic_globe),
    ("CRICKET: ENGLAND LEVEL SERIES",
     "England beat Australia by eight wickets in the second T20 to level the five-match series.",
     pic_bat),
    (None, None, None),
]

NUMBERS = [
    ("700,000", "Russian troops killed"),
    ("11", "wounded in Riyadh strike"),
    ("3", "tankers hit in Hormuz"),
    ("60 km", "Houthis from Aden"),
]


def story_card(cv, x, y, w, h, kicker, body, painter):
    painter(cv, x, y, 72)
    tx = x + 72 + 10
    tw = w - 72 - 10
    after = draw_para(cv, tx, y + 1, kicker, 3, tw, INK, 23, bold=True)
    draw_para(cv, tx, after + 2, body, 2, tw, INK, 15)


def numbers_panel(cv, x, y, w, h):
    cv.box(x, y, w, h, CREAM)
    cv.frame(x, y, w, h, INK, 2)
    draw_text(cv, x + 12, y + 8, "BY THE NUMBERS", 3, RED, bold=True)
    ny = y + 30
    for figure, label in NUMBERS:
        fw = draw_text(cv, x + 12, ny, figure, 2, RED, bold=True)
        draw_text(cv, x + 12 + fw + 10, ny, label, 2, INK)
        ny += 15


# ---- compose ---------------------------------------------------------
def build():
    cv = Canvas(W, H, PAPER)

    # masthead
    draw_centred(cv, W // 2, 24, "THE WORLD TODAY", 10, INK, bold=True)
    cv.box(MARGIN, 104, INNER, 4, INK)
    cv.box(MARGIN, 112, INNER, 1, INK)

    # date line
    draw_centred(cv, W // 2, 124, "WEDNESDAY 25 NOVEMBER 2026", 4, RED,
                 bold=True)
    draw_text(cv, MARGIN, 130, "WORLD EDITION", 2, GREY)
    tag = "NO. 25 NOV"
    draw_text(cv, W - MARGIN - text_w(tag, 2), 130, tag, 2, GREY)

    # lead
    draw_centred(cv, W // 2, 164, "THE WAR AT SEA", 3, RED, bold=True)
    draw_centred(cv, W // 2, 192, "KYIV OWNS THE", 9, INK, bold=True)
    draw_centred(cv, W // 2, 256, "SEA STRIKES", 9, RED, bold=True)
    draw_para(cv, MARGIN, 330,
              "Zelensky confirms Ukraine hit a Russian cargo ship in the "
              "Gulf of Finland. Moscow calls the drone campaign "
              "\"terrorism\"; Norway urges caution.",
              3, INNER, INK, 26)

    # lead picture
    lead_art(cv, MARGIN, 416, INNER, 142)
    cv.box(MARGIN, 570, INNER, 2, INK)

    # supporting stories: two columns, four rows
    col_w = (INNER - 24) // 2
    row_h = 96
    grid_y = 580
    for idx, (kicker, body, painter) in enumerate(CARDS):
        col = idx % 2
        row = idx // 2
        bx = MARGIN + col * (col_w + 24)
        by = grid_y + row * row_h
        if kicker is None:
            numbers_panel(cv, bx, by, col_w, row_h - 4)
        else:
            story_card(cv, bx, by, col_w, row_h - 4, kicker, body, painter)

    # footer
    cv.box(MARGIN, 974, INNER, 2, INK)
    draw_centred(cv, W // 2, 982,
                 "THE WORLD TODAY - WEDNESDAY 25 NOVEMBER 2026", 2, INK,
                 bold=True)
    return cv


# ---- PNG writer ------------------------------------------------------
def _chunk(kind, payload):
    body = kind + payload
    return (struct.pack('>I', len(payload)) + body +
            struct.pack('>I', zlib.crc32(body) & 0xFFFFFFFF))


def encode_png(cv):
    scan = bytearray()
    for y in range(H):
        scan.append(0)
        start = y * W * 3
        scan += cv.buf[start:start + W * 3]
    header = struct.pack('>IIBBBBB', W, H, 8, 2, 0, 0, 0)
    png = b'\x89PNG\r\n\x1a\n'
    png += _chunk(b'IHDR', header)
    png += _chunk(b'IDAT', zlib.compress(bytes(scan), 9))
    png += _chunk(b'IEND', b'')
    return png


# ---- entry point -----------------------------------------------------
def main():
    outdir = os.environ.get('MAKEFUN_OUTPUT_DIR', '/output')
    os.makedirs(outdir, exist_ok=True)
    target = os.path.join(outdir, 'entry.png')
    data = encode_png(build())
    fd, tmp = tempfile.mkstemp(dir=outdir, prefix='.entry-', suffix='.png')
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
        os.chmod(tmp, 0o644)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


if __name__ == '__main__':
    main()
