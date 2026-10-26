"""アプリアイコン: 裏面と「星」を少しずらして重ねる(等倍のまま128x128へ置く=ドットを崩さない)。"""
from pathlib import Path
from PIL import Image
here = Path(__file__).resolve().parent
cards = here.parent / "out" / "cards"
im = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
im.alpha_composite(Image.open(cards / "back.png"), (10, 4))
im.alpha_composite(Image.open(cards / "m17.png"), (54, 12))
im.save(here / "icon_tarot.png")
