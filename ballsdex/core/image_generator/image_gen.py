import os
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image, ImageDraw, ImageFont, ImageOps

if TYPE_CHECKING:
    from ballsdex.core.models import BallInstance


SOURCES_PATH = Path(os.path.dirname(os.path.abspath(__file__)), "./src")
WIDTH = 1500
HEIGHT = 2000

RECTANGLE_WIDTH = WIDTH - 40
RECTANGLE_HEIGHT = (HEIGHT // 5) * 2

CORNERS = ((163, 308), (1264, 954))
artwork_size = [b - a for a, b in zip(*CORNERS)]

title_font = ImageFont.truetype(str(SOURCES_PATH / "jf-openhuninn-2.0.ttf"), 140)
capacity_name_font = ImageFont.truetype(str(SOURCES_PATH / "jf-openhuninn-2.0.ttf"), 100)
capacity_description_font = ImageFont.truetype(str(SOURCES_PATH / "jf-openhuninn-2.0.ttf"), 65)
stats_font = ImageFont.truetype(str(SOURCES_PATH / "Bobby Jones Soft.otf"), 130)
credits_font = ImageFont.truetype(str(SOURCES_PATH / "jf-openhuninn-2.0.ttf"), 40)

def draw_card(ball_instance: "BallInstance"):
    ball = ball_instance.countryball
    ball_health = (237, 115, 101, 255)

    if ball_instance.shiny:
        image = Image.open(str(SOURCES_PATH / "shiny.png"))
        ball_health = (255, 255, 255, 255)
    elif special_image := ball_instance.special_card:
        image = Image.open("." + special_image)
    else:
        image = Image.open("." + ball.cached_regime.background)
    icon = Image.open("." + ball.cached_economy.icon) if ball.cached_economy else None

    draw = ImageDraw.Draw(image)
    draw.text((350, 150), ball.short_name or ball.country, font=title_font, stroke_width=2)
    for i, line in enumerate(textwrap.wrap(f"{ball.capacity_name}", width=26)):
        draw.text(
            (200, 1110 + 100 * i),
            line,
            font=capacity_name_font,
            fill=(230, 230, 230, 255),
            stroke_width=3,
            stroke_fill=(0, 0, 0, 255),
        )
    for i, line in enumerate(textwrap.wrap(ball.capacity_description, width=16)):
        draw.text(
            (200, 1250 + 70 * i),
            line,
            font=capacity_description_font,
            stroke_width=2,
            stroke_fill=(0, 0, 0, 255),
        )
    draw.text(
        (185, 1700),
        str(ball_instance.health),
        font=stats_font,
        fill=ball_health,
        stroke_width=1,
        stroke_fill=(0, 0, 0, 255),
    )
    draw.text(
        (1243, 1700),
        str(ball_instance.attack),
        font=stats_font,
        fill=(252, 194, 76, 255),
        stroke_width=1,
        stroke_fill=(0, 0, 0, 255),
        anchor="ra",
    )
    draw.text(
        (30, 1950),
        # Modifying the line below is breaking the licence as you are removing credits
        # If you don't want to receive a DMCA, just don't
        "Created by El Laggron.",
        font=credits_font,
        fill=(0, 0, 0, 255),
        stroke_width=0,
        stroke_fill=(255, 255, 255, 255),
    )
    draw.text(
        (1398, 1950),
        f"Artwork: {ball.credits}",
        font=credits_font,
        fill=(0, 0, 0, 255),
        stroke_width=0,
        stroke_fill=(255, 255, 255, 255),
        anchor="ra",
    )

    artwork = Image.open("." + ball.collection_card)
    image.paste(ImageOps.fit(artwork, artwork_size), CORNERS[0])  # type: ignore

    if icon:
        icon = ImageOps.fit(icon, (120, 120))
        image.paste(icon, (162, 158), mask=icon)
        icon.close()
    artwork.close()

    return image
