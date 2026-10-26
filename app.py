"""PIXEL TAROT // ケルト十字

自作ピクセルタロット(78枚)でケルト十字に10枚引き、ロード中のローカルLLMに鑑定文を書かせる。
- カード絵: tarot.py が書き出す out/cards/*.png(64x112)。無ければ起動時に作る
- LLM: 動いている llama-server を /proc から探して自動で使う(HOSHIYOMI LOG と同じ見方)
- 履歴: ~/.pixel-tarot/history.jsonl に1行1回

起動:  ./run.sh
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
import random
import re
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from PyQt6.QtCore import QDate, QElapsedTimer, QPointF, QRectF, Qt, QThread, QTime, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QConicalGradient, QFont, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient, QTransform
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QSplitter, QTabWidget, QTimeEdit, QVBoxLayout,
    QWidget,
)

import enochian as EN
from cards_data import BY_ID, CARDS, HOUSES, OPPOSE, PLANET_GLYPH, POSITIONS, SIGN_ELEMENT, in_zone

HERE = Path(__file__).resolve().parent
CARD_DIR = HERE / "out" / "cards"
DATA_DIR = Path.home() / ".pixel-tarot"
HISTORY = DATA_DIR / "history.jsonl"
PEOPLE = DATA_DIR / "people.json"  # 自分以外の出生データ(この端末だけ・600)
# ホロスコープ✕タロット: 天体計算と出生データは HOSHIYOMI LOG のものを借りる(向こうは一切書き換えない)
# HOSHIYOMI LOG(https://github.com/muuchan0279/hoshiyomi-log)の置き場所。環境変数 → 隣のフォルダ(2つの名前)の順に探す
HOSHIYOMI_DIR = next((d for d in [Path(os.environ["PIXEL_TAROT_HOSHIYOMI"])] if d.exists()), None) \
    if os.environ.get("PIXEL_TAROT_HOSHIYOMI") else None
HOSHIYOMI_DIR = HOSHIYOMI_DIR or next((HERE.parent / n for n in ("hoshiyomi", "hoshiyomi-log") if (HERE.parent / n).exists()),
                                      HERE.parent / "hoshiyomi-log")
HOSHIYOMI_DB = Path.home() / ".hoshiyomi" / "hoshiyomi.db"
GLYPH_FONT = "DejaVu Sans"
LIL_TXT = "#c39bff"   # 黄金の夜明けの対応表示
WHITE_GLOW = "#fffbe0"
GOLD_HEX = "#dea628"

# ───────────────────────── テーマ（HOSHIYOMI LOG と同じ Pixel × Neon） ─────────────────────────
BG = "#07070f"
PANEL = "#0d0d1c"
CYAN = "#00f0ff"
MAGENTA = "#ff2bd6"
YELLOW = "#f8ff4a"
GREEN = "#39ff8f"
DIM = "#3a4a66"
TEXT = "#d8f7ff"
FONT_STACK = ["DotGothic16", "PixelMplus12", "Noto Sans CJK JP", "sans-serif"]

QSS = f"""
* {{ color: {TEXT}; font-size: 13px; }}
QMainWindow, QWidget {{ background: {BG}; }}
QTabWidget::pane {{ border: 1px solid {DIM}; top: -1px; }}
QTabBar::tab {{ background: {PANEL}; border: 1px solid {DIM}; padding: 6px 14px; margin-right: 2px; color: {DIM}; }}
QTabBar::tab:selected {{ color: {CYAN}; border-color: {CYAN}; border-bottom: 2px solid {MAGENTA}; }}
QPlainTextEdit, QListWidget {{ background: {PANEL}; border: 1px solid {DIM}; selection-background-color: {MAGENTA}; padding: 4px; }}
QPlainTextEdit:focus {{ border-color: {CYAN}; }}
QPushButton {{ background: {PANEL}; border: 1px solid {CYAN}; color: {CYAN}; padding: 6px 12px; }}
QPushButton:hover {{ background: #00303a; }}
QPushButton:pressed {{ background: {CYAN}; color: {BG}; }}
QPushButton:disabled {{ border-color: {DIM}; color: {DIM}; }}
QPushButton#hot {{ border-color: {MAGENTA}; color: {MAGENTA}; }}
QPushButton#hot:hover {{ background: #3a0030; }}
QLabel#h {{ color: {CYAN}; font-size: 15px; letter-spacing: 2px; }}
QLabel#sub {{ color: {DIM}; }}
QSplitter::handle {{ background: {DIM}; }}
QLineEdit, QDateEdit, QTimeEdit, QDoubleSpinBox, QComboBox {{
    background: {PANEL}; border: 1px solid {DIM}; selection-background-color: {MAGENTA}; padding: 4px; }}
QComboBox QAbstractItemView {{ background: {PANEL}; selection-background-color: {MAGENTA}; }}
QLabel {{ background: transparent; }}
QCheckBox::indicator {{ width: 12px; height: 12px; border: 1px solid {CYAN}; background: {PANEL}; }}
QCheckBox::indicator:checked {{ background: {MAGENTA}; }}
"""


_UI_FONT = None


def ui_font() -> str:
    global _UI_FONT  # 描画のたびにフォント一覧を引くと重いので1回だけ
    if _UI_FONT is None:
        from PyQt6.QtGui import QFontDatabase
        available = set(QFontDatabase.families())
        _UI_FONT = next((f for f in FONT_STACK if f in available), "sans-serif")
    return _UI_FONT


def glow(widget, color=CYAN, radius=16):
    eff = QGraphicsDropShadowEffect(widget)
    eff.setColor(QColor(color))
    eff.setBlurRadius(radius)
    eff.setOffset(0, 0)
    widget.setGraphicsEffect(eff)
    return widget


def heading(text, color=CYAN):
    lb = QLabel(text)
    lb.setObjectName("h")
    lb.setStyleSheet(f"color:{color};")
    return glow(lb, color, 14)


# ───────────────────────── LLM ─────────────────────────
SYSTEM_PROMPT = """あなたは経験豊かなタロット占い師です。ケルト十字スプレッドで引かれた10枚のカードと相談内容をもとに、日本語で鑑定文を書いてください。
ルール:
- 相談内容に正面から答える。相談が空なら、相談者のいまの全体運として読む。
- 最初に全体の印象を2〜3文で(大アルカナの多さ、目立つスート、逆位置の多さが示すこと)。
- 次に10枚を位置の順に読む。各カードは「1. 現在 — 愚者(正位置)」の形の見出しを1行置き、その下に位置の意味とカードの意味を結びつけて2〜3文。
- 最後に「まとめ」の見出しで、結果のカードを他のカード(特に現在・障害・近い未来・願望と恐れ)とのつながりから読み、全体の流れと具体的な行動のヒントを1〜2個。
- 与えられたキーワードは手がかりであり、そのまま並べず文章にする。
- [黄金の夜明け] は黄金の夜明け団の対応(ヘブライ文字・惑星・星座・デカン・元素)。読みの裏づけとして、要所で1〜2回さりげなく使う(全部のカードで説明しない)。
- 不幸を断定する予言はしない。病気・法律・お金の判断を占いで代わりに決めない。
- Markdown の記号(#, **, - など)は使わない。全体で1200〜1800字。"""

HORO_PROMPT = """あなたはタロットと西洋占星術の両方に通じた占い師です。占う相手の出生図の12ハウスに1枚ずつ、さらに中央に1枚タロットを置く「ホロスコープ・スプレッド」を読みます。日本語で鑑定文を書いてください。
ルール:
- 主役はタロット。各ハウスのカードを、そのハウスが表す生活の分野で読む。そのハウスのサイン・出生時の天体・今日通過中の天体は、カードの読みに色や時期を添える背景として使う(天体が無いハウスはカードだけで読んでよい)。
- 相談内容があればそれに関係の深いハウスを厚めに読む。空なら、いまの全体運として読む。
- 占う相手の名前が与えられたら「〇〇さん」と呼びかけて書く。名前が無ければ「あなた」。
- 最初に「全体のテーマ」として中央のカードを読み、大アルカナの多さや逆位置の多さにも触れる(2〜4文)。
- 次に第1〜第12ハウスを順に読む。各ハウスは「第1ハウス(自分) — 愚者(正位置)」の形の見出しを1行置き、その下に1〜3文。
- 最後に「まとめ」の見出しで、カードと星が一緒に強く示している分野を2〜3つ挙げ、具体的な行動のヒントを1〜2個。
- 与えられたキーワードは手がかりであり、そのまま並べず文章にする。
- [黄金の夜明け] は黄金の夜明け団の対応(ヘブライ文字・惑星・星座・デカン・元素)。カードと星をつなぐ橋として使う。
- 「共鳴」と書かれたカードは、カードの対応する星や星座が実際の星図と重なっている。偶然引いたカードが星と一致した特別なしるしとして、そのハウスは他より厚く読み、まとめでも必ず触れる。「共鳴★」はさらに強い。共鳴・共鳴★は与えられたカードにだけ、与えられたとおりの強さで書く(書かれていないカードを共鳴と呼ばない)。逆に「元素が反発」はカードの力が弱まる・空回りしやすいと読む。
- 不幸を断定する予言はしない。病気・法律・お金の判断を占いで代わりに決めない。
- Markdown の記号(#, **, - など)は使わない。全体で1600〜2400字。"""


class LLMWorker(QThread):
    chunk = pyqtSignal(str)
    done = pyqtSignal(str, bool)  # 全文 or エラー文, ok

    def __init__(self, base_url: str, model: str, prompt, llama: bool = True, system: str = SYSTEM_PROMPT,
                 temperature: float = 0.85, max_tokens: int = 3000):
        super().__init__()
        self.temperature, self.max_tokens = temperature, max_tokens  # prompt は文字列 or 会話の list
        self.base_url, self.model, self.prompt, self.llama = base_url.rstrip("/"), model, prompt, llama
        self.system = system
        self.stop = False

    def run(self):
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": self.system}] + (
                self.prompt if isinstance(self.prompt, list) else [{"role": "user", "content": self.prompt}]),
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": True,
        }
        if self.llama:
            # Qwen3 系は思考を切らないと content が空のまま reasoning_content に全部入る
            body["chat_template_kwargs"] = {"enable_thinking": False}
        buf = ""
        try:
            req = urllib.request.Request(
                f"{self.base_url}/chat/completions", data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=300) as r:
                for raw in r:
                    if self.stop:
                        break
                    line = raw.decode(errors="replace").strip()
                    if not line.startswith("data:"):
                        continue
                    d = line[5:].strip()
                    if d == "[DONE]":
                        break
                    j = json.loads(d)
                    ch = (j.get("choices") or [{}])[0]
                    delta = (ch.get("delta") or {}).get("content") or (ch.get("message") or {}).get("content") or ""
                    if delta:
                        buf += delta
                        self.chunk.emit(delta)
            text = re.sub(r"<think>.*?</think>", "", buf, flags=re.S).strip()
            if not text:
                raise ValueError("返事が空でした(思考モードのまま max_tokens を使い切った可能性)")
            self.done.emit(text, True)
        except Exception as e:  # noqa: BLE001
            self.done.emit(f"{type(e).__name__}: {e}", False)


# ロード中のローカルLLMを探す。動いている llama-server のコマンドラインを読むだけ(nvidia-smi は叩かない)
def find_llama_servers() -> list[dict]:
    found = []
    for d in Path("/proc").iterdir():
        if not d.name.isdigit():
            continue
        try:
            raw = (d / "cmdline").read_bytes()
        except OSError:
            continue
        args = [a.decode(errors="replace") for a in raw.split(b"\0") if a]
        if not args or Path(args[0]).name != "llama-server":
            continue
        srv = {"pid": int(d.name), "port": 8080, "model_path": None, "ctx": None, "alias": None}
        for i, a in enumerate(args[:-1]):
            nxt = args[i + 1]
            if a in ("-m", "--model"):
                srv["model_path"] = nxt
            elif a == "--port" and nxt.isdigit():
                srv["port"] = int(nxt)
            elif a in ("-c", "--ctx-size") and nxt.isdigit():
                srv["ctx"] = int(nxt)
            elif a in ("-a", "--alias"):
                srv["alias"] = nxt
        mp = srv["model_path"]
        srv["name"] = srv["alias"] or (Path(mp).name.removesuffix(".gguf") if mp else "llama-server")
        found.append(srv)
    found.sort(key=lambda s: (s["port"] != 8000, s["port"]))
    return found


def probe_server(srv: dict) -> dict:
    """/v1/models で生死と model id を確かめる。読み込み中の llama-server は 503 を返す"""
    url = srv.get("url") or f"http://127.0.0.1:{srv['port']}/v1"
    srv = dict(srv, url=url, state="down", model_id=srv["name"])
    try:
        with urllib.request.urlopen(f"{url}/models", timeout=2) as r:
            data = json.loads(r.read())
        ids = [m.get("id") for m in data.get("data", []) if m.get("id")]
        srv["model_id"] = ids[0] if ids else srv["name"]
        srv["state"] = "ready"
    except urllib.error.HTTPError as e:
        srv["state"] = "loading" if e.code == 503 else "down"
    except Exception:  # noqa: BLE001
        pass
    return srv


class LLMProbe(QThread):
    found = pyqtSignal(list)

    def run(self):
        override = os.environ.get("PIXEL_TAROT_LLM_URL")  # テスト用: 決め打ちの OpenAI 互換先
        if override:
            self.found.emit([probe_server({"name": "override", "port": 0, "ctx": None, "url": override.rstrip("/")})])
            return
        self.found.emit([probe_server(s) for s in find_llama_servers()])


# ───────────────────────── 引く・読む ─────────────────────────
def draw_spread(reversals: bool, rng=None, n: int = 10) -> list[tuple[str, bool]]:
    rng = rng or random.SystemRandom()
    deck = [c["id"] for c in CARDS]
    rng.shuffle(deck)
    return [(cid, reversals and rng.random() < 0.5) for cid in deck[:n]]


def card_line(i: int, cid: str, rev: bool, positions=POSITIONS) -> str:
    c = BY_ID[cid]
    pos, pdesc = positions[i]
    return (f"{i + 1}. {pos}({pdesc}): {c['ja']} {c['en']} / {'逆位置' if rev else '正位置'}"
            f" — キーワード: {c['rev'] if rev else c['up']} [黄金の夜明け: {c['gd']['text']}]")


def stats(spread) -> str:
    major = sum(BY_ID[c]["major"] for c, _ in spread)
    suits = Counter(c.split("_")[0] for c, _ in spread if not BY_ID[c]["major"])
    rev = sum(r for _, r in spread)
    ja = {"wands": "ワンド", "cups": "カップ", "swords": "ソード", "pentacles": "ペンタクル"}
    s = "・".join(f"{ja[k]}{v}" for k, v in suits.most_common()) or "なし"
    return f"大アルカナ {major}枚 / 小アルカナのスート内訳 {s} / 逆位置 {rev}枚"


def build_prompt(question: str, spread) -> str:
    q = question.strip() or "(特に質問なし。全体運として)"
    lines = [f"相談: {q}", "", "引いたカード:"]
    lines += [card_line(i, c, r) for i, (c, r) in enumerate(spread)]
    lines += ["", f"全体: {stats(spread)}"]
    return "\n".join(lines)


def read_hoshiyomi_settings() -> dict:
    """HOSHIYOMI LOG の設定(出生データ)を読み取り専用で開く。無ければ空"""
    if not HOSHIYOMI_DB.exists():
        return {}
    con = sqlite3.connect(f"file:{HOSHIYOMI_DB}?mode=ro", uri=True)
    try:
        return dict(con.execute("SELECT key, value FROM settings").fetchall())
    finally:
        con.close()


class Astro:
    """HOSHIYOMI LOG の astro_core を借りて、出生図と今日の星を作る。ハウスはホールサイン(向こうと同じ)"""

    def __init__(self):
        self.A = None
        self.natal = None
        self.transit = None
        self.aspects = []
        self.error = ""
        self.who = "自分"

    def load(self, person: dict | None = None, when: datetime | None = None) -> bool:
        """person=None なら自分(HOSHIYOMI LOG の出生データ)。when=None なら今の星"""
        self.who = person["name"] if person else "自分"
        try:
            if self.A is None:
                path = HOSHIYOMI_DIR / "astro_core.py"
                if not path.exists():
                    raise FileNotFoundError(f"{path} が見つかりません")
                spec = importlib.util.spec_from_file_location("hoshiyomi_astro_core", path)
                mod = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = mod  # dataclass は sys.modules から自分のモジュールを引くので先に登録
                try:
                    spec.loader.exec_module(mod)
                except Exception:
                    sys.modules.pop(spec.name, None)
                    raise
                self.A = mod
            A = self.A
            st = person if person else read_hoshiyomi_settings()
            self.natal = None
            if st.get("birth_date"):
                y, m, d = map(int, st["birth_date"].split("-"))
                bt = st.get("birth_time")
                hh, mm = (map(int, bt.split(":")) if bt else (None, 0))
                self.natal = A.natal_chart(
                    y, m, d, hh, mm, float(st.get("utc_offset") or 9.0),
                    float(st["lat"]) if st.get("lat") else None,
                    float(st["lon"]) if st.get("lon") else None,
                )
            now = (when or datetime.now()).astimezone()
            self.transit = A.compute_chart(now.replace(tzinfo=None) - (now.utcoffset() or timedelta(0)))
            self.aspects = A.transit_aspects(self.transit, self.natal) if self.natal else []
            self.error = ""
        except Exception as e:  # noqa: BLE001
            self.error = f"{type(e).__name__}: {e}"
        return not self.error

    @property
    def has_houses(self) -> bool:
        return bool(self.natal and self.natal.asc is not None)

    def house_sign(self, k: int) -> int:
        """第kハウス(1〜12)のサイン番号。出生時刻が無ければ牡羊座=第1のナチュラルハウス"""
        base = int(self.natal.asc // 30) if self.has_houses else 0
        return (base + k - 1) % 12

    def sign_name(self, i: int) -> str:
        return self.A.SIGNS[i][0]

    def natal_in(self, k: int):
        return [b for b in (self.natal.bodies if self.natal else []) if b.sign_index == self.house_sign(k)]

    def transit_in(self, k: int):
        return [b for b in (self.transit.bodies if self.transit else []) if b.sign_index == self.house_sign(k)]

    def house_facts(self, k: int) -> str:
        if not self.A or not self.transit:
            return "星図なし"
        nat = "・".join(b.name + ("(逆行)" if b.retro else "") for b in self.natal_in(k)) or "なし"
        tr = "・".join(b.name + ("(逆行)" if b.retro else "") for b in self.transit_in(k)) or "なし"
        return f"サイン {self.sign_name(self.house_sign(k))} / 出生時の天体 {nat} / 今日通過中 {tr}"


def resonance(astro: "Astro", k: int, cid: str) -> tuple[int, list[str], list[tuple[bool, str]]]:
    """第kハウス(1〜12、13=中央)に置いたカードと星図の共鳴。
    戻り値=(点数, 理由, 線を引く天体[(今の星か, 惑星名)])。4点以上で共鳴、6点以上で強い共鳴
    (ランダムに13枚引いて試すと、共鳴は平均1.2枚・強い共鳴が出るのは3回に1回ほど)"""
    g = BY_ID[cid]["gd"]
    if not astro.A or not astro.transit:
        return 0, [], []
    score, why, hits = 0, [], []
    house = k <= 12
    if g["planet"] and house:
        pl = g["planet"]
        if any(b.name == pl for b in astro.transit_in(k)):
            score += 3
            why.append(f"対応星の{pl}が今このハウスを通過中")
            hits.append((True, pl))
        if any(b.name == pl for b in astro.natal_in(k)):
            score += 2
            why.append(f"対応星の{pl}が出生図でこのハウスにある")
            hits.append((False, pl))
    if house and g["signs"] and astro.house_sign(k) in g["signs"]:
        score += 2
        why.append(f"このハウスのサイン({astro.sign_name(astro.house_sign(k))})がカードの対応サイン")
    if g["zone"]:
        # 範囲に入った天体は何個あっても1回だけ数える(サイン1つを受け持つ大アルカナが点を稼ぎすぎないように)
        width = (g["zone"][1] - g["zone"][0]) % 360 or 360
        now_in = [b.name for b in astro.transit.bodies if in_zone(b.lon, g["zone"])]
        if now_in:
            score += 3 if width <= 10 else 2
            why.append(f"今の{'・'.join(now_in)}がカードの受け持つ度数に入っている")
            hits += [(True, n) for n in now_in]
        nat_in = [b.name for b in (astro.natal.bodies if astro.natal else []) if in_zone(b.lon, g["zone"])]
        if nat_in:
            score += 1
            why.append(f"出生時の{'・'.join(nat_in)}がカードの受け持つ度数にある")
            hits += [(False, n) for n in nat_in]
    if house and g["element"]:
        hel = SIGN_ELEMENT[astro.house_sign(k)]
        if hel == g["element"]:
            score += 1
            why.append(f"元素が同じ({hel})")
        elif OPPOSE[hel] == g["element"]:
            score -= 1
            why.append(f"元素が反発(カード{g['element']}・ハウス{hel})")
    return score, why, hits


def res_mark(score: int) -> str:
    return "共鳴★" if score >= 6 else "共鳴" if score >= 4 else ""


def build_horo_prompt(question: str, spread, astro: Astro) -> str:
    q = question.strip() or "(特に質問なし。全体運として)"
    lines = [f"相談: {q}", ""]
    if astro.who != "自分":
        lines.insert(0, f"占う相手: {astro.who}さん")
    if astro.error or not astro.A:
        lines.append("(星図を計算できなかったので、星の情報は無し。カードとハウスの意味だけで読む)")
    elif not astro.natal:
        lines.append("(出生データが無いので、ハウスは牡羊座を第1ハウスとするナチュラルハウス。出生時の天体は無し)")
    elif not astro.has_houses:
        lines.append("(出生時刻が不明なので、ハウスは牡羊座を第1ハウスとするナチュラルハウスで代用)")
    lines.append(card_line(12, *spread[12], HOUSES).split(". ", 1)[1])  # 中央は番号なし
    sc, why, _ = resonance(astro, 13, spread[12][0])
    if why:
        lines.append(f"    {res_mark(sc) or '星との関係'}: {'・'.join(why)}")
    lines.append("")
    for k in range(1, 13):
        lines.append(card_line(k - 1, *spread[k - 1], HOUSES))
        lines.append(f"    星: {astro.house_facts(k)}")
        sc, why, _ = resonance(astro, k, spread[k - 1][0])
        if why:
            lines.append(f"    {res_mark(sc) or '星との関係'}: {'・'.join(why)}")
    lines += ["", "今日の星と出生図のアスペクト(オーブ小さい順):"]
    lines += [f"- {a.label()}" for a in astro.aspects[:6]] or ["- 目立つアスペクトなし"]
    lines += ["", f"全体: {stats(spread)}"]
    return "\n".join(lines)


def load_history() -> list[dict]:
    if not HISTORY.exists():
        return []
    out = []
    for line in HISTORY.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def append_history(rec: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with HISTORY.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ───────────────────────── ケルト十字の盤面 ─────────────────────────
CW, CH = 64, 112
LW, LH = 400, 490          # 盤面の論理サイズ(カード1x基準)
CX, CY = 145, 245          # 十字の中心
STAFF_X = CX + 212
LAYOUT = [  # (中心x, 中心y, 90°回転)
    (CX, CY, False),                 # 1 現在
    (CX, CY, True),                  # 2 障害(横向きに重ねる)
    (CX, CY + CH + 8, False),        # 3 根底
    (CX - 100, CY, False),           # 4 過去
    (CX, CY - CH - 8, False),        # 5 目標
    (CX + 100, CY, False),           # 6 近い未来
    (STAFF_X, 425, False),           # 7 本人(杖は下から上へ)
    (STAFF_X, 305, False),           # 8 周囲
    (STAFF_X, 185, False),           # 9 願望と恐れ
    (STAFF_X, 65, False),            # 10 結果
]


def card_rect(i: int) -> QRectF:
    x, y, rot = LAYOUT[i]
    w, h = (CH, CW) if rot else (CW, CH)
    return QRectF(x - w / 2, y - h / 2, w, h)


ROMAN = ["0", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV",
         "XV", "XVI", "XVII", "XVIII", "XIX", "XX", "XXI"]


class DealAnim:
    """配る→1枚ずつめくる→大アルカナは光る、の時間割。時刻はすべてこの時計から(秒)。
    大アルカナの後は演出を見せるために次をめくるまで間をあける。"""
    FLY, STAGGER, PAUSE, GAP, FLIP, MAJOR_HOLD, BURST = 0.40, 0.07, 0.15, 0.22, 0.26, 0.55, 1.2

    def __init__(self):
        self.clock = QElapsedTimer()
        self.n = 0
        self.majors: list[bool] = []
        self.active = False

    def start(self, spread):
        self.n = len(spread)
        self.majors = [BY_ID[c]["major"] for c, _ in spread]
        self.clock.start()
        self.active = True

    def finish(self):
        self.active = False

    def t(self) -> float:
        return self.clock.elapsed() / 1000 if self.active else 1e9

    def flip_start(self, i: int) -> float:
        base = self.n * self.STAGGER + self.FLY + self.PAUSE
        return base + i * self.GAP + self.MAJOR_HOLD * sum(self.majors[:i])

    def state(self, i: int):
        """(飛んでいる進み0〜1, 表か, 横の縮み0〜1, 大アルカナ演出の経過秒 or None)"""
        if not self.active:
            return 1.0, True, 1.0, None
        t = self.t()
        fly = min(1.0, max(0.0, (t - i * self.STAGGER) / self.FLY))
        fly = 1 - (1 - fly) ** 3
        fs = self.flip_start(i)
        if t < fs:
            return fly, False, 1.0, None
        ft = (t - fs) / self.FLIP
        if ft < 0.5:
            return 1.0, False, max(0.06, 1 - 2 * ft), None
        if ft < 1:
            return 1.0, True, max(0.06, 2 * ft - 1), None
        bt = t - fs - self.FLIP
        return 1.0, True, 1.0, (bt if self.majors[i] and bt < self.BURST else None)

    def revealed(self) -> int:
        t = self.t()
        return sum(1 for i in range(self.n) if t >= self.flip_start(i) + self.FLIP)

    def done(self) -> bool:
        return not self.active or self.t() > self.flip_start(self.n - 1) + self.FLIP + self.BURST


def draw_burst(p: QPainter, c: QPointF, bt: float, u: float, seed: int, cw: float, ch: float, label: str, font_px: float):
    """大アルカナが表になった瞬間の演出。u=ドット1個ぶんの大きさ(描き先の単位で)。"""
    k = bt / DealAnim.BURST
    fade = 1 - k
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.translate(c)
    # カードが白く光る
    if bt < 0.3:
        w = QColor(WHITE_GLOW)
        w.setAlpha(int(220 * (1 - bt / 0.3)))
        p.fillRect(QRectF(-cw / 2, -ch / 2, cw, ch), w)
    # 回る金の光線
    for j in range(12):
        a = math.radians(j * 30 + bt * 45)
        r0 = (ch * 0.45) + 18 * u * k
        r1 = r0 + (14 + 30 * k) * u * (0.6 if j % 2 else 1.0)
        col = QColor(YELLOW if j % 2 == 0 else GOLD_HEX)
        col.setAlpha(int(230 * fade))
        p.setPen(QPen(col, 2 * u))
        p.drawLine(QPointF(math.cos(a) * r0, math.sin(a) * r0), QPointF(math.cos(a) * r1, math.sin(a) * r1))
    # 広がる輪
    ring = QColor(YELLOW)
    ring.setAlpha(int(255 * fade))
    p.setPen(QPen(ring, 1.5 * u))
    p.setBrush(Qt.BrushStyle.NoBrush)
    rr = ch * 0.55 + 70 * u * k
    p.drawEllipse(QPointF(0, 0), rr, rr)
    # ピクセルの火花(重力つき・角はとがらせたまま)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    rnd = random.Random(seed)
    for j in range(26):
        ang = rnd.random() * math.tau
        spd = (50 + rnd.random() * 80) * u
        x = math.cos(ang) * spd * bt
        y = math.sin(ang) * spd * bt + 70 * u * bt * bt
        sz = (2 if rnd.random() < 0.6 else 3) * u
        col = QColor(rnd.choice([YELLOW, WHITE_GLOW, WHITE_GLOW, MAGENTA, CYAN]))
        col.setAlpha(int(255 * min(1.0, fade * 1.6)))
        p.fillRect(QRectF(x - sz / 2, y - sz / 2, sz, sz), col)
    # 名前の札
    a = min(1.0, bt / 0.15) * min(1.0, fade * 2.5)
    f = QFont(ui_font())
    f.setPixelSize(max(8, int(font_px)))
    p.setFont(f)
    tw = p.fontMetrics().horizontalAdvance(label) + 10 * u
    box = QRectF(-tw / 2, -ch / 2 - font_px - 10 * u, tw, font_px + 6 * u)
    bg = QColor(BG)
    bg.setAlpha(int(230 * a))
    p.fillRect(box, bg)
    pen = QColor(YELLOW)
    pen.setAlpha(int(255 * a))
    p.setPen(QPen(pen, 1))
    p.drawRect(box)
    p.drawText(box, Qt.AlignmentFlag.AlignCenter, label)
    p.restore()


def major_label(cid: str) -> str:
    c = BY_ID[cid]
    return f"{ROMAN[int(cid[1:])]}  {c['ja']}"


class SpreadView(QWidget):
    picked = pyqtSignal(int)

    def __init__(self, pix: dict[str, QPixmap]):
        super().__init__()
        self.pix = pix
        self.spread: list[tuple[str, bool]] = []
        self.revealed = 0
        self.selected = -1
        self.setMinimumSize(LW // 1, LH // 1)
        self.setMouseTracking(True)
        self.deal = DealAnim()
        self._timer = QTimer(self, interval=16, timeout=self._tick)  # 配っている間だけ回す

    def set_spread(self, spread, animate=True):
        self.spread = spread
        self.selected = -1
        if animate and spread:
            self.deal.start(spread)
            self.revealed = 0
            self._timer.start()
        else:
            self.deal.finish()
            self.revealed = len(spread)
        self.update()

    def _tick(self):
        self.revealed = self.deal.revealed()
        if self.deal.done():
            self.deal.finish()
            self.revealed = len(self.spread)
            self._timer.stop()  # 配り終えたら止める(アイドル時は何も回さない)
        self.update()

    @property
    def dealing(self) -> bool:
        return self._timer.isActive()

    def _geom(self):
        s = min(self.width() / LW, self.height() / LH)
        s = math.floor(s) if s >= 2 else max(0.5, math.floor(s * 4) / 4)  # 2倍以上は整数倍=ドットが揃う
        ox = (self.width() - LW * s) / 2
        oy = (self.height() - LH * s) / 2
        return s, ox, oy

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        s, ox, oy = self._geom()
        p.translate(ox, oy)
        p.scale(s, s)
        # 置き場の枠(まだ引いていない時も形が分かるように)
        p.setPen(QPen(QColor(DIM), 1 / s, Qt.PenStyle.DashLine))
        for i in range(10):
            if i == 1 and self.spread:
                continue
            p.drawRect(card_rect(i).adjusted(0.5, 0.5, -0.5, -0.5))
        bursts = []
        ox0, oy0 = LW / 2, LH + 60  # 山札(画面の下)から飛んでくる
        for i, (cid, rev) in enumerate(self.spread):
            x, y, rot = LAYOUT[i]
            fly, face, sx, bt = self.deal.state(i)
            if fly <= 0:
                continue
            pm = self.pix[cid] if face else self.pix["back"]
            ang = (90 * fly if rot else 0) + (180 if (rev and face) else 0)
            p.save()
            p.translate(ox0 + (x - ox0) * fly, oy0 + (y - oy0) * fly)
            p.rotate(ang)
            p.scale(sx, 1)
            p.drawPixmap(QPointF(-CW / 2, -CH / 2), pm)
            p.restore()
            if bt is not None:
                bursts.append((i, cid, bt))
        for i, cid, bt in bursts:
            x, y, rot = LAYOUT[i]
            w_, h_ = (CH, CW) if rot else (CW, CH)
            draw_burst(p, QPointF(x, y), bt, 1.0, i * 7 + 1, w_, h_, major_label(cid), 10)
        # 番号
        f = QFont(ui_font())
        f.setPixelSize(9)
        p.setFont(f)
        for i in range(10):
            r = card_rect(i)
            if i == 1:
                bx, by = r.right() - 2, r.top() - 4
            else:
                bx, by = r.left() - 4, r.top() - 4
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(MAGENTA if i == self.selected else BG))
            p.drawRect(QRectF(bx - 1, by - 1, 12, 11))
            p.setPen(QColor(BG if i == self.selected else CYAN))
            p.drawText(QRectF(bx - 1, by - 1, 12, 11), Qt.AlignmentFlag.AlignCenter, str(i + 1))
        if 0 <= self.selected < len(self.spread):
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(MAGENTA), 2 / s))
            p.drawRect(card_rect(self.selected).adjusted(-1.5, -1.5, 1.5, 1.5))
        p.end()

    def _hit(self, pos) -> int:
        s, ox, oy = self._geom()
        pt = QPointF((pos.x() - ox) / s, (pos.y() - oy) / s)
        if card_rect(1).contains(pt) and self.spread:
            return 1  # 横向きの2枚目が上に乗っている
        for i in range(10):
            if i != 1 and card_rect(i).contains(pt):
                return i
        return -1

    def mousePressEvent(self, e):
        i = self._hit(e.position())
        if 0 <= i < self.revealed:
            self.selected = i
            self.update()
            self.picked.emit(i)

    def mouseMoveEvent(self, e):
        i = self._hit(e.position())
        if 0 <= i < self.revealed:
            cid, rev = self.spread[i]
            self.setToolTip(f"{i + 1}. {POSITIONS[i][0]} — {BY_ID[cid]['ja']}{'(逆)' if rev else ''}")
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.setToolTip("")
            self.unsetCursor()


class HoroWheel(QWidget):
    """HOSHIYOMI LOG の星図(内=出生図シアン/外=今日の星マゼンタ)を移植し、まわりに12ハウスのカード、中央に1枚。
    カードはハウスの真ん中の方角に置き、押すとそのハウスの扇形が光る。"""
    picked = pyqtSignal(int)

    def __init__(self, pix: dict[str, QPixmap], astro: Astro):
        super().__init__()
        self.pix, self.astro = pix, astro
        self.spread: list[tuple[str, bool]] = []
        self.revealed = 0
        self.selected = -1
        self.setMinimumSize(560, 560)
        self.setMouseTracking(True)
        self.phase = 0.0
        rnd = random.Random(7)
        self.stars = [(rnd.random(), rnd.random(), rnd.random() * math.tau, rnd.choice([1, 1, 2])) for _ in range(160)]
        # 星図の動きは見えている間だけ回す(タブを離れる/最小化で止まる)
        self.anim = QTimer(self, interval=self.IDLE_MS, timeout=self._tick)
        self.deal = DealAnim()  # 配っている間だけ anim を 16ms に上げる
        self._static_key, self._static_pm = None, None
        self._last_input = time.monotonic()
        self._clock = QElapsedTimer()
        self._clock.start()

    # ---- 盤面の状態(SpreadView と同じ口) ----
    def set_spread(self, spread, animate=True):
        self.spread = spread
        self.selected = -1
        if animate and spread:
            self.deal.start(spread)
            self.revealed = 0
            self.anim.setInterval(16)
            self.wake()
        else:
            self.deal.finish()
            self.revealed = len(spread)
        self.update()

    @property
    def dealing(self) -> bool:
        return self.deal.active

    IDLE_MS = 100      # 配っていない間は 10fps
    SLEEP_AFTER = 30   # この秒数マウスが動かなければ星図のアニメを止める(乗せれば再開)

    def wake(self):
        self._last_input = time.monotonic()
        if self.isVisible() and not self.anim.isActive():
            self._clock.restart()
            self.anim.start()

    def enterEvent(self, e):
        self.wake()
        super().enterEvent(e)

    def showEvent(self, e):
        self.wake()
        super().showEvent(e)

    def hideEvent(self, e):
        self.anim.stop()
        super().hideEvent(e)

    def _tick(self):
        if self.window().isMinimized():
            return
        dt = self._clock.restart() / 1000
        self.phase = (self.phase + dt) % (math.tau * 100)  # 1秒で1進む(間隔を変えても速さは同じ)
        if self.deal.active:
            self.revealed = self.deal.revealed()
            if self.deal.done():
                self.deal.finish()
                self.revealed = len(self.spread)
                self.anim.setInterval(self.IDLE_MS)
        elif time.monotonic() - self._last_input > self.SLEEP_AFTER:
            self.anim.stop()  # 放っておかれたら止まる(CPU 0)。止まった絵はそのまま残る
            return
        self.update()

    # ---- 幾何 ----
    def _geom(self):
        W, H = self.width(), self.height()
        for s in (2, 1.5, 1.25, 1, 0.75, 0.5):
            cw, ch = CW * s, CH * s
            ry = H / 2 - ch / 2 - 6
            rx = min(W / 2 - cw / 2 - 6, ry * 1.45)
            # 横に並ぶ2枚(ハウス境界が水平付近)が縦に重ならない / 上の2枚が横に重ならない
            if ry >= 2.0 * ch and rx >= 2.8 * cw:
                break
        R = max(60.0, min(ry - ch / 2, rx - cw / 2) - 10)
        return W / 2, H / 2, s, rx, ry, R

    def _ref(self):
        n = self.astro.natal
        return n.asc if n and n.asc is not None else 0.0

    def _th(self, lon):
        return math.radians(180 + (lon - self._ref()))

    def _pt(self, cx, cy, r, lon):
        th = self._th(lon)
        return QPointF(cx + r * math.cos(th), cy - r * math.sin(th))

    def card_center(self, i: int, g=None) -> QPointF:
        cx, cy, s, rx, ry, R = g or self._geom()
        if i == 12:
            return QPointF(cx, cy)
        lon = self.astro.house_sign(i + 1) * 30 + 15 if self.astro.A else i * 30 + 15
        th = self._th(lon)
        return QPointF(cx + rx * math.cos(th), cy - ry * math.sin(th))

    def card_rect(self, i: int, g=None) -> QRectF:
        g = g or self._geom()
        s = g[2]
        c = self.card_center(i, g)
        return QRectF(c.x() - CW * s / 2, c.y() - CH * s / 2, CW * s, CH * s)

    @staticmethod
    def _spread(lons, min_gap=7.0):
        order = sorted(range(len(lons)), key=lambda i: lons[i])
        disp = {i: lons[i] for i in order}
        for _ in range(3):
            for a, b in zip(order, order[1:]):
                if (disp[b] - disp[a]) % 360 < min_gap:
                    disp[b] = disp[a] + min_gap
        return [disp[i] for i in range(len(lons))]

    # ---- 描画 ----
    def _static_layer(self, cx, cy, R, r_sign_out, r_sign_in, r_na, r_core):
        """動かない部分(リング・星座記号・目盛り・ASC/MC)。大きさか星図が変わったときだけ描き直す"""
        A, natal, transit = self.astro.A, self.astro.natal, self.astro.transit
        lit_i = transit.bodies[0].sign_index if transit else -1
        key = (self.width(), self.height(), self.devicePixelRatioF(), round(self._ref(), 4), lit_i, A is not None,
               natal.asc if natal else None)
        if key == self._static_key:
            return self._static_pm
        dpr = self.devicePixelRatioF()
        pm = QPixmap(int(self.width() * dpr), int(self.height() * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        q = QPainter(pm)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)
        q.setBrush(Qt.BrushStyle.NoBrush)
        q.setPen(QPen(QColor(CYAN), 2))
        q.drawEllipse(QPointF(cx, cy), r_sign_out, r_sign_out)
        q.setPen(QPen(QColor(DIM), 1))
        q.drawEllipse(QPointF(cx, cy), r_sign_in, r_sign_in)
        q.drawEllipse(QPointF(cx, cy), r_na + 18, r_na + 18)
        q.drawEllipse(QPointF(cx, cy), r_core, r_core)
        if A:
            q.setFont(QFont(GLYPH_FONT, max(9, int(R / 18))))
            for i, (_name, gly) in enumerate(A.SIGNS):
                q.setPen(QPen(QColor(DIM), 1))
                q.drawLine(self._pt(cx, cy, r_sign_in, i * 30), self._pt(cx, cy, r_sign_out, i * 30))
                lit = transit and transit.bodies[0].sign_index == i
                q.setPen(QColor(YELLOW if lit else CYAN))
                pt = self._pt(cx, cy, (r_sign_in + r_sign_out) / 2, i * 30 + 15)
                q.drawText(QRectF(pt.x() - 14, pt.y() - 12, 28, 24), Qt.AlignmentFlag.AlignCenter, gly + "︎")
            q.setPen(QPen(QColor(DIM), 1))
            for d in range(0, 360, 5):
                q.drawLine(self._pt(cx, cy, r_sign_in, d), self._pt(cx, cy, r_sign_in - (6 if d % 30 else 0) - 3, d))

        if natal and natal.asc is not None:
            for lon, lab in ((natal.asc, "ASC"), (natal.mc, "MC")):
                c = QColor(YELLOW)
                c.setAlpha(150)
                q.setPen(QPen(c, 1, Qt.PenStyle.DashLine))
                q.drawLine(self._pt(cx, cy, r_core, lon), self._pt(cx, cy, r_sign_in, lon))

        q.end()
        self._static_key, self._static_pm = key, pm
        return pm

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor(BG))
        g = self._geom()
        cx, cy, s, rx, ry, R = g

        # 瞬く星: 160個を4つの組に分けて画像にし、組ごとの濃さだけ変える(毎回160個描くと重い)
        skey = (w, h, self.devicePixelRatioF())
        if getattr(self, "_star_key", None) != skey:
            dpr = self.devicePixelRatioF()
            self._star_pms = []
            for grp in range(4):
                pm = QPixmap(int(w * dpr), int(h * dpr))
                pm.setDevicePixelRatio(dpr)
                pm.fill(Qt.GlobalColor.transparent)
                q = QPainter(pm)
                for j, (x, y, _ph, sz) in enumerate(self.stars):
                    if j % 4 == grp:
                        q.fillRect(QRectF(x * w, y * h, sz, sz), QColor(CYAN if sz == 2 else TEXT))
                q.end()
                self._star_pms.append(pm)
            self._star_key = skey
        for grp, pm in enumerate(self._star_pms):
            p.setOpacity((60 + 120 * (0.5 + 0.5 * math.sin(self.phase * 0.6 + grp * 1.7))) / 255)
            p.drawPixmap(0, 0, pm)
        p.setOpacity(1.0)

        A, natal, transit = self.astro.A, self.astro.natal, self.astro.transit
        r_sign_out, r_sign_in = R, R * 0.86
        r_tr, r_na, r_core = R * 0.76, R * 0.56, R * 0.44

        gr = QRadialGradient(QPointF(cx, cy), r_core)
        gr.setColorAt(0, QColor(255, 43, 214, 40))
        gr.setColorAt(1, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(gr))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), r_core, r_core)

        sweep = (self.phase * 12) % 360  # レーダー掃引: 線18本の代わりに扇形1枚のグラデーション
        cg = QConicalGradient(QPointF(cx, cy), sweep)  # 1.0(=sweepの角度)が一番明るく、時計回りに27°で消える
        c0 = QColor(CYAN)
        c0.setAlpha(60)
        cg.setColorAt(0.0, QColor(0, 0, 0, 0))
        cg.setColorAt(0.925, QColor(0, 0, 0, 0))
        cg.setColorAt(1.0, c0)
        p.setBrush(QBrush(cg))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPie(QRectF(cx - r_sign_in, cy - r_sign_in, 2 * r_sign_in, 2 * r_sign_in), int((sweep - 27) * 16), 27 * 16)

        # 選んだハウスの扇形を光らせる
        if 0 <= self.selected < 12 and A:
            lon0 = self.astro.house_sign(self.selected + 1) * 30
            th0 = 180 + (lon0 - self._ref())
            path = QPainterPath()
            path.arcMoveTo(QRectF(cx - r_core, cy - r_core, 2 * r_core, 2 * r_core), th0)
            path.arcTo(QRectF(cx - r_sign_out, cy - r_sign_out, 2 * r_sign_out, 2 * r_sign_out), th0, 30)
            path.arcTo(QRectF(cx - r_core, cy - r_core, 2 * r_core, 2 * r_core), th0 + 30, -30)
            path.closeSubpath()
            c = QColor(MAGENTA)
            c.setAlpha(int(50 + 30 * math.sin(self.phase * 2)))
            p.setBrush(c)
            p.setPen(QPen(QColor(MAGENTA), 1))
            p.drawPath(path)

        p.drawPixmap(0, 0, self._static_layer(cx, cy, R, r_sign_out, r_sign_in, r_na, r_core))

        pulse = 0.5 + 0.5 * math.sin(self.phase * 2)
        for a in self.astro.aspects[:10]:  # アスペクト線(脈動)
            hard = a.name in ("スクエア", "オポジション")
            c = QColor(MAGENTA if hard else GREEN if a.name != "合" else YELLOW)
            strength = max(0.15, 1 - a.orb / 8)
            c.setAlpha(int(40 + 160 * strength * (0.6 + 0.4 * pulse)))
            p.setPen(QPen(c, 1 + 2 * strength))
            p.drawLine(self._pt(cx, cy, r_core, a.transit.lon), self._pt(cx, cy, r_core, a.natal.lon))

        def draw_ring(chart, r, color, outer):
            disp = self._spread([b.lon for b in chart.bodies])
            for b, dl in zip(chart.bodies, disp):
                self._gpos[(outer, b.name)] = self._pt(cx, cy, r, dl)
            gf = QFont(GLYPH_FONT, max(10, int(R / 16)))
            p.setFont(gf)
            for b, dl in zip(chart.bodies, disp):
                tick_r = r_sign_in if outer else r_na + 18
                p.setPen(QPen(QColor(color), 2))
                p.drawLine(self._pt(cx, cy, tick_r, b.lon), self._pt(cx, cy, tick_r - 6, b.lon))
                pt = self._pt(cx, cy, r, dl)
                col = QColor(color)
                if b.retro:
                    col = QColor(YELLOW)
                    col.setAlpha(int(140 + 115 * pulse))
                p.setPen(col)
                p.drawText(QRectF(pt.x() - 13, pt.y() - 13, 26, 26), Qt.AlignmentFlag.AlignCenter, b.glyph)
                dot = self._pt(cx, cy, r_core, b.lon)
                c2 = QColor(color)
                c2.setAlpha(200)
                p.fillRect(QRectF(dot.x() - 2, dot.y() - 2, 4, 4), c2)

        self._gpos = {}
        if natal:
            draw_ring(natal, r_na, CYAN, False)
        if transit:
            draw_ring(transit, r_tr, MAGENTA, True)

        # 共鳴: カードから、重なっている天体の記号へ金の線
        res = {}
        if A:
            for i, (cid, _rev) in enumerate(self.spread[:self.revealed]):
                res[i] = resonance(self.astro, i + 1, cid)
                sel = i == self.selected
                if not sel and res[i][0] < 4:
                    continue
                for outer, name in res[i][2]:
                    if not sel and not outer:
                        continue  # 選んでいないカードは「今の星」との線だけ
                    gp = self._gpos.get((outer, name))
                    if gp is None:
                        continue
                    c = QColor(YELLOW)
                    c.setAlpha(int(110 + 110 * pulse))
                    p.setPen(QPen(c, 2 if res[i][0] >= 6 else 1.4))
                    p.drawLine(self.card_center(i, g), gp)
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawEllipse(gp, 12, 12)

        # カードとハウスを結ぶ細い線
        if A:
            for i in range(12):
                c = QColor(MAGENTA if i == self.selected else DIM)
                c.setAlpha(230 if i == self.selected else 110)
                p.setPen(QPen(c, 1, Qt.PenStyle.DotLine))
                lon = self.astro.house_sign(i + 1) * 30 + 15
                p.drawLine(self._pt(cx, cy, r_sign_out + 2, lon), self.card_center(i, g))

        # カード(ドットは崩さない)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        n = len(self.spread)
        bursts = []
        for i in range(13):
            ctr = self.card_center(i, g)
            p.save()
            if i < n:
                cid, rev = self.spread[i]
                fly, face, sx, bt = self.deal.state(i)
                if fly <= 0:
                    p.restore()
                    continue
                p.translate(QPointF(cx + (ctr.x() - cx) * fly, cy + (ctr.y() - cy) * fly))  # 星図の中心から飛ぶ
                p.scale(s, s)
                if rev and face:
                    p.rotate(180)
                p.scale(sx, 1)
                p.drawPixmap(QPointF(-CW / 2, -CH / 2), self.pix[cid] if face else self.pix["back"])
                if bt is not None:
                    bursts.append((i, cid, bt))
            else:
                p.translate(ctr)
                p.scale(s, s)
                c = QColor(DIM)
                p.setPen(QPen(c, 1 / s, Qt.PenStyle.DashLine))
                p.drawRect(QRectF(-CW / 2 + 0.5, -CH / 2 + 0.5, CW - 1, CH - 1))
            p.restore()
        # 番号
        f = QFont(ui_font())
        f.setPixelSize(11)
        p.setFont(f)
        for i in range(13):
            r = self.card_rect(i, g)
            box = QRectF(r.left() - 5, r.top() - 5, 18, 14)
            sel = i == self.selected
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(MAGENTA if sel else BG))
            p.drawRect(box)
            p.setPen(QColor(BG if sel else (YELLOW if i == 12 else CYAN)))
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, "★" if i == 12 else str(i + 1))
        # 共鳴したカードは金の枠で脈打たせる。強い共鳴は二重枠+四隅のきらめき
        for i, (sc, _w, _h) in res.items():
            if sc < 4:
                continue
            r = self.card_rect(i, g)
            c = QColor(YELLOW)
            c.setAlpha(int(140 + 115 * pulse))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(c, 2))
            p.drawRect(r.adjusted(-4, -4, 4, 4))
            if sc >= 6:
                p.drawRect(r.adjusted(-7, -7, 7, 7))
                for k, (x, y) in enumerate(((r.left() - 7, r.top() - 7), (r.right() + 7, r.top() - 7),
                                            (r.left() - 7, r.bottom() + 7), (r.right() + 7, r.bottom() + 7))):
                    a = 2 + 3 * (0.5 + 0.5 * math.sin(self.phase * 3 + k * 1.6))
                    p.setPen(QPen(QColor(WHITE_GLOW), 2))
                    p.drawLine(QPointF(x - a, y), QPointF(x + a, y))
                    p.drawLine(QPointF(x, y - a), QPointF(x, y + a))
            tag = QRectF(r.center().x() - 22, r.bottom() + 3, 44, 14)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(YELLOW))
            p.drawRect(tag)
            p.setPen(QColor(BG))
            p.setFont(f)
            p.drawText(tag, Qt.AlignmentFlag.AlignCenter, res_mark(sc))
        # 黄金の夜明けの対応記号(右上)
        gf2 = QFont(GLYPH_FONT)
        gf2.setPixelSize(11)
        for i, (cid, _rev) in enumerate(self.spread[:self.revealed]):
            r = self.card_rect(i, g)
            box = QRectF(r.right() - 12, r.top() - 5, 17, 14)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(BG))
            p.drawRect(box)
            p.setPen(QColor(YELLOW if res.get(i, (0,))[0] >= 4 else LIL_TXT))
            p.setFont(gf2)
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, BY_ID[cid]["gd"]["glyph"] + "\uFE0E")
        if 0 <= self.selected < n:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(MAGENTA), 2))
            p.drawRect(self.card_rect(self.selected, g).adjusted(-2, -2, 2, 2))
        for i, cid, bt in bursts:
            draw_burst(p, self.card_center(i, g), bt, s, i * 7 + 1, CW * s, CH * s, major_label(cid), 12 * s)

        p.setFont(QFont(ui_font(), 9))
        p.setPen(QColor(CYAN))
        p.drawText(8, h - 26, "内: 出生図")
        p.setPen(QColor(MAGENTA))
        p.drawText(8, h - 10, "外: 今日の星")
        if self.astro.error:
            p.setPen(QColor(YELLOW))
            p.drawText(8, 16, f"星図なし: {self.astro.error}")
        elif not self.astro.has_houses:
            p.setPen(QColor(YELLOW))
            p.drawText(8, 16, "出生時刻/出生データが無いのでナチュラルハウス(牡羊座=第1)")
        p.end()

    def _hit(self, pos) -> int:
        g = self._geom()
        for i in [12] + list(range(12)):
            if self.card_rect(i, g).contains(pos):
                return i
        return -1

    def mousePressEvent(self, e):
        self.wake()
        i = self._hit(e.position())
        if 0 <= i < self.revealed:
            self.selected = i
            self.update()
            self.picked.emit(i)

    def mouseMoveEvent(self, e):
        self.wake()
        i = self._hit(e.position())
        if 0 <= i < self.revealed:
            cid, rev = self.spread[i]
            self.setToolTip(f"{HOUSES[i][0]}({HOUSES[i][1]}) — {BY_ID[cid]['ja']}{'(逆)' if rev else ''}")
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.setToolTip("")
            self.unsetCursor()


# ───────────────────────── 画面 ─────────────────────────
# ───────────────────────── 占う相手 ─────────────────────────
# 地名検索はしない(外部送信を避ける)。主な都市だけ手元に持ち、無ければ緯度経度を手入力
CITIES = [
    ("札幌", 43.0621, 141.3544, 9.0), ("仙台", 38.2682, 140.8694, 9.0), ("秋田", 39.7186, 140.1024, 9.0),
    ("東京", 35.6812, 139.7671, 9.0), ("横浜", 35.4437, 139.6380, 9.0), ("名古屋", 35.1815, 136.9066, 9.0),
    ("金沢", 36.5613, 136.6562, 9.0), ("京都", 35.0116, 135.7681, 9.0), ("大阪", 34.6937, 135.5023, 9.0),
    ("神戸", 34.6901, 135.1955, 9.0), ("広島", 34.3853, 132.4553, 9.0), ("福岡", 33.5904, 130.4017, 9.0),
    ("那覇", 26.2124, 127.6809, 9.0), ("ソウル", 37.5665, 126.9780, 9.0), ("台北", 25.0330, 121.5654, 8.0),
    ("トビリシ", 41.7151, 44.8271, 4.0), ("バトゥミ", 41.6168, 41.6367, 4.0), ("クタイシ", 42.2679, 42.7180, 4.0),
    ("マドリード", 40.4168, -3.7038, 1.0), ("ロンドン", 51.5074, -0.1278, 0.0), ("ニューヨーク", 40.7128, -74.0060, -5.0),
]


def load_people() -> list[dict]:
    try:
        return json.loads(PEOPLE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def save_people(people: list[dict]):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = PEOPLE.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)  # 他人の出生データなので本人だけ読める
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(people, f, ensure_ascii=False, indent=1)
    os.replace(tmp, PEOPLE)


class PersonDialog(QDialog):
    def __init__(self, parent=None, person: dict | None = None, saved: bool = True):
        super().__init__(parent)
        self.setWindowTitle("占う相手の出生データ")
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText("呼び名(例: たろう)")
        form.addRow("名前", self.name)
        self.bdate = QDateEdit(calendarPopup=True)
        self.bdate.setDisplayFormat("yyyy-MM-dd")
        self.bdate.setDate(QDate(1995, 1, 1))
        form.addRow("生年月日", self.bdate)
        trow = QHBoxLayout()
        self.time_known = QCheckBox("出生時刻が分かる")
        self.btime = QTimeEdit()
        self.btime.setDisplayFormat("HH:mm")
        self.btime.setEnabled(False)
        self.time_known.toggled.connect(self.btime.setEnabled)
        trow.addWidget(self.time_known)
        trow.addWidget(self.btime)
        form.addRow("出生時刻", trow)
        self.city = QComboBox()
        self.city.addItem("(都市から選ぶ…)", None)
        for c in CITIES:
            self.city.addItem(c[0], c)
        self.city.activated.connect(self._city)
        form.addRow("出生地", self.city)
        self.lat = QDoubleSpinBox(minimum=-90, maximum=90, decimals=4, value=35.6812)
        self.lon = QDoubleSpinBox(minimum=-180, maximum=180, decimals=4, value=139.7671)
        self.offset = QDoubleSpinBox(minimum=-12, maximum=14, singleStep=0.5, value=9.0, suffix=" h")
        form.addRow("緯度", self.lat)
        form.addRow("経度", self.lon)
        form.addRow("UTCオフセット", self.offset)
        lay.addLayout(form)
        note = QLabel("時刻が不明なら正午で計算し、ハウスは牡羊座=第1のナチュラルハウスになります。"
                      "夏時間の国・昔の日本(1948〜51年の夏時間)はオフセットを手で直してください。地名検索はしません。")
        note.setWordWrap(True)
        note.setObjectName("sub")
        lay.addWidget(note)
        self.keep = QCheckBox("この人を保存する(この端末だけ)")
        self.keep.setChecked(saved)
        lay.addWidget(self.keep)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        if person:
            self.name.setText(person["name"])
            self.bdate.setDate(QDate.fromString(person["birth_date"], "yyyy-MM-dd"))
            if person.get("birth_time"):
                self.time_known.setChecked(True)
                self.btime.setTime(QTime.fromString(person["birth_time"], "HH:mm"))
            self.lat.setValue(float(person.get("lat") or 0))
            self.lon.setValue(float(person.get("lon") or 0))
            self.offset.setValue(float(person.get("utc_offset") or 9.0))

    def _city(self, _i):
        c = self.city.currentData()
        if c:
            self.lat.setValue(c[1])
            self.lon.setValue(c[2])
            self.offset.setValue(c[3])

    def _ok(self):
        n = self.name.text().strip()
        if not n or n == "自分":
            QMessageBox.warning(self, "名前", "名前を入れてください(「自分」以外)")
            return
        self.accept()

    def result_person(self) -> tuple[dict, bool]:
        return {
            "name": self.name.text().strip(),
            "birth_date": self.bdate.date().toString("yyyy-MM-dd"),
            "birth_time": self.btime.time().toString("HH:mm") if self.time_known.isChecked() else "",
            "utc_offset": self.offset.value(),
            "lat": self.lat.value(),
            "lon": self.lon.value(),
        }, self.keep.isChecked()


class ReadTab(QWidget):
    def __init__(self, app: "Main", kind: str = "celtic"):
        super().__init__()
        self.app = app
        self.kind = kind  # celtic | horo
        self.positions = HOUSES if kind == "horo" else POSITIONS
        self.spread: list[tuple[str, bool]] = []
        self.worker: LLMWorker | None = None
        self.saved = True

        lay = QHBoxLayout(self)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.view = HoroWheel(app.pix, app.astro) if kind == "horo" else SpreadView(app.pix)
        self.view.picked.connect(self.show_card)
        split.addWidget(self.view)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(8, 0, 0, 0)
        self.person: dict | None = None  # None=自分(HOSHIYOMI LOG)
        if kind == "horo":
            rl.addWidget(heading("WHO  // 占う相手", YELLOW))
            prow = QHBoxLayout()
            self.who_cb = QComboBox()
            self.who_cb.activated.connect(self._person_changed)
            prow.addWidget(self.who_cb, 1)
            self.edit_b = QPushButton("編集")
            self.edit_b.clicked.connect(self._edit_person)
            self.del_b = QPushButton("削除")
            self.del_b.clicked.connect(self._delete_person)
            prow.addWidget(self.edit_b)
            prow.addWidget(self.del_b)
            rl.addLayout(prow)
            self._fill_people()
        rl.addWidget(heading("QUESTION  // 占いたいこと"))
        self.q = QPlainTextEdit()
        self.q.setPlaceholderText("例: 今の仕事を続けるべき? (空なら全体運)")
        self.q.setFixedHeight(64)
        rl.addWidget(self.q)
        row = QHBoxLayout()
        self.rev_cb = QCheckBox("逆位置あり")
        self.rev_cb.setChecked(True)
        row.addWidget(self.rev_cb)
        row.addStretch()
        self.draw_b = QPushButton("✦ シャッフルして引く")
        self.draw_b.setObjectName("hot")
        self.draw_b.clicked.connect(self.draw)
        self.read_b = QPushButton("☾ 占う")
        self.read_b.clicked.connect(self.read)
        self.read_b.setEnabled(False)
        row.addWidget(self.draw_b)
        row.addWidget(self.read_b)
        rl.addLayout(row)

        det = QHBoxLayout()
        self.card_img = QLabel()
        self.card_img.setFixedSize(CW * 2, CH * 2)
        self.card_img.setStyleSheet(f"border:1px solid {DIM};")
        det.addWidget(self.card_img)
        self.card_txt = QLabel("カードを引いたら、盤面のカードを押すと意味が出ます。")
        self.card_txt.setWordWrap(True)
        self.card_txt.setAlignment(Qt.AlignmentFlag.AlignTop)
        det.addWidget(self.card_txt, 1)
        rl.addLayout(det)

        rl.addWidget(heading("READING  // 鑑定", MAGENTA))
        self.out = QPlainTextEdit()
        self.out.setReadOnly(True)
        rl.addWidget(self.out, 1)
        self.status = QLabel("")
        self.status.setObjectName("sub")
        rl.addWidget(self.status)
        split.addWidget(right)
        split.setSizes([660, 460] if kind == "horo" else [560, 520])
        lay.addWidget(split)

    # ---- 占う相手(ホロスコープだけ) ----
    ADD = "__add__"

    def _fill_people(self, select: dict | None = None):
        self.people = load_people()
        self.who_cb.clear()
        self.who_cb.addItem("自分(星読みログの出生データ)", None)
        for x in self.people:
            self.who_cb.addItem(f"{x['name']}  {x['birth_date']}", x["name"])
        if select and not any(x["name"] == select["name"] for x in self.people):
            self.who_cb.addItem(f"{select['name']}(保存しない・今回だけ)", "__temp__")
        self.who_cb.addItem("＋ 新しい人を追加…", self.ADD)
        self._select_person(select, refill=False)

    def _select_person(self, person: dict | None, refill: bool = True):
        if refill:
            self._fill_people(person)
            return
        self.person = person
        if person is None:
            idx = 0
        else:
            idx = self.who_cb.findData(person["name"])
            if idx < 0:
                idx = self.who_cb.findData("__temp__")
        self.who_cb.setCurrentIndex(max(0, idx))
        self.edit_b.setEnabled(person is not None)
        self.del_b.setEnabled(person is not None and any(x["name"] == person["name"] for x in self.people))

    def _person_changed(self, _i):
        data = self.who_cb.currentData()
        if data == self.ADD:
            dlg = PersonDialog(self)
            if dlg.exec():
                person, keep = dlg.result_person()
                if keep:
                    save_people([x for x in load_people() if x["name"] != person["name"]] + [person])
                self._apply_person(person)
            else:
                self._select_person(self.person, refill=False)  # キャンセル=元の人に戻す
            return
        if data == "__temp__":
            return
        self._apply_person(None if data is None else next(x for x in self.people if x["name"] == data))

    def _apply_person(self, person: dict | None):
        self._select_person(person)
        self.app.astro.load(person)
        self.view.set_spread([], animate=False)  # 前の人のカードは片付ける
        self.spread = []
        self.read_b.setEnabled(False)
        self.out.clear()
        self.card_img.clear()
        self.card_txt.setText("カードを引いたら、盤面のカードを押すと意味が出ます。")
        self.status.setText(f"{self.app.astro.who} の星図" + (f"  /  {self.app.astro.error}" if self.app.astro.error else ""))

    def _edit_person(self):
        if not self.person:
            return
        old = self.person["name"]
        saved = any(x["name"] == old for x in load_people())
        dlg = PersonDialog(self, self.person, saved)
        if dlg.exec():
            person, keep = dlg.result_person()
            rest = [x for x in load_people() if x["name"] not in (old, person["name"])]
            save_people(rest + [person] if keep else rest)
            self._apply_person(person)

    def _delete_person(self):
        if not self.person:
            return
        name = self.person["name"]
        if QMessageBox.question(self, "削除", f"{name}さんの出生データを消しますか？\n(履歴の占い結果は残ります)") != QMessageBox.StandardButton.Yes:
            return
        save_people([x for x in load_people() if x["name"] != name])
        self._apply_person(None)

    def draw(self):
        if self.worker and self.worker.isRunning():
            return
        if self.kind == "horo":
            self.app.astro.load(self.person)  # 今日の星を引いた瞬間で計算し直す
        self.spread = draw_spread(self.rev_cb.isChecked(), n=len(self.positions))
        self.view.set_spread(self.spread)
        self.out.clear()
        self.card_img.clear()
        self.card_txt.setText("カードを押すと意味が出ます。")
        self.status.setText(stats(self.spread))
        self.read_b.setEnabled(True)
        self.saved = True

    def show_card(self, i: int):
        cid, rev = self.spread[i]
        c = BY_ID[cid]
        pm = self.app.pix[cid].scaled(CW * 2, CH * 2, transformMode=Qt.TransformationMode.FastTransformation)
        if rev:
            pm = pm.transformed(QTransform().rotate(180))
        self.card_img.setPixmap(pm)
        pos, pdesc = self.positions[i]
        head = pos if self.kind == "horo" else f"{i + 1}. {pos}"
        star = ""
        if self.kind == "horo" and i < 12 and self.app.astro.A:
            star = f"<span style='color:{DIM}'>{self.app.astro.house_facts(i + 1)}</span><br>"
        gdl = f"<span style='color:{LIL_TXT}'>黄金の夜明け: {c['gd']['text']}</span><br>"
        if self.kind == "horo" and self.app.astro.A:
            sc, why, _ = resonance(self.app.astro, i + 1, cid)
            if why:
                mk = res_mark(sc)
                gdl += f"<span style='color:{YELLOW if mk else DIM}'>{(mk + ': ') if mk else ''}{'・'.join(why)}</span><br>"
        self.card_txt.setText(
            f"<span style='color:{CYAN}'>{head}</span> <span style='color:{DIM}'>{pdesc}</span><br>{star}<br>"
            f"<span style='color:{YELLOW}; font-size:16px'>{c['ja']}</span><br>"
            f"<span style='color:{DIM}'>{c['en']}</span><br><br>"
            f"<span style='color:{MAGENTA if rev else GREEN}'>{'逆位置' if rev else '正位置'}</span><br>"
            f"{c['rev'] if rev else c['up']}<br><br>"
            f"<span style='color:{DIM}'>{'正位置' if rev else '逆位置'}なら: {c['up'] if rev else c['rev']}</span><br><br>"
            f"{gdl}"
        )

    def read(self):
        if not self.spread or (self.worker and self.worker.isRunning()):
            return
        tgt, why = self.app.llm_target()
        self.out.clear()
        if not tgt:
            kw = "\n".join([stats(self.spread), ""] + [card_line(i, c, r, self.positions) for i, (c, r) in enumerate(self.spread)])
            self.out.setPlainText(f"[{why}]\nLLMなしで、キーワードだけ並べます。\n\n{kw}")
            self._save(self.out.toPlainText(), "(LLMなし)")
            return
        self.model_name = tgt["name"]
        self.status.setText(f"{tgt['name']} が読んでいます…")
        self.draw_b.setEnabled(False)
        self.read_b.setEnabled(False)
        if self.kind == "horo":
            prompt, system = build_horo_prompt(self.q.toPlainText(), self.spread, self.app.astro), HORO_PROMPT
        else:
            prompt, system = build_prompt(self.q.toPlainText(), self.spread), SYSTEM_PROMPT
        self.worker = LLMWorker(tgt["url"], tgt["model_id"], prompt, tgt.get("llama", True), system)
        self.worker.chunk.connect(self._chunk)
        self.worker.done.connect(self._done)
        self.worker.start()

    def _chunk(self, t: str):
        cur = self.out.textCursor()
        cur.movePosition(cur.MoveOperation.End)
        cur.insertText(t)
        self.out.ensureCursorVisible()

    def _done(self, text: str, ok: bool):
        self.draw_b.setEnabled(True)
        self.read_b.setEnabled(True)
        if ok:
            self.out.setPlainText(text)
            self._save(text, self.model_name)
            self.status.setText(f"{stats(self.spread)}  /  {self.model_name}  /  履歴に保存しました")
        else:
            self.out.appendPlainText(f"\n\n[失敗] {text}")
            self.status.setText("LLMの呼び出しに失敗しました")

    def _save(self, reading: str, model: str):
        rec = {
            "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
            "question": self.q.toPlainText().strip(),
            "spread": self.kind,
            "person": self.app.astro.who if self.kind == "horo" else "",
            "cards": [[c, r] for c, r in self.spread],
            "reading": reading,
            "model": model,
        }
        append_history(rec)
        self.app.hist_tab.refresh()

    def restore(self, rec: dict):
        note = ""
        if self.kind == "horo":
            who = rec.get("person") or "自分"
            person = None if who == "自分" else next((x for x in load_people() if x["name"] == who), None)
            if who == "自分" or person:
                self._select_person(person)
                try:
                    when = datetime.fromisoformat(rec["ts"])
                except (KeyError, ValueError):
                    when = None
                self.app.astro.load(person, when)  # 占ったときの星に戻す
            else:
                note = f"  /  {who}さんの出生データは保存されていないので、星図は今の選択のまま"
        self.spread = [(c, bool(r)) for c, r in rec["cards"]]
        self.q.setPlainText(rec.get("question", ""))
        self.view.set_spread(self.spread, animate=False)
        self.out.setPlainText(rec.get("reading", ""))
        self.status.setText(f"{rec.get('ts', '')}  /  {rec.get('model', '')}{note}")
        self.read_b.setEnabled(True)


# ───────────────────────── スクライング(Sigillum Dei Aemeth) ─────────────────────────
# ディー(問う人)とケリー(水晶を覗く人)の交信を再現する。印章は「霊視の前に場を整える台座」として、
# 水晶の下に敷かれていた(大英博物館の蜜蝋の現物)。形と名前は ディーの手稿 Sloane MS 3188 の図から読める範囲だけ。
# 外周40マスの文字と五芒星のまわりの文字は判読できないので再現しない(印だけ)。
SCRY_DIR = DATA_DIR / "scrying"   # 1回の交信 = 1ファイル(JSON)

SEAL_OUTER = ["SAAIEME", "BTZKASE", "HEIDENE", "DEIMOA", "IMEGCBE", "ILAOIVN", "IHRLAAV"]   # 外の七角形・右上の辺から時計回り
SEAL_DAUGHTERS = ["El", "Me", "Ese", "Iana", "Akele", "Azdobn", "Stimcul"]   # 七芒星の先端・頂上から時計回り(光の娘たち)
SEAL_SONS = ["I", "Heeoa", "Ih", "Beigia", "Ilr", "Stimcul", "Dmal"]          # 各先端の三角の底辺の帯(光の息子たち)
SEAL_BAND1 = ["S", "Ab", "Ath", "Ized", "Ekiei", "Madimi", "Esemeli"]         # 内の七角形(外側の帯)・上の辺から時計回り
SEAL_BAND2 = ["E", "An", "Ave", "Liba", "Rocle", "Hagonel", "Ilemese"]        # 内の七角形(内側の帯)

SCRY_PROMPT = """あなたは16世紀の霊視者エドワード・ケリーです。ジョン・ディー博士の書斎で、机に敷いた Sigillum Dei Aemeth(神の真理の印章)の上に置かれた水晶(ショーストーン)を覗いています。問う人(ディーの役)の言葉に応えて、水晶の中に見えるものを語ってください。
ルール:
- 見えた光景・色・光・人影・身ぶり・象徴・文字を、具体的な映像として描写する。説明や助言はしない(読み解くのは問う人)。
- 1回の返答は100〜250字。現在形の短い文で、ケリーが見たままを口にする調子で。
- ときどき水晶の中の存在(天使、小さな人影、子どもの姿など)が短い言葉を語る。その言葉は「」で書く。名乗ることもある。
- 像がかすむ・乱れる・消えることもある。そのときはそう言ってよい。
- 前のやり取りで現れた存在や象徴は、同じ霊視の続きとして再び現れてよい。
- 実在の人物の未来や、病気・法律・お金について断定しない。芝居がかった雰囲気は保つ。
- Markdown の記号は使わない。"""
SCRY_OPEN = "(祈りが終わった。E.K. は印章の上の水晶を覗き込む。最初に見えたものを語れ)"
AETHYR_FILE = DATA_DIR / "aethyrs.json"   # アエティールの旅の進み具合 {"done": [30, 29, ...]}
AETHYR_PROMPT = """
今回は30のアエティール(エノク魔術の霊的な層。外側の第30 TEX から内側の第1 LIL へ深くなる)のうち、第{n}のアエティール {name} を霊視している。問う人は第19の呼びかけをこの名で唱え、統治者 {govs} の名を呼んだ。水晶の中に {name} の世界が開く。
- その層の風景・建物・光・存在を描写する。番号が小さい(内側の)層ほど高次で、象徴は抽象的で強烈になる。番号が大きい(外側の)層ほど地上に近い。
- 統治者が姿を見せ、名乗ることもある。
- 有名な霊視の記録(クロウリー『幻視と声』など)の文章をなぞらない。あなた自身の霊視として語る。"""


def is_opening(turn: dict) -> bool:
    """交信の冒頭(祈り・呼びかけ)の発言か。記録の表示では問いとして扱わない"""
    return turn["role"] == "user" and (turn["content"] == SCRY_OPEN or turn["content"].startswith(("(第19の呼びかけ", "(名を唱えた")))


def aethyr_done() -> list[int]:
    try:
        return json.loads(AETHYR_FILE.read_text(encoding="utf-8")).get("done", [])
    except (OSError, json.JSONDecodeError):
        return []


def mark_aethyr(n: int):
    done = sorted(set(aethyr_done()) | {n}, reverse=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = AETHYR_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"done": done}, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, AETHYR_FILE)


def next_aethyr() -> int | None:
    rest = [n for n in range(30, 0, -1) if n not in aethyr_done()]
    return rest[0] if rest else None


class AethyrBar(QWidget):
    """30マスの進み具合。左が第30(TEX)・右が第1(LIL)。済=金/次=マゼンタの枠/まだ=暗い"""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(30)
        self.done: list[int] = []
        self.nxt: int | None = None

    def set_state(self, done, nxt):
        self.done, self.nxt = done, nxt
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        w = self.width()
        cell = min(18.0, (w - 4) / 30)
        f = QFont(ui_font())
        f.setPixelSize(8)
        p.setFont(f)
        for k, n in enumerate(range(30, 0, -1)):
            r = QRectF(2 + k * cell, 2, cell - 2, cell - 2)
            if n in self.done:
                p.fillRect(r, QColor("#e8c25a"))
            else:
                p.fillRect(r, QColor(PANEL))
            if n == self.nxt:
                p.setPen(QPen(QColor(MAGENTA), 2))
                p.drawRect(r)
            if n in (30, 20, 10, 1):
                p.setPen(QColor(DIM))
                p.drawText(QRectF(r.left() - 4, r.bottom() + 1, cell + 8, 10), Qt.AlignmentFlag.AlignCenter, str(n))
        p.end()



def _poly(cx, cy, r, n, rot):
    return [QPointF(cx + r * math.cos(rot + k * math.tau / n), cy + r * math.sin(rot + k * math.tau / n)) for k in range(n)]


def crystal_image(t: float | None) -> QPixmap:
    """32x32 の水晶玉(ドット絵)。t が与えられたら中で霧が渦を巻く。"""
    from PyQt6.QtGui import QImage
    n = 32
    img = QImage(n, n, QImage.Format.Format_ARGB32)
    img.fill(0)
    c = (n - 1) / 2
    pal = [QColor("#0a1030"), QColor("#16245a"), QColor("#2a4a9a"), QColor("#5a8ad8"), QColor("#a8d4ff")]
    for y in range(n):
        for x in range(n):
            dx, dy = (x - c) / (n / 2 - 1), (y - c) / (n / 2 - 1)
            d = dx * dx + dy * dy
            if d > 1:
                continue
            # 左上から光が当たる球の陰影(4段階に量子化=ドット絵らしく)
            lz = max(0.0, -dx * 0.5 - dy * 0.6 + math.sqrt(max(0.0, 1 - d)) * 0.62)
            k = min(3, int(lz * 4))
            col = QColor(pal[k])
            if t is not None:  # 霧: 角度と半径で回る縞
                ang = math.atan2(dy, dx)
                sw = math.sin(ang * 2 + math.sqrt(d) * 7 - t * 2.4)
                if sw > 0.55 and d < 0.8:
                    col = QColor("#c39bff") if sw > 0.8 else QColor("#7b5cc4")
            if d > 0.86:
                col = QColor("#7fb0f0")   # ふち
            col.setAlpha(225)
            img.setPixelColor(x, y, col)
    for (x, y) in ((10, 8), (11, 8), (9, 9), (10, 9), (9, 10), (13, 7)):  # ハイライト
        img.setPixelColor(x, y, QColor("#ffffff"))
    return QPixmap.fromImage(img)


class SealView(QWidget):
    """Sigillum Dei Aemeth と水晶。交信を始めると外から内へ順に光る(場を整える)。
    アニメは「光っていく間」と「水晶が見ている間」だけ回す。"""

    def __init__(self):
        super().__init__()
        self.setMinimumSize(460, 460)
        self.lit = 0.0          # 0=眠っている 1=すべて光っている
        self.seeing = False     # 水晶の中で霧が渦を巻いている
        self._ritual = QElapsedTimer()
        self._ritual_on = False
        self._clock = QElapsedTimer()
        self._clock.start()
        self.timer = QTimer(self, interval=33, timeout=self._tick)
        self.on_ritual_done = None
        self._crystal_still = crystal_image(None)

    RITUAL_SEC = 4.2

    def start_ritual(self, done_cb=None):
        self.on_ritual_done = done_cb
        self.lit = 0.0
        self._ritual.start()
        self._ritual_on = True
        self.timer.start()

    def set_lit(self, v: float):
        self.lit = v
        self._ritual_on = False
        self._sync_timer()
        self.update()

    def set_seeing(self, on: bool):
        self.seeing = on
        self._sync_timer()
        self.update()

    def _sync_timer(self):
        if self._ritual_on or self.seeing:
            self.timer.start()
        else:
            self.timer.stop()

    def _tick(self):
        if self._ritual_on:
            self.lit = min(1.0, self._ritual.elapsed() / 1000 / self.RITUAL_SEC)
            if self.lit >= 1.0:
                self._ritual_on = False
                self._sync_timer()
                if self.on_ritual_done:
                    self.on_ritual_done()
        self.update()

    def _col(self, start: float, end: float, on: str, base_alpha=255) -> QColor:
        """層ごとの光り具合。start〜end の間に暗→明"""
        k = 0.0 if self.lit <= start else 1.0 if self.lit >= end else (self.lit - start) / (end - start)
        a = QColor(DIM)
        b = QColor(on)
        c = QColor(int(a.red() + (b.red() - a.red()) * k), int(a.green() + (b.green() - a.green()) * k),
                   int(a.blue() + (b.blue() - a.blue()) * k))
        c.setAlpha(base_alpha)
        return c

    def _text_on_line(self, p, a: QPointF, b: QPointF, text: str, col: QColor, px: float, offset: float = 0):
        mid = QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2)
        ang = math.degrees(math.atan2(b.y() - a.y(), b.x() - a.x()))
        if ang > 90 or ang < -90:
            ang += 180  # 逆さまにしない
        p.save()
        p.translate(mid)
        p.rotate(ang)
        f = QFont(ui_font())
        f.setPixelSize(max(7, int(px)))
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, px * 0.25)
        p.setFont(f)
        p.setPen(col)
        p.drawText(QRectF(-200, offset - px, 400, px * 2), Qt.AlignmentFlag.AlignCenter, text)
        p.restore()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor(BG))
        cx, cy = w / 2, h / 2
        R = min(w, h) / 2 - 14
        gold = "#e8c25a"
        # 下から灯る淡い光(光りきると強くなる)
        g = QRadialGradient(QPointF(cx, cy), R)
        g.setColorAt(0, QColor(232, 194, 90, int(10 + 40 * self.lit)))
        g.setColorAt(1, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(g))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), R, R)
        p.setBrush(Qt.BrushStyle.NoBrush)

        # 外周: 2本の円と40マス(1マスずつ灯る)
        r1, r2 = R, R * 0.90
        p.setPen(QPen(self._col(0.0, 0.08, gold), 1.6))
        p.drawEllipse(QPointF(cx, cy), r1, r1)
        p.drawEllipse(QPointF(cx, cy), r2, r2)
        for k in range(40):
            a = -math.pi / 2 + k * math.tau / 40
            on = self._col(0.02 + k * 0.006, 0.04 + k * 0.006, gold)
            p.setPen(QPen(on, 1))
            p.drawLine(QPointF(cx + r2 * math.cos(a), cy + r2 * math.sin(a)), QPointF(cx + r1 * math.cos(a), cy + r1 * math.sin(a)))
            m = a + math.tau / 80
            rm = (r1 + r2) / 2
            mx, my = cx + rm * math.cos(m), cy + rm * math.sin(m)
            s = max(1.5, R / 110)
            if k % 5 == 0:  # 手稿でも外周のところどころに十字が入る
                p.drawLine(QPointF(mx - 2 * s, my), QPointF(mx + 2 * s, my))
                p.drawLine(QPointF(mx, my - 2 * s), QPointF(mx, my + 2 * s))
            else:
                p.fillRect(QRectF(mx - s / 2, my - s / 2, s, s), on)

        # 外の七角形(頂点が上)と7つの名前
        rot0 = -math.pi / 2
        H1 = _poly(cx, cy, r2, 7, rot0)
        H1i = _poly(cx, cy, r2 * 0.86, 7, rot0)
        col = self._col(0.27, 0.36, gold)
        p.setPen(QPen(col, 1.4))
        p.drawPolygon(H1)
        p.setPen(QPen(col, 0.8))
        p.drawPolygon(H1i)
        for k in range(7):
            a, b = H1[k], H1[(k + 1) % 7]
            ai, bi = H1i[k], H1i[(k + 1) % 7]
            self._text_on_line(p, QPointF((a.x() + ai.x()) / 2, (a.y() + ai.y()) / 2), QPointF((b.x() + bi.x()) / 2, (b.y() + bi.y()) / 2),
                               SEAL_OUTER[k], self._col(0.30 + k * 0.01, 0.40 + k * 0.01, TEXT), R * 0.045)

        # 七芒星 {7/2}: 帯(2本線)で描く。先端の三角に娘たち、底辺の帯に息子たち
        V = H1i
        colS = self._col(0.42, 0.55, gold)
        bw = R * 0.035
        for k in range(7):
            a, b = V[k], V[(k + 2) % 7]
            dx, dy = b.x() - a.x(), b.y() - a.y()
            L_ = math.hypot(dx, dy)
            nx, ny = -dy / L_ * bw, dx / L_ * bw
            p.setPen(QPen(colS, 1))
            p.drawLine(QPointF(a.x() + nx, a.y() + ny), QPointF(b.x() + nx, b.y() + ny))
            p.drawLine(QPointF(a.x() - nx, a.y() - ny), QPointF(b.x() - nx, b.y() - ny))
        for k in range(7):
            ang = rot0 + k * math.tau / 7
            rr = r2 * 0.70
            pt = QPointF(cx + rr * math.cos(ang), cy + rr * math.sin(ang))
            f = QFont(ui_font())
            f.setPixelSize(max(7, int(R * 0.048)))
            p.setFont(f)
            p.setPen(self._col(0.46 + k * 0.012, 0.58 + k * 0.012, YELLOW))
            p.drawText(QRectF(pt.x() - 40, pt.y() - 10, 80, 20), Qt.AlignmentFlag.AlignCenter, SEAL_DAUGHTERS[k])
            # 先端kの三角の底辺 = 頂点k-1 と k+1 を結ぶ帯のうち、三角に面した区間の真ん中
            pa, pb = V[(k - 1) % 7], V[(k + 1) % 7]
            ma = QPointF(pa.x() + (pb.x() - pa.x()) * 0.36, pa.y() + (pb.y() - pa.y()) * 0.36)
            mb = QPointF(pa.x() + (pb.x() - pa.x()) * 0.64, pa.y() + (pb.y() - pa.y()) * 0.64)
            self._text_on_line(p, ma, mb, SEAL_SONS[k], self._col(0.50 + k * 0.012, 0.62 + k * 0.012, LIL_TXT), R * 0.04)

        # 内の七角形(辺が上)2本の帯
        rotI = -math.pi / 2 + math.pi / 7
        radii = (R * 0.50, R * 0.43, R * 0.36)
        polys = [_poly(cx, cy, r, 7, rotI) for r in radii]
        colI = self._col(0.64, 0.76, gold)
        p.setPen(QPen(colI, 1))
        for pl in polys:
            p.drawPolygon(pl)
        for names, (pa_, pb_), st in ((SEAL_BAND1, (polys[0], polys[1]), 0.66), (SEAL_BAND2, (polys[1], polys[2]), 0.72)):
            for k in range(7):
                # 上の辺から時計回り: rotI だと頂点6が左上・頂点0が右上なので、辺k = 頂点(k+6)%7 → k%7
                i0, i1 = (k + 6) % 7, k % 7
                a = QPointF((pa_[i0].x() + pb_[i0].x()) / 2, (pa_[i0].y() + pb_[i0].y()) / 2)
                b = QPointF((pa_[i1].x() + pb_[i1].x()) / 2, (pa_[i1].y() + pb_[i1].y()) / 2)
                self._text_on_line(p, a, b, names[k], self._col(st + k * 0.008, st + 0.1 + k * 0.008, TEXT), R * 0.036)

        # 五芒星と十字
        rp = R * 0.33
        P = _poly(cx, cy, rp, 5, -math.pi / 2)
        colP = self._col(0.80, 0.90, YELLOW)
        p.setPen(QPen(colP, 1.4))
        for k in range(5):
            p.drawLine(P[k], P[(k + 2) % 5])
        cs = R * 0.05
        p.drawLine(QPointF(cx - cs, cy), QPointF(cx + cs, cy))
        p.drawLine(QPointF(cx, cy - cs), QPointF(cx, cy + cs))

        # 水晶(印章の真ん中に置く)
        if self.lit >= 0.88:
            k = min(1.0, (self.lit - 0.88) / 0.12)
            t = self._clock.elapsed() / 1000 if self.seeing else None
            pm = crystal_image(t) if t is not None else self._crystal_still
            size = int(R * 0.40 // 32 * 32) or 32  # 32の整数倍 = ドットが揃う
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
            p.setOpacity(k)
            if self.seeing:
                gl = QRadialGradient(QPointF(cx, cy), size)
                gl.setColorAt(0, QColor(195, 155, 255, 90))
                gl.setColorAt(1, QColor(0, 0, 0, 0))
                p.setBrush(QBrush(gl))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(cx, cy), size, size)
            p.drawPixmap(QRectF(cx - size / 2, cy - size / 2, size, size), pm, QRectF(0, 0, 32, 32))
            p.setOpacity(1.0)

        p.setFont(QFont(ui_font(), 9))
        p.setPen(QColor(DIM))
        p.drawText(8, h - 10, "形と名前: John Dee, Sloane MS 3188(外周40文字・五芒星の文字は省略)")
        p.end()


def load_sessions() -> list[dict]:
    out = []
    if SCRY_DIR.exists():
        for f in SCRY_DIR.glob("*.json"):
            try:
                out.append(json.loads(f.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
    return sorted(out, key=lambda r: r.get("ts", ""))


def save_session(rec: dict):
    SCRY_DIR.mkdir(parents=True, exist_ok=True)
    f = SCRY_DIR / f"{rec['id']}.json"
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, f)


def session_text(rec: dict) -> str:
    head = (f"  第{rec['aethyr']}のアエティール {EN.aethyr(rec['aethyr'])[1]}" if rec.get("aethyr")
            else f"  マスの霊視 {rec['square']}" if rec.get("square") else "")
    lines = [f"{rec.get('ts', '')[:16].replace('T', ' ')}  霊視の記録{head}  ({rec.get('model', '')})", ""]
    for t in rec.get("turns", []):
        who = "Δ" if t["role"] == "user" else "E.K."
        txt = "(祈りののち、水晶を覗く)" if is_opening(t) else t["content"]
        lines += [f"{who}: {txt}", ""]
    return "\n".join(lines)


class ScryTab(QWidget):
    def __init__(self, app: "Main"):
        super().__init__()
        self.app = app
        self.worker: LLMWorker | None = None
        self.rec: dict | None = None
        lay = QHBoxLayout(self)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.seal = SealView()
        split.addWidget(self.seal)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(8, 0, 0, 0)
        rl.addWidget(heading("SCRYING  // 水晶の霊視", YELLOW))
        note = QLabel("Δ=あなた(ディーの役)が問い、E.K.(ケリーの役)=ローカルLLMが水晶に見えたものを語る。"
                      "印章は交信の前に場を整える台座として水晶の下に敷かれていた。")
        note.setWordWrap(True)
        note.setObjectName("sub")
        rl.addWidget(note)
        mrow = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItems(["自由な霊視", "アエティールの旅(第30 TEX → 第1 LIL)"])
        self.mode.currentIndexChanged.connect(self._refresh_journey)
        mrow.addWidget(self.mode, 1)
        rl.addLayout(mrow)
        self.bar = AethyrBar()
        rl.addWidget(self.bar)
        self.journey = QLabel("")
        self.journey.setWordWrap(True)
        rl.addWidget(self.journey)
        from PyQt6.QtWidgets import QTextBrowser
        self.log = QTextBrowser()
        self.log.setStyleSheet(f"background:{PANEL}; border:1px solid {DIM};")
        rl.addWidget(self.log, 1)
        row = QHBoxLayout()
        self.inp = QLineEdit()
        self.inp.setPlaceholderText("水晶に問う(例: 窓の向こうに何がいる?)")
        self.inp.returnPressed.connect(self.ask)
        self.ask_b = QPushButton("問う")
        self.ask_b.clicked.connect(self.ask)
        row.addWidget(self.inp, 1)
        row.addWidget(self.ask_b)
        rl.addLayout(row)
        row2 = QHBoxLayout()
        self.start_b = QPushButton("◈ 交信を始める")
        self.start_b.setObjectName("hot")
        self.start_b.clicked.connect(self.start)
        self.end_b = QPushButton("封じる(終える)")
        self.end_b.clicked.connect(self.end)
        row2.addWidget(self.start_b)
        row2.addStretch()
        row2.addWidget(self.end_b)
        rl.addLayout(row2)
        self.status = QLabel("")
        self.status.setObjectName("sub")
        rl.addWidget(self.status)
        split.addWidget(right)
        split.setSizes([620, 500])
        lay.addWidget(split)
        self._set_active(False)
        self._refresh_journey()

    def _refresh_journey(self, *_):
        on = self.mode.currentIndex() == 1
        self.bar.setVisible(on)
        self.journey.setVisible(on)
        done, nxt = aethyr_done(), next_aethyr()
        self.bar.set_state(done, nxt)
        if nxt is None:
            self.journey.setText(f"<span style='color:{YELLOW}'>30のアエティールを巡り終えた。</span>")
            return
        n, name, govs = EN.aethyr(nxt)
        alt = [f"{g}(異読 {EN.GOV_VARIANTS[g]})" for g in govs if g in EN.GOV_VARIANTS]
        self.journey.setText(
            f"<span style='color:{CYAN}'>次: 第{n}のアエティール <b>{name}</b></span>  {len(done)}/30 済<br>"
            f"<span style='color:{LIL_TXT}'>統治者: {'・'.join(govs)}</span>"
            + (f"<br><span style='color:{DIM}'>{' / '.join(alt)}</span>" if alt else ""))

    def _set_active(self, on: bool):
        self.inp.setEnabled(on)
        self.ask_b.setEnabled(on)
        self.end_b.setEnabled(on)
        self.start_b.setEnabled(not on)

    def _block(self, html: str):
        """記録欄に段落を1つ足す(insertHtml だけだと前の段落にくっつく)"""
        cur = self.log.textCursor()
        cur.movePosition(cur.MoveOperation.End)
        if not self.log.document().isEmpty():
            cur.insertBlock()
        cur.insertHtml(html)
        self.log.setTextCursor(cur)
        self.log.ensureCursorVisible()

    def _note(self, text: str):
        self._block(f"<span style='color:{DIM}'>{text}</span>")

    def _append(self, who: str, text: str):
        color = CYAN if who == "Δ" else MAGENTA
        safe = text.replace("&", "&amp;").replace("<", "&lt;").replace("\n", "<br>")
        self._block(f"<span style='color:{color}'>{who}:</span> <span style='color:{TEXT}'>{safe}</span>")

    def start(self):
        tgt, why = self.app.llm_target()
        if not tgt:
            self.status.setText(f"水晶は曇ったまま… ({why})")
            return
        self.log.clear()
        now = datetime.now().astimezone()
        self.rec = {"id": now.strftime("%Y%m%d-%H%M%S"), "ts": now.isoformat(timespec="seconds"),
                    "model": tgt["name"], "turns": []}
        self._note(f"{now.strftime('%Y年%m月%d日 %H:%M')} — 霊視の記録")
        opening = SCRY_OPEN
        if self.mode.currentIndex() == 1:
            nxt = next_aethyr()
            if nxt is None:
                self.status.setText("30のアエティールはもう巡り終えています")
                self.rec = None
                return
            n, name, govs = EN.aethyr(nxt)
            self.rec["aethyr"] = n
            words = EN.call19_for(name).split()
            self._note(f"第19の呼びかけ — 第{n}のアエティール {name}")
            self._block(f"<span style='color:{LIL_TXT}'>{' '.join(words[:12])} …</span>")
            self._note(EN.CALL19_EN_HEAD.replace("___", name))
            self._note(f"統治者の名を呼ぶ: {'・'.join(govs)}")
            opening = (f"(第19の呼びかけを「{name}」の名で唱え終え、統治者 {'・'.join(govs)} の名を呼んだ。"
                       f"E.K. は水晶を覗く。第{n}のアエティール {name} の最初の光景を語れ)")
        self.status.setText("印章に灯をともしています…")
        self.start_b.setEnabled(False)
        self.mode.setEnabled(False)
        self.seal.start_ritual(lambda: self._send(opening, show=False))

    def start_square(self, opening: str, extra_prompt: str, label: str, chain_lines: list[str]):
        """エノキアンタブの「このマスを霊視する」から。印章を灯してから、そのマスへ入る"""
        if self.worker and self.worker.isRunning():
            return
        tgt, why = self.app.llm_target()
        if not tgt:
            self.status.setText(f"水晶は曇ったまま… ({why})")
            return
        self.mode.setCurrentIndex(0)
        self.log.clear()
        now = datetime.now().astimezone()
        self.rec = {"id": now.strftime("%Y%m%d-%H%M%S"), "ts": now.isoformat(timespec="seconds"),
                    "model": tgt["name"], "turns": [], "square": label, "square_prompt": extra_prompt}
        self._note(f"{now.strftime('%Y年%m月%d日 %H:%M')} — マスの霊視 {label}")
        for ln in chain_lines:
            self._block(f"<span style='color:{LIL_TXT}'>{ln}</span>")
        self.status.setText("印章に灯をともしています…")
        self.start_b.setEnabled(False)
        self.mode.setEnabled(False)
        self.seal.start_ritual(lambda: self._send(opening, show=False))

    def ask(self):
        q = self.inp.text().strip()
        if not q or not self.rec or (self.worker and self.worker.isRunning()):
            return
        self.inp.clear()
        self._send(q)

    def _send(self, text: str, show: bool = True):
        tgt, why = self.app.llm_target()
        if not tgt:
            self.status.setText(f"水晶は曇ったまま… ({why})")
            self._set_active(True)
            return
        if show:
            self._append("Δ", text)
        else:
            self._note("(祈りののち、E.K. は水晶を覗く)")
        self.rec["turns"].append({"role": "user", "content": text})
        self._set_active(False)
        self.start_b.setEnabled(False)
        self.status.setText(f"E.K. が水晶を覗いています… ({tgt['name']})")
        self.seal.set_seeing(True)
        self._block(f"<span style='color:{MAGENTA}'>E.K.:</span> ")
        system = SCRY_PROMPT + self.rec.get("square_prompt", "")
        if self.rec.get("aethyr"):
            n, name, govs = EN.aethyr(self.rec["aethyr"])
            system += AETHYR_PROMPT.format(n=n, name=name, govs="・".join(govs))
        self.worker = LLMWorker(tgt["url"], tgt["model_id"], list(self.rec["turns"]), tgt.get("llama", True),
                                system, temperature=1.0, max_tokens=700)
        self.worker.chunk.connect(self._chunk)
        self.worker.done.connect(self._done)
        self.worker.start()

    def _chunk(self, t: str):
        from PyQt6.QtGui import QTextCharFormat
        cur = self.log.textCursor()
        cur.movePosition(cur.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(TEXT))
        cur.insertText(t, fmt)
        self.log.setTextCursor(cur)
        self.log.ensureCursorVisible()

    def _done(self, text: str, ok: bool):
        self.seal.set_seeing(False)
        self._set_active(True)
        if ok:
            self.rec["turns"].append({"role": "assistant", "content": text})
            save_session(self.rec)  # 1往復ごとに保存(途中で閉じても残る)
            self.app.hist_tab.refresh()
            self.status.setText(f"{len(self.rec['turns']) // 2} 往復  /  記録しました")
        else:
            self.rec["turns"].pop()  # 答えの無い問いは記録しない
            self._chunk(f"\n[像が消えた: {text}]")
            self.status.setText("LLMの呼び出しに失敗しました")

    def end(self):
        if self.worker and self.worker.isRunning():
            return
        if self.rec and self.rec["turns"]:
            save_session(self.rec)
            if self.rec.get("aethyr") and any(t["role"] == "assistant" for t in self.rec["turns"]):
                mark_aethyr(self.rec["aethyr"])   # 霊視が1回でもあれば、その層は巡った
        self._note("— 封じた —")
        self.mode.setEnabled(True)
        self._refresh_journey()
        self.rec = None
        self.seal.set_lit(0.0)
        self._set_active(False)
        self.status.setText("交信を終えました")

    def restore(self, rec: dict):
        """履歴から開く: 記録を表示して、その続きから問える"""
        self.rec = rec
        self.mode.setCurrentIndex(1 if rec.get("aethyr") else 0)
        self.mode.setEnabled(False)
        self.log.clear()
        self._note(f"{rec.get('ts', '')[:16].replace('T', ' ')} — 霊視の記録(続きから)")
        for t in rec.get("turns", []):
            if is_opening(t):
                self._note("(祈りののち、E.K. は水晶を覗く)")
            else:
                self._append("Δ" if t["role"] == "user" else "E.K.", t["content"])
        self.seal.set_lit(1.0)
        self._set_active(True)


# ───────────────────────── エノキアン・タブレット(名前の取り出し方を見せる) ─────────────────────────
TAB_TINT = {"air": "#3a3412", "water": "#10263c", "earth": "#14301a", "fire": "#3c1616"}
TAB_EDGE = {"air": "#f8e04a", "water": "#4aa8ff", "earth": "#5ad46a", "fire": "#ff5a4a"}


class EnochView(QWidget):
    """大きな表(4枚+黒十字)と結合のタブレット。名前を選ぶと、読む順にマスが1文字ずつ光る"""
    stepped = pyqtSignal(str, int)   # ここまでの名前, 何文字目

    def __init__(self):
        super().__init__()
        self.setMinimumSize(480, 560)
        self.setMouseTracking(True)
        self.path: list[tuple] = []
        self.name = ""
        self.step = 0
        self.focus_tab: str | None = None
        self.timer = QTimer(self, interval=150, timeout=self._tick)   # 光っていく間だけ回す

    def play(self, entry: dict):
        self.path = entry["cells"]
        self.name = entry["name"]
        tab = entry.get("tab")
        self.focus_tab = tab
        # 結合のタブレットのマスは ("union", i, j)、それ以外はタブレットの (r, c) を (tab, r, c) にそろえる
        self.path = [c if c[0] == "union" else (tab, c[0], c[1]) for c in entry["cells"]]
        self.step = 0
        self.timer.start()
        self.update()

    def _tick(self):
        self.step += 1
        self.stepped.emit(self.name[:self.step], self.step)
        if self.step >= len(self.path):
            self.timer.stop()
        self.update()

    def _geom(self):
        W, H = self.width(), self.height()
        cell = min((W - 16) / EN.GRID_W, (H - 16) / (EN.GRID_H + 5.5))
        ox = (W - cell * EN.GRID_W) / 2
        oy = 8
        uy = oy + cell * (EN.GRID_H + 1.0)          # 結合のタブレット(5×4)は下に
        ux = (W - cell * 5) / 2
        return cell, ox, oy, ux, uy

    def _rect(self, key, g=None):
        cell, ox, oy, ux, uy = g or self._geom()
        if key[0] == "union":
            _, i, j = key
            return QRectF(ux + j * cell, uy + i * cell, cell, cell)
        tab, r, c = key
        R0, C0 = EN.ORIGIN[tab]
        return QRectF(ox + (C0 + c) * cell, oy + (R0 + r) * cell, cell, cell)

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(BG))
        g = self._geom()
        cell, ox, oy, ux, uy = g
        f = QFont(ui_font())
        f.setPixelSize(max(7, int(cell * 0.58)))
        p.setFont(f)
        lit = set(self.path[:self.step])
        for R in range(EN.GRID_H):
            for C in range(EN.GRID_W):
                kind, tab, r, c, ch = EN.great_cell(R, C)
                rect = QRectF(ox + C * cell, oy + R * cell, cell, cell)
                if kind == "cross":
                    p.fillRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), QColor("#1a1424"))
                    if ch:
                        p.setPen(QColor(MAGENTA))
                        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, ch)
                    continue
                base = QColor(TAB_TINT[tab])
                rl = EN.role(tab, r, c)
                if rl.startswith(("中心", "霊の線", "父の線", "子の線")):
                    base = base.lighter(175)          # 中心の大十字
                elif "カルヴァリ" in rl:
                    base = base.lighter(135)          # 小区画の十字
                if self.focus_tab and tab != self.focus_tab:
                    base = base.darker(150)
                p.fillRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), base)
                on = (tab, r, c) in lit
                if on:
                    p.fillRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), QColor(248, 224, 74, 200))
                p.setPen(QColor(BG if on else TEXT))
                if (r, c) in EN.REVERSED[tab]:   # 裏返しに書かれた文字
                    p.save()
                    p.translate(rect.center())
                    p.scale(-1, 1)
                    p.drawText(QRectF(-cell / 2, -cell / 2, cell, cell), Qt.AlignmentFlag.AlignCenter, ch)
                    p.restore()
                else:
                    p.drawText(rect, Qt.AlignmentFlag.AlignCenter, ch)
        # タブレットの外枠と小区画の区切り
        for tab, (R0, C0) in EN.ORIGIN.items():
            col = QColor(TAB_EDGE[tab])
            if self.focus_tab and tab != self.focus_tab:
                col.setAlpha(90)
            p.setPen(QPen(col, 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(QRectF(ox + C0 * cell, oy + R0 * cell, 12 * cell, 13 * cell))
        # 結合のタブレット
        p.setPen(QColor(DIM))
        p.drawText(QRectF(ux - cell * 6, uy, cell * 5.6, cell), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "結合")
        for i, row in enumerate(EN.UNION):
            for j, ch in enumerate(row):
                rect = QRectF(ux + j * cell, uy + i * cell, cell, cell)
                on = ("union", i, j) in lit
                p.fillRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), QColor(248, 224, 74, 200) if on else QColor("#2a1a3a"))
                p.setPen(QColor(BG if on else LIL_TXT))
                p.drawText(rect, Qt.AlignmentFlag.AlignCenter, ch)
        # 読む順の線
        if self.step > 0:
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            pts = [self._rect(k, g).center() for k in self.path[:self.step]]
            p.setPen(QPen(QColor(MAGENTA), max(1.5, cell * 0.09)))
            for a, b in zip(pts, pts[1:]):
                p.drawLine(a, b)
            last = self._rect(self.path[self.step - 1], g)
            p.setPen(QPen(QColor(MAGENTA), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(last.adjusted(-1, -1, 1, 1))
            first = self._rect(self.path[0], g)
            p.setBrush(QColor(MAGENTA))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(first.center(), cell * 0.12, cell * 0.12)
        p.end()

    def _key_at(self, pos):
        cell, ox, oy, ux, uy = self._geom()
        C, R = int((pos.x() - ox) // cell), int((pos.y() - oy) // cell)
        if 0 <= R < EN.GRID_H and 0 <= C < EN.GRID_W:
            return EN.great_cell(R, C)
        j, i = int((pos.x() - ux) // cell), int((pos.y() - uy) // cell)
        if 0 <= i < 4 and 0 <= j < 5:
            return ("union", i, j)
        return None

    def mouseMoveEvent(self, e):
        k = self._key_at(e.position())
        if not k:
            self.setToolTip("")
        elif k[0] == "union":
            _, i, j = k
            self.setToolTip(f"結合のタブレット {i + 1}行{j + 1}列 「{EN.UNION[i][j]}」 行={EN.ELEMENTS[i]} / 列={['霊', '空気', '水', '地', '火'][j]}")
        elif k[0] == "cross":
            self.setToolTip(f"黒十字 「{k[4]}」(結合のタブレットの文字を並べた帯)" if k[4] else "黒十字")
        else:
            _, tab, r, c, ch = k
            rv = "(裏返し)" if (r, c) in EN.REVERSED[tab] else ""
            self.setToolTip(f"{EN.ELEMENTS[EN.ELEMENT_KEY.index(tab)]}のタブレット {r + 1}行{c + 1}列 「{ch}」{rv}\n{EN.role(tab, r, c)}")


# ───────── タロットから入る(カード → 物見の塔のマス) ─────────
SUIT_TAB = {"wands": "fire", "cups": "water", "swords": "air", "pentacles": "earth"}
COURT_SUB = {"knight": "fire", "queen": "water", "king": "air", "page": "earth"}
ELEM_COL = {"火": "#c83c3c", "水": "#3c6cc8", "空気": "#d8c040", "地": "#3c8a4a", "霊": "#e8e8f0"}


def _planet_of(s: int, k: int) -> str:
    from cards_data import DECAN_RULERS
    return DECAN_RULERS[s][k]


def card_squares(cid: str, rng=None) -> dict:
    """カードに対応するマス。traditional=True は Liber Chanokh の規則どおり、False はこのアプリが決めた部分"""
    from cards_data import DECAN_RULERS, SIGN_ELEMENT, SIGN_JA
    rng = rng or random.SystemRandom()
    c = BY_ID[cid]
    g = c["gd"]
    key_of_el = {v: k for k, v in EN.ELEM_OF_KEY.items()}
    key_of_el["風"] = "air"   # cards_data は空気を「風」と書く
    cross = lambda tab: [(r, cc) for r in range(13) for cc in range(12) if EN.cross_decan(tab, r, cc)]
    if not c["major"]:
        suit, rest = cid.split("_", 1)
        n = int(rest[:2])
        tab = SUIT_TAB[suit]
        if 2 <= n <= 10:
            s = g["signs"][0]
            k = int((g["zone"][0] - s * 30) // 10)
            cell = next(x for x in cross(tab) if EN.cross_decan(tab, *x) == (s, k))
            return {"tab": tab, "cells": [cell], "traditional": True,
                    "how": f"{SIGN_JA[s]}の第{k + 1}デカン(支配星 {DECAN_RULERS[s][k]})= 中心の大十字のマス。塔はスートの元素で選ぶ。"}
        if n == 1:
            r0, c0 = EN.SUBQUADS[tab]
            return {"tab": tab, "cells": [(r0, c0 + 2)], "traditional": False,
                    "how": f"エース = ケテル(セフィロト1番)。小区画は{EN.ELEM_OF_KEY[tab]}の中の{EN.ELEM_OF_KEY[tab]}(このアプリの選び方)。"}
        court = rest.split("_")[1]
        sub = COURT_SUB[court]
        r0, c0 = EN.SUBQUADS[sub]
        cells = [(r0, c0 + j) for j in range(5) if j != 2]
        return {"tab": tab, "cells": cells, "traditional": False,
                "how": f"絵札 = ケルビムのマス。{EN.ELEM_OF_KEY[tab]}の中の{EN.ELEM_OF_KEY[sub]}の4マス"
                       f"(どの1マスかの規則は原典が省略しているので4つとも)。"}
    if g["signs"]:
        s = g["signs"][0]
        tab = key_of_el[SIGN_ELEMENT[s]]
        cells = [x for x in cross(tab) if EN.cross_decan(tab, *x)[0] == s]
        return {"tab": tab, "cells": cells, "traditional": False,
                "how": f"{SIGN_JA[s]}のカード → その星座の3デカンのマス。塔は星座の元素({SIGN_ELEMENT[s]})。"}
    if g["planet"]:
        tab = rng.choice(EN.ELEMENT_KEY)
        cells = [x for x in cross(tab) if _planet_of(*EN.cross_decan(tab, *x)) == g["planet"]]
        return {"tab": tab, "cells": cells, "traditional": False,
                "how": f"{g['planet']}のカード → {g['planet']}が支配するデカンのマス。惑星は4つの塔すべてにいるので、"
                       f"今回は運で{EN.ELEM_OF_KEY[tab]}の塔。"}
    tab = key_of_el[g["element"]]
    cells = [(6, 4), (5, 5), (5, 6), (6, 7), (7, 6), (7, 5), (6, 5), (6, 6)]
    return {"tab": tab, "cells": cells, "traditional": False,
            "how": f"元素({g['element']})のカード → {g['element']}の塔の大王の座(中心の渦)。"}


def square_pyramid(tab: str, r: int, c: int) -> dict:
    from cards_data import PLANET_GLYPH, SIGN_GLYPH, SIGN_JA
    # 星座記号は絵文字フォントに化けて消えるので、記号の直後に U+FE0E(文字として表示)を付ける
    return EN.pyramid(tab, r, c, sign_glyph=lambda s: f"{SIGN_GLYPH[s]}\uFE0E {SIGN_JA[s]}",
                      planet_of=lambda s, k: f"{PLANET_GLYPH[_planet_of(s, k)]} {_planet_of(s, k)}")


class PyramidView(QWidget):
    """マスの四角錐を真上から見た図。中の小さな正方形が頂上(文字)、まわりの4つの台形が4面"""

    def __init__(self):
        super().__init__()
        self.setMinimumSize(200, 200)
        self.pyr: dict | None = None
        self.letter = ""

    def set_square(self, pyr: dict, letter: str):
        self.pyr, self.letter = pyr, letter
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(BG))
        if not self.pyr:
            p.end()
            return
        S = min(self.width(), self.height()) - 10
        x0, y0 = (self.width() - S) / 2, (self.height() - S) / 2
        a, b = S * 0.32, S * 0.68
        O = [QPointF(x0, y0), QPointF(x0 + S, y0), QPointF(x0 + S, y0 + S), QPointF(x0, y0 + S)]
        I = [QPointF(x0 + a, y0 + a), QPointF(x0 + b, y0 + a), QPointF(x0 + b, y0 + b), QPointF(x0 + a, y0 + b)]
        sides = [("top", O[0], O[1], I[1], I[0]), ("right", O[1], O[2], I[2], I[1]),
                 ("bottom", O[2], O[3], I[3], I[2]), ("left", O[3], O[0], I[0], I[3])]
        f = QFont(GLYPH_FONT)
        f.setPixelSize(max(9, int(S * 0.065)))
        for name, p1, p2, p3, p4 in sides:
            val = self.pyr[name]
            el = val if val in ELEM_COL else None
            col = QColor(ELEM_COL[el]) if el else QColor("#3a2a5a")
            if val == "?":
                col = QColor("#202030")
            from PyQt6.QtGui import QPolygonF
            poly = QPolygonF([p1, p2, p3, p4])
            p.setBrush(col)
            p.setPen(QPen(QColor(BG), 2))
            p.drawPolygon(poly)
            cxp = (p1.x() + p2.x() + p3.x() + p4.x()) / 4
            cyp = (p1.y() + p2.y() + p3.y() + p4.y()) / 4
            p.setFont(f)
            p.setPen(QColor(BG if el in ("空気", "霊") else TEXT))
            p.drawText(QRectF(cxp - S * 0.3, cyp - S * 0.08, S * 0.6, S * 0.16), Qt.AlignmentFlag.AlignCenter, val)
        p.setBrush(QColor(PANEL))
        p.setPen(QPen(QColor(YELLOW), 2))
        from PyQt6.QtGui import QPolygonF
        p.drawPolygon(QPolygonF(I))
        fl = QFont(ui_font())
        fl.setPixelSize(int(S * 0.2))
        p.setFont(fl)
        p.setPen(QColor(YELLOW))
        p.drawText(QRectF(x0 + a, y0 + a, b - a, b - a), Qt.AlignmentFlag.AlignCenter, self.letter)
        p.end()


SQUARE_PROMPT = """
今回は黄金の夜明け団の「マスの霊視」。物見の塔の1マスを四角錐として思い描き、その中へ入る。
- 塔: {tower}の塔 / {pos} / 文字「{letter}」/ マスの種類: {kind}
- 四角錐の4面: 上={top} 下={bottom} 左={left} 右={right}
- 問う人が唱えた名(上の階層から): {chain}
- 入口になったタロット: {card}
- 四角錐の頂上から中へ入り、そこに広がる世界を描写する。4面の元素・星座・惑星・セフィラの性質が、風景・光・色・温度に表れる。
- マスの天使(文字「{letter}」を持つ存在)や、唱えた名の存在が現れて、短く語ることがある。"""


class EnochTab(QWidget):
    def __init__(self, app: "Main"):
        super().__init__()
        self.app = app
        lay = QHBoxLayout(self)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.view = EnochView()
        self.view.stepped.connect(self._stepped)
        split.addWidget(self.view)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(8, 0, 0, 0)
        rl.addWidget(heading("ENOCHIAN  // 物見の塔(1587年改訂版)", YELLOW))
        note = QLabel("タブレットは「名前を取り出すための表」。名前を押すと、どのマスをどの順に読むかが光る。"
                      "上の階層から順に: 結合のタブレットの霊名 → 三つの聖名 → 大王 → 六長老 → 小区画の十字の神名 → ケルビム → 奉仕天使。"
                      "下の名前は上の名前で呼び出し・従わせる。")
        note.setWordWrap(True)
        note.setObjectName("sub")
        rl.addWidget(note)
        inner = QTabWidget()
        rl.addWidget(inner, 1)
        page1 = QWidget()
        p1 = QVBoxLayout(page1)
        p1.setContentsMargins(0, 4, 0, 0)
        inner.addTab(page1, "名前の取り出し")
        inner.addTab(self._tarot_page(), "タロットから入る")
        rl_outer, rl = rl, p1
        from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setStyleSheet(f"QTreeWidget {{ background:{PANEL}; border:1px solid {DIM}; }}"
                                f"QTreeWidget::item:selected {{ background:{MAGENTA}; color:{BG}; }}")
        self.entries: dict[int, dict] = {}
        top = QTreeWidgetItem(["結合のタブレット(霊)"])
        self.tree.addTopLevelItem(top)
        for e in EN.union_names():
            self._leaf(top, dict(e, tab=None))
        for key, ja in zip(EN.ELEMENT_KEY, EN.ELEMENTS):
            t = QTreeWidgetItem([f"{ja}のタブレット"])
            self.tree.addTopLevelItem(t)
            groups: dict[str, QTreeWidgetItem] = {}
            for e in EN.derive(key):
                if e["group"] not in groups:
                    groups[e["group"]] = QTreeWidgetItem([e["group"]])
                    t.addChild(groups[e["group"]])
                self._leaf(groups[e["group"]], dict(e, tab=key))
        self.tree.itemClicked.connect(self._clicked)
        rl.addWidget(self.tree, 1)
        self.big = QLabel("")
        self.big.setStyleSheet(f"color:{YELLOW}; font-size:26px; letter-spacing:6px;")
        glow(self.big, YELLOW, 14)
        rl.addWidget(self.big)
        self.rule = QLabel("")
        self.rule.setWordWrap(True)
        rl.addWidget(self.rule)
        src = QLabel("文字: Tabula Recensa(1587)/ 取り出し方: ディーの方法(“On Methods Vsed to Deriue … Names”)。"
                     "文書の例と全部一致することを確認済み。ケルビムの大天使・悪霊(カコダエモン)は規則が読み切れないので入れていない。"
                     "U と V は同じ文字。")
        src.setWordWrap(True)
        src.setObjectName("sub")
        rl_outer.addWidget(src)
        split.addWidget(right)
        split.setSizes([660, 460])
        lay.addWidget(split)

    def _tarot_page(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 4, 0, 0)
        row = QHBoxLayout()
        self.draw_b = QPushButton("✦ カードを1枚引く")
        self.draw_b.setObjectName("hot")
        self.draw_b.clicked.connect(self.draw_card)
        self.enter_b = QPushButton("◈ このマスを霊視する")
        self.enter_b.clicked.connect(self.enter_square)
        self.enter_b.setEnabled(False)
        row.addWidget(self.draw_b)
        row.addWidget(self.enter_b)
        v.addLayout(row)
        mid = QHBoxLayout()
        self.t_card = QLabel()
        self.t_card.setFixedSize(CW * 2, CH * 2)
        self.t_card.setStyleSheet(f"border:1px solid {DIM};")
        mid.addWidget(self.t_card)
        self.pyr = PyramidView()
        mid.addWidget(self.pyr, 1)
        v.addLayout(mid)
        self.t_info = QLabel("カードを引くと、そのカードに対応する物見の塔のマスへ飛び、マスの四角錐(4つの面の対応)を見せる。")
        self.t_info.setWordWrap(True)
        self.t_info.setAlignment(Qt.AlignmentFlag.AlignTop)
        v.addWidget(self.t_info, 1)
        note = QLabel("規則: 中心の大十字=36デカン=数札2〜10、小区画の十字=セフィロト(Liber Chanokh / The Equinox I:7、Plate IV と照合済み)。"
                      "★ は原典どおり、☆ はこのアプリが決めた部分(エース・絵札・大アルカナの行き先)。")
        note.setWordWrap(True)
        note.setObjectName("sub")
        v.addWidget(note)
        return w

    def draw_card(self):
        cid = random.SystemRandom().choice(CARDS)["id"]
        self.show_card_square(cid)

    def show_card_square(self, cid: str, info: dict | None = None):
        from cards_data import BY_ID as B
        info = info or card_squares(cid)
        self.t_cid, self.t_sq = cid, info
        c = B[cid]
        self.t_card.setPixmap(self.app.pix[cid].scaled(CW * 2, CH * 2, transformMode=Qt.TransformationMode.FastTransformation))
        tab = info["tab"]
        r, cc = info["cells"][0]
        pyr = square_pyramid(tab, r, cc)
        self.pyr.set_square(pyr, EN.letter(tab, r, cc))
        mark = "★ 原典どおり" if info["traditional"] else "☆ このアプリが決めた行き先"
        chain = EN.invocation_chain(tab, r, cc)
        more = f"(ほか{len(info['cells']) - 1}マスも光る・四角錐は最初のマス)" if len(info["cells"]) > 1 else ""
        self.t_info.setText(
            f"<span style='color:{YELLOW}; font-size:15px'>{c['ja']}</span> <span style='color:{DIM}'>{c['en']}</span><br>"
            f"<span style='color:{LIL_TXT}'>黄金の夜明け: {c['gd']['text']}</span><br>"
            f"<span style='color:{CYAN}'>→ {EN.ELEM_OF_KEY[tab]}の塔 {r + 1}行{cc + 1}列「{EN.letter(tab, r, cc)}」</span> {more}<br>"
            f"{info['how']} <span style='color:{YELLOW if info['traditional'] else DIM}'>{mark}</span><br>"
            f"<span style='color:{DIM}'>{pyr['kind']} / 上={pyr['top']} 下={pyr['bottom']} 左={pyr['left']} 右={pyr['right']}</span><br>"
            f"<span style='color:{DIM}'>唱える名: {' → '.join(n for _, n in chain)}</span>")
        self.view.play({"tab": tab, "cells": info["cells"], "name": EN.letter(tab, r, cc)})
        self.cur = {"name": ""}
        self.enter_b.setEnabled(True)

    def enter_square(self):
        from cards_data import BY_ID as B
        tab = self.t_sq["tab"]
        r, cc = self.t_sq["cells"][0]
        pyr = square_pyramid(tab, r, cc)
        chain = EN.invocation_chain(tab, r, cc)
        letter = EN.letter(tab, r, cc)
        tower = EN.ELEM_OF_KEY[tab]
        c = B[self.t_cid]
        extra = SQUARE_PROMPT.format(tower=tower, pos=f"{r + 1}行{cc + 1}列", letter=letter, kind=pyr["kind"],
                                     top=pyr["top"], bottom=pyr["bottom"], left=pyr["left"], right=pyr["right"],
                                     chain=" → ".join(f"{k} {n}" for k, n in chain), card=f"{c['ja']}({c['gd']['text']})")
        opening = (f"(名を唱えた: {' → '.join(n for _, n in chain)}。{tower}の塔 {r + 1}行{cc + 1}列「{letter}」の四角錐の前に立つ。"
                   f"E.K. は水晶を覗く。最初の光景を語れ)")
        label = f"{tower}の塔 {r + 1}-{cc + 1}「{letter}」"
        self.app.scry_tab.start_square(opening, extra, label, [f"{k}: {n}" for k, n in chain])
        self.app.tabs.setCurrentWidget(self.app.scry_tab)

    def _leaf(self, parent, e):
        from PyQt6.QtWidgets import QTreeWidgetItem
        it = QTreeWidgetItem([f"{e['label']} — {e['name']}"])
        it.setData(0, Qt.ItemDataRole.UserRole, len(self.entries))
        self.entries[len(self.entries)] = e
        parent.addChild(it)

    def _clicked(self, it, _col):
        idx = it.data(0, Qt.ItemDataRole.UserRole)
        if idx is None:
            it.setExpanded(not it.isExpanded())
            return
        e = self.entries[idx]
        self.cur = e
        self.big.setText("")
        where = "結合のタブレット" if e["tab"] is None else f"{EN.ELEMENTS[EN.ELEMENT_KEY.index(e['tab'])]}のタブレット"
        self.rule.setText(f"<span style='color:{CYAN}'>{where} / {e['group']} / {e['label']}</span><br>{e['rule']}")
        self.view.play(e)

    def _stepped(self, so_far: str, n: int):
        name = self.cur["name"]
        self.big.setText(f"{so_far}<span style='color:{DIM}'>{'・' * (len(name) - n)}</span>")


class HistoryTab(QWidget):
    def __init__(self, app: "Main"):
        super().__init__()
        self.app = app
        lay = QHBoxLayout(self)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.lst = QListWidget()
        self.lst.currentItemChanged.connect(self._show)
        split.addWidget(self.lst)
        right = QWidget()
        rl = QVBoxLayout(right)
        self.txt = QPlainTextEdit()
        self.txt.setReadOnly(True)
        rl.addWidget(self.txt, 1)
        b = QPushButton("この結果を盤面に開く")
        b.clicked.connect(self._open)
        rl.addWidget(b)
        split.addWidget(right)
        split.setSizes([340, 700])
        lay.addWidget(split)
        self.recs: list[dict] = []
        self.refresh()

    def refresh(self):
        scry = [dict(r, spread="scry") for r in load_sessions()]
        self.recs = sorted(load_history() + scry, key=lambda r: r.get("ts", ""), reverse=True)
        self.lst.clear()
        for rec in self.recs:
            if rec.get("spread") == "scry":
                first = next((t["content"] for t in rec.get("turns", []) if t["role"] == "user" and not is_opening(t)), "(問いなし)")
                aeth = f"[{EN.aethyr(rec['aethyr'])[1]}] " if rec.get("aethyr") else f"[{rec['square']}] " if rec.get("square") else ""
                it = QListWidgetItem(f"◈ {rec.get('ts', '')[:16].replace('T', ' ')}  {aeth}{first[:24]}")
                self.lst.addItem(it)
                continue
            q = rec.get("question") or "(全体運)"
            mark = "☉" if rec.get("spread") == "horo" else "✚"
            who = f"[{rec['person']}] " if rec.get("person") and rec["person"] != "自分" else ""
            it = QListWidgetItem(f"{mark} {rec.get('ts', '')[:16].replace('T', ' ')}  {who}{q[:24]}")
            self.lst.addItem(it)

    def _show(self, cur, _prev):
        i = self.lst.row(cur) if cur else -1
        if not (0 <= i < len(self.recs)):
            self.txt.clear()
            return
        rec = self.recs[i]
        if rec.get("spread") == "scry":
            self.txt.setPlainText(session_text(rec))
            return
        pos = HOUSES if rec.get("spread") == "horo" else POSITIONS
        cards = "\n".join(card_line(k, c, bool(r), pos) for k, (c, r) in enumerate(rec["cards"]))
        self.txt.setPlainText(f"相談: {rec.get('question') or '(全体運)'}\nモデル: {rec.get('model', '')}\n\n{cards}\n\n{rec.get('reading', '')}")

    def _open(self):
        i = self.lst.currentRow()
        if 0 <= i < len(self.recs):
            sp = self.recs[i].get("spread")
            tab = self.app.horo_tab if sp == "horo" else self.app.scry_tab if sp == "scry" else self.app.read_tab
            tab.restore(self.recs[i])
            self.app.tabs.setCurrentWidget(tab)


def load_pixmaps() -> dict[str, QPixmap]:
    need = [c["id"] for c in CARDS] + ["back"]
    if any(not (CARD_DIR / f"{n}.png").exists() for n in need):
        subprocess.run([sys.executable, str(HERE / "tarot.py")], check=True)
    return {n: QPixmap(str(CARD_DIR / f"{n}.png")) for n in need}


class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PIXEL TAROT // ケルト十字・ホロスコープ")
        self.resize(1180, 800)
        self.pix = load_pixmaps()
        self.astro = Astro()  # 天体計算(skyfield)は ホロスコープ✕タロット を初めて開いたときに読む

        root = QWidget()
        rl = QVBoxLayout(root)
        bar = QHBoxLayout()
        title = QLabel("PIXEL TAROT")
        title.setStyleSheet(f"color:{CYAN}; font-size:22px; letter-spacing:4px;")
        glow(title, CYAN, 22)
        bar.addWidget(title)
        self.sub = sub = QLabel("CELTIC CROSS")
        sub.setStyleSheet(f"color:{MAGENTA}; letter-spacing:3px; padding-left:12px;")
        bar.addWidget(sub)
        bar.addStretch()
        self.llm_badge = QPushButton("LLM ◌ 検出中…")
        self.llm_badge.setFlat(True)
        self.llm_badge.setCursor(Qt.CursorShape.PointingHandCursor)
        self.llm_badge.setToolTip("ロード中のローカルLLM(クリックで再検出・15秒ごとに自動更新)")
        self.llm_badge.clicked.connect(self.probe_llm)
        bar.addWidget(self.llm_badge)
        rl.addLayout(bar)
        line = QFrame()
        line.setFixedHeight(2)
        line.setStyleSheet(f"background:{MAGENTA};")
        glow(line, MAGENTA, 12)
        rl.addWidget(line)

        self.tabs = QTabWidget()
        self.hist_tab = HistoryTab(self)
        self.read_tab = ReadTab(self)
        self.horo_tab = ReadTab(self, "horo")
        self.tabs.addTab(self.read_tab, "ケルト十字")
        self.tabs.addTab(self.horo_tab, "ホロスコープ✕タロット")
        self.scry_tab = ScryTab(self)
        self.tabs.addTab(self.scry_tab, "スクライング")
        self.enoch_tab = EnochTab(self)
        self.tabs.addTab(self.enoch_tab, "エノキアン")
        self.tabs.addTab(self.hist_tab, "履歴")
        self.tabs.currentChanged.connect(self._tab_changed)
        rl.addWidget(self.tabs, 1)
        self.setCentralWidget(root)

        self.servers: list[dict] = []
        self._probe = None
        QTimer(self, timeout=self.probe_llm, interval=15000).start()
        self.probe_llm()

    def closeEvent(self, e):
        # 動いているスレッドを置いたまま終わると Qt が abort する(QThread: Destroyed while thread is still running)
        for tab in (self.read_tab, self.horo_tab, self.scry_tab):
            if tab.worker and tab.worker.isRunning():
                tab.worker.stop = True
        for th in (self._probe, self.read_tab.worker, self.horo_tab.worker, self.scry_tab.worker):
            if th and th.isRunning():
                th.wait(5000)
        super().closeEvent(e)

    def _tab_changed(self, _i):
        cur = self.tabs.currentWidget()
        self.sub.setText("HOROSCOPE × TAROT" if cur is self.horo_tab else "CELTIC CROSS" if cur is self.read_tab
                         else "SIGILLUM DEI AEMETH" if cur is self.scry_tab
                         else "ENOCHIAN TABLETS" if cur is self.enoch_tab else "HISTORY")
        if self.tabs.currentWidget() is self.horo_tab and self.astro.A is None:
            self.astro.load(self.horo_tab.person)
            self.horo_tab.view.update()

    def probe_llm(self):
        if self._probe and self._probe.isRunning():
            return
        if self.isMinimized() and self.servers:
            return  # 見えていない間は回さない
        self._probe = LLMProbe()
        self._probe.found.connect(self._on_servers)
        self._probe.start()

    def _on_servers(self, servers: list[dict]):
        self.servers = servers
        ready = [s for s in servers if s["state"] == "ready"]
        if ready:
            s = ready[0]
            ctx = f"{s['ctx'] // 1024}K" if s.get("ctx") else ""
            more = f"  +{len(servers) - 1}" if len(servers) > 1 else ""
            self._badge(f"LLM ● {s['name']}  :{s['port']}  {ctx}{more}", GREEN)
        elif servers:
            self._badge(f"LLM ◐ {servers[0]['name']} 読み込み中…", YELLOW)
        else:
            self._badge("LLM × 未ロード(キーワードだけで占えます)", MAGENTA)

    def _badge(self, text: str, color: str):
        self.llm_badge.setText(text)
        self.llm_badge.setStyleSheet(f"QPushButton {{ border:none; color:{color}; padding:4px 10px; }}")

    def llm_target(self) -> tuple[dict | None, str]:
        ready = [s for s in self.servers if s["state"] == "ready"]
        if ready:
            return dict(ready[0], llama=True), ""
        if self.servers:
            return None, f"{self.servers[0]['name']} はまだ読み込み中"
        return None, "ローカルLLMがロードされていません"


def main():
    app = QApplication(sys.argv)
    app.setDesktopFileName("pixel-tarot")  # Wayland の app_id。.desktop と紐付けてアイコン化けを防ぐ
    app.setFont(QFont(ui_font(), 10))
    app.setStyleSheet(QSS)
    w = Main()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
