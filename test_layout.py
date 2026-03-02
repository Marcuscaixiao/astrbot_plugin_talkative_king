from PIL import Image, ImageDraw, ImageFont
import os
import datetime

def test_render():
    # Simulate data
    render_data = {
        "title": "今日发言排行榜",
        "date": datetime.datetime.now().strftime("%Y-%m-%d"),
        "users": []
    }
    
    # Add dummy users
    for i in range(5):
        render_data["users"].append({
            "name": f"用户测试{i}",
            "count": 100 - i,
            "rank": i + 1,
            "avatar": None # Skip avatar download for layout test
        })

    # Add a long name user
    render_data["users"].append({
        "name": "这是一个非常非常长的名字测试截断",
        "count": 50,
        "rank": 6,
        "avatar": None
    })

    # Copy-paste logic from main.py (simplified)
    width = 1000
    card_height = 100
    header_height = 160
    padding = 25
    
    cols = 2
    card_width = (width - (cols + 1) * padding) // cols
    
    user_count = len(render_data["users"])
    rows = (user_count + 1) // 2
    
    total_height = header_height + rows * (card_height + padding) + padding
    if total_height < 300:
        total_height = 300
        
    img = Image.new('RGBA', (width, total_height), (240, 242, 245, 255))
    draw = ImageDraw.Draw(img)
    
    # Font loading
    font_path = os.path.join(os.getcwd(), "assets", "msyh.ttc")
    try:
        font_title = ImageFont.truetype(font_path, 48)
        font_text = ImageFont.truetype(font_path, 28)
        font_small = ImageFont.truetype(font_path, 20)
        print("Font loaded.")
    except Exception as e:
        print(f"Font load failed: {e}")
        font_title = ImageFont.load_default()
        font_text = ImageFont.load_default()
        font_small = ImageFont.load_default()

    draw.rectangle([0, 0, width, header_height], fill=(255, 255, 255))
    draw.text((40, 40), render_data["title"], font=font_title, fill=(50, 50, 50))
    draw.text((40, 110), render_data["date"], font=font_small, fill=(100, 100, 100))
    
    for i, user in enumerate(render_data["users"]):
        col = i % 2
        row = i // 2
        x = padding + col * (card_width + padding)
        y = header_height + row * (card_height + padding)
        
        draw.rectangle([x, y, x + card_width, y + card_height], fill=(255, 255, 255), outline=(230, 230, 230), width=1)
        
        # Avatar placeholder
        draw.ellipse([x + 15, y + 15, x + 85, y + 85], fill=(200, 200, 200))
        
        text_x = x + 100
        name = user["name"]
        if len(name) > 10:
            name = name[:9] + "..."
        
        draw.text((text_x, y + 20), name, font=font_text, fill=(0, 0, 0))
        stats_text = f"发言: {user['count']}次"
        draw.text((text_x, y + 60), stats_text, font=font_small, fill=(100, 100, 100))

    output_path = "test_layout_output.png"
    img.save(output_path)
    print(f"Saved layout test to {output_path}")

if __name__ == "__main__":
    test_render()
