"""The tray / installer icon, drawn in code so no image files need to live in the repo."""
from PIL import Image, ImageDraw


def draw(size=64, lit=True):
    s = size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((1, 1, s - 2, s - 2), radius=s // 6, fill=(18, 22, 28, 255),
                        outline=(255, 140, 60, 255), width=max(1, s // 22))
    # three power bars, like the in-game MFD
    on = (255, 140, 60, 255) if lit else (120, 120, 120, 255)
    bw, gap = s * 0.16, s * 0.1
    x0 = (s - 3 * bw - 2 * gap) / 2
    for i, h in enumerate((0.42, 0.62, 0.32)):
        x = x0 + i * (bw + gap)
        d.rectangle((x, s * 0.8 - s * h, x + bw, s * 0.8), fill=on)
    return img


if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "icon.ico"
    draw(256).save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("wrote", out)
