from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import math


ASSET_DIR = Path("quotation_assets")
OUTPUT = Path("quotation_assets_contact_sheet_v2.jpg")

files = sorted(
    f for f in ASSET_DIR.iterdir()
    if f.suffix.lower() in [".png", ".jpg", ".jpeg"]
)

thumb_width = 220
thumb_height = 160
label_height = 45
columns = 4

rows = math.ceil(len(files) / columns)

sheet = Image.new(
    "RGB",
    (columns * thumb_width, rows * (thumb_height + label_height)),
    "#eeeeee"
)

draw = ImageDraw.Draw(sheet)

try:
    font = ImageFont.truetype("arial.ttf", 13)
except:
    font = ImageFont.load_default()


for index, file_path in enumerate(files):

    row = index // columns
    column = index % columns

    x = column * thumb_width
    y = row * (thumb_height + label_height)

    try:
        image = Image.open(file_path)

        # Properly handle transparency
        if image.mode in ("RGBA", "LA") or "transparency" in image.info:
            image = image.convert("RGBA")

            # Light checkerboard background
            bg = Image.new(
                "RGB",
                image.size,
                "#f5f5f5"
            )

            bg_rgba = bg.convert("RGBA")
            bg_rgba.alpha_composite(image)

            image = bg_rgba.convert("RGB")

        else:
            image = image.convert("RGB")

        image.thumbnail(
            (thumb_width - 20, thumb_height - 20)
        )

        image_x = x + (thumb_width - image.width) // 2
        image_y = y + (thumb_height - image.height) // 2

        sheet.paste(image, (image_x, image_y))

    except Exception as e:
        draw.text(
            (x + 10, y + 10),
            f"ERROR\n{e}",
            fill="red",
            font=font
        )

    draw.rectangle(
        [
            x,
            y,
            x + thumb_width - 1,
            y + thumb_height + label_height - 1
        ],
        outline="gray"
    )

    filename = file_path.name

    if len(filename) > 30:
        filename = filename[:27] + "..."

    draw.text(
        (x + 8, y + thumb_height + 5),
        filename,
        fill="black",
        font=font
    )


sheet.save(OUTPUT, quality=95)

print()
print(f"Created: {OUTPUT}")
print(f"Images: {len(files)}")