"""Generate the app's code-drawn comic document icon and Windows ICO sizes."""

from pathlib import Path
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parents[1]
target = root / "desktop/assets"
target.mkdir(parents=True, exist_ok=True)
size = 1024
image = Image.new("RGBA", (size, size))
draw = ImageDraw.Draw(image)
ink, blue, yellow, paper = "#25252D", "#3656D9", "#FFE18B", "#FFFEFA"
draw.polygon([(760,38),(798,110),(894,78),(878,167),(975,199),(899,254),(941,342),(848,333),(824,423),(756,361),(677,418),(674,321),(583,293),(658,233),(619,148),(710,156)], fill=yellow, outline=ink, width=18)
draw.rounded_rectangle((186,144,810,946), radius=44, fill=ink)
draw.polygon([(154,108),(615,108),(774,267),(774,908),(154,908)], fill=paper, outline=ink, width=24)
draw.polygon([(615,108),(615,267),(774,267)], fill=yellow, outline=ink, width=20)
draw.rounded_rectangle((226,338,664,366),radius=14,fill=ink)
draw.rounded_rectangle((226,399,552,425),radius=13,fill=ink)
draw.rounded_rectangle((226,489,706,825),radius=32,fill=ink)
draw.rounded_rectangle((210,473,690,809),radius=32,fill=blue,outline=ink,width=18)
draw.line([(275,723),(275,561),(345,650),(414,561),(414,723)],fill=paper,width=30,joint="curve")
draw.line([(551,555),(551,704)],fill=paper,width=28)
draw.polygon([(488,673),(614,673),(551,746)],fill=paper)
image.save(target / "md-converter.png")
image.resize((48,48), Image.Resampling.LANCZOS).save(target / "brand-48.png")
image.save(target / "md-converter.ico",sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
print(target / "md-converter.ico")
