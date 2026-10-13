"""Read a floor-plan picture (image or PDF page) as a grey-scale array (IMP-04)."""
from __future__ import annotations

from pathlib import Path
from typing import Tuple

import numpy as np

IMAGE_EXT = {".bmp", ".gif", ".jpg", ".jpeg", ".png", ".tga", ".tif", ".tiff"}


def kind_of(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        return "pdf"
    if ext in IMAGE_EXT:
        return "image"
    raise ValueError(f"unsupported plan file {ext!r}; use a PDF or one of {', '.join(sorted(IMAGE_EXT))}")


def read_gray(path: str, page: int = 0, dpi: int = 100) -> np.ndarray:
    """Grey-scale pixels (0 black .. 255 white); transparent areas count as white."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"plan file not found: {p}")
    if kind_of(path) == "pdf":
        try:
            import fitz
        except ImportError:
            raise ValueError("PDF plans need the 'pymupdf' package (pip install pymupdf)") from None
        with fitz.open(str(p)) as doc:
            if not 0 <= page < len(doc):
                raise ValueError(f"{p.name} has {len(doc)} page(s); page {page} does not exist")
            pix = doc[page].get_pixmap(dpi=dpi, colorspace=fitz.csGRAY, alpha=False)
            return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width).astype(float)
    from PIL import Image
    with Image.open(p) as im:
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
            im = Image.alpha_composite(bg, im)
        return np.asarray(im.convert("L"), dtype=float)


def size_px(path: str, page: int = 0) -> Tuple[int, int]:
    """``(width, height)`` in pixels (a PDF page at 100 dpi)."""
    g = read_gray(path, page)
    return g.shape[1], g.shape[0]
