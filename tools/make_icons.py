"""アプリアイコン（PNG）を作る。python tools/make_icons.py
緑の地に、朱色の輪のスタンプと「道」の字。maskable 版は中央の安全域（約80%）に収める。
文字は Windows 同梱の BIZ UD明朝（SIL Open Font License）で描く。メタデータは付けない。"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONT = "C:/Windows/Fonts/BIZ-UDMinchoM.ttc"
GREEN, PAPER, VERMILION = (47, 111, 79), (246, 241, 228), (181, 68, 44)


def icon(size, maskable=False):
    k = 4                       # 大きく描いて縮め、輪郭を滑らかにする
    S = size * k
    im = Image.new("RGB", (S, S), GREEN)
    d = ImageDraw.Draw(im)
    c = S / 2
    r = S * (0.30 if maskable else 0.375)
    d.ellipse([c - r, c - r, c + r, c + r], fill=PAPER)
    ring = S * (0.028 if maskable else 0.035)
    r2 = r - S * 0.045
    d.ellipse([c - r2, c - r2, c + r2, c + r2], outline=VERMILION, width=int(ring))
    font = ImageFont.truetype(FONT, int(S * (0.29 if maskable else 0.37)))
    d.text((c, c + S * 0.01), "道", font=font, fill=VERMILION, anchor="mm")
    return im.resize((size, size), Image.LANCZOS)


out = ROOT / "icons"
out.mkdir(exist_ok=True)
for name, size, mask in [("icon-192.png", 192, False), ("icon-512.png", 512, False),
                         ("icon-maskable-512.png", 512, True), ("apple-touch-icon.png", 180, False)]:
    icon(size, mask).save(out / name, optimize=True)
    print(name, (out / name).stat().st_size)
