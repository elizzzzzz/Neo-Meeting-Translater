from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "icons"
OUT.mkdir(parents=True, exist_ok=True)
SIZE = 1024


def font(size: int):
    return ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", size)


def rounded_gradient(colors: tuple[tuple[int, int, int], tuple[int, int, int]], radius: int = 210) -> Image.Image:
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    pixels = image.load()
    for y in range(SIZE):
        ratio = y / (SIZE - 1)
        color = tuple(round(colors[0][i] * (1 - ratio) + colors[1][i] * ratio) for i in range(3)) + (255,)
        for x in range(SIZE):
            pixels[x, y] = color
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle((18, 18, SIZE - 18, SIZE - 18), radius=radius, fill=255)
    image.putalpha(mask)
    return image


def variant_a() -> Image.Image:
    image = rounded_gradient(((12, 22, 48), (0, 108, 170)))
    draw = ImageDraw.Draw(image)
    # Two overlapping language bubbles.
    draw.rounded_rectangle((170, 245, 850, 650), radius=115, fill=(246, 250, 255, 245))
    draw.polygon([(235, 615), (205, 770), (390, 650)], fill=(246, 250, 255, 245))
    draw.rounded_rectangle((300, 360, 790, 735), radius=100, fill=(71, 214, 190, 235))
    draw.polygon([(690, 700), (790, 835), (780, 650)], fill=(71, 214, 190, 235))
    # Conversation waveform.
    bars = [34, 72, 125, 178, 110, 56, 160, 205, 132, 75, 38]
    x = 245
    for index, height in enumerate(bars):
        color = (16, 82, 145, 255) if index < 6 else (255, 255, 255, 255)
        draw.rounded_rectangle((x, 455 - height // 2, x + 20, 455 + height // 2), radius=10, fill=color)
        x += 42
    draw.text((355, 755), "LI", font=font(58), fill=(255, 255, 255, 220))
    return image


def variant_b() -> Image.Image:
    image = rounded_gradient(((24, 16, 46), (102, 43, 150)))
    draw = ImageDraw.Draw(image)
    glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((155, 130, 870, 870), fill=(255, 95, 182, 75))
    glow = glow.filter(ImageFilter.GaussianBlur(75))
    image.alpha_composite(glow)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((270, 135, 754, 889), radius=175, outline=(255, 255, 255, 220), width=20)
    heights = [82, 150, 240, 345, 230, 125, 260, 365, 245, 145, 88]
    x = 330
    for index, height in enumerate(heights):
        color = (102, 240, 220, 255) if index < 6 else (255, 126, 190, 255)
        draw.rounded_rectangle((x, 510 - height // 2, x + 25, 510 + height // 2), radius=12, fill=color)
        x += 38
    draw.text((462, 775), "LI", font=font(54), fill=(255, 255, 255, 240))
    return image


def variant_c() -> Image.Image:
    image = Image.new("RGBA", (SIZE, SIZE), (242, 240, 234, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((26, 26, SIZE - 26, SIZE - 26), radius=210, fill=(242, 240, 234, 255), outline=(25, 30, 40, 255), width=22)
    draw.ellipse((172, 166, 852, 846), fill=(15, 42, 75, 255))
    draw.rounded_rectangle((282, 245, 742, 690), radius=92, fill=(242, 240, 234, 255))
    draw.polygon([(355, 660), (270, 775), (438, 695)], fill=(242, 240, 234, 255))
    # Translation arrows and compact wordmark.
    draw.arc((355, 325, 670, 645), 205, 345, fill=(10, 120, 215, 255), width=24)
    draw.polygon([(640, 390), (715, 420), (650, 470)], fill=(10, 120, 215, 255))
    draw.arc((355, 325, 670, 645), 25, 165, fill=(244, 124, 60, 255), width=24)
    draw.polygon([(385, 575), (310, 545), (375, 495)], fill=(244, 124, 60, 255))
    draw.text((408, 720), "LI", font=font(70), fill=(15, 42, 75, 255))
    return image


VARIANTS = {"variant-a": variant_a, "variant-b": variant_b, "variant-c": variant_c}


def write_iconset(name: str, image: Image.Image) -> None:
    base = OUT / name
    image.save(base.with_suffix(".png"))
    iconset = OUT / f"{name}.iconset"
    iconset.mkdir(exist_ok=True)
    for size in (16, 32, 128, 256, 512):
        image.resize((size, size), Image.Resampling.LANCZOS).save(iconset / f"icon_{size}x{size}.png")
        image.resize((size * 2, size * 2), Image.Resampling.LANCZOS).save(iconset / f"icon_{size}x{size}@2x.png")


for name, builder in VARIANTS.items():
    write_iconset(name, builder())

preview = Image.new("RGB", (1500, 610), (247, 247, 249))
preview_draw = ImageDraw.Draw(preview)
for index, name in enumerate(VARIANTS):
    image = Image.open(OUT / f"{name}.png").convert("RGB").resize((430, 430), Image.Resampling.LANCZOS)
    left = 35 + index * 490
    preview.paste(image, (left, 35))
    preview_draw.text((left, 495), {"variant-a": "A · Bilingual Bubbles", "variant-b": "B · Spectrum Gate", "variant-c": "C · Translation Mark"}[name], fill=(29, 29, 31), font=font(26))
preview.save(OUT / "preview.png")
