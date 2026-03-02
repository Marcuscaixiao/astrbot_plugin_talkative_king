import os
from PIL import Image, ImageFont, ImageDraw
from pilmoji import Pilmoji

def test_render():
    width, height = 500, 200
    img = Image.new('RGBA', (width, height), (255, 255, 255, 255))
    
    text = "Test: ( 。v_v 。) 杂鱼~"
    
    font_path = "C:\\Windows\\Fonts\\msyh.ttc"
    try:
        font = ImageFont.truetype(font_path, 28)
    except Exception as e:
        print(f"Failed to load msyh.ttc: {e}")
        return

    # Fallback fonts
    candidates = [
        "seguiemj.ttf", 
        "segoeui.ttf",  
        "msgothic.ttc", 
        "simsun.ttc",   
        "malgun.ttf",   
    ]
    base = "C:\\Windows\\Fonts"
    fallback_fonts = []
    for f in candidates:
        p = os.path.join(base, f)
        if os.path.exists(p):
            try:
                fallback_fonts.append(ImageFont.truetype(p, 28))
                print(f"Loaded fallback: {f}")
            except:
                print(f"Failed fallback: {f}")

    print(f"Total fallback fonts: {len(fallback_fonts)}")

    with Pilmoji(img) as pm:
        pm.text((10, 50), text, font=font, fill=(0, 0, 0))

    img.save("test_output.png")
    print("Saved test_output.png")

if __name__ == "__main__":
    test_render()
