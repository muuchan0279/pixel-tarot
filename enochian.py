"""エノキアン・タブレット(1587年 ラファエルによる改訂版 = Tabula Recensa)と、名前の取り出し方。

文字の出典: "On Methods Vsed to Deriue Certayne Divers Names from the Enochian Tablets"
(funet occult archive: pub/doc/occult/hermetica/enochia/enocmeth.txt, enochtab.txt)。
大きな表(Great Table)の行をそのまま写した。取り出しの規則も同じ文書(ディーの方法による)から。
同じ文書の例(三つの聖名・大王・空気の六長老・十字の神名・ケルビム・奉仕天使)と一致することを
self_check() で確かめている。

入れていないもの: ケルビムの大天使と悪霊(カコダエモン)に付ける黒十字の文字は、文書の例どうしで
規則が読み切れないので扱わない。一部のマスにある2文字目の異読も扱わない。
"""
from __future__ import annotations

# 大きな表の上半分(空気 | 水)と下半分(地 | 火)。'::' の間にある1文字が黒十字の縦の帯
_UPPER = """
r Z i l a f A Y t l p a|e|T a O A d v p t D n i m
a r d Z a i d p a L a m| |a a b c o o r o m e b b
c z o n s a r o Y a v b|x|T o g c o n x m a l G m
T o i T t z o P a c o C|a|n h o d D i a l e a o c
S i g a s o m r b z n h|r|p a t A x i o V s P s N
f m o n d a T d i a r i|p|S a a i x a a r V r o i
o r o i b A h a o z p i| |m p h a r s l g a i o l
t N a b r V i x g a s d|h|M a m g l o i n L i r x
O i i i t T p a l O a i| |o l a a D n g a T a p a
A b a m o o o a C u c a|C|p a L c o i d x P a c n
N a o c O T t n p r n T|o|n d a z N z i V a a s a
o c a n m a g o t r o i|m|i i d P o n s d A s p i
S h i a l r a p m z o x|a|x r i n h t a r n d i L
"""
_LOWER = """
b O a Z a R o p h a R a|a|d o n p a T d a n V a a
u N n a x o P S o n d n|m|o l o a G e o o b a u a
a i g r a n o o m a g g|o|O P a m n o V G m d n m
o r p m n i n g b e a l|C|a p l s T e d e c a o p
r s O n i z i r l e m v| |s c m i o o n A m l o x
i z i n r C z i a M h l|h|V a r s G d L b r i a p
M o r d i a l h C t G a| |o i P t e a a p D o c e
O c a n c h i a s o m t|p|P s u a c N r Z i r Z a
A r b i z m i i l p i z|r|S i o d a o i n r z f m
O p a n a l a m S m a P|a|d a l t T d n a d i r e
d O l o P i n i a n b a|x|d i x o m o n s i o s p
r x p a o c s i z i x p| |O o D p z i A p a n l i
a x t i r V a s t r i m|e|r g o a n n p A C r a r
"""
# 黒十字の横の帯(上下のあいだの1行・25マス)。"_" は文字の無いマス
# 大きな表の文字位置から: 0-4 motib / 5-6 空き / 7-11 aTnan / 12 空き / 13-17 nanTa / 18-19 空き / 20-24 bitom
BLACK_CROSS_ROW = "m o t i b _ _ a T n a n _ n a n T a _ _ b i t o m".split()

UNION = ["EXARP", "HCOMA", "NANTA", "BITOM"]   # 結合のタブレット(行=空気/水/地/火、列=霊/空気/水/地/火)
ELEMENTS = ["空気", "水", "地", "火"]
GRID_W, GRID_H = 25, 27   # 大きな表 = 12 + 黒十字1 + 12 / 13 + 1 + 13
ORIGIN = {"air": (0, 0), "water": (0, 13), "earth": (14, 0), "fire": (14, 13)}
ELEMENT_KEY = ["air", "water", "earth", "fire"]


def _parse(block: str):
    left, mid, right = [], [], []
    for line in block.strip().splitlines():
        a, m, b = line.split("|")
        left.append(a.split())
        mid.append(m.strip())
        right.append(b.split())
    return left, mid, right


_ul, _um, _ur = _parse(_UPPER)
_ll, _lm, _lr = _parse(_LOWER)
TABLETS = {"air": _ul, "water": _ur, "earth": _ll, "fire": _lr}   # 各 13行×12列
BLACK_CROSS_UPPER = _um   # 縦の帯(上)13マス
BLACK_CROSS_LOWER = _lm   # 縦の帯(下)13マス

# 文字が裏返しに書かれているマス(enochtab.txt の {} 表記)。(行, 列) 0始まり
REVERSED = {
    "air": {(8, 0), (9, 0)},
    "water": {(4, 11), (12, 11)},
    "earth": {(7, 0), (8, 0)},
    "fire": {(12, 6), (12, 7)},
}

# 小区画: 左上=空気 右上=水 左下=地 右下=火(各タブレットの中で)。行0-5/7-12・列0-4/7-11
SUBQUADS = {"air": (0, 0), "water": (0, 7), "earth": (7, 0), "fire": (7, 7)}


def great_cell(R: int, C: int):
    """大きな表の(行,列) → (種類, タブレット, 行, 列, 文字)。種類 = tablet | cross | empty"""
    if R == 13:
        ch = BLACK_CROSS_ROW[C]
        return ("cross", None, R, C, "" if ch == "_" else ch)
    if C == 12:
        ch = (BLACK_CROSS_UPPER if R < 13 else BLACK_CROSS_LOWER)[R if R < 13 else R - 14]
        return ("cross", None, R, C, ch)
    tab = ("air" if C < 12 else "water") if R < 13 else ("earth" if C < 12 else "fire")
    r0, c0 = ORIGIN[tab]
    return ("tablet", tab, R - r0, C - c0, TABLETS[tab][R - r0][C - c0])


def role(tab: str, r: int, c: int) -> str:
    """マスの役割(GD の呼び方)"""
    if r == 6 and c in (5, 6):
        return "中心(霊・父・子の線が交わる)"
    if r == 6:
        return "霊の線 Linea Spiritus Sancti(三つの聖名・長老)"
    if c == 5:
        return "父の線 Linea Patris(長老)"
    if c == 6:
        return "子の線 Linea Filii(長老)"
    sub = ("air" if c < 5 else "water") if r < 6 else ("earth" if c < 5 else "fire")
    r0, c0 = SUBQUADS[sub]
    sr, sc = r - r0, c - c0
    where = f"{ELEMENTS[ELEMENT_KEY.index(tab)]}の中の{ELEMENTS[ELEMENT_KEY.index(sub)]}"
    if sc == 2 or sr == 1:
        return f"{where}・カルヴァリ十字(セフィロトのマス・十字の神名)"
    if sr == 0:
        return f"{where}・ケルビムのマス"
    return f"{where}・奉仕天使のマス"


def letter(tab: str, r: int, c: int) -> str:
    return TABLETS[tab][r][c]


def _name(tab, cells):
    return "".join(letter(tab, r, c) for r, c in cells).upper()


def derive(tab: str) -> list[dict]:
    """1枚のタブレットから名前を取り出す。各項目 = {group, label, name, cells[(r,c)], rule}"""
    out = []
    # 三つの聖名(霊の線 = 7行目を 3・4・5 文字に分ける)
    for (a, b), lab in (((0, 3), "第1の聖名"), ((3, 7), "第2の聖名"), ((7, 12), "第3の聖名")):
        cells = [(6, c) for c in range(a, b)]
        out.append({"group": "三つの聖名", "label": lab, "name": _name(tab, cells), "cells": cells,
                    "rule": "7行目(霊の線 Linea Spiritus Sancti)を左から 3・4・5 文字に分けて読む。"})
    # 大王(中心の渦)
    cells = [(6, 4), (5, 5), (5, 6), (6, 7), (7, 6), (7, 5), (6, 5), (6, 6)]
    out.append({"group": "大王", "label": "大王", "name": _name(tab, cells), "cells": cells,
                "rule": "中心の十字の真ん中を、7行目の5列目から渦を巻くように8文字読む。"})
    # 六長老(中心から外へ)
    seniors = [
        ("右へ", [(6, c) for c in range(5, 12)], "6列目・7行目から右へ"),
        ("左へ", [(6, c) for c in range(6, -1, -1)], "7列目・7行目から左へ"),
        ("上へ(7列目)", [(r, 6) for r in range(6, -1, -1)], "7列目・7行目から上へ"),
        ("上へ(6列目)", [(r, 5) for r in range(6, -1, -1)], "6列目・7行目から上へ"),
        ("下へ(7列目)", [(r, 6) for r in range(6, 13)], "7列目・7行目から下へ"),
        ("下へ(6列目)", [(r, 5) for r in range(6, 13)], "6列目・7行目から下へ"),
    ]
    for lab, cells, how in seniors:
        out.append({"group": "六長老", "label": lab, "name": _name(tab, cells), "cells": cells,
                    "rule": f"中心の十字(父の線=6列目・子の線=7列目・霊の線=7行目)を中心から外へ7文字。{how}。"})
    # 小区画ごと
    for sub, (r0, c0) in SUBQUADS.items():
        se = ELEMENTS[ELEMENT_KEY.index(sub)]
        te = ELEMENTS[ELEMENT_KEY.index(tab)]
        g = f"{te}の中の{se}"
        v = [(r0 + i, c0 + 2) for i in range(6)]
        h = [(r0 + 1, c0 + j) for j in range(5)]
        out.append({"group": g, "label": "十字の神名(縦・呼び出す)", "name": _name(tab, v), "cells": v,
                    "rule": "小区画のカルヴァリ十字。3列目を上から下へ6文字=奉仕天使を呼び出す神名。"})
        out.append({"group": g, "label": "十字の神名(横・従わせる)", "name": _name(tab, h), "cells": h,
                    "rule": "小区画のカルヴァリ十字。2行目を左から右へ5文字=奉仕天使を従わせる神名。"})
        kc = [(r0, c0 + j) for j in range(5) if j != 2]
        kn = _name(tab, kc)
        comp = [kn[i:] + kn[:i] for i in range(1, 4)]
        out.append({"group": g, "label": "ケルビム天使", "name": kn, "cells": kc,
                    "rule": f"小区画の1行目(3列目を除く)を左から4文字。1文字ずつずらした仲間: {'・'.join(comp)}。"})
        for i in range(4):
            sc = [(r0 + 2 + i, c0 + j) for j in range(5) if j != 2]
            sn = _name(tab, sc)
            comp = [sn[k:] + sn[:k] for k in range(1, 4)]
            out.append({"group": g, "label": f"奉仕天使 {i + 1}", "name": sn, "cells": sc,
                        "rule": f"小区画の{3 + i}行目(3列目を除く)を左から4文字。仲間: {'・'.join(comp)}。"})
    return out


def union_names() -> list[dict]:
    out = []
    for i, n in enumerate(UNION):
        out.append({"group": "結合のタブレット", "label": f"{ELEMENTS[i]}を治める", "name": n,
                    "cells": [("union", i, j) for j in range(5)],
                    "rule": f"結合のタブレットの{i + 1}行目を左から。{ELEMENTS[i]}のタブレットを治める霊の名。"})
    for j, lab in enumerate(["霊", "空気", "水", "地", "火"]):
        n = "".join(UNION[i][j] for i in range(4))
        out.append({"group": "結合のタブレット", "label": f"{lab}の列", "name": n,
                    "cells": [("union", i, j) for i in range(4)],
                    "rule": f"結合のタブレットの{j + 1}列目を上から。{lab}に当てられる。"})
    return out


# 文書の例(答え合わせ用)
_EXPECT = {
    "air": {"三つの聖名": ["ORO", "IBAH", "AOZPI"], "大王": ["BATAIVAH"],
            "六長老": ["AHAOZPI", "HABIORO", "HTMORDA", "AAOZAIF", "HIPOTGA", "AVTOTAR"]},
    "water": {"三つの聖名": ["MPH", "ARSL", "GAIOL"], "大王": ["RAAGIOSL"]},
    "earth": {"三つの聖名": ["MOR", "DIAL", "HCTGA"], "大王": ["ICZHIHAL"]},
    "fire": {"三つの聖名": ["OIP", "TEAA", "PDOCE"], "大王": ["EDLPRNAA"]},
}
_EXPECT_SUB = {  # (タブレット, グループ, ラベル) → 名前
    ("air", "空気の中の空気", "十字の神名(縦・呼び出す)"): "IDOIGO",
    ("air", "空気の中の空気", "十字の神名(横・従わせる)"): "ARDZA",
    ("air", "空気の中の空気", "ケルビム天使"): "RZLA",
    ("air", "空気の中の火", "ケルビム天使"): "XGSD",
    ("air", "空気の中の空気", "奉仕天使 1"): "CZNS",
    ("air", "空気の中の空気", "奉仕天使 2"): "TOTT",
    ("air", "空気の中の空気", "奉仕天使 3"): "SIAS",
    ("air", "空気の中の空気", "奉仕天使 4"): "FMND",
    ("air", "空気の中の地", "十字の神名(縦・呼び出す)"): "AIAOAI",   # 文書は逆読み IAOAIA
    ("air", "空気の中の地", "十字の神名(横・従わせる)"): "OIIIT",     # 文書は逆読み TIIIO
}


def self_check() -> list[str]:
    """文書の例と照合。食い違いを文字列で返す(空なら全部一致)"""
    bad = []
    for tab, groups in _EXPECT.items():
        d = derive(tab)
        for g, names in groups.items():
            got = [e["name"] for e in d if e["group"] == g]
            if got != names:
                bad.append(f"{tab} {g}: {got} != {names}")
    for (tab, g, lab), name in _EXPECT_SUB.items():
        got = next((e["name"] for e in derive(tab) if e["group"] == g and e["label"] == lab), None)
        if got != name:
            bad.append(f"{tab} {g} {lab}: {got} != {name}")
    for tab, t in TABLETS.items():
        if len(t) != 13 or any(len(r) != 12 for r in t):
            bad.append(f"{tab}: 13x12 ではない")
    if len(BLACK_CROSS_ROW) != 25:
        bad.append("黒十字の横の帯が25マスではない")
    # 3つ目の資料(Benjamin Rowe "The Temple of Fire")の地の中の火: VOLXDO / SIODA
    e = {x["label"]: x["name"] for x in derive("fire") if x["group"] == "火の中の地"}
    uv = lambda x: (x or "").replace("U", "V")  # 当時の綴りでは U と V は同じ文字
    if uv(e.get("十字の神名(縦・呼び出す)")) != "VOLXDO" or uv(e.get("十字の神名(横・従わせる)")) != "SIODA":
        bad.append(f"火の中の地の十字: {e}")
    return bad + _check_aethyrs()



# ───────── 30のアエティールと91人の統治者 ─────────
# 出典: "The Formal Names of the Thirty Airs and their Ninety One Governors"(keepsilence.org の第19の呼びかけ資料)。
# この資料はクロウリー『Liber Chanokh』の綴り。Benjamin Rowe の異同表(gov.dif: Recensa/Turner/James/Chanokh を比較)で
# Chanokh だけが外れている名前は多数派に直し、資料が割れている名前は異読として残す。
AETHYRS = [  # (番号, 名前, 統治者) 外側の30(TEX)から内側の1(LIL)へ進む
    (1, "LIL", ["OCCODON", "PASCOMB", "VALGARS"]),
    (2, "ARN", ["DOAGNIS", "PACASNA", "DIALIVA"]),
    (3, "ZOM", ["SAMAPHA", "VIROCHI", "ANDISPI"]),
    (4, "PAZ", ["THOTANP", "AXZIARG", "POTHNIR"]),
    (5, "LIT", ["LAZDIXI", "NOCAMAL", "TIARPAX"]),
    (6, "MAZ", ["SAXTOMP", "VAVAAMP", "ZIRZIRD"]),
    (7, "DEO", ["OPMACAS", "GENADOL", "ASPIAON"]),
    (8, "ZID", ["ZAMFRES", "TODNAON", "PRISTAC"]),
    (9, "ZIP", ["ODDIORG", "CRALPIR", "DOANZIN"]),
    (10, "ZAX", ["LEXARPH", "COMANAN", "TABITOM"]),
    (11, "ICH", ["MOLPAND", "VSNARDA", "PONODOL"]),
    (12, "LOE", ["TAPAMAL", "GEDOONS", "AMBRIOL"]),
    (13, "ZIM", ["GECAOND", "LAPARIN", "DOCEPAX"]),
    (14, "VTA", ["TEDOOND", "VIVIPOS", "OOANAMB"]),
    (15, "OXO", ["TAHANDO", "NOCIABI", "TASTOXO"]),
    (16, "LEA", ["COCARPT", "LANACON", "SOCHIAL"]),
    (17, "TAN", ["SIGMORF", "AYDROPT", "TOCARZI"]),
    (18, "ZEN", ["NABAOMI", "ZAFASAI", "YALPAMB"]),
    (19, "POP", ["TORZOXI", "ABAIOND", "OMAGRAP"]),
    (20, "CHR", ["ZILDRON", "PARZIBA", "TOTOCAN"]),
    (21, "ASP", ["CHIRSPA", "TOANTOM", "VIXPALG"]),
    (22, "LIN", ["OZIDAIA", "PARAOAN", "CALZIRG"]),
    (23, "TOR", ["RONOAMB", "ONIZIMP", "ZAXANIN"]),
    (24, "NIA", ["ORCANIR", "CHIALPS", "SOAGEEL"]),
    (25, "VTI", ["MIRZIND", "OBUAORS", "RANGLAM"]),
    (26, "DES", ["POPHAND", "NIGRANA", "BAZCHIM"]),
    (27, "ZAA", ["SAZIAMI", "MATHVLA", "ORPANIB"]),
    (28, "BAG", ["LABNIXP", "FOCISNI", "OXLOPAR"]),
    (29, "RII", ["VASTRIM", "ODRAXTI", "GOMZIAM"]),
    (30, "TEX", ["TAAOGLA", "GEMNIMB", "ADVORPT", "DOZINAL"]),
]
# 異読(Rowe の表で資料が割れているもの・直したもの)。表示用
GOV_VARIANTS = {
    "THOTANP": "THOTANF(Chanokh)", "OPMACAS": "OBMACAS(Chanokh)", "VSNARDA": "VANARDA(Chanokh)",
    "AMBRIOL": "AMBRIAL(Chanokh)", "ORCANIR": "ORCAMIR(Chanokh)", "TAAOGLA": "TAONGLA(Chanokh)・TAOAGLA",
    "TAHANDO": "TAHAMDO(Recensa/James)", "LANACON": "LAUACON(Recensa/James)", "ABAIOND": "ABRIOND(Recensa/James)",
    "CHIRSPA": "CHIRZPA(Recensa/James)", "RONOAMB": "RONOOMB(Recensa/James)", "FOCISNI": "POCISNI(Recensa/James)",
    "DOZINAL": "DAZINAL(Turner)・DOXINAL(James)", "AYDROPT": "AVDROPT(James)",
}

# 第19の呼びかけ(30のアエティールの呼びかけ)。"___" にアエティールの名を入れて唱える
CALL19 = ("MADRIIAX DSPRAF ___ CHIS MICAOLZ SAANIR CAOSGO OD FISIS BALZIZRAS IAIDA NONCA GOHVLIM MICMA ADOIAN MAD "
          "IAOD BLIORB SOBA OOAONA CHIS LVCIFTIAS PIRIPSOL DS ABRAASSA NONCF NETAAIB CAOSGI OD TILB ADPHAHT DAMPLOZ "
          "TOOAT NONCF GMICALZOMA LRASD TOFGLO MARB YARRY IDOIGO OD TORZVLP IAODAF GOHOL CAOSGA TABAORD SAANIR OD "
          "CHRISTEOS YRPOIL TIOBL BVSDIRTILB NOALN PAID ORSBA OD DODRMNI ZYLNA ELZAPTILB PARMGI PIRIPSAX OD TA QVRLST "
          "BOOAPIS LNIBM OVCHO SYMP OD CHRISTEOS AGTOLTORN MIRC Q TIOBL LEL TON PAOMBD DILZMO ASPIAN OD CHRISTEOS "
          "AGLTOLTORN PARACH ASYMP CORDZIZ DODPAL OD FIFALZ LSMNAD OD FARGT BAMS OMAOAS CONISBRA OD AVAVOX TONVG "
          "ORSCATBL NOASMI TABGES LEVITHMONG VNCHI OMPTILB ORS BAGLE MOOOAH OLCORDZIZ LCAPIMAO IXOMAXIP OD CACOCASB "
          "GOSAA BAGLEN PII TIANTA ABABALOND OD FAORGT TELOCVOVIM MADRIIAX TORZV OADRIAX OROCHA ABOAPRI TABAORI PRIAZ "
          "ARTABAS ADRPAN CORSTA DOBIX YOLCAM PRIAZI ARCOAZIOR OD QVASB QTING RIPIR PAAOXT SAGACOR VML OD PRDZAR CACRG "
          "AOIVEAE CORMPT TORZV ZACAR OD ZAMRAN ASPT SIBSI BVTMONA DS SVRZAS TIA BALTAN ODO CICLE QAA OD OZAZMA PLAPLI "
          "IADNAMAD")
CALL19_EN_HEAD = "O you heavens which dwell in the ___ air, are mighty in the parts of the earth, and execute the judgement of the highest."


def aethyr(n: int):
    return next(a for a in AETHYRS if a[0] == n)


def call19_for(name: str) -> str:
    return CALL19.replace("___", name)


def _check_aethyrs() -> list[str]:
    bad = []
    if [a[0] for a in AETHYRS] != list(range(1, 31)):
        bad.append("アエティールの番号が1〜30でない")
    if sum(len(a[2]) for a in AETHYRS) != 91:
        bad.append("統治者が91人でない")
    return bad


if __name__ == "__main__":
    b = self_check()
    print("OK: 文書の例と全部一致" if not b else "\n".join(b))


# ───────── マスの四角錐(Liber Chanokh 1912 = The Equinox I:7 の規則と Plate IV) ─────────
# 中心の大十字36マス = 黄道36デカン。父の線=活動宮・子の線=柔軟宮・霊の線=不動宮。
# 父/子の線: タブレットの元素のサインが一番上、下から上へテトラグラマトンの順(火→水→空気→地)。
# 霊の線: 元素のサインが左端、右から左へ同じ順。デカンの向きは逆=父/子は上から下へ・霊の線は左から右へ第1→第3。
# 四角錐の面: 上=霊・下=タブレットの元素・左=サイン・右=惑星(デカンの支配星)。
# 小区画の十字10マス = セフィロト。Plate IV の番号: 縦(上から) 1,6,7,8,9,10 / 横(左から) 5,3,6,2,4。
# 面: 上=霊・下=セフィラ・左=タブレットの元素・右=小区画の元素。
# ケルビムのマス: 上=タブレットの元素・下=小区画の元素。左右は「やや複雑な規則」で原典が省略 → 不明として扱う。
# 奉仕天使のマス: 上下=上に立つケルビム(規則は原典の例のみ)・左=タブレット・右=小区画の元素。
TETRA = ["火", "水", "空気", "地"]
ELEM_OF_KEY = dict(zip(ELEMENT_KEY, ELEMENTS))
CARDINAL = {"火": 0, "水": 3, "空気": 6, "地": 9}
FIXED = {"火": 4, "水": 7, "空気": 10, "地": 1}
MUTABLE = {"火": 8, "水": 11, "空気": 2, "地": 5}
SEPHIROT = ["ケテル", "コクマー", "ビナー", "ケセド", "ゲブラー", "ティファレト", "ネツァク", "ホド", "イェソド", "マルクト"]
CALVARY_V = [1, 6, 7, 8, 9, 10]   # 3列目・上から
CALVARY_H = [5, 3, 6, 2, 4]       # 2行目・左から(3列目は6=ティファレト)


def _tetra_after(el: str) -> list[str]:
    """el の次から始めて el で終わる順(下→上、または右→左に並べる順)"""
    i = TETRA.index(el)
    return [TETRA[(i + 1 + k) % 4] for k in range(4)]


def cross_decan(tab: str, r: int, c: int):
    """中心の大十字のマスなら (サイン番号, デカン0-2)。それ以外は None"""
    el = ELEM_OF_KEY[tab]
    seq = _tetra_after(el)
    if r == 6:   # 霊の線: 右端のブロックが seq[0]、左端が el
        block = 3 - c // 3
        return FIXED[seq[block]], c % 3
    if c in (5, 6):
        signs = CARDINAL if c == 5 else MUTABLE
        rows_up = [12, 11, 10, 9, 8, 7, 5, 4, 3, 2, 1, 0]   # 下から上へ(霊の線の行を除く)
        k = rows_up.index(r)
        block = k // 3
        top_rows = sorted(rows_up[block * 3:block * 3 + 3])  # ブロックの中は上から第1→第3デカン
        return signs[seq[block]], top_rows.index(r)
    return None


def sub_of(r: int, c: int):
    if r == 6 or c in (5, 6):
        return None
    return ("air" if c < 5 else "water") if r < 6 else ("earth" if c < 5 else "fire")


def calvary_sephira(r: int, c: int):
    sub = sub_of(r, c)
    if not sub:
        return None
    r0, c0 = SUBQUADS[sub]
    sr, sc = r - r0, c - c0
    if sc == 2:
        return CALVARY_V[sr]
    if sr == 1:
        return CALVARY_H[sc]
    return None


def pyramid(tab: str, r: int, c: int, sign_glyph=None, planet_of=None) -> dict:
    """四角錐の4面。sign_glyph(サイン番号)と planet_of(サイン, デカン) は表示用に外から渡す"""
    el = ELEM_OF_KEY[tab]
    d = cross_decan(tab, r, c)
    if d:
        s, k = d
        return {"kind": "大十字(デカン)", "top": "霊", "bottom": el,
                "left": sign_glyph(s) if sign_glyph else str(s), "right": planet_of(s, k) if planet_of else str(k)}
    sub = sub_of(r, c)
    se = ELEM_OF_KEY[sub]
    n = calvary_sephira(r, c)
    if n:
        return {"kind": "カルヴァリ十字(セフィロト)", "top": "霊", "bottom": f"{n} {SEPHIROT[n - 1]}", "left": el, "right": se}
    r0, _ = SUBQUADS[sub]
    if r == r0:
        return {"kind": "ケルビム", "top": el, "bottom": se, "left": "?", "right": "?"}
    return {"kind": "奉仕天使", "top": "ケルビム", "bottom": "ケルビム", "left": el, "right": se}


def holders(tab: str, r: int, c: int) -> list[dict]:
    """このマスを含む名前(取り出しの一覧から)"""
    return [e for e in derive(tab) if (r, c) in e["cells"]]


def invocation_chain(tab: str, r: int, c: int) -> list[tuple[str, str]]:
    """マスに入るときに唱える名の順(上の階層から)。[(役割, 名前)]"""
    d = {(e["group"], e["label"]): e["name"] for e in derive(tab)}
    chain = [("結合のタブレットの霊名", UNION[ELEMENT_KEY.index(tab)]),
             ("三つの聖名", " ".join(e["name"] for e in derive(tab) if e["group"] == "三つの聖名")),
             ("大王", d[("大王", "大王")])]
    sub = sub_of(r, c)
    for e in holders(tab, r, c):
        if e["group"] == "六長老":
            chain.append(("長老", e["name"]))
    if sub:
        g = f"{ELEM_OF_KEY[tab]}の中の{ELEM_OF_KEY[sub]}"
        chain.append(("十字の神名(呼び出す)", d[(g, "十字の神名(縦・呼び出す)")]))
        chain.append(("十字の神名(従わせる)", d[(g, "十字の神名(横・従わせる)")]))
        chain.append(("ケルビム", d[(g, "ケルビム天使")]))
        for e in holders(tab, r, c):
            if e["label"].startswith("奉仕天使"):
                chain.append(("奉仕天使", e["name"]))
    return chain
