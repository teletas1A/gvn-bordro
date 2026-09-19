from PIL import Image, ImageDraw, ImageFont

size = 256
image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((4, 4, size - 4, size - 4), radius=56, fill="#d71920")
try:
    font = ImageFont.truetype("arialbd.ttf", 168)
except OSError:
    font = ImageFont.load_default(size=168)
box = draw.textbbox((0, 0), "B", font=font)
x = (size - (box[2] - box[0])) / 2
y = (size - (box[3] - box[1])) / 2 - box[1] - 4
draw.text((x, y), "B", font=font, fill="white")
image.save("assets/gvn_bordro.ico", format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
