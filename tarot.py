#!/usr/bin/env python3
"""PIXEL TAROT — 78枚(大アルカナ22+小アルカナ56)を手続きで描く。

カード 64x112 / 絵の窓 54x78。描き方は pixel-fantasy と同じ「面で描く→層ごとに外周アウトライン」。
小アルカナの数札(2〜10)はマルセイユ式=スートの記号を並べる。絵札とエースは絵。
出力: out/cards/*.png(1x) out/cards4x/*.png(4x) out/sheet_major.png out/sheet_minor.png
"""
import math
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent / "out"

# ---- palette ---------------------------------------------------------------
K = (26, 19, 33)
NIGHT = (20, 22, 50); NAVY = (32, 36, 78); BLUE = (52, 84, 170); SKY = (102, 158, 230); PALE = (178, 214, 245)
PURD = (62, 34, 90); PUR = (116, 62, 158); LIL = (178, 132, 214)
REDD = (124, 28, 44); RED = (206, 52, 52); PINK = (240, 140, 150)
ORAD = (170, 78, 30); ORANGE = (232, 124, 40)
GOLDD = (156, 98, 26); GOLD = (222, 166, 40); YEL = (250, 224, 90); CREAM = (250, 240, 210)
GRND = (30, 84, 52); GRN = (58, 140, 70); LIME = (146, 206, 80)
BRND = (84, 50, 34); BRN = (140, 88, 50); TAN = (204, 160, 110)
SKIN = (246, 196, 160); SKSH = (212, 146, 116)
GRYD = (70, 70, 88); GRY = (128, 130, 148); GRYL = (192, 194, 206); WHT = (248, 248, 250)
TEALD = (24, 96, 120); TEAL = (40, 150, 170); TEALL = (120, 210, 220)
BLK = (44, 38, 54)

SH = {RED: REDD, BLUE: NAVY, SKY: BLUE, WHT: GRYL, GRYL: GRY, GRY: GRYD, PUR: PURD, LIL: PUR,
      GRN: GRND, LIME: GRN, ORANGE: ORAD, GOLD: GOLDD, YEL: GOLD, BRN: BRND, TAN: BRN, PALE: SKY,
      CREAM: TAN, BLK: K, GRYD: BLK, TEAL: TEALD, TEALL: TEAL, PINK: RED, NAVY: NIGHT, SKIN: SKSH,
      REDD: K, PURD: K, GRND: K, NIGHT: K, BRND: K, GOLDD: BRND, ORAD: BRND, SKSH: BRN}


def sh(c):
    return SH.get(c, K)


AW, AH = 54, 78
CW, CH = 64, 112


# ---- drawing ---------------------------------------------------------------
class L:
    def __init__(s, w=AW, h=AH):
        s.w, s.h = w, h
        s.im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        s.d = ImageDraw.Draw(s.im)

    def px(s, x, y, c):
        x, y = int(round(x)), int(round(y))
        if 0 <= x < s.w and 0 <= y < s.h:
            s.im.putpixel((x, y), c + (255,))

    def rect(s, x0, y0, x1, y1, c):
        s.d.rectangle([min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)], fill=c)

    def ell(s, cx, cy, rx, ry, c):
        s.d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=c)

    def ring(s, cx, cy, rx, ry, c):
        s.d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], outline=c)

    def poly(s, pts, c):
        s.d.polygon([tuple(map(round, p)) for p in pts], fill=c)

    def line(s, pts, c, w=1):
        s.d.line([tuple(map(round, p)) for p in pts], fill=c, width=w)


def outline(im, col=K):
    a = np.array(im)
    al = a[..., 3] > 0
    n = np.zeros_like(al)
    n[1:] |= al[:-1]; n[:-1] |= al[1:]; n[:, 1:] |= al[:, :-1]; n[:, :-1] |= al[:, 1:]
    a[n & ~al] = col + (255,)
    return Image.fromarray(a)


class Scene:
    def __init__(s):
        s.bg = L()
        s.layers = []

    def layer(s, ol=True):
        l = L()
        s.layers.append((l, ol))
        return l

    def render(s):
        im = s.bg.im.copy()
        for l, ol in s.layers:
            im.alpha_composite(outline(l.im) if ol else l.im)
        return im


def bands(l, spec, x0=0, x1=AW - 1, dither=True):
    """spec=[(y,color),...] 上から。境界1行を市松でぼかす。"""
    for i, (y0, c) in enumerate(spec):
        y1 = spec[i + 1][0] - 1 if i + 1 < len(spec) else l.h - 1
        l.rect(x0, y0, x1, y1, c)
    if dither:
        for i in range(1, len(spec)):
            y0, _ = spec[i]
            pc = spec[i - 1][1]
            for x in range(x0, x1 + 1):
                if (x + y0) % 2 == 0:
                    l.px(x, y0, pc)


def stars(l, n, seed, y1=40, cols=(WHT, PALE)):
    r = random.Random(seed)
    for i in range(n):
        x, y = r.randrange(1, AW - 1), r.randrange(1, y1)
        l.px(x, y, cols[i % len(cols)])


def cloud(l, cx, cy, w, c=WHT, c2=GRYL):
    l.ell(cx, cy + 1, w, 3, c2)
    l.ell(cx - w // 2, cy, w // 2, 3, c)
    l.ell(cx + w // 3, cy - 1, w // 2 + 1, 3, c)
    l.ell(cx, cy - 2, w // 3 + 1, 3, c)


def mountains(l, y, peaks, c=GRY, snow=WHT):
    for (px_, h, w) in peaks:
        l.poly([(px_ - w, y), (px_, y - h), (px_ + w, y)], c)
        l.poly([(px_ - w * 0.3, y - h * 0.7), (px_, y - h), (px_ + w * 0.3, y - h * 0.7)], snow)


def sun(l, cx, cy, r, rays=True, face=False, c=YEL, rim=GOLD):
    if rays:
        for i in range(16):
            a = i * math.pi / 8
            rr = r + (5 if i % 2 == 0 else 3)
            l.line([(cx + math.cos(a) * (r - 1), cy + math.sin(a) * (r - 1)),
                    (cx + math.cos(a) * rr, cy + math.sin(a) * rr)], rim if i % 2 else c, 1)
    l.ell(cx, cy, r, r, rim)
    l.ell(cx, cy, r - 1, r - 1, c)
    if face:
        l.px(cx - 2, cy - 1, GOLDD); l.px(cx + 2, cy - 1, GOLDD)
        l.line([(cx - 1, cy + 2), (cx + 1, cy + 2)], GOLDD)


def moon_crescent(l, cx, cy, r, c=YEL, bgc=None):
    l.ell(cx, cy, r, r, c)
    if bgc:
        l.ell(cx + r // 2 + 1, cy - 1, r, r, bgc)


def lemniscate(l, cx, cy, c=GOLD):
    for dx, dy in [(-3, 0), (-2, -1), (-1, -1), (-2, 1), (-1, 1), (0, 0), (1, -1), (2, -1), (1, 1), (2, 1), (3, 0)]:
        l.px(cx + dx, cy + dy, c)


def pillar(l, x, y0, y1, c, cap=None):
    l.rect(x, y0, x + 5, y1, c)
    l.rect(x + 4, y0, x + 5, y1, sh(c))
    cap = cap or c
    l.rect(x - 1, y0, x + 6, y0 + 1, cap)
    l.rect(x - 1, y1 - 1, x + 6, y1, cap)


# ---- creatures --------------------------------------------------------------
def figure(l, cx, fy, robe, *, hair=BRN, skin=SKIN, head=None, lh=None, rh=None, seated=False,
           sleeve=None, trim=None, beard=None, cape=None, longhair=False, legs=None, halo=None, eyes=K):
    """正面向きの人。lh/rh は「絵で見て左/右の手」の座標。戻り値に頭/肩位置。"""
    H = 30 if not seated else 25
    hy = fy - H + 3
    sy = hy + 4
    sleeve = sleeve or sh(robe)
    if halo:
        l.ell(cx, hy, 5, 5, halo)
    if cape:
        l.poly([(cx - 5, sy), (cx + 5, sy), (cx + 9, fy), (cx - 9, fy)], cape)
        l.poly([(cx + 3, sy), (cx + 5, sy), (cx + 9, fy), (cx + 5, fy)], sh(cape))
    if longhair:
        l.rect(cx - 4, hy - 2, cx + 4, sy + 4, hair)
    rb = fy if not legs else fy - 8
    if seated:
        l.poly([(cx - 4, sy), (cx + 4, sy), (cx + 5, sy + 9), (cx - 5, sy + 9)], robe)
        l.rect(cx - 6, sy + 9, cx + 6, rb, robe)
        l.poly([(cx + 2, sy), (cx + 4, sy), (cx + 5, sy + 9), (cx + 3, sy + 9)], sh(robe))
        l.rect(cx + 4, sy + 9, cx + 6, rb, sh(robe))
        l.line([(cx - 6, sy + 12), (cx + 6, sy + 12)], sh(robe))
    else:
        l.poly([(cx - 4, sy), (cx + 4, sy), (cx + 6, rb), (cx - 6, rb)], robe)
        l.poly([(cx + 2, sy + 1), (cx + 4, sy), (cx + 6, rb), (cx + 3, rb)], sh(robe))
    if legs:
        l.rect(cx - 3, rb, cx - 2, fy, legs)
        l.rect(cx + 2, rb, cx + 3, fy, legs)
    if trim:
        l.rect(cx - 4, sy + 7, cx + 4, sy + 7, trim)
        l.line([(cx, sy), (cx, sy + 2)], trim)
    # head
    l.ell(cx, hy, 3, 3, skin)
    if hair:
        l.rect(cx - 3, hy - 3, cx + 3, hy - 2, hair)
        l.px(cx - 3, hy - 1, hair); l.px(cx + 3, hy - 1, hair)
        if longhair:
            l.rect(cx - 4, hy - 1, cx - 3, sy + 4, hair)
            l.rect(cx + 3, hy - 1, cx + 4, sy + 4, hair)
    if eyes:
        l.px(cx - 1, hy, eyes); l.px(cx + 1, hy, eyes)
    if beard:
        l.poly([(cx - 3, hy + 1), (cx + 3, hy + 1), (cx + 2, hy + 5), (cx, hy + 7), (cx - 2, hy + 5)], beard)
        l.px(cx, hy + 2, sh(beard))
    lh = lh or (cx - 6, sy + 10)
    rh = rh or (cx + 6, sy + 10)
    for shx, (hx, hy2) in ((cx - 4, lh), (cx + 4, rh)):
        l.line([(shx, sy + 1), (hx, hy2)], sleeve, 2)
        l.rect(hx, hy2, hx + 1, hy2 + 1, skin)
    if head:
        headwear(l, head, cx, hy)
    return {"hy": hy, "sy": sy, "lh": lh, "rh": rh}


def headwear(l, kind, cx, hy):
    if kind == "crown":
        l.rect(cx - 3, hy - 4, cx + 3, hy - 3, GOLD)
        for x in (cx - 3, cx, cx + 3):
            l.px(x, hy - 5, GOLD)
        l.px(cx, hy - 4, RED)
    elif kind == "qcrown":
        l.rect(cx - 3, hy - 4, cx + 3, hy - 3, GOLD)
        for x in (cx - 3, cx - 1, cx + 1, cx + 3):
            l.px(x, hy - 5, GOLD)
        l.px(cx, hy - 6, YEL)
    elif kind == "mitre":
        l.poly([(cx - 3, hy - 2), (cx + 3, hy - 2), (cx + 2, hy - 8), (cx, hy - 10), (cx - 2, hy - 8)], GOLD)
        for y in (hy - 4, hy - 7):
            l.line([(cx - 2, y), (cx + 2, y)], GOLDD)
    elif kind == "moon":
        l.px(cx - 3, hy - 5, WHT); l.px(cx - 2, hy - 4, WHT)
        l.px(cx + 3, hy - 5, WHT); l.px(cx + 2, hy - 4, WHT)
        l.ell(cx, hy - 5, 1, 1, WHT)
    elif kind == "horns":
        for sgn in (-1, 1):
            l.line([(cx + 2 * sgn, hy - 3), (cx + 4 * sgn, hy - 5), (cx + 4 * sgn, hy - 7)], GRYL)
    elif kind == "stars":
        for i in range(7):
            a = math.pi + i * math.pi / 6
            l.px(cx + math.cos(a) * 5, hy - 1 + math.sin(a) * 5, YEL)
    elif kind == "wreath":
        l.line([(cx - 3, hy - 3), (cx + 3, hy - 3)], GRN)
        l.px(cx - 2, hy - 4, LIME); l.px(cx + 2, hy - 4, LIME); l.px(cx, hy - 4, RED)
    elif kind == "helmet":
        l.rect(cx - 3, hy - 4, cx + 3, hy - 2, GRYL)
        l.rect(cx + 2, hy - 4, cx + 3, hy - 2, GRY)
        l.px(cx, hy - 5, RED); l.px(cx, hy - 6, RED)
    elif kind == "feather":
        l.rect(cx - 3, hy - 4, cx + 3, hy - 3, GRN)
        l.line([(cx + 2, hy - 4), (cx + 5, hy - 8)], RED)
        l.px(cx + 4, hy - 8, RED)
    elif kind == "hood":
        pass


def hand_from_cloud(l, cx, cy, side=-1):
    """雲から伸びる手(エース用)。side=-1 で左の雲から。"""
    l.rect(cx - 2, cy - 2, cx + 2, cy + 3, SKIN)
    l.rect(cx + 1, cy - 2, cx + 2, cy + 3, SKSH)
    x0 = 3 if side < 0 else AW - 4
    l.line([(x0 + 5 * -side, cy + 1), (cx - 2 * side, cy + 1)], SKIN, 3)


def horse(l, cx, gy, col=WHT, mane=GRY, face=1):
    f = lambda x: cx + (x - cx) * face
    l.ell(cx, gy - 12, 10, 5, col)
    for x in (cx - 8, cx - 5, cx + 5, cx + 8):
        c = col if x in (cx - 8, cx + 5) else sh(col)
        l.rect(f(x), gy - 9, f(x) + face, gy, c)
        l.rect(f(x), gy, f(x) + face, gy, K)
    l.poly([(f(cx + 5), gy - 16), (f(cx + 10), gy - 12), (f(cx + 14), gy - 22), (f(cx + 10), gy - 24)], col)
    l.poly([(f(cx + 10), gy - 25), (f(cx + 14), gy - 25), (f(cx + 18), gy - 19), (f(cx + 16), gy - 17), (f(cx + 12), gy - 20)], col)
    l.px(f(cx + 11), gy - 27, col); l.px(f(cx + 11), gy - 26, col)
    l.px(f(cx + 13), gy - 23, K)
    l.line([(f(cx + 9), gy - 25), (f(cx + 5), gy - 17)], mane, 2)
    l.line([(f(cx - 10), gy - 14), (f(cx - 13), gy - 5)], mane, 2)
    l.ell(cx - 2 * face, gy - 10, 6, 1, sh(col))


def lion(l, cx, gy, face=-1):
    f = lambda x: cx + (x - cx) * face
    l.line([(f(cx - 10), gy - 9), (f(cx - 14), gy - 13)], ORANGE, 1)
    l.ell(f(cx - 14), gy - 14, 1, 1, ORAD)
    l.ell(cx, gy - 8, 10, 4, ORANGE)
    for x in (cx - 8, cx - 5, cx + 4, cx + 7):
        l.rect(f(x), gy - 5, f(x) + face, gy, ORANGE if x in (cx - 8, cx + 4) else ORAD)
    l.ell(f(cx + 9), gy - 12, 6, 6, ORAD)
    l.ell(f(cx + 11), gy - 11, 3, 3, ORANGE)
    l.px(f(cx + 12), gy - 12, K)
    l.px(f(cx + 14), gy - 10, K)
    l.ell(cx, gy - 6, 7, 1, ORAD)


def dog(l, cx, gy, col=WHT, face=1, jump=0):
    f = lambda x: cx + (x - cx) * face
    gy -= jump
    l.ell(cx, gy - 5, 4, 2, col)
    for x in (cx - 3, cx + 3):
        l.rect(f(x), gy - 3, f(x), gy, col)
    l.ell(f(cx + 5), gy - 8, 2, 2, col)
    l.px(f(cx + 7), gy - 8, col)
    l.px(f(cx + 4), gy - 11, sh(col)); l.px(f(cx + 4), gy - 10, sh(col))
    l.px(f(cx + 6), gy - 9, K)
    l.line([(f(cx - 4), gy - 6), (f(cx - 6), gy - 9)], col)


def sphinx(l, cx, gy, col):
    l.rect(cx - 5, gy - 4, cx + 5, gy, col)
    l.rect(cx - 3, gy - 10, cx + 3, gy - 4, col)
    l.ell(cx, gy - 11, 3, 3, SKIN if col != BLK else SKSH)
    l.rect(cx - 4, gy - 13, cx + 4, gy - 12, sh(col) if col != BLK else GRY)
    l.rect(cx - 4, gy - 12, cx - 3, gy - 8, sh(col) if col != BLK else GRY)
    l.rect(cx + 3, gy - 12, cx + 4, gy - 8, sh(col) if col != BLK else GRY)
    l.px(cx - 1, gy - 11, K); l.px(cx + 1, gy - 11, K)


def throne(l, cx, fy, col=GRY, top=None):
    l.rect(cx - 9, fy - 33, cx + 9, fy, col)
    l.rect(cx + 6, fy - 33, cx + 9, fy, sh(col))
    l.rect(cx - 11, fy - 12, cx + 11, fy, col)
    l.rect(cx + 8, fy - 12, cx + 11, fy, sh(col))
    if top:
        top(l, cx, fy - 33)


# ---- suit icons ---------------------------------------------------------------
def i_wand(l, cx, cy, h, ang=0):
    t, b = cy - h // 2, cy + h // 2
    l.rect(cx, t, cx + 1, b, BRN)
    l.rect(cx + 1, t + 1, cx + 1, b, BRND)
    l.px(cx, t, TAN)
    for k, (dx, fy) in enumerate([(-2, 0.25), (2, 0.5), (-2, 0.75)]):
        y = t + int(h * fy)
        if dx < 0:
            l.px(cx - 1, y, LIME); l.px(cx - 2, y - 1, GRN)
        else:
            l.px(cx + 2, y, LIME); l.px(cx + 3, y - 1, GRN)


def i_cup(l, cx, cy, h):
    w = max(3, int(h * 0.32))
    t = cy - h // 2
    m = t + int(h * 0.45)
    b = cy + h // 2
    l.poly([(cx - w, t), (cx + w, t), (cx + w, m - 1), (cx + 1, m + 1), (cx - 1, m + 1), (cx - w, m - 1)], GOLD)
    l.poly([(cx + w - 1, t), (cx + w, t), (cx + w, m - 1), (cx + 1, m + 1)], GOLDD)
    l.rect(cx - w + 1, t + 1, cx - w + 1, m - 2, YEL)
    l.rect(cx, m + 1, cx, b - 2, GOLD)
    bw = max(2, w - 1)
    l.rect(cx - bw, b - 1, cx + bw, b, GOLD)
    l.rect(cx + 1, b - 1, cx + bw, b, GOLDD)
    if h >= 20:
        l.rect(cx - w, t, cx + w, t, YEL)
        l.ell(cx, (t + m) // 2, 1, 1, RED)


def i_sword(l, cx, cy, h):
    t, b = cy - h // 2, cy + h // 2
    g = b - max(3, h // 4)
    l.px(cx, t, GRYL)
    l.rect(cx - 1, t + 1, cx + 1, g - 1, GRYL)
    l.rect(cx, t + 1, cx, g - 1, WHT)
    l.rect(cx + 1, t + 2, cx + 1, g - 1, GRY)
    gw = max(3, h // 5)
    l.rect(cx - gw, g, cx + gw, g, GOLD)
    l.rect(cx, g + 1, cx, b - 1, BRN)
    l.px(cx, b, GOLD)
    if h >= 20:
        l.rect(cx - gw, g, cx + gw, g + 1, GOLD)
        l.px(cx - gw, g - 1, GOLD); l.px(cx + gw, g - 1, GOLD)


def i_pent(l, cx, cy, r):
    l.ell(cx, cy, r, r, GOLD)
    l.ell(cx, cy, r - 1, r - 1, YEL)
    ro, ri = r - 1.5, (r - 1.5) * 0.42
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = ro if i % 2 == 0 else ri
        pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
    l.poly(pts, GOLDD)
    if r >= 8:
        l.ring(cx, cy, r, r, GOLDD)


def icon(l, suit, cx, cy, h):
    if suit == "wands":
        i_wand(l, cx, cy, h)
    elif suit == "cups":
        i_cup(l, cx, cy, h)
    elif suit == "swords":
        i_sword(l, cx, cy, h)
    else:
        i_pent(l, cx, cy, h // 2 - 1)


# ---- major arcana -------------------------------------------------------------
def m00(S):  # Fool
    b = S.bg
    bands(b, [(0, SKY), (20, PALE)])
    sun(b, 44, 9, 4)
    mountains(b, 52, [(10, 18, 12), (30, 12, 10)], GRYL, WHT)
    g = S.layer()
    g.poly([(0, 60), (40, 58), (44, 62), (40, 78), (0, 78)], GRN)
    g.poly([(40, 58), (44, 62), (40, 78), (37, 78)], BRN)
    f = S.layer()
    o = figure(f, 22, 60, ORANGE, trim=YEL, sleeve=WHT, head="feather", hair=YEL, lh=(14, 36), rh=(28, 34), legs=YEL)
    f.line([(30, 33), (36, 26), (16, 44)], BRN)
    f.line([(30, 34), (34, 28)], BRN)
    f.ell(14, 43, 3, 2, RED)
    f.px(15, 34, WHT); f.px(14, 33, WHT); f.px(16, 33, WHT); f.px(15, 32, GRN)
    d = S.layer()
    dog(d, 34, 61, WHT, face=-1, jump=3)


def m01(S):  # Magician
    b = S.bg
    bands(b, [(0, YEL), (30, GOLD)])
    for x in range(3, AW, 10):
        b.ell(x, 4, 2, 2, RED); b.px(x, 7, GRN)
    f = S.layer()
    o = figure(f, 27, 62, WHT, cape=RED, trim=BLUE, hair=BLK, lh=(19, 22), rh=(33, 38))
    f.rect(19, 13, 20, 22, WHT)
    f.px(19, 12, WHT)
    lemniscate(f, 27, 13)
    t = S.layer()
    t.rect(4, 54, 49, 58, BRN)
    t.rect(4, 54, 49, 54, TAN)
    t.rect(6, 59, 8, 77, BRND); t.rect(45, 59, 47, 77, BRND)
    icon(t, "cups", 12, 49, 9)
    icon(t, "pentacles", 20, 50, 8)
    i_sword(t, 36, 48, 11)
    i_wand(t, 43, 48, 11)


def m02(S):  # High Priestess
    b = S.bg
    bands(b, [(0, NAVY), (50, BLUE)])
    b.rect(9, 6, 44, 64, PURD)
    for y in range(9, 62, 6):
        for x in range(12, 44, 6):
            b.ell(x + (y // 6 % 2) * 3, y, 1, 1, REDD)
    p = S.layer()
    pillar(p, 2, 4, 70, BLK, GRY)
    pillar(p, 46, 4, 70, WHT, GRYL)
    p.px(4, 30, WHT); p.px(4, 31, WHT); p.px(5, 30, WHT); p.px(4, 32, WHT); p.px(5, 32, WHT)
    p.px(48, 30, BLK); p.px(48, 31, BLK); p.px(48, 32, BLK); p.px(47, 32, BLK)
    f = S.layer()
    figure(f, 27, 66, BLUE, cape=WHT, trim=WHT, hair=None, head="moon", lh=(22, 39), rh=(30, 39), seated=True)
    f.rect(23, 39, 31, 41, CREAM)
    f.px(23, 40, TAN); f.px(31, 40, TAN)
    m = S.layer()
    m.ell(27, 71, 6, 3, YEL)
    m.ell(27, 69, 6, 3, (0, 0, 0, 0))


def m03(S):  # Empress
    b = S.bg
    bands(b, [(0, YEL), (40, LIME), (62, GOLD)])
    for x in range(0, AW, 4):
        b.line([(x, 62), (x + 1, 58)], GOLDD)
    tr = S.layer()
    for x in (6, 47):
        tr.rect(x, 26, x + 1, 45, BRN)
        tr.ell(x, 22, 5, 6, GRN)
        tr.ell(x - 1, 20, 3, 3, LIME)
    tr.rect(16, 36, 38, 66, RED)
    tr.rect(16, 36, 38, 38, PINK)
    f = S.layer()
    figure(f, 27, 66, WHT, hair=YEL, longhair=True, head="stars", trim=RED, rh=(34, 38), lh=(20, 45), seated=True)
    f.line([(35, 28), (35, 40)], GOLD)
    f.ell(35, 27, 1, 1, YEL)
    for (x, y) in ((24, 44), (29, 50), (23, 54), (30, 58)):
        f.px(x, y, RED)
    h = S.layer()
    h.poly([(9, 54), (15, 54), (15, 59), (12, 63), (9, 59)], GRYL)
    h.ell(12, 57, 1, 1, GOLD); h.px(12, 59, GOLD); h.px(11, 60, GOLD); h.px(13, 60, GOLD)


def m04(S):  # Emperor
    b = S.bg
    bands(b, [(0, ORANGE), (34, ORAD)])
    mountains(b, 60, [(8, 26, 12), (44, 30, 14), (26, 16, 10)], BRN, ORANGE)
    b.rect(0, 60, AW - 1, AH - 1, BRND)

    def rams(l, cx, y):
        for sx in (cx - 9, cx + 9):
            l.ell(sx, y, 3, 3, GRYL)
            l.px(sx, y, GRY)
    t = S.layer()
    throne(t, 27, 72, GRY, rams)
    f = S.layer()
    figure(f, 27, 72, RED, cape=REDD, hair=WHT, beard=WHT, head="crown", sleeve=GRYL, lh=(18, 46), rh=(34, 50), seated=True)
    f.line([(19, 34), (19, 46)], GOLD)
    f.ring(19, 32, 1, 2, GOLD)
    f.line([(17, 35), (21, 35)], GOLD)
    f.ell(35, 49, 2, 2, GOLD); f.px(35, 46, GOLD)


def m05(S):  # Hierophant
    b = S.bg
    bands(b, [(0, GRYL), (66, GRY)])
    p = S.layer()
    pillar(p, 3, 8, 66, GRY)
    pillar(p, 45, 8, 66, GRY)
    t = S.layer()
    throne(t, 27, 64, GRYD)
    f = S.layer()
    figure(f, 27, 64, RED, cape=REDD, sleeve=WHT, hair=None, head="mitre", trim=WHT, lh=(19, 33), rh=(34, 42), seated=True)
    f.line([(36, 22), (36, 50)], GOLD)
    for y in (24, 27, 30):
        f.line([(34, y), (38, y)], GOLD)
    f.px(19, 31, SKIN); f.px(20, 31, SKIN)
    k = S.layer()
    k.line([(21, 66), (33, 71)], GOLD); k.line([(33, 66), (21, 71)], GRYL)
    k.ell(21, 66, 1, 1, GOLD); k.ell(33, 66, 1, 1, GRYL)
    a = S.layer()
    for cx, col in ((12, RED), (42, WHT)):
        a.ell(cx, 70, 4, 7, col)
        a.ell(cx, 63, 3, 3, BRN if col == RED else YEL)
        a.px(cx, 61, SKIN)


def m06(S):  # Lovers
    b = S.bg
    bands(b, [(0, SKY), (28, PALE), (60, LIME)])
    sun(b, 27, 8, 6)
    mountains(b, 60, [(27, 18, 8)], GRYL, WHT)
    c = S.layer()
    cloud(c, 27, 26, 14, WHT, GRYL)
    a = S.layer()
    a.poly([(27, 14), (8, 6), (12, 16), (22, 22)], LIL)
    a.poly([(27, 14), (46, 6), (42, 16), (32, 22)], LIL)
    a.poly([(27, 14), (46, 6), (44, 9), (34, 19)], PUR)
    a.ell(27, 14, 3, 3, SKIN)
    a.rect(24, 10, 30, 11, RED); a.px(23, 12, RED); a.px(31, 12, RED); a.px(31, 13, ORANGE); a.px(23, 13, ORANGE)
    a.px(26, 14, K); a.px(28, 14, K)
    a.rect(24, 18, 30, 22, PUR)
    tr = S.layer()
    tr.rect(46, 38, 47, 66, BRN)
    tr.ell(47, 36, 5, 6, GRN)
    for (x, y) in ((45, 34), (49, 37), (46, 39)):
        tr.px(x, y, RED)
    tr.line([(46, 44), (48, 46), (46, 48), (48, 50)], LIME)
    tr.rect(6, 40, 7, 66, BRN)
    for (x, y) in ((4, 36), (8, 35), (6, 33), (3, 39), (9, 38)):
        tr.px(x, y, ORANGE); tr.px(x, y - 1, YEL)
    f = S.layer()
    figure(f, 16, 68, PALE, hair=BRN, rh=(21, 50))
    figure(f, 38, 68, PINK, hair=YEL, longhair=True, lh=(32, 46), rh=(44, 52))


def m07(S):  # Chariot
    b = S.bg
    bands(b, [(0, YEL), (38, GOLD)])
    for x in range(0, AW, 9):
        b.rect(x, 28, x + 6, 38, GRYL)
        b.rect(x + 1, 25, x + 2, 27, GRYL); b.rect(x + 4, 25, x + 5, 27, GRYL)
    b.rect(0, 38, AW - 1, 50, TEAL)
    b.rect(0, 50, AW - 1, AH - 1, LIME)
    c = S.layer()
    c.rect(11, 4, 43, 9, NAVY)
    for x in range(13, 43, 4):
        c.px(x, 6, YEL)
    c.rect(12, 9, 13, 30, GRY); c.rect(41, 9, 42, 30, GRY)
    f = S.layer()
    figure(f, 27, 52, GRYL, sleeve=GRY, head="crown", hair=YEL, rh=(35, 32), lh=(19, 38))
    f.line([(36, 18), (36, 34)], GOLD); f.ell(36, 17, 1, 1, YEL)
    f.ell(27, 31, 2, 2, YEL)
    box = S.layer()
    box.rect(9, 40, 45, 58, GRY)
    box.rect(9, 40, 45, 41, GRYL)
    box.rect(40, 42, 45, 58, GRYD)
    box.ell(27, 49, 4, 3, RED); box.px(23, 49, WHT); box.px(31, 49, WHT); box.px(22, 48, WHT); box.px(32, 48, WHT)
    box.ell(11, 59, 3, 3, BRN); box.ell(43, 59, 3, 3, BRN)
    s = S.layer()
    sphinx(s, 15, 74, BLK)
    sphinx(s, 39, 74, WHT)


def m08(S):  # Strength
    b = S.bg
    bands(b, [(0, YEL), (44, LIME), (60, GRN)])
    mountains(b, 44, [(44, 14, 10)], LIL, WHT)
    l_ = S.layer()
    lion(l_, 30, 70, face=-1)
    f = S.layer()
    figure(f, 32, 66, WHT, hair=YEL, longhair=True, head="wreath", trim=RED, lh=(22, 55), rh=(27, 51))
    lemniscate(f, 32, 30)
    f.px(28, 42, RED); f.px(31, 46, RED); f.px(34, 52, RED); f.px(30, 58, RED)


def m09(S):  # Hermit
    b = S.bg
    bands(b, [(0, NIGHT), (36, NAVY)])
    stars(b, 14, 9, 30)
    mountains(b, 78, [(12, 30, 22), (46, 22, 16)], GRYD, GRYL)
    f = S.layer()
    o = figure(f, 28, 72, GRY, hair=None, beard=WHT, skin=SKIN, lh=(17, 34), rh=(36, 44), cape=GRYD)
    hy = o["hy"]
    f.ell(28, hy, 4, 4, GRY)
    f.ell(28, hy + 1, 2, 3, SKIN)
    f.px(27, hy, K); f.px(29, hy, K)
    f.poly([(26, hy + 3), (30, hy + 3), (29, hy + 7), (28, hy + 8), (27, hy + 7)], WHT)
    f.line([(37, 30), (40, 74)], BRN, 2)
    lm = S.layer()
    lm.line([(18, 34), (18, 37)], GRYD)
    lm.rect(16, 37, 20, 43, GOLD)
    lm.rect(17, 38, 19, 42, YEL)
    lm.px(18, 40, WHT)
    gl = S.layer(ol=False)
    for (x, y) in ((14, 40), (22, 40), (18, 35), (18, 46), (15, 36), (21, 36), (15, 44), (21, 44)):
        gl.px(x, y, YEL)


def corner_beasts(S):
    """運命の輪/世界の四隅: 天使(左上)・鷲(右上)・牛(左下)・獅子(右下)。雲の上に顔を出す。"""
    c = S.layer()
    for (x, y) in ((9, 13), (47, 13), (7, 74), (47, 74)):
        cloud(c, x, y, 7)
    w = S.layer()  # 天使の翼: 肩から斜め上へ。下の縁を段々にして羽先に見せる(頭とは別の層=輪郭で分ける)
    for m in (lambda x: x, lambda x: 18 - x):
        w.poly([(m(7), 10), (m(6), 6), (m(3), 2), (m(1), 1), (m(0), 4), (m(1), 5), (m(1), 7),
                (m(3), 7), (m(3), 9), (m(5), 9), (m(5), 11)], PALE)
        w.line([(m(2), 3), (m(5), 7)], SKY)
        w.px(m(2), 6, SKY); w.px(m(4), 8, SKY)
        w.px(m(1), 2, WHT); w.px(m(2), 2, WHT)
    a = S.layer()  # 天使: 金髪
    a.ell(9, 7, 3, 3, SKIN)
    a.rect(6, 3, 12, 4, YEL); a.px(6, 5, YEL); a.px(12, 5, YEL)
    a.px(8, 7, K); a.px(10, 7, K); a.px(9, 9, PINK)
    e = S.layer()  # 鷲: 翼を広げた茶色+白い頭+黄色いくちばし
    e.poly([(46, 9), (39, 2), (40, 7), (42, 10)], BRN)
    e.poly([(48, 9), (55, 2), (54, 7), (52, 10)], BRN)
    e.line([(41, 5), (44, 9)], BRND); e.line([(53, 5), (50, 9)], BRND)
    e.ell(47, 8, 2, 3, BRN)
    e.ell(47, 4, 2, 2, WHT)
    e.px(48, 4, K); e.px(49, 5, YEL); e.px(50, 5, YEL); e.px(49, 6, GOLD)
    b = S.layer()  # 牛: 茶色い顔+角+鼻づら
    b.line([(4, 64), (2, 62), (2, 60)], CREAM); b.line([(10, 64), (12, 62), (12, 60)], CREAM)
    b.px(3, 65, BRN); b.px(11, 65, BRN)
    b.ell(7, 67, 3, 3, BRN)
    b.rect(5, 69, 9, 71, TAN)
    b.px(6, 70, BRND); b.px(8, 70, BRND)
    b.px(6, 66, K); b.px(8, 66, K)
    n = S.layer()  # 獅子: たてがみ+顔
    n.ell(47, 67, 5, 5, ORAD)
    for (x, y) in ((42, 64), (52, 64), (43, 71), (51, 71), (47, 61)):
        n.px(x, y, ORAD)
    n.ell(47, 68, 3, 3, ORANGE)
    n.px(46, 67, K); n.px(48, 67, K)
    n.px(47, 69, BRND); n.px(46, 70, BRND); n.px(48, 70, BRND)


def m10(S):  # Wheel of Fortune
    b = S.bg
    bands(b, [(0, SKY), (60, PALE)])
    corner_beasts(S)
    w = S.layer()
    w.ell(27, 40, 18, 18, ORANGE)
    w.ell(27, 40, 15, 15, YEL)
    w.ell(27, 40, 11, 11, ORANGE)
    for i in range(8):
        a = i * math.pi / 4
        w.line([(27, 40), (27 + math.cos(a) * 15, 40 + math.sin(a) * 15)], ORAD)
    w.ell(27, 40, 3, 3, GOLD)
    for i, ch in enumerate("TARO"):
        a = -math.pi / 2 + i * math.pi / 2
        w.px(27 + math.cos(a) * 13, 40 + math.sin(a) * 13, REDD)
    s = S.layer()
    s.rect(23, 16, 31, 20, BLUE)
    s.ell(27, 14, 3, 3, SKSH)
    s.rect(24, 11, 30, 12, NAVY)
    s.line([(32, 15), (30, 21)], GRYL)
    s.ell(32, 14, 1, 1, GRYL)
    s.line([(8, 30), (10, 36), (7, 42), (10, 48), (8, 54)], GOLD, 2)
    s.px(8, 29, K)
    s.ell(46, 54, 3, 6, RED)
    s.ell(46, 47, 2, 3, RED)
    s.px(45, 43, RED); s.px(47, 43, RED)


def m11(S):  # Justice
    b = S.bg
    bands(b, [(0, GRYL), (64, GRY)])
    b.rect(9, 4, 44, 64, PUR)
    b.rect(40, 4, 44, 64, PURD)
    p = S.layer()
    pillar(p, 2, 6, 66, GRY)
    pillar(p, 46, 6, 66, GRY)
    t = S.layer()
    throne(t, 27, 70, GRYD)
    f = S.layer()
    figure(f, 27, 70, RED, cape=GRN, hair=BRN, head="crown", lh=(18, 44), rh=(35, 46), seated=True)
    i_sword(f, 19, 30, 26)
    sc = S.layer()
    sc.line([(36, 32), (36, 46)], GOLD)
    sc.line([(30, 32), (42, 32)], GOLD)
    for x in (30, 42):
        sc.line([(x, 32), (x, 37)], GOLD)
        sc.rect(x - 2, 38, x + 2, 38, GOLD)
        sc.px(x - 1, 39, GOLDD); sc.px(x, 39, GOLDD); sc.px(x + 1, 39, GOLDD)


def m12(S):  # Hanged Man
    b = S.bg
    bands(b, [(0, PALE), (64, GRN)])
    t = S.layer()
    t.rect(4, 6, 49, 9, BRN)
    t.rect(4, 6, 49, 6, TAN)
    t.rect(5, 6, 8, 70, BRN); t.rect(45, 6, 48, 70, BRN)
    t.rect(7, 10, 8, 70, BRND); t.rect(47, 10, 48, 70, BRND)
    for (x, y) in ((4, 14), (9, 22), (44, 18), (49, 26), (20, 5), (34, 5)):
        t.ell(x, y, 2, 1, LIME)
    t.line([(27, 9), (27, 12)], BRND)
    fl = L()
    figure(fl, 27, 66, BLUE, hair=YEL, legs=RED, halo=YEL, lh=(22, 46), rh=(31, 46), sleeve=BLUE)
    fl.rect(23, 60, 27, 61, RED)
    fl.d.rectangle([26, 58, 27, 66], fill=(0, 0, 0, 0))
    fl.rect(26, 58, 27, 61, RED)
    fl.rect(28, 58, 29, 66, RED)
    fl.rect(28, 66, 29, 66, BRND)
    flipped = fl.im.transpose(Image.FLIP_TOP_BOTTOM)
    lay = S.layer()
    lay.im.alpha_composite(flipped)


def m13(S):  # Death
    b = S.bg
    bands(b, [(0, GRYL), (38, PALE), (62, GRY)])
    sun(b, 44, 46, 4, rays=False)
    tw = S.layer()
    for x in (38, 50):
        tw.rect(x - 2, 40, x + 2, 62, GRYD)
        tw.rect(x - 3, 38, x + 3, 40, GRYD)
    hl = S.layer()
    horse(hl, 20, 72, WHT, GRY, face=1)
    r = S.layer()
    o = figure(r, 20, 60, BLK, hair=None, skin=WHT, eyes=K, sleeve=GRYD, lh=(12, 34), rh=(27, 46))
    r.px(19, o["hy"] + 2, K); r.px(21, o["hy"] + 2, K)
    r.line([(12, 44), (12, 18)], BRND)
    r.rect(13, 18, 26, 27, BLK)
    r.ell(19, 22, 2, 2, WHT)
    r.px(19, 22, GOLD)
    hl2 = S.layer()
    hl2.ell(20, 60, 10, 5, WHT)
    hl2.ell(18, 62, 6, 1, GRYL)
    hl2.px(13, 64, BLK); hl2.rect(13, 64, 14, 68, BLK)


def m14(S):  # Temperance
    b = S.bg
    bands(b, [(0, PALE), (52, LIME), (64, TEAL)])
    mountains(b, 52, [(44, 14, 9)], GRYL, WHT)
    sun(b, 44, 37, 2, rays=False)
    b.line([(44, 40), (44, 52), (40, 64)], CREAM)
    w = S.layer()
    w.poly([(27, 28), (4, 8), (6, 22), (18, 36)], RED)
    w.poly([(27, 28), (50, 8), (48, 22), (36, 36)], RED)
    w.poly([(27, 28), (50, 8), (48, 12), (33, 31)], REDD)
    f = S.layer()
    figure(f, 27, 68, WHT, hair=YEL, halo=YEL, lh=(17, 38), rh=(35, 46), trim=GOLD)
    f.poly([(25, 30), (29, 30), (27, 33)], GOLD)
    icon(f, "cups", 18, 37, 7)
    icon(f, "cups", 36, 46, 7)
    wt = S.layer(ol=False)
    wt.line([(19, 37), (27, 40), (35, 44)], TEALL)
    ir = S.layer()
    for x in (6, 10):
        ir.line([(x, 66), (x, 60)], GRN)
        ir.ell(x, 59, 1, 1, YEL)


def m15(S):  # Devil
    b = S.bg
    bands(b, [(0, K), (62, BLK)])
    w = S.layer()
    w.poly([(27, 20), (4, 6), (2, 14), (6, 13), (6, 20), (11, 18), (18, 26)], GRYD)
    w.poly([(27, 20), (50, 6), (52, 14), (48, 13), (48, 20), (43, 18), (36, 26)], GRYD)
    d = S.layer()
    figure(d, 27, 46, BRN, skin=TAN, hair=None, head="horns", eyes=RED, lh=(18, 22), rh=(34, 34), beard=BRND)
    d.ell(27, 5, 3, 3, GRYL)
    d.ell(27, 5, 2, 2, K)
    d.px(27, 3, GRYL)
    d.line([(35, 34), (40, 40)], ORANGE, 2); d.px(41, 41, YEL)
    blk = S.layer()
    blk.rect(16, 46, 38, 53, GRYD)
    blk.rect(36, 46, 38, 53, BLK)
    blk.ell(27, 49, 2, 1, GRY)
    p = S.layer()
    figure(p, 14, 75, SKSH, skin=SKIN, hair=BRN, head="horns")
    figure(p, 40, 75, SKSH, skin=SKIN, hair=YEL, longhair=True, head="horns")
    ch = S.layer(ol=False)
    ch.line([(26, 52), (14, 59)], GRY); ch.line([(28, 52), (40, 59)], GRY)
    ch.line([(9, 70), (5, 75)], ORANGE)
    ch.line([(45, 70), (49, 75)], GRN)


def m16(S):  # Tower
    b = S.bg
    bands(b, [(0, K), (30, NIGHT)])
    stars(b, 10, 16, 60, (GRY, GRYD))
    r = S.layer()
    r.poly([(8, 78), (16, 62), (38, 62), (46, 78)], GRYD)
    r.poly([(30, 62), (38, 62), (46, 78), (36, 78)], BLK)
    t = S.layer()
    t.rect(18, 22, 35, 64, GRY)
    t.rect(31, 22, 35, 64, GRYD)
    t.rect(17, 20, 36, 23, GRYL)
    for (x, y) in ((22, 32), (29, 32), (25, 46), (22, 56)):
        t.rect(x, y, x + 2, y + 4, ORANGE)
        t.rect(x, y, x + 2, y + 1, YEL)
    t.rect(25, 58, 28, 64, K)
    fl = S.layer(ol=False)
    for (x, y) in ((23, 31), (30, 31), (26, 45), (23, 55)):
        fl.px(x, y - 1, ORANGE); fl.px(x + 1, y - 2, YEL)
    cr = S.layer()
    cr.rect(36, 12, 42, 14, GOLD)
    cr.px(36, 11, GOLD); cr.px(39, 11, GOLD); cr.px(42, 11, GOLD)
    lt = S.layer(ol=False)
    lt.line([(52, 0), (44, 8), (48, 10), (36, 22)], YEL, 2)
    lt.line([(52, 0), (44, 8), (48, 10), (36, 22)], WHT, 1)
    fg = S.layer()
    for (cx, cy, c) in ((10, 40, RED), (44, 46, BLUE)):
        fg.ell(cx, cy, 2, 2, SKIN)
        fg.rect(cx - 2, cy - 9, cx + 2, cy - 3, c)
        fg.line([(cx - 2, cy - 8), (cx - 5, cy - 11)], SKIN)
        fg.line([(cx + 2, cy - 8), (cx + 5, cy - 11)], SKIN)
    sp = S.layer(ol=False)
    for (x, y) in ((6, 20), (14, 28), (40, 30), (48, 24), (8, 52), (46, 60)):
        sp.px(x, y, YEL)


def m17(S):  # Star
    b = S.bg
    bands(b, [(0, NAVY), (36, BLUE), (58, GRN)])
    b.ell(36, 70, 18, 6, TEAL)
    s = S.layer(ol=False)
    for i in range(8):
        a = i * math.pi / 4
        rr = 9 if i % 2 == 0 else 6
        s.line([(27, 13), (27 + math.cos(a) * rr, 13 + math.sin(a) * rr)], YEL, 1)
    s.ell(27, 13, 3, 3, YEL)
    s.px(27, 13, WHT)
    for (x, y) in ((6, 6), (48, 6), (4, 18), (50, 18), (10, 28), (44, 28), (27, 30)):
        s.px(x, y, WHT); s.px(x - 1, y, PALE); s.px(x + 1, y, PALE); s.px(x, y - 1, PALE); s.px(x, y + 1, PALE)
    tr = S.layer()
    tr.rect(6, 40, 7, 58, BRN)
    tr.ell(7, 38, 4, 4, GRN)
    tr.ell(10, 34, 2, 1, ORANGE)
    f = S.layer()
    figure(f, 27, 66, PALE, hair=YEL, longhair=True, lh=(18, 54), rh=(36, 56), seated=True)
    j = S.layer()
    j.ell(17, 57, 2, 3, ORANGE); j.ell(37, 59, 2, 3, ORANGE)
    wt = S.layer(ol=False)
    wt.line([(16, 60), (12, 66), (10, 70)], TEALL)
    wt.line([(38, 62), (40, 70)], TEALL)


def m18(S):  # Moon
    b = S.bg
    bands(b, [(0, NAVY), (40, BLUE), (52, GRN)])
    b.poly([(25, 52), (29, 52), (36, 78), (18, 78)], TAN)
    b.ell(27, 72, 14, 5, TEAL)
    m = S.layer()
    for i in range(16):
        a = i * math.pi / 8
        m.line([(27 + math.cos(a) * 9, 15 + math.sin(a) * 9), (27 + math.cos(a) * 12, 15 + math.sin(a) * 12)], GOLD)
    m.ell(27, 15, 9, 9, YEL)
    m.ell(30, 14, 7, 8, PALE)
    m.px(28, 13, BLUE); m.px(27, 18, BLUE)
    dr = S.layer(ol=False)
    for (x, y) in ((14, 30), (22, 34), (32, 32), (40, 29), (27, 38)):
        dr.px(x, y, YEL); dr.px(x, y + 1, GOLD)
    tw = S.layer()
    for x in (6, 48):
        tw.rect(x - 3, 30, x + 3, 58, GRYL)
        tw.rect(x + 1, 30, x + 3, 58, GRY)
        tw.rect(x - 4, 28, x + 4, 30, GRYL)
        tw.rect(x - 1, 36, x, 38, K)
    an = S.layer()
    dog(an, 15, 64, WHT, face=1)
    dog(an, 39, 64, GRY, face=-1)
    cr = S.layer()
    cr.ell(27, 72, 3, 2, RED)
    cr.px(24, 69, RED); cr.px(30, 69, RED); cr.px(23, 68, RED); cr.px(31, 68, RED)


def m19(S):  # Sun
    b = S.bg
    bands(b, [(0, SKY), (30, PALE)])
    sun(b, 27, 14, 9, face=True)
    w = S.layer()
    w.rect(0, 48, AW - 1, 56, GRYL)
    for x in range(0, AW, 6):
        w.line([(x, 48), (x, 56)], GRY)
    w.line([(0, 52), (AW - 1, 52)], GRY)
    for x in (6, 16, 38, 48):
        w.line([(x, 48), (x, 40)], GRN)
        w.ell(x, 38, 3, 3, YEL)
        w.ell(x, 38, 1, 1, BRN)
    g = S.layer()
    g.rect(0, 64, AW - 1, AH - 1, LIME)
    h = S.layer()
    horse(h, 26, 76, WHT, GRYL, face=1)
    c = S.layer()
    figure(c, 26, 64, SKIN, hair=YEL, head="wreath", rh=(33, 46), lh=(20, 52), sleeve=SKIN)
    c.line([(20, 52), (14, 28)], BRND)
    c.poly([(14, 28), (4, 30), (6, 38), (15, 36)], RED)
    h2 = S.layer()
    h2.ell(26, 64, 10, 4, WHT)


def m20(S):  # Judgement
    b = S.bg
    bands(b, [(0, PALE), (46, SKY), (60, BLUE)])
    mountains(b, 60, [(6, 14, 8), (48, 16, 9)], WHT, WHT)
    c = S.layer()
    cloud(c, 27, 30, 18, WHT, GRYL)
    a = S.layer()
    a.poly([(27, 14), (6, 4), (8, 16), (20, 24)], RED)
    a.poly([(27, 14), (48, 4), (46, 16), (34, 24)], RED)
    a.ell(27, 12, 3, 3, SKIN)
    a.rect(24, 8, 30, 9, YEL)
    a.px(26, 12, K); a.px(28, 12, K)
    a.rect(24, 16, 30, 26, BLUE)
    tp = S.layer()
    tp.line([(29, 15), (42, 26)], GOLD)
    tp.poly([(42, 26), (46, 24), (44, 30)], GOLD)
    tp.line([(36, 22), (36, 28)], GRYL)
    tp.rect(36, 23, 41, 27, WHT)
    tp.line([(38, 23), (38, 27)], RED); tp.line([(36, 25), (41, 25)], RED)
    cf = S.layer()
    for (cx, col) in ((12, GRY), (27, GRY), (42, GRY)):
        cf.rect(cx - 6, 70, cx + 6, 74, BRN)
        cf.ell(cx, 60, 2, 2, GRYL)
        cf.rect(cx - 2, 63, cx + 2, 70, col)
        cf.line([(cx - 2, 64), (cx - 5, 57)], GRYL)
        cf.line([(cx + 2, 64), (cx + 5, 57)], GRYL)


def m21(S):  # World
    b = S.bg
    bands(b, [(0, SKY), (50, PALE)])
    corner_beasts(S)
    w = S.layer()
    w.ell(27, 39, 15, 26, GRN)
    w.ell(27, 39, 12, 23, (0, 0, 0, 0))
    for i in range(24):
        a = i * math.pi / 12
        w.px(27 + math.cos(a) * 14, 39 + math.sin(a) * 25, LIME)
    for y in (13, 65):
        w.line([(23, y), (31, y)], RED)
        w.line([(25, y - 2), (29, y + 2)], RED)
    f = S.layer()
    figure(f, 27, 58, PUR, skin=SKIN, hair=BRN, longhair=True, lh=(19, 36), rh=(35, 38), legs=SKIN)
    f.rect(19, 30, 20, 40, WHT); f.rect(36, 32, 37, 42, WHT)
    f.line([(23, 50), (20, 56)], SKIN, 2)


MAJORS = [
    ("0", "THE FOOL", m00), ("I", "THE MAGICIAN", m01), ("II", "HIGH PRIESTESS", m02),
    ("III", "THE EMPRESS", m03), ("IV", "THE EMPEROR", m04), ("V", "HIEROPHANT", m05),
    ("VI", "THE LOVERS", m06), ("VII", "THE CHARIOT", m07), ("VIII", "STRENGTH", m08),
    ("IX", "THE HERMIT", m09), ("X", "WHEEL OF|FORTUNE", m10), ("XI", "JUSTICE", m11),
    ("XII", "HANGED MAN", m12), ("XIII", "DEATH", m13), ("XIV", "TEMPERANCE", m14),
    ("XV", "THE DEVIL", m15), ("XVI", "THE TOWER", m16), ("XVII", "THE STAR", m17),
    ("XVIII", "THE MOON", m18), ("XIX", "THE SUN", m19), ("XX", "JUDGEMENT", m20),
    ("XXI", "THE WORLD", m21),
]


# ---- minor arcana -------------------------------------------------------------
SUITS = ["wands", "cups", "swords", "pentacles"]
SUIT_BG = {
    "wands": [(0, YEL), (40, GOLD), (60, ORAD)],
    "cups": [(0, PALE), (44, SKY), (60, TEAL)],
    "swords": [(0, GRYL), (40, PALE), (60, GRY)],
    "pentacles": [(0, PALE), (46, LIME), (60, GRN)],
}
SUIT_FRAME = {"wands": ORANGE, "cups": BLUE, "swords": GRY, "pentacles": GRN, "major": PUR}
SUIT_TINT = {"wands": (246, 214, 160), "cups": (200, 222, 244), "swords": (222, 222, 232), "pentacles": (212, 234, 190)}
NUM = ["ACE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE", "TEN"]
ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]
COURTS = [("PAGE", "P"), ("KNIGHT", "N"), ("QUEEN", "Q"), ("KING", "K")]

COL_L, COL_C, COL_R = 15, 27, 39
LAYOUT = {
    2: [(COL_C, 20), (COL_C, 58)],
    3: [(COL_C, 14), (COL_C, 39), (COL_C, 64)],
    4: [(COL_L, 20), (COL_R, 20), (COL_L, 58), (COL_R, 58)],
    5: [(COL_L, 16), (COL_R, 16), (COL_C, 39), (COL_L, 62), (COL_R, 62)],
    6: [(COL_L, 14), (COL_R, 14), (COL_L, 39), (COL_R, 39), (COL_L, 64), (COL_R, 64)],
    7: [(COL_L, 14), (COL_R, 14), (COL_C, 26), (COL_L, 39), (COL_R, 39), (COL_L, 64), (COL_R, 64)],
    8: [(x, y) for y in (12, 30, 48, 66) for x in (COL_L, COL_R)],
    9: [(x, y) for y in (12, 30, 48, 66) for x in (COL_L, COL_R)] + [(COL_C, 39)],
    10: [(x, y) for y in (12, 30, 48, 66) for x in (COL_L, COL_R)] + [(COL_C, 21), (COL_C, 57)],
}


def pip_bg(l, suit):
    tint = SUIT_TINT[suit]
    l.rect(0, 0, AW - 1, AH - 1, tint)
    dk = tuple(int(c * 0.88) for c in tint)
    for y in range(0, AH, 8):
        for x in range(0, AW, 8):
            o = 4 if (y // 8) % 2 else 0
            l.px(x + o, y, dk); l.px(x + o + 1, y + 1, dk); l.px(x + o - 1, y + 1, dk); l.px(x + o, y + 2, dk)


def minor_pip(S, suit, n):
    pip_bg(S.bg, suit)
    l = S.layer()
    for (x, y) in LAYOUT[n]:
        icon(l, suit, x, y, 14 if n < 8 else 12)


def minor_ace(S, suit):
    bands(S.bg, SUIT_BG[suit])
    if suit == "pentacles":
        S.bg.poly([(20, 78), (34, 78), (30, 62), (24, 62)], TAN)
    if suit == "cups":
        S.bg.rect(0, 60, AW - 1, AH - 1, TEAL)
    c = S.layer()
    cloud(c, 7, 46, 6)
    ic = S.layer()
    if suit == "pentacles":
        i_pent(ic, 27, 32, 13)
        hy = 46
    else:
        icon(ic, suit, 27, 32, 40)
        hy = 44
    h = S.layer()
    hand_from_cloud(h, 27, hy, -1)
    c2 = S.layer()
    cloud(c2, 6, 46, 5)
    sp = S.layer(ol=False)
    for (x, y) in ((12, 10), (42, 8), (44, 26), (10, 28), (40, 52), (14, 60)):
        sp.px(x, y, YEL if suit != "swords" else WHT)
    if suit == "cups":
        for (x, y) in ((24, 54), (30, 58), (27, 64), (22, 68), (33, 70)):
            sp.px(x, y, TEALL)


COURT_ROBE = {
    ("wands", 0): (ORANGE, YEL), ("wands", 1): (GOLD, RED), ("wands", 2): (YEL, ORANGE), ("wands", 3): (RED, GOLD),
    ("cups", 0): (PINK, BLUE), ("cups", 1): (BLUE, WHT), ("cups", 2): (PALE, BLUE), ("cups", 3): (BLUE, GOLD),
    ("swords", 0): (PALE, GRY), ("swords", 1): (GRYL, RED), ("swords", 2): (WHT, SKY), ("swords", 3): (BLUE, GRYL),
    ("pentacles", 0): (GRN, BRN), ("pentacles", 1): (BRN, GRN), ("pentacles", 2): (RED, GRN), ("pentacles", 3): (BLK, GOLD),
}


def court_bg(S, suit):
    b = S.bg
    bands(b, SUIT_BG[suit])
    if suit == "wands":
        b.poly([(4, 60), (12, 46), (20, 60)], TAN); b.poly([(34, 60), (44, 44), (54, 60)], TAN)
        b.poly([(44, 44), (54, 60), (48, 60)], GOLDD)
    elif suit == "cups":
        for x in range(2, AW, 7):
            b.line([(x, 64), (x + 2, 63), (x + 4, 64)], TEALL)
    elif suit == "swords":
        for (x, y) in ((10, 14), (40, 22)):
            cloud(b, x, y, 6, WHT, GRYL)
    else:
        for x in range(4, AW, 9):
            b.ell(x, 58, 3, 3, GRN); b.rect(x, 60, x, 62, BRN)


def minor_court(S, suit, ci):
    court_bg(S, suit)
    robe, trim = COURT_ROBE[(suit, ci)]
    hair = [YEL, BRN, YEL, GRY][ci]
    if ci == 0:  # page: 立って記号を掲げる
        f = S.layer()
        o = figure(f, 27, 72, robe, trim=trim, hair=hair, legs=trim, lh=(19, 36), rh=(35, 36), head="feather" if suit == "wands" else None)
        it = S.layer()
        if suit == "pentacles":
            i_pent(it, 27, 32, 6)
        elif suit == "wands":
            i_wand(it, 21, 30, 40)
        elif suit == "swords":
            i_sword(it, 20, 26, 28)
        else:
            i_cup(it, 27, 32, 12)
        if suit in ("pentacles", "cups"):
            h2 = S.layer()
            h2.rect(21, 34, 22, 35, SKIN); h2.rect(32, 34, 33, 35, SKIN)
    elif ci == 1:  # knight: 馬上
        f = S.layer()
        figure(f, 24, 60, robe, trim=trim, hair=hair, head="helmet", lh=(15, 40), rh=(31, 48), seated=True, sleeve=GRYL)
        h = S.layer()
        horse(h, 24, 76, [WHT, BRN, GRYL, BLK][SUITS.index(suit)], GRY if suit != "pentacles" else BRND, face=1)
        lg = S.layer()
        lg.rect(22, 62, 23, 68, trim)
        lg.rect(22, 68, 24, 69, BRND)
        it = S.layer()
        if suit == "pentacles":
            i_pent(it, 15, 34, 6)
        elif suit == "wands":
            i_wand(it, 15, 30, 30)
        elif suit == "swords":
            i_sword(it, 15, 24, 30)
        else:
            i_cup(it, 15, 34, 12)
    else:  # queen/king: 玉座
        t = S.layer()
        throne(t, 27, 72, GRYL if suit != "pentacles" else BRN,
               lambda l, cx, y: icon(l, suit, cx, y - 2, 9))
        f = S.layer()
        if ci == 2:
            figure(f, 27, 72, robe, trim=trim, hair=hair, longhair=True, head="qcrown", lh=(18, 42), rh=(34, 54), seated=True, cape=trim)
        else:
            figure(f, 27, 72, robe, trim=trim, hair=hair, beard=hair, head="crown", lh=(18, 42), rh=(34, 54), seated=True, cape=trim)
        it = S.layer()
        if suit == "pentacles":
            i_pent(it, 19, 40, 6)
        elif suit == "wands":
            i_wand(it, 19, 38, 32)
        elif suit == "swords":
            i_sword(it, 19, 30, 26)
        else:
            i_cup(it, 19, 38, 12)


# ---- card frame + font --------------------------------------------------------
FONT = {
    "A": [".#.", "#.#", "###", "#.#", "#.#"], "B": ["##.", "#.#", "##.", "#.#", "##."],
    "C": [".##", "#..", "#..", "#..", ".##"], "D": ["##.", "#.#", "#.#", "#.#", "##."],
    "E": ["###", "#..", "##.", "#..", "###"], "F": ["###", "#..", "##.", "#..", "#.."],
    "G": [".##", "#..", "#.#", "#.#", ".##"], "H": ["#.#", "#.#", "###", "#.#", "#.#"],
    "I": ["###", ".#.", ".#.", ".#.", "###"], "J": ["..#", "..#", "..#", "#.#", ".#."],
    "K": ["#.#", "#.#", "##.", "#.#", "#.#"], "L": ["#..", "#..", "#..", "#..", "###"],
    "M": ["#...#", "##.##", "#.#.#", "#...#", "#...#"], "N": ["#..#", "##.#", "#.##", "#..#", "#..#"],
    "O": [".#.", "#.#", "#.#", "#.#", ".#."], "P": ["##.", "#.#", "##.", "#..", "#.."],
    "Q": [".#.", "#.#", "#.#", "##.", ".##"], "R": ["##.", "#.#", "##.", "#.#", "#.#"],
    "S": [".##", "#..", ".#.", "..#", "##."], "T": ["###", ".#.", ".#.", ".#.", ".#."],
    "U": ["#.#", "#.#", "#.#", "#.#", "###"], "V": ["#.#", "#.#", "#.#", "#.#", ".#."],
    "W": ["#...#", "#...#", "#.#.#", "##.##", "#...#"], "X": ["#.#", "#.#", ".#.", "#.#", "#.#"],
    "Y": ["#.#", "#.#", ".#.", ".#.", ".#."], "Z": ["###", "..#", ".#.", "#..", "###"],
    "0": [".#.", "#.#", "#.#", "#.#", ".#."], " ": ["..", "..", "..", "..", ".."],
}


def text_w(s):
    return sum(len(FONT[c][0]) + 1 for c in s) - 1


def text(im, s, cx, y, col):
    x = cx - text_w(s) // 2
    for ch in s:
        g = FONT[ch]
        for r, row in enumerate(g):
            for c, v in enumerate(row):
                if v == "#":
                    im.putpixel((x + c, y + r), col + (255,))
        x += len(g[0]) + 1


def mini_icon(im, suit, cx, cy, col):
    pat = {
        "wands": ["..#", ".#.", "#.."],
        "cups": ["###", ".#.", "###"],
        "swords": [".#.", "###", ".#."],
        "pentacles": [".#.", "#.#", ".#."],
        "major": [".#.", "###", ".#."],
    }[suit]
    for r, row in enumerate(pat):
        for c, v in enumerate(row):
            if v == "#":
                im.putpixel((cx - 1 + c, cy - 1 + r), col + (255,))


def frame(art, top, label, suit):
    im = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    fc = SUIT_FRAME[suit]
    d.rectangle([0, 0, CW - 1, CH - 1], fill=K)
    d.rectangle([1, 1, CW - 2, CH - 2], fill=fc)
    d.rectangle([3, 3, CW - 4, CH - 4], fill=K)
    d.rectangle([4, 4, CW - 5, CH - 5], fill=CREAM)
    for (x, y) in ((2, 2), (CW - 3, 2), (2, CH - 3), (CW - 3, CH - 3)):
        d.point((x, y), fill=GOLD if suit == "major" else sh(fc))
    d.rectangle([4, 13, CW - 5, 92], fill=K)
    im.paste(art, (5, 14))
    text(im, top, CW // 2, 6, K)
    w = text_w(top)
    mini_icon(im, suit, CW // 2 - w // 2 - 5, 8, fc if suit != "major" else GOLDD)
    mini_icon(im, suit, CW // 2 + w // 2 + 5, 8, fc if suit != "major" else GOLDD)
    lines = label.split("|")
    if len(lines) == 1:
        text(im, lines[0], CW // 2, 98, K)
    else:
        text(im, lines[0], CW // 2, 95, K)
        text(im, lines[1], CW // 2, 101, K)
    for (x, y) in ((0, 0), (CW - 1, 0), (0, CH - 1), (CW - 1, CH - 1)):
        im.putpixel((x, y), (0, 0, 0, 0))
    return im


def card_back():
    """裏面。上下左右対称(逆位置が裏から見えないように)。"""
    im = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    l = L(CW, CH)
    l.rect(0, 0, CW - 1, CH - 1, K)
    l.rect(1, 1, CW - 2, CH - 2, PUR)
    l.rect(3, 3, CW - 4, CH - 4, K)
    l.rect(4, 4, CW - 5, CH - 5, NAVY)
    for y in range(4, CH - 4):
        for x in range(4, CW - 4):
            if (x + y) % 8 == 0 or (x - y) % 8 == 0:
                l.px(x, y, PURD)
    for (x0, y0, x1, y1) in ((7, 7, CW - 8, 7), (7, CH - 8, CW - 8, CH - 8), (7, 7, 7, CH - 8), (CW - 8, 7, CW - 8, CH - 8)):
        l.line([(x0, y0), (x1, y1)], GOLDD)
    cx, cy = CW // 2, CH // 2
    l.ell(cx, cy, 16, 16, NIGHT)
    l.ring(cx, cy, 16, 16, GOLD)
    for i in range(8):
        a = i * math.pi / 4
        rr = 13 if i % 2 == 0 else 9
        l.line([(cx, cy), (cx + math.cos(a) * rr, cy + math.sin(a) * rr)], GOLD if i % 2 == 0 else GOLDD)
    l.ell(cx, cy, 4, 4, YEL)
    l.ell(cx, cy, 2, 2, WHT)
    for dy in (-34, 34):
        l.ell(cx, cy + dy, 5, 5, YEL)
        l.ell(cx + (3 if dy < 0 else -3), cy + dy, 4, 4, NAVY)
    for (dx, dy) in ((-18, -40), (18, -40), (-18, 40), (18, 40), (-22, 0), (22, 0)):
        l.px(cx + dx, cy + dy, WHT)
        for ox, oy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            l.px(cx + dx + ox, cy + dy + oy, PALE)
    for (x, y) in ((2, 2), (CW - 3, 2), (2, CH - 3), (CW - 3, CH - 3)):
        l.px(x, y, GOLD)
    im = l.im
    # 上下対称を保証(三日月は向きが違うので、上の帯を下へ点対称で写す)
    top = im.crop((0, 0, CW, 39))  # 中央の紋章(y40〜72)は触らない
    im.paste(top.rotate(180), (0, CH - 39))
    for (x, y) in ((0, 0), (CW - 1, 0), (0, CH - 1), (CW - 1, CH - 1)):
        im.putpixel((x, y), (0, 0, 0, 0))
    return im


def split_label(s):
    if "|" in s or text_w(s) <= 48:
        return s
    if " OF " in s:
        a, _, b = s.partition(" OF ")
        return f"{a}|OF {b}"
    a, _, b = s.partition(" ")
    return f"{a}|{b}"


def build():
    cards = []
    for i, (rom, name, fn) in enumerate(MAJORS):
        S = Scene(); fn(S)
        cards.append((f"m{i:02d}", frame(S.render(), rom, split_label(name), "major")))
    for suit in SUITS:
        for n in range(1, 11):
            S = Scene()
            minor_ace(S, suit) if n == 1 else minor_pip(S, suit, n)
            cards.append((f"{suit}_{n:02d}", frame(S.render(), ROMAN[n - 1], split_label(f"{NUM[n-1]} OF {suit.upper()}"), suit)))
        for ci, (cname, ch) in enumerate(COURTS):
            S = Scene(); minor_court(S, suit, ci)
            cards.append((f"{suit}_{11+ci}_{cname.lower()}", frame(S.render(), ch, split_label(f"{cname} OF {suit.upper()}"), suit)))
    return cards


def sheet(cards, cols, scale, bg=(36, 30, 46)):
    rows = math.ceil(len(cards) / cols)
    g = 4
    sh_ = Image.new("RGBA", (cols * (CW + g) + g, rows * (CH + g) + g), bg + (255,))
    for i, (_, im) in enumerate(cards):
        sh_.alpha_composite(im, (g + (i % cols) * (CW + g), g + (i // cols) * (CH + g)))
    return sh_.resize((sh_.width * scale, sh_.height * scale), Image.NEAREST)


def main():
    cards = build()
    (OUT / "cards").mkdir(parents=True, exist_ok=True)
    (OUT / "cards4x").mkdir(parents=True, exist_ok=True)
    for name, im in cards:
        im.save(OUT / "cards" / f"{name}.png")
        im.resize((CW * 4, CH * 4), Image.NEAREST).save(OUT / "cards4x" / f"{name}.png")
    cards.append(("back", card_back()))
    for name, im in cards[-1:]:
        im.save(OUT / "cards" / f"{name}.png")
        im.resize((CW * 4, CH * 4), Image.NEAREST).save(OUT / "cards4x" / f"{name}.png")
    cards.pop()
    sheet(cards[:22], 11, 3).save(OUT / "sheet_major.png")
    sheet(cards[22:], 14, 2).save(OUT / "sheet_minor.png")
    print(len(cards), "cards ->", OUT)


if __name__ == "__main__":
    main()
