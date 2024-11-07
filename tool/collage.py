from tool.worker import offloaded  # type: ignore
import io, asyncio
from base64 import urlsafe_b64encode
from datetime import datetime, timedelta
from typing import Optional, Union, Any, List
from functools import partial, wraps
from io import BytesIO
from math import sqrt
from pathlib import Path
import matplotlib.pyplot as plt
from PIL import Image, ImageDraw, ImageMath
import aiohttp
import dateparser
import discord
import imagehash as ih
from humanize import naturaldelta
from loguru import logger
from discord.ext import commands
from wordcloud import STOPWORDS, WordCloud
from xxhash import xxh64_hexdigest
import concurrent.futures

executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)


def _collage_paste(image: Image, x: int, y: int, background: Image):
    background.paste(
        image,
        (
            x * 256,
            y * 256,
        ),
    )


def async_executor():
    def outer(func):
        @wraps(func)
        def inner(*args, **kwargs):
            task = partial(func, *args, **kwargs)
            return asyncio.get_event_loop().run_in_executor(executor, task)

        return inner

    return outer


def _collage_open(image: BytesIO, resize: Optional[bool] = False):
    if not resize:
        image = (
            Image.open(image)
            .convert("RGBA")
        )
        return image
    image = (
        Image.open(image)
        .convert("RGBA")
        .resize(
            (
                256,
                256,
            )
        )
    )
    return image


@offloaded
def validate_image(data: bytes):
    import magic

    magic_instance = magic.Magic()
    image_formats = {
        "JPEG": [b"\xFF\xD8\xFF"],
        "PNG": [b"\x89\x50\x4E\x47\x0D\x0A\x1A\x0A"],
        "GIF": [b"\x47\x49\x46\x38\x37\x61", b"\x47\x49\x46\x38\x39\x61"],
        "WEBP": [b"\x52\x49\x46\x46\x00\x00\x00\x00\x57\x45\x42\x50"],
        "JPG": [b"\xFF\xD8\xFF"],
    }
    file_header = data[:12]
    try:
        detected_type = magic_instance.from_buffer(file_header)

        for format_name, magic_numbers in image_formats.items():
            for magic_number in magic_numbers:
                if file_header.startswith(magic_number):
                    return True
        return False
    except Exception as e:
        raise e


async def _validate_image_(data: bytes):
    try:
        _ = await validate_image(data)
        return _
    except Exception as e:
        logger.info(f"validating image raised: {e}")
        return False


@offloaded
def _make_bar(percentage_1, color_1, percentage_2, color_2, bar_width: int = 10, height: int = 1, corner_radius: int = 0.2) -> bytes:
    """
    Generate a bar with two colors representing two different percentages,
    with a rounded left corner on the first segment and a rounded right corner
    on the second segment.

    :param percentage_1: The percentage for the first color (0-100)
    :param color_1: The color for the first segment
    :param percentage_2: The percentage for the second color (0-100)
    :param color_2: The color for the second segment
    :param bar_width: The width of the bar (default is 10 units)
    :param height: The height of the bar (default is 1 unit)
    :param corner_radius: The radius of the rounded corners (default is 0.2 units)
    """
    import matplotlib.pyplot as plt
    from matplotlib.patches import PathPatch, Path
    from matplotlib.path import Path
    from PIL import Image
    import matplotlib
    from io import BytesIO
    matplotlib.use("agg")
    plt.switch_backend("agg")
    if not (0 <= percentage_1 <= 100 and 0 <= percentage_2 <= 100):
        raise ValueError("Percentages must be between 0 and 100.")

    if percentage_1 + percentage_2 > 100:
        raise ValueError("The sum of percentages cannot exceed 100.")

    fig, ax = plt.subplots(figsize=(10, 2))
    
    # Calculate the width of each segment
    width_1 = (percentage_1 / 100) * bar_width
    width_2 = (percentage_2 / 100) * bar_width

    # Define the rounded rectangle path for the first segment (left side rounded)
    if width_1 > 0:
        path_data = [
            (Path.MOVETO, [corner_radius, 0]),
            (Path.LINETO, [width_1, 0]),
            (Path.LINETO, [width_1, height]),
            (Path.LINETO, [corner_radius, height]),
            (Path.CURVE3, [0, height]),
            (Path.CURVE3, [0, height - corner_radius]),
            (Path.LINETO, [0, corner_radius]),
            (Path.CURVE3, [0, 0]),
            (Path.CURVE3, [corner_radius, 0])
        ]
        codes, verts = zip(*path_data)
        path = Path(verts, codes)
        patch = PathPatch(path, facecolor=color_1, edgecolor='none')
        ax.add_patch(patch)

    # Define the rounded rectangle path for the second segment (right side rounded)
    if width_2 > 0:
        path_data = [
            (Path.MOVETO, [width_1, 0]),
            (Path.LINETO, [width_1 + width_2 - corner_radius, 0]),
            (Path.CURVE3, [width_1 + width_2, 0]),
            (Path.CURVE3, [width_1 + width_2, corner_radius]),
            (Path.LINETO, [width_1 + width_2, height - corner_radius]),
            (Path.CURVE3, [width_1 + width_2, height]),
            (Path.CURVE3, [width_1 + width_2 - corner_radius, height]),
            (Path.LINETO, [width_1, height]),
            (Path.LINETO, [width_1, 0])
        ]
        codes, verts = zip(*path_data)
        path = Path(verts, codes)
        patch = PathPatch(path, facecolor=color_2, edgecolor='none')
        ax.add_patch(patch)

    # Set limits and remove axes
    ax.set_xlim(0, bar_width)
    ax.set_ylim(0, height)
    ax.axis('off')
    buffer = BytesIO()
    plt.savefig(buffer, transparent=True)
    buffer.seek(0)
    image = Image.open(buffer).convert("RGBA")

    # Get the bounding box of the non-transparent areas
    bbox = image.getbbox()
    output_path = BytesIO()

    if bbox:
        # Crop the image to the bounding box
        image_cropped = image.crop(bbox)
        image_cropped.save(output_path, format="png")
    return output_path.getvalue()

    


@offloaded
def _make_chart(name: str, data: list, avatar: bytes) -> bytes:
    import matplotlib
    import matplotlib.pyplot as plt
    from PIL import Image, ImageDraw, ImageMath
    from humanize import naturaldelta
    from datetime import datetime, timedelta
    from io import BytesIO

    matplotlib.use("agg")
    plt.switch_backend("agg")
    status = ["online", "idle", "dnd", "offline"]
    seconds = [0, 0, 0, 0]
    for i, s in enumerate(status):
        seconds[i] += data[i]
    durations = [naturaldelta(timedelta(seconds=s)) for s in seconds]
    colors = ["#43b581", "#faa61a", "#f04747", "#747f8d"]
    fig, ax = plt.subplots(figsize=(6, 8))
    wedges, _ = ax.pie(
        seconds, colors=colors, startangle=90, wedgeprops=dict(width=0.3)
    )
    ax.axis("equal")
    ax.set_aspect("equal")
    img = Image.open(BytesIO(avatar)).convert("RGBA")
    if img.format == "GIF":
        img = img.convert("RGBA").copy()
    mask = Image.new("L", img.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0) + img.size, fill=255)
    alpha = ImageMath.eval("a*b/255", a=img.split()[3], b=mask).convert("L")
    img.putalpha(alpha)
    width, height = img.size
    aspect_ratio = height / width
    half_width = 0.91
    half_height = aspect_ratio * half_width
    extent = [-half_width, half_width, -half_height, half_height]
    plt.imshow(img, extent=extent, zorder=-1)
    legend = ax.legend(
        wedges,
        durations,
        title=f"{name}'s activity overall",
        loc="upper center",
        bbox_to_anchor=(0.5, 0.08),
    )
    frame = legend.get_frame()
    frame.set_facecolor("#2C2F33")
    frame.set_edgecolor("#23272A")
    for text in legend.get_texts():
        text.set_color("#FFFFFF")
    plt.setp(legend.get_title(), color="w")
    buffer = BytesIO()
    plt.savefig(buffer, transparent=True)
    buffer.seek(0)
    return buffer.getvalue()


async def make_chart(
    member: Union[discord.Member, discord.User], data: Any, avatar: bytes
) -> bytes:
    return await _make_chart(member.name, data, avatar)


async def _collage_read(image: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(image) as response:
            try:
                resp = await response.read()
            except Exception:
                return None
    try:
        return await asyncio.get_event_loop().run_in_executor(
            executor, lambda: _collage_open(BytesIO(resp))
        )
    except Exception as e:
        logger.info(f"_collage_read raised {e}")
        return None


async def collage(images: list):
    l = []
    from base64 import urlsafe_b64encode
    from datetime import datetime
    from functools import partial, wraps
    from io import BytesIO
    from math import sqrt
    from pathlib import Path

    import aiohttp, asyncio
    import dateparser
    import discord
    import imagehash as ih

    from discord.ext import commands
    from PIL import Image
    from wordcloud import STOPWORDS, WordCloud
    from xxhash import xxh64_hexdigest

    return await __collage(images)

async def collage_(images: list):
    l = []
    from base64 import urlsafe_b64encode
    from datetime import datetime
    from functools import partial, wraps
    from io import BytesIO
    from math import sqrt
    from pathlib import Path

    import aiohttp, asyncio
    import dateparser
    import discord
    import imagehash as ih

    from discord.ext import commands
    from PIL import Image
    from wordcloud import STOPWORDS, WordCloud
    from xxhash import xxh64_hexdigest

    return await ___collage(images)

@offloaded
def __resize(image: bytes, size: tuple):
    i = Image.open(BytesIO(image)).convert("RGBA").resize(size)
    buffer = BytesIO()
    i.save(buffer, format="png")
    i.close()
    return buffer.getvalue()

@offloaded
def ___collage(_images: List[List[bytes]]) -> List[bytes]:
    if not _images:
        return None
    collages = []

    def open_image(image: bytes):
        return Image.open(BytesIO(image)).convert("RGBA").resize((300, 300))
    
    for images in _images:
        images = [open_image(i) for i in images]
        rows = int(sqrt(len(images)))
        columns = (len(images) + rows - 1) // rows

        background = Image.new(
            "RGBA",
            (
                columns * 256,
                rows * 256,
            ),
        )
        tasks = list()
        for i, image in enumerate(images):
            _collage_paste(image, i % columns, i // columns, background)
        #    await asyncio.gather(*tasks)

        buffer = BytesIO()
        background.save(
            buffer,
            format="png",
        )
        buffer.seek(0)

        background.close()
        for image in images:
            image.close()
        collages.append(buffer.getvalue())
    return collages


@offloaded
def __collage(images: list):
    if not images:
        return None

    def open_image(image: bytes):
        return Image.open(BytesIO(image)).convert("RGBA")#.resize((300, 300))

    images = [open_image(i) for i in images]
    rows = int(sqrt(len(images)))
    columns = (len(images) + rows - 1) // rows

    background = Image.new(
        "RGBA",
        (
            columns * 256,
            rows * 256,
        ),
    )
    tasks = list()
    for i, image in enumerate(images):
        _collage_paste(image, i % columns, i // columns, background)
    #    await asyncio.gather(*tasks)

    buffer = BytesIO()
    background.save(
        buffer,
        format="png",
    )
    buffer.seek(0)

    background.close()
    for image in images:
        image.close()
    return buffer.getvalue()
