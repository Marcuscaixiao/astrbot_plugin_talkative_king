from PIL import Image, ImageDraw, ImageFont
import os

def test_render():
    width = 1000
    height = 500
    img = Image.new('RGBA', (width, height), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    font_path = os.path.join(os.getcwd(), "assets", "msyh.ttc")
    print(f"Testing font path: {font_path}")
    
    try:
        font_title = ImageFont.truetype(font_path, 48)
        font_text = ImageFont.truetype(font_path, 28)
        print("Font loaded successfully!")
    except Exception as e:
        print(f"Failed to load font: {e}")
        return

    draw.text((50, 50), "今日发言排行榜 (Test Title)", font=font_title, fill=(0, 0, 0))
    draw.text((50, 150), "用户测试: 中文显示正常吗？", font=font_text, fill=(0, 0, 0))
    
    output_path = "test_font_output.png"
    img.save(output_path)
    print(f"Image saved to {output_path}")

if __name__ == "__main__":
    test_render()
