"""Image optimization helpers — downscale and recompress uploads with Pillow.

Keeps the stored originals small (fast first paint, cheap storage); the
opt_img template tag then serves further-scaled versions from Cloudinary.
"""
import io
import os

from PIL import Image, ImageOps

MAX_DIMENSION = 1920
JPEG_QUALITY = 82
WEBP_QUALITY = 82


def optimize_image(data: bytes, name: str):
    """Return (optimized_bytes, name) or None if the data should be kept as-is.

    Downscales the long edge to MAX_DIMENSION, strips EXIF orientation and
    re-encodes (JPEG q82 / optimized PNG / WebP q82). PNG is kept as PNG so
    transparency and the site's CSS rules for .png assets keep working.
    Animated formats (GIF/WebP) return None so frames are never flattened.
    """
    try:
        image = Image.open(io.BytesIO(data))
        if getattr(image, 'is_animated', False):
            return None
        image = ImageOps.exif_transpose(image)
        image.load()
    except Exception:
        return None

    fmt = (image.format or '').upper()
    ext = os.path.splitext(name)[1].lower()
    is_png = fmt == 'PNG' or ext == '.png'
    is_webp = not is_png and (fmt == 'WEBP' or ext == '.webp')

    width, height = image.size
    longest = max(width, height)
    if longest > MAX_DIMENSION:
        scale = MAX_DIMENSION / longest
        image = image.resize((round(width * scale), round(height * scale)), Image.LANCZOS)

    out = io.BytesIO()
    if is_png:
        if image.mode not in ('RGBA', 'LA', 'P'):
            image = image.convert('RGBA')
        image.save(out, format='PNG', optimize=True)
    elif is_webp:
        if image.mode == 'P':
            image = image.convert('RGBA')
        image.save(out, format='WEBP', quality=WEBP_QUALITY, method=6)
    else:
        if image.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', image.size, (255, 255, 255))
            background.paste(image, mask=image.getchannel('A') if image.mode == 'RGBA' else None)
            image = background
        else:
            image = image.convert('RGB')
        image.save(out, format='JPEG', quality=JPEG_QUALITY, optimize=True, progressive=True)

    return out.getvalue(), name
