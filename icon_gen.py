# icon_gen.py
from PIL import Image

# 1) 원본 PNG 파일 열기
img = Image.open("icon_source.png")

# 2) ICO 로 저장 (크기별로 여러 스케일 포함)
img.save(
    "app.ico",
    format="ICO",
    sizes=[(256,256), (128,128), (64,64), (48,48), (32,32), (16,16)]
)
