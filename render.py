import base64
from io import BytesIO
from itertools import repeat
from operator import mul
from typing import List, Literal, NewType, Optional, Tuple, Union


import pypdfium2 as pdfium
from PIL import Image, ImageDraw, ImageFont
from rich import print

from box import Box

PILImage = Image.Image
PdfPage = pdfium.PdfPage
RGBA = Tuple[int, int, int, int]
SVG = NewType("SVG", str)


def _circle_bbox(
    center: Tuple[float, float], radius: float
) -> Tuple[float, float, float, float]:
    """Generate a bounding box for a circle
    (i.e. a square at `center` with width 2 * radius).

    Use for PIL because it doesn't have a circle function (only ellipse)."""
    cx, cy = center
    return (cx - radius), (cy - radius), (cx + radius), (cy + radius)


def _scale_coords(coordinates: Tuple[float, ...], factor: float) -> Tuple[float, ...]:
    """Scale the coordinates by `factor`."""
    return tuple(map(mul, coordinates, repeat(factor)))


def _invert_coords(
    coordinates: Tuple[float, float], height: float
) -> Tuple[float, float]:
    """Invert an (x, y) coordinate pair.
    For going from bottom-left to top-left origin orientations."""
    x, y = coordinates
    return (x, height - y)


def _b64_encode_image(image: PILImage, format="png") -> str:
    buffered = BytesIO()
    image.save(buffered, format=format)
    img_str = base64.b64encode(buffered.getvalue()).decode()
    return img_str


def _alpha_to_percent(rgba: RGBA) -> Tuple[int, int, int, float]:
    return rgba[0], rgba[1], rgba[2], round(rgba[3] / 255, 3)


DEFAULT_BOX_COLOR = (255, 111, 97, 64)
DEFAULT_LABEL_BG_COLOR = (245, 223, 77, 196)
DEFAULT_LABEL_TEXT_COLOR = (102, 103, 171, 255)


def _get_system_font():
    font = None
    for font_name in ["Menlo", "Monaco", "Consolas", "Ubuntu Mono", "Courier New"]:
        try:
            ImageFont.truetype(font_name, 12)
            font = font_name
            break
        except OSError:
            continue
    if font is None:
        raise RuntimeError("No suitable system default monospace font available.")
    print(f"Using font '{font_name}' for display.")
    return font


def render_boxes_as_image(
    page: PdfPage,
    boxes: List[Box],
    scale: float = 1.0,
    font_name: Optional[str] = None,
    box_colors: Union[RGBA, List[RGBA], None] = None,
    box_labels: Union[List[str], None] = None,
    label_bg_color: Union[RGBA, None] = None,
    label_text_color: Union[RGBA, None] = None,
) -> PILImage:
    if box_colors is None:
        box_colors = list(repeat(DEFAULT_BOX_COLOR, len(boxes)))
    if isinstance(box_colors, tuple):
        box_colors = list(repeat(box_colors, len(boxes)))
    if box_labels is None:
        box_labels = [str(i) for i in range(len(boxes))]
    if label_bg_color is None:
        label_bg_color = DEFAULT_LABEL_BG_COLOR
    if label_text_color is None:
        label_text_color = DEFAULT_LABEL_TEXT_COLOR
    if font_name is None:
        font_name = _get_system_font()

    w, h = page.get_size()

    # We immediately "flip" the page so that the image origin orientation (top-left)
    # matches the PDF orentation (bottom-left). This way we don't have to transform the
    # coordiantes every time we want to use them, we just have to make sure we flip back
    # to image orientation when we're done adding things to that canvas
    image = page.render_topil(scale=scale).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    draw = ImageDraw.Draw(image, mode="RGBA")

    # We need to create a new layer and draw object for text, because we
    # don't want to 'flip' it back when it's done - otherwise the characters
    # will be upside-down
    text_layer = Image.new("RGBA", image.size, (255, 255, 255, 0))
    draw_text = ImageDraw.Draw(text_layer)

    font = ImageFont.truetype(font_name, int(6 * scale))

    for box, color in zip(boxes, box_colors):
        draw.rectangle(box.scale_coords(scale), fill=color)

    centers = [b.center for b in boxes]
    for label, c in zip(box_labels, centers):
        cx, cy = _scale_coords(c, scale)
        _, _, tw, th = draw_text.textbbox(
            (0, 0),
            label,
            font,
        )
        # We don't want the width/height scaling for the ellipse to be exactly 2,
        # because we want the boundaries to extend a bit beyond the text
        ex1, ey1, ex2, ey2 = (
            cx - tw / 1.5,
            cy - th / 1.5,
            cx + tw / 1.5,
            cy + th / 1.5,
        )
        draw.ellipse([ex1, ey1, ex2, ey2], fill=label_bg_color)
        # the original image is already "inverted" due to the flip transpose, so we need
        # to invert these coordinates for the text layer
        cxt, cyt = _invert_coords((cx, cy), h * scale)
        draw_text.text(
            (cxt, cyt),
            text=label,
            font=font,
            fill=label_text_color,
            anchor="mm",
        )
    image = image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    image = Image.alpha_composite(image.convert("RGBA"), text_layer.convert("RGBA"))
    return image


svg_page_template = """
<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
<defs>
  <style type="text/css">
    text {{
          font-family: monospace;
          font-weight: 700;
    }}
  </style>
</defs>
<image href="data:image/{img_type};base64,{img_str}" x="0.0" y="0.0" height="100%" width="100%" preserveAspectRatio="none" />
{svgrects_str}
{svgcircles_str}
{textrects_str}
</svg>
"""


def render_boxes_as_svg(
    page: PdfPage,
    boxes: List[Box],
    scale: float = 1.0,
    box_colors: Union[RGBA, List[RGBA], None] = None,
    box_labels: Union[List[str], None] = None,
    label_bg_color: Union[RGBA, None] = None,
    label_text_color: Union[RGBA, None] = None,
    img_type: Literal["jpeg", "png"] = "png",
) -> SVG:
    if box_colors is None:
        box_colors = list(repeat(DEFAULT_BOX_COLOR, len(boxes)))  # type: ignore
    if isinstance(box_colors, tuple):
        box_colors = list(repeat(box_colors, len(boxes)))
    if box_labels is None:
        box_labels = [str(i) for i in range(len(boxes))]
    if label_bg_color is None:
        label_bg_color = DEFAULT_LABEL_BG_COLOR
    label_bg_color = _alpha_to_percent(label_bg_color)  # type: ignore
    if label_text_color is None:
        label_text_color = DEFAULT_LABEL_TEXT_COLOR
    label_text_color = _alpha_to_percent(label_text_color)  # type: ignore

    w, h = page.get_size()
    image = page.render_topil(scale=scale)
    # We have to base64 encode the original image, rather than provide a relative file
    # reference (which is also supported in SVG `image` elements), beacuse whenever I
    # tried do provide a file reference, it returned the source image upside-down. Plus
    # I don't think we want to depend on locating a file on a file system if this is
    # eventually going to serve these visualisations like displaCy does
    b64_image = _b64_encode_image(image, img_type)

    svgrects = []
    for box, color in zip(boxes, box_colors):  # type: ignore
        bx, by, bw, bh = _scale_coords(box.to_xywh(), scale)
        # We need to invert, but also additionally subtract the height so that the
        # coordinate maps to the upper-left of the box
        by = (scale * h) - (by + bh)
        color = _alpha_to_percent(color)
        rect_text = (
            f'<rect x="{bx}" '
            f'y="{by}" '
            f'width="{bw}" '
            f'height="{bh}" '
            f'style="fill:rgba{color}" />'
        )
        svgrects.append(rect_text)

    centers = [b.center for b in boxes]
    svgcircles = []
    textrects = []
    for label, c in zip(box_labels, centers):
        c = _scale_coords(c, scale)
        cx, cy = _invert_coords(c, scale * h)
        r = 4 * scale

        text_circle = (
            f'<circle cx="{cx}" '
            f'cy="{cy}" '
            f'r="{r}" '
            f'style="fill:rgba{label_bg_color}" />'
        )
        svgcircles.append(text_circle)

        text = (
            f'<text font-size="{6 * scale}" '
            f'fill="rgba{label_text_color}" '
            f'x="{cx}" y="{cy}" '
            'dominant-baseline="middle" '
            'text-anchor="middle" '
            f'style="text-shadow: -1px 1px 0 rgba{label_bg_color},'
            f"1px 1px 0 rgba{label_bg_color},"
            f"1px -1px 0 rgba{label_bg_color},"
            f'-1px -1px 0 rgba{label_bg_color}" '
            'font-weight="bold">'
            f"{label}"
            "</text>"
        )
        textrects.append(text)
    svgcircles_str = "\n".join(svgcircles)
    textrects_str = "\n".join(textrects)
    svgrects_str = "\n".join(svgrects)

    image = svg_page_template.format(
        width=w * scale,
        height=h * scale,
        img_type=img_type,
        img_str=b64_image,
        svgrects_str=svgrects_str,
        svgcircles_str=svgcircles_str,
        textrects_str=textrects_str,
    ).strip()
    return SVG(image)
