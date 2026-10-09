"""Generate the repository banner (assets/banner.png).

Night-sky gradient with a starfield and layered ridges, matching the palette of
the translation's own wallpaper set. Text is drawn with a system font; if none
of the candidates is present the banner is still produced without text.

Run: python tools/make-banner.py
"""
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1280, 320
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'assets', 'banner.png')
rng = np.random.default_rng(20261008)

FONT_CANDIDATES = [
    (r'C:\Windows\Fonts\seguisb.ttf', 'semibold'),
    (r'C:\Windows\Fonts\segoeui.ttf', 'regular'),
    (r'C:\Windows\Fonts\arialbd.ttf', 'semibold'),
    (r'C:\Windows\Fonts\arial.ttf', 'regular'),
]


def load_font(size, want):
    for path, kind in FONT_CANDIDATES:
        if kind == want and os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    for path, _ in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def gradient(stops):
    ys = np.linspace(0.0, 1.0, H)
    pos = np.array([s[0] for s in stops])
    cols = np.array([s[1] for s in stops], dtype=float)
    out = np.empty((H, 3))
    for c in range(3):
        out[:, c] = np.interp(ys, pos, cols[:, c])
    return np.repeat(out[:, None, :], W, axis=1)


def value_noise_1d(n, octaves, seed_scale=1.0):
    total = np.zeros(n)
    amp, freq, norm = 1.0, 4 * seed_scale, 0.0
    for _ in range(octaves):
        pts = max(2, int(round(freq)))
        anchors = rng.random(pts + 2)
        xs = np.linspace(0.0, pts, n, endpoint=False)
        i0 = np.floor(xs).astype(int)
        frac = xs - i0
        smooth = frac * frac * (3 - 2 * frac)
        total += amp * (anchors[i0] * (1 - smooth) + anchors[i0 + 1] * smooth)
        norm += amp
        amp *= 0.5
        freq *= 2.05
    total /= norm
    total -= total.min()
    if total.max() > 0:
        total /= total.max()
    return total


def fill_ridge(img, height_px, color, haze, haze_color):
    mask = np.zeros((H, W), dtype=bool)
    yy = np.arange(H)[:, None]
    mask[yy >= height_px[None, :]] = True
    col = np.array(color, dtype=float) * (1 - haze) + np.array(haze_color, dtype=float) * haze
    img[mask] = col
    return img


# --- background -----------------------------------------------------------
img = gradient([
    (0.00, (5, 8, 18)), (0.34, (11, 22, 44)),
    (0.62, (26, 46, 78)), (0.80, (14, 22, 40)), (1.00, (5, 8, 16)),
])

# starfield
layer = Image.new('L', (W, H), 0)
d = ImageDraw.Draw(layer)
for _ in range(420):
    x = int(rng.integers(0, W))
    y = int(rng.random() ** 1.5 * H * 0.72)
    b = int(50 + rng.random() ** 3 * 190)
    r = rng.random() * 1.4 + 0.3
    d.ellipse([x - r, y - r, x + r, y + r], fill=b)
glow = layer.filter(ImageFilter.GaussianBlur(1.8))
base = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
base = Image.composite(Image.new('RGB', (W, H), (255, 255, 255)), base,
                       glow.point(lambda v: int(v * 0.5)))
img = np.asarray(Image.composite(Image.new('RGB', (W, H), (255, 255, 255)), base, layer), dtype=float)

# moon glow on the right
yy, xx = np.mgrid[0:H, 0:W]
dist = np.sqrt((xx - 1080) ** 2 + (yy - 70) ** 2)
img += (np.clip(1 - dist / 260, 0, 1) ** 2.6)[:, :, None] * np.array([150, 172, 208]) * 0.5
img += (np.clip(1 - dist / 34, 0, 1) ** 2.0)[:, :, None] * np.array([255, 255, 255]) * 0.85

# layered ridges — kept low so the text block sits on clean sky
horizon = (74, 96, 126)
for base_p, relief, oct_, haze, col in [
    (0.80, 0.075, 3, 0.62, (40, 56, 82)),
    (0.86, 0.065, 4, 0.40, (26, 38, 60)),
    (0.92, 0.055, 5, 0.18, (14, 21, 36)),
    (0.99, 0.045, 6, 0.05, (7, 11, 20)),
]:
    h = (base_p + value_noise_1d(W, oct_, seed_scale=1.1) * relief) * H
    fill_ridge(img, h, col, haze, horizon)

# vignette
r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2) / np.sqrt(2)
img *= (1 - 0.38 * (r ** 2.2))[:, :, None]

# --- text -----------------------------------------------------------------
out = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), 'RGB')
draw = ImageDraw.Draw(out)

title_font = load_font(56, 'semibold')
sub_font = load_font(23, 'regular')
tag_font = load_font(17, 'regular')

title = 'dsh-locale-ru'
sub = 'Русский язык для DeepSeek Harness'
tag = '57 пространств имён · 2603 строки · MIT'

x, y = 74, 96
# soft shadow keeps the text legible over the stars
draw.text((x + 2, y + 2), title, font=title_font, fill=(0, 0, 0))
draw.text((x, y), title, font=title_font, fill=(240, 246, 255))

draw.text((x + 1, y + 78), sub, font=sub_font, fill=(6, 10, 20))
draw.text((x, y + 77), sub, font=sub_font, fill=(176, 199, 232))

draw.line([(x, y + 122), (x + 74, y + 122)], fill=(72, 122, 214), width=3)
draw.text((x, y + 140), tag, font=tag_font, fill=(122, 148, 182))

os.makedirs(os.path.dirname(OUT), exist_ok=True)
out.save(OUT, 'PNG', optimize=True)
print(f'wrote {OUT} ({out.size[0]}x{out.size[1]}, {os.path.getsize(OUT)} bytes)')
