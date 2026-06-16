#!/usr/bin/env python3
"""Assemble a labeled contact sheet from a list of PNGs.
Usage: make_contact_sheet.py OUT.png COLS "img1.png:Caption 1" "img2.png:Caption 2" ...
"""
import sys
from PIL import Image, ImageDraw, ImageFont

def main():
    out = sys.argv[1]
    cols = int(sys.argv[2])
    items = []
    for a in sys.argv[3:]:
        path, _, cap = a.partition(":")
        items.append((path, cap))
    thumb_w = 520
    pad = 8
    cap_h = 26
    imgs = []
    for path, cap in items:
        try:
            im = Image.open(path).convert("RGB")
        except Exception as e:
            print("skip", path, e); continue
        w, h = im.size
        tw = thumb_w
        th = int(h * (tw / w))
        im = im.resize((tw, th))
        imgs.append((im, cap))
    if not imgs:
        print("no images"); return
    rows = (len(imgs) + cols - 1) // cols
    cell_w = thumb_w + pad
    cell_h = max(i.size[1] for i, _ in imgs) + cap_h + pad
    sheet = Image.new("RGB", (cols * cell_w + pad, rows * cell_h + pad), (18, 18, 22))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 15)
    except Exception:
        font = ImageFont.load_default()
    for idx, (im, cap) in enumerate(imgs):
        r = idx // cols
        c = idx % cols
        x = pad + c * cell_w
        y = pad + r * cell_h
        draw.rectangle([x, y, x + thumb_w, y + cap_h - 4], fill=(40, 44, 54))
        draw.text((x + 6, y + 4), cap, fill=(235, 235, 240), font=font)
        sheet.paste(im, (x, y + cap_h))
    sheet.save(out)
    print("wrote", out, sheet.size)

if __name__ == "__main__":
    main()
