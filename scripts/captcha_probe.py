"""Quick CLI to test ddddocr against a captured captcha sample.

Usage:
    # 1. Plain char/digits OCR
    python captcha_probe.py ocr <image_path>

    # 2. Click-word captcha (file = raw image; --words = comma-separated targets)
    python captcha_probe.py click <image_path> --words 史,何,光

    # 3. Slider captcha (--bg = background, --tile = puzzle piece)
    python captcha_probe.py slide --bg bg.png --tile tile.png

    # 4. Probe via a URL (will GET it once and treat as image)
    python captcha_probe.py ocr --url https://example.com/captcha.png

Used during phase 1 to verify which captcha family the target site uses, before
wiring solver into <pkg>/captcha.py.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _load_bytes(path_or_url: str) -> bytes:
    if path_or_url.startswith(("http://", "https://")):
        import requests
        r = requests.get(path_or_url, timeout=15)
        r.raise_for_status()
        return r.content
    return Path(path_or_url).read_bytes()


def cmd_ocr(args: argparse.Namespace) -> None:
    import ddddocr
    src = args.url or args.image
    if not src:
        sys.exit("ocr requires <image> or --url")
    img = _load_bytes(src)
    ocr = ddddocr.DdddOcr(show_ad=False)
    text = ocr.classification(img)
    print(json.dumps({"mode": "ocr", "result": text}, ensure_ascii=False, indent=2))


def cmd_click(args: argparse.Namespace) -> None:
    import ddddocr
    from io import BytesIO
    from PIL import Image
    img_bytes = _load_bytes(args.url or args.image)
    det = ddddocr.DdddOcr(det=True, show_ad=False)
    ocr = ddddocr.DdddOcr(show_ad=False)
    boxes = det.detection(img_bytes)
    img = Image.open(BytesIO(img_bytes))
    img_w, img_h = img.size
    detected = []
    for x1, y1, x2, y2 in boxes:
        pad = 8
        crop = img.crop((max(0, x1 - pad), max(0, y1 - pad),
                         min(img_w, x2 + pad), min(img_h, y2 + pad)))
        buf = BytesIO(); crop.save(buf, format="PNG")
        ch = ocr.classification(buf.getvalue())
        detected.append({"ch": ch, "cx": (x1 + x2) / 2, "cy": (y1 + y2) / 2,
                         "box": [x1, y1, x2, y2]})
    targets = [w.strip() for w in (args.words or "").split(",") if w.strip()]
    matched = []
    used: set[int] = set()
    for t in targets:
        best_i, best_score = None, -1
        for i, d in enumerate(detected):
            if i in used:
                continue
            score = 10 if d["ch"] == t else (5 if t in d["ch"] or d["ch"] in t else 0)
            if score > best_score:
                best_score, best_i = score, i
        if best_i is not None:
            used.add(best_i)
            matched.append({"target": t, "matched": detected[best_i]})
    print(json.dumps({
        "mode": "click",
        "image_size": [img_w, img_h],
        "detected_boxes": detected,
        "word_list": targets,
        "matched": matched,
        "note": "Centers are in original image coords. Scale to STD before submitting.",
    }, ensure_ascii=False, indent=2))


def cmd_slide(args: argparse.Namespace) -> None:
    import ddddocr
    if not (args.bg and args.tile):
        sys.exit("slide requires --bg and --tile")
    bg = _load_bytes(args.bg)
    tile = _load_bytes(args.tile)
    det = ddddocr.DdddOcr(det=False, ocr=False, show_ad=False)
    res = det.slide_match(tile, bg, simple_target=True)
    gap_x = res["target"][0] if isinstance(res, dict) and "target" in res else None
    print(json.dumps({
        "mode": "slide",
        "raw": res,
        "gap_x": gap_x,
        "note": "gap_x is the absolute x-offset on the background. Synthesize a humanized track to that x.",
    }, ensure_ascii=False, indent=2))


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    p_ocr = sub.add_parser("ocr", help="plain char/digit OCR")
    p_ocr.add_argument("image", nargs="?")
    p_ocr.add_argument("--url")
    p_ocr.set_defaults(func=cmd_ocr)

    p_click = sub.add_parser("click", help="click-word captcha")
    p_click.add_argument("image", nargs="?")
    p_click.add_argument("--url")
    p_click.add_argument("--words", help="comma-separated target words, e.g. 史,何,光")
    p_click.set_defaults(func=cmd_click)

    p_slide = sub.add_parser("slide", help="slider captcha")
    p_slide.add_argument("--bg", required=True)
    p_slide.add_argument("--tile", required=True)
    p_slide.set_defaults(func=cmd_slide)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
