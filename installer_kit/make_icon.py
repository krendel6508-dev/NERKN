"""Generate the build icon without importing or launching the application."""
from pathlib import Path
from PIL import Image, ImageDraw

image = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((12, 12, 244, 244), radius=52, fill='#33e6a6')
draw.polygon([(128, 55), (190, 80), (182, 154), (158, 183), (128, 204),
              (98, 183), (74, 154), (66, 80)], fill='#090c1a')
draw.line([(96, 127), (119, 150), (162, 105)], fill='#4fd1ff', width=15)
image.save(Path(__file__).with_name('app_icon.ico'), sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
