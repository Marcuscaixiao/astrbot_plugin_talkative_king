import os
import json
import asyncio
import datetime
import io
import aiohttp
import random
import tempfile
import shutil
import re
from pathlib import Path
try:
    from pilmoji import Pilmoji
    HAS_PILMOJI = True
except ImportError:
    HAS_PILMOJI = False
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps
from astrbot.api.event import filter, AstrMessageEvent, MessageChain
from astrbot.api.star import Context, Star, StarTools, register
from astrbot.api import logger

@register("talkative_king", "User", "统计群组发言并生成排行榜", "1.4.0", "")
class TalkativeKing(Star):
    ZAKO_PHRASES = [
        "杂鱼~杂鱼~",
        "不会吧不会吧，今天只有这点人说话？",
        "这种程度就不行了吗？好弱哎~",
        "寂寞的群聊，杂鱼般的发言量~",
        "再不努力说话就要被看扁了哦~",
        "杂鱼❤~ 杂鱼❤~",
        "就这？就这？",
        "好安静啊，杂鱼们都在睡觉吗？",
        "有没有人理理我嘛~ 杂鱼们！",
        "连颜文字都发不出来吧？ ( 。v_v 。) 杂鱼~"
    ]

    def get_fallback_fonts(self, size):
        fonts = []
        # Fallback list for special symbols (Kaomoji, etc.)
        candidates = [
            "seguiemj.ttf", # Segoe UI Emoji (Symbols)
            "segoeui.ttf",  # Segoe UI
            "msgothic.ttc", # MS Gothic (Japanese/Kaomoji)
            "simsun.ttc",   # SimSun (Chinese)
            "malgun.ttf",   # Malgun Gothic (Korean)
        ]
        base = "C:\\Windows\\Fonts"
        for f in candidates:
            p = os.path.join(base, f)
            if os.path.exists(p):
                try:
                    fonts.append(ImageFont.truetype(p, size))
                except:
                    pass
        return fonts

    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.plugin_root_name = "astrbot_plugin_talkative_king"
        self.data_dir = Path(StarTools.get_data_dir("astrbot_plugin_talkative_king"))
        self.data_path = os.path.join(os.getcwd(), "data", "talkative_king.json")
        self.data = self.load_data()
        # 定时自动发送相关状态
        # 后台任务对象（asyncio.Task）
        self._auto_send_task = None
        # 标记后台任务是否已启动，避免重复启动
        self._auto_send_started = False
        # 记录每个群今天是否已自动发送过，key 为 group_id，value 为日期字符串
        # 防止同一分钟内重复发送 / loop 多次触发
        self._auto_send_last_sent = {}
        self._cleanup_legacy_render_dir()

    def _cleanup_legacy_render_dir(self):
        legacy_dir = os.path.join(os.getcwd(), "data", "talkative_king_images")
        if not os.path.isdir(legacy_dir):
            return
        try:
            shutil.rmtree(legacy_dir)
            logger.info("已清理旧版排行榜图片缓存目录。")
        except Exception as e:
            logger.warning(f"Failed to remove legacy leaderboard image cache dir: {e}")

    def _load_runtime_config(self):
        candidate_names = [
            f"{self.plugin_root_name}_config.json",
            "talkative_king_config.json",
        ]
        config_dir = Path(os.getcwd()) / "data" / "config"

        for filename in candidate_names:
            config_path = config_dir / filename
            if not config_path.is_file():
                continue

            try:
                with config_path.open("r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    return loaded
            except Exception as e:
                logger.warning(f"Failed to load runtime config from {config_path}: {e}")

        return self.config if isinstance(self.config, dict) else {}

    def _resolve_config_file_path(self, value):
        if isinstance(value, dict):
            for key in ("path", "value", "file_path", "file"):
                candidate = value.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    value = candidate
                    break

        if not isinstance(value, str):
            return None

        raw_path = value.strip()
        if not raw_path:
            return None

        direct_path = Path(raw_path).expanduser()
        if direct_path.is_file():
            return str(direct_path)

        rel = raw_path.replace("\\", "/").lstrip("/")
        parts = [part for part in rel.split("/") if part]
        if not parts or any(part in {".", ".."} for part in parts):
            return None

        candidate_roots = [
            self.data_dir,
            Path(os.getcwd()) / "data",
            Path(os.getcwd()),
        ]

        for root in candidate_roots:
            target = (root / "/".join(parts)).resolve(strict=False)
            try:
                target.relative_to(root.resolve(strict=False))
            except ValueError:
                continue

            if target.is_file():
                return str(target)

        return None

    def _get_background_path(self):
        asset_bg_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "assets",
            "background.jpg",
        )

        effective_config = self._load_runtime_config()
        if not isinstance(effective_config, dict):
            return asset_bg_path

        custom_bg_list = effective_config.get("custom_bg", [])
        if isinstance(custom_bg_list, list):
            # WebUI 的 file 配置是追加式上传，最新上传的背景应优先生效。
            for item in reversed(custom_bg_list):
                resolved = self._resolve_config_file_path(item)
                if resolved:
                    return resolved

        fallback_path = effective_config.get("custom_bg_path", "")
        resolved_fallback = self._resolve_config_file_path(fallback_path)
        if resolved_fallback:
            return resolved_fallback

        return asset_bg_path

    def get_current_date(self):
        # Enforce UTC+8 (Beijing Time) for consistency
        utc_now = datetime.datetime.utcnow()
        beijing_now = utc_now + datetime.timedelta(hours=8)
        return beijing_now.date()
        
    def load_data(self):
        if not os.path.exists(os.path.dirname(self.data_path)):
            try:
                os.makedirs(os.path.dirname(self.data_path), exist_ok=True)
            except Exception as e:
                logger.warning(f"Failed to create data directory: {e}")
            
        if os.path.exists(self.data_path):
            try:
                with open(self.data_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Ensure basic structure
                    if "groups" not in data:
                        data["groups"] = {}
                    if "date" not in data:
                        data["date"] = self.get_current_date().isoformat()
                    # umo_map: group_id -> unified_msg_origin，用于定时主动推送
                    if "umo_map" not in data or not isinstance(data["umo_map"], dict):
                        data["umo_map"] = {}
                    
                    # Sanitize keys: Convert all Group IDs to strings
                    # This fixes the issue where some groups might have been stored as integers
                    # and thus are not accessible via string lookup.
                    if "groups" in data and isinstance(data["groups"], dict):
                        new_groups = {}
                        for k, v in data["groups"].items():
                            new_groups[str(k)] = v
                        data["groups"] = new_groups

                    if "yesterday" in data and isinstance(data["yesterday"], dict):
                        y_groups = data["yesterday"].get("groups", {})
                        if isinstance(y_groups, dict):
                            new_y_groups = {}
                            for k, v in y_groups.items():
                                new_y_groups[str(k)] = v
                            data["yesterday"]["groups"] = new_y_groups
                    
                    return data
            except Exception as e:
                logger.error(f"Failed to load data: {e}")
        return {"date": self.get_current_date().isoformat(), "groups": {}, "umo_map": {}}

    async def save_data(self):
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._save_data_sync)
        except Exception as e:
            logger.error(f"Failed to save data: {e}")

    def _save_data_sync(self):
        try:
            os.makedirs(os.path.dirname(self.data_path), exist_ok=True)
            # Atomic write using temp file
            dir_path = os.path.dirname(self.data_path)
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=dir_path, delete=False) as tf:
                json.dump(self.data, tf, ensure_ascii=False, indent=2)
                temp_path = tf.name
            
            # Atomic replace
            shutil.move(temp_path, self.data_path)
        except Exception as e:
            logger.error(f"Failed to save data atomically: {e}")
            # Try direct write fallback
            try:
                with open(self.data_path, 'w', encoding='utf-8') as f:
                    json.dump(self.data, f, ensure_ascii=False, indent=2)
            except Exception as e2:
                logger.error(f"Failed fallback save: {e2}")

    async def check_reset(self):
        today = self.get_current_date()
        today_str = today.isoformat()
        
        data_date_str = self.data.get("date")
        if not data_date_str:
             self.data["date"] = today_str
             return

        try:
            data_date = datetime.date.fromisoformat(data_date_str)
        except ValueError:
            # Invalid date format, reset everything
            self.data["date"] = today_str
            self.data["groups"] = {}
            self.data["yesterday"] = {}
            await self.save_data()
            return

        if data_date < today:
            # It's a new day
            delta = (today - data_date).days
            
            if delta == 1:
                # Exactly yesterday
                # Deep copy and ensure keys are strings just in case
                groups_data = self.data.get("groups", {})
                sanitized_groups = {}
                for k, v in groups_data.items():
                    sanitized_groups[str(k)] = v

                self.data["yesterday"] = {
                    "date": data_date_str,
                    "groups": sanitized_groups
                }
            else:
                # Older than yesterday (bot was off yesterday)
                # Yesterday has no data
                self.data["yesterday"] = {
                    "date": (today - datetime.timedelta(days=1)).isoformat(),
                    "groups": {} 
                }
            
            # Reset today
            self.data["date"] = today_str
            self.data["groups"] = {}
            await self.save_data()

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event: AstrMessageEvent):
        # 懒启动定时自动发送后台任务（确保 event loop 已运行）
        self._ensure_auto_send_task()

        # 1. Trigger Check (Priority)
        msg = event.message_str or ""
        
        # Robust Trigger Matching
        # 1. Remove At-mentions (e.g., @123456 or @User)
        # Regex: @ followed by non-whitespace
        clean_msg = re.sub(r"@\S+", "", msg)
        
        # 2. Remove common command prefixes and punctuation
        # Remove leading/trailing non-word chars (punctuations, spaces)
        clean_msg = re.sub(r"^[!！/\\.。\s]+", "", clean_msg)
        clean_msg = re.sub(r"[!！.。\s]+$", "", clean_msg)
        
        # 3. Remove internal spaces for fuzzy match
        clean_msg = clean_msg.replace(" ", "").replace("　", "")
        
        keywords_today = ["今日壁画王", "今日发言排行榜", "今日发言", "今日排行"]
        keywords_yesterday = ["昨日壁画王", "昨日发言排行榜", "昨日发言", "昨日排行"]
        
        is_today_cmd = clean_msg in keywords_today
        is_yesterday_cmd = clean_msg in keywords_yesterday
        
        if is_today_cmd:
            try:
                await self.check_reset()
                await self.cmd_today(event)
            except Exception as e:
                logger.error(f"Error executing cmd_today: {e}")
            event.stop_event()
            return
        elif is_yesterday_cmd:
            try:
                await self.check_reset()
                await self.cmd_yesterday(event)
            except Exception as e:
                logger.error(f"Error executing cmd_yesterday: {e}")
            event.stop_event()
            return

        # 2. Data Collection
        try:
            await self.check_reset()
            group_id = str(event.get_group_id()) # Ensure string
            user_id = event.get_sender_id()
            user_name = event.get_sender_name()

            if not group_id or not user_id:
                return

            # 记录该群的 unified_msg_origin，供定时主动推送使用
            try:
                umo = event.unified_msg_origin
                if umo and self.data.get("umo_map", {}).get(group_id) != umo:
                    self.data.setdefault("umo_map", {})[group_id] = umo
                    await self.save_data()
            except Exception as e:
                logger.warning(f"Failed to record unified_msg_origin: {e}")

            # Fallback for empty name
            if not user_name:
                user_name = str(user_id)

            if group_id not in self.data["groups"]:
                self.data["groups"][group_id] = {}
                
            # Initialize user if new
            if user_id not in self.data["groups"][group_id]:
                self.data["groups"][group_id][user_id] = {
                    "count": 0,
                    "name": user_name,
                    "avatar": f"https://q1.qlogo.cn/g?b=qq&nk={user_id}&s=640"
                }
            
            # Smart Name Update Logic
            # Only update the name if the new name is NOT just the User ID
            # OR if the currently stored name IS just the User ID (upgrade it)
            should_update_name = True
            
            current_stored_name = self.data["groups"][group_id][user_id].get("name", "")
            is_new_name_id = (user_name == str(user_id) or user_name == f"用户{user_id}")
            is_stored_name_id = (current_stored_name == str(user_id) or current_stored_name == f"用户{user_id}")
            
            if is_new_name_id and not is_stored_name_id:
                # If we have a good name stored, and the new one is just an ID, preserve the old good name.
                should_update_name = False
            
            if should_update_name:
                self.data["groups"][group_id][user_id]["name"] = user_name
                
            self.data["groups"][group_id][user_id]["count"] += 1
            await self.save_data()
        except Exception as e:
            logger.error(f"TalkativeKing processing error: {e}")

    async def _download_avatar(self, url, session=None):
        if session:
            try:
                async with session.get(url, timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        return Image.open(io.BytesIO(data)).convert("RGBA")
            except Exception as e:
                logger.warning(f"Download avatar failed: {e}")
            return None
        else:
            try:
                async with aiohttp.ClientSession() as session:
                    return await self._download_avatar(url, session=session)
            except Exception as e:
                logger.warning(f"Download avatar failed: {e}")
            return None

    def _create_circle_avatar(self, img, size):
        img = img.resize((size, size), Image.Resampling.LANCZOS)
        mask = Image.new('L', (size, size), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, size, size), fill=255)
        output = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        output.paste(img, (0, 0), mask)
        return output

    async def render_pil_image(self, render_data):
        # Pre-download avatars concurrently
        avatars = []
        async with aiohttp.ClientSession() as session:
            tasks = []
            for user in render_data["users"]:
                tasks.append(self._download_avatar(user["avatar"], session))
            avatars = await asyncio.gather(*tasks)

        # Canvas settings
        width = 1000  # Increased width for better clarity
        # Header + (Rows * RowHeight) + Padding
        card_height = 100
        header_height = 160 # Increased header height
        padding = 25
        
        # Calculate grid layout
        cols = 2
        card_width = (width - (cols + 1) * padding) // cols
        
        # Recalculate height based on grid
        user_count = len(render_data["users"])
        rows = (user_count + 1) // 2
        if user_count == 0:
            rows = 0
            
        total_height = header_height + rows * (card_height + padding) + padding
        if total_height < 300:
            total_height = 300
            
        # Create image
        # Try to load background
        bg_path = self._get_background_path()
        
        if os.path.exists(bg_path):
            try:
                bg_img = Image.open(bg_path).convert("RGBA")
                # Resize/Crop background to fill the canvas
                # We want to cover the whole area
                bg_ratio = bg_img.width / bg_img.height
                canvas_ratio = width / total_height
                
                if canvas_ratio > bg_ratio:
                    # Canvas is wider than background - fit to width
                    new_width = width
                    new_height = int(width / bg_ratio)
                else:
                    # Canvas is taller than background - fit to height
                    new_height = total_height
                    new_width = int(total_height * bg_ratio)
                
                bg_img = bg_img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                # Center crop
                left = (new_width - width) // 2
                top = (new_height - total_height) // 2
                bg_img = bg_img.crop((left, top, left + width, top + total_height))
                
                # Apply a light blur or overlay to improve readability
                # bg_img = bg_img.filter(ImageFilter.GaussianBlur(radius=3))
                
                img = bg_img
            except Exception as e:
                logger.warning(f"Failed to load background: {e}")
                img = Image.new('RGBA', (width, total_height), (240, 242, 245, 255))
        else:
            img = Image.new('RGBA', (width, total_height), (240, 242, 245, 255))

        # Create a transparent layer for drawing to support alpha composite
        overlay = Image.new('RGBA', (width, total_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        
        # Initialize Pilmoji if available
        # Pick a random Zako phrase
        zako_phrase = random.choice(self.ZAKO_PHRASES)

        # Fonts
        font_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "msyh.ttc")
        if not os.path.exists(font_path):
             # Fallback to system font if local asset missing
             font_path = "C:\\Windows\\Fonts\\msyh.ttc"

        try:
            font_title = ImageFont.truetype(font_path, 48) # Larger title
            font_text = ImageFont.truetype(font_path, 28)  # Larger name
            font_small = ImageFont.truetype(font_path, 20) # Larger stats
            font_rank = ImageFont.truetype(font_path, 24)  # Rank number
        except Exception as e:
            logger.warning(f"Failed to load custom font: {e}, using default")
            font_title = ImageFont.load_default()
            font_text = ImageFont.load_default()
            font_small = ImageFont.load_default()
            font_rank = ImageFont.load_default()

        # Helper for text with shadow
        def draw_text_with_shadow(xy, text, font, fill, shadow_color=(0, 0, 0, 180), offset=(2, 2)):
            try:
                # Ensure coordinates are integers
                x = int(xy[0])
                y = int(xy[1])
                ox = int(offset[0])
                oy = int(offset[1])
                
                if HAS_PILMOJI:
                    # Use Pilmoji for emoji support
                    with Pilmoji(overlay) as pm:
                        pm.text((x + ox, y + oy), text, font=font, fill=shadow_color)
                        pm.text((x, y), text, font=font, fill=fill)
                else:
                    draw.text((x + ox, y + oy), text, font=font, fill=shadow_color)
                    draw.text((x, y), text, font=font, fill=fill)
            except Exception as e:
                logger.warning(f"Failed to draw text shadow: {e}")
                # Fallback to simple text
                try:
                    if HAS_PILMOJI:
                        with Pilmoji(overlay) as pm:
                            pm.text(xy, text, font=font, fill=fill)
                    else:
                        draw.text(xy, text, font=font, fill=fill)
                except:
                    pass

        # Helper to get text size
        def get_text_size(text, font):
            try:
                if HAS_PILMOJI:
                    with Pilmoji(overlay) as pm:
                        return pm.getsize(text, font)
                else:
                    bbox = draw.textbbox((0, 0), text, font=font)
                    return bbox[2] - bbox[0], bbox[3] - bbox[1]
            except:
                # Fallback
                bbox = draw.textbbox((0, 0), text, font=font)
                return bbox[2] - bbox[0], bbox[3] - bbox[1]

        # Draw Header Background (Glassmorphism)
        # Semi-transparent white rounded box for header
        header_bg_box = [20, 20, width - 20, header_height - 10]
        draw.rounded_rectangle(header_bg_box, radius=15, fill=(255, 255, 255, 200))
        
        draw_text_with_shadow((50, 40), render_data["title"], font=font_title, fill=(235, 85, 130)) # Pinkish title
        draw.text((50, 100), render_data["date"], font=font_small, fill=(100, 100, 100))

        if user_count == 0:
             # Draw centered Zako phrase for empty data
             try:
                 # Calculate text size for centering
                 text_w, text_h = get_text_size(zako_phrase, font_title)
                 
                 x_pos = (width - text_w) // 2
                 # Center in the remaining space below header
                 body_height = total_height - header_height
                 y_pos = header_height + (body_height - text_h) // 2 - 10
                 
                 # Draw with heavy shadow/outline for visibility
                 draw_text_with_shadow((x_pos, y_pos), zako_phrase, font=font_title, fill=(255, 80, 80), offset=(3,3))
             except:
                 # Fallback if textbbox fails (older PIL)
                 draw_text_with_shadow((50, 180), zako_phrase, font=font_title, fill=(255, 80, 80))
             
        else:
            # Draw Zako phrase in header area (top right)
            try:
                # Use a slightly smaller font or the text font
                text_w, _ = get_text_size(zako_phrase, font_text)
                
                # Position: Right aligned in header, vertically centered relative to header content
                x_pos = width - text_w - 50
                y_pos = 60 # Approximate middle of header content
                
                draw_text_with_shadow((x_pos, y_pos), zako_phrase, font=font_text, fill=(235, 85, 130)) 
            except:
                draw_text_with_shadow((width - 300, 60), zako_phrase, font=font_text, fill=(235, 85, 130))

        # Draw Users
        for i, user in enumerate(render_data["users"]):
            col = i % 2
            row = i // 2
            
            x = padding + col * (card_width + padding)
            y = header_height + row * (card_height + padding)
            
            # Card Background (Semi-transparent dark/grey gradient or solid)
            # Ref image seems to have dark cards with white text? Or transparent.
            # Let's go with semi-transparent black/grey for contrast against colorful bg
            card_box = [x, y, x + card_width, y + card_height]
            
            # Gradient-like effect or solid glass
            # Using solid semi-transparent black for readability on any background
            draw.rounded_rectangle(card_box, radius=15, fill=(0, 0, 0, 120), outline=(255, 255, 255, 100), width=1)
            
            # Avatar
            avatar_img = avatars[i]
            
            if avatar_img:
                avatar_size = 70 
                avatar_circle = self._create_circle_avatar(avatar_img, avatar_size)
                # Paste avatar onto overlay requires careful handling if overlay has alpha
                # Easier to paste onto the base image, but we are drawing on 'overlay'
                # We can paste onto 'overlay' directly
                overlay.paste(avatar_circle, (x + 15, y + 15), avatar_circle)
            else:
                # Placeholder
                draw.ellipse([x + 15, y + 15, x + 85, y + 85], fill=(200, 200, 200, 200))
                
            # Text Info
            text_x = x + 100
            # Name
            name = user["name"]
            # Truncate
            if len(name) > 10:
                name = name[:9] + "..."
            
            # White text for dark cards
            # Use Pilmoji for name to support emojis
            if HAS_PILMOJI:
                with Pilmoji(overlay) as pm:
                    pm.text((text_x, y + 20), name, font=font_text, fill=(255, 255, 255))
            else:
                draw.text((text_x, y + 20), name, font=font_text, fill=(255, 255, 255))
            
            # Stats
            stats_text = f"发言次数: {user['count']}次  排名: {user['rank']}"
            draw.text((text_x, y + 65), stats_text, font=font_small, fill=(200, 200, 200))

            # Rank Badge (Optional, since we have text rank now)
            # Let's keep a subtle visual indicator for top 3
            rank = user['rank']
            if rank <= 3:
                colors = [(255, 215, 0), (192, 192, 192), (205, 127, 50)]
                # Add a small glow or border to avatar?
                # Or just a colored number
                pass 

        # Composite overlay onto background
        img = Image.alpha_composite(img, overlay)


        # 写入系统临时文件，发送完成后立即删除，不在插件数据目录保留任何排行榜图片
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
            output_path = tmp_file.name

        # 使用 JPEG 格式并压缩质量，大幅减小体积，避免框架上传超时
        img.convert('RGB').save(output_path, format='JPEG', quality=85)
        
        # 转换为绝对路径并替换反斜杠为正斜杠，增强 NapCat 等框架在 Windows 下的路径兼容性
        output_path = os.path.abspath(output_path).replace('\\', '/')
        return output_path

    @filter.command("今日壁画王", alias={"今日发言排行榜", "今日发言", "今日排行"})
    async def cmd_today(self, event: AstrMessageEvent):
        await self.check_reset()
        await self.send_leaderboard(event, "today")

    @filter.command("昨日壁画王", alias={"昨日发言排行榜", "昨日发言", "昨日排行"})
    async def cmd_yesterday(self, event: AstrMessageEvent):
        await self.check_reset()
        await self.send_leaderboard(event, "yesterday")

    async def send_leaderboard(self, event: AstrMessageEvent, which="today"):
        group_id = str(event.get_group_id())
        if not group_id:
            await event.send(event.plain_result("请在群聊中使用此指令。"))
            return

        # Render Image
        image_path = None
        try:
            image_path = await self._render_leaderboard_image(group_id, which)
            if image_path and os.path.exists(image_path):
                await event.send(event.image_result(image_path))
            else:
                await event.send(event.plain_result("生成图片失败: 未能获取图片路径"))
        except Exception as e:
            logger.error(f"Render failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await event.send(event.plain_result(f"生成图片失败: {e}"))
        finally:
            if image_path and os.path.exists(image_path):
                try:
                    os.remove(image_path)
                except OSError as cleanup_error:
                    logger.warning(f"Failed to remove temporary leaderboard image: {cleanup_error}")

    async def _render_leaderboard_image(self, group_id, which="today"):
        """根据 group_id 与 which(today/yesterday) 生成排行榜图片，返回图片路径或 None。
        该方法不依赖 event，手动指令与定时自动发送共用。"""
        if which == "today":
            target_data = self.data["groups"]
            date_str = self.data.get("date", "未知日期")
            title = "今日发言排行榜"
        else:
            yesterday_info = self.data.get("yesterday")
            if not yesterday_info:
                # Handle missing yesterday data
                target_data = {}
                date_str = (self.get_current_date() - datetime.timedelta(days=1)).isoformat()
            else:
                target_data = yesterday_info.get("groups", {})
                date_str = yesterday_info.get("date", "未知日期")
            title = "昨日发言排行榜"

        # Even if no data, we proceed to render the "Zako" image
        group_data = target_data.get(group_id, {})

        # Sort users
        sorted_users = sorted(group_data.items(), key=lambda x: x[1]["count"], reverse=True)
        top_users = sorted_users[:20]

        # Prepare data for PIL
        render_users = []
        for index, (uid, info) in enumerate(top_users):
            render_users.append({
                "rank": index + 1,
                "name": info["name"],
                "count": info["count"],
                "avatar": info.get("avatar", f"https://q1.qlogo.cn/g?b=qq&nk={uid}&s=640")
            })

        render_data = {
            "title": title,
            "date": date_str,
            "users": render_users
        }

        image_path = await self.render_pil_image(render_data)
        return image_path

    # ===================== 定时自动发送 =====================

    def _ensure_auto_send_task(self):
        """懒启动定时自动发送后台任务，保证仅在 event loop 运行后创建。"""
        if self._auto_send_started:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # 当前没有运行中的 loop，跳过（下次消息到来再尝试）
            return
        self._auto_send_started = True
        self._auto_send_task = loop.create_task(self._auto_send_loop())
        logger.info("TalkativeKing 定时自动发送后台任务已启动。")

    async def _auto_send_loop(self):
        """后台循环：每分钟检查一次是否到达设定发送时间，到达则向目标群主动推送今日壁画王。"""
        while True:
            try:
                await asyncio.sleep(60)
                await self._auto_send_tick()
            except asyncio.CancelledError:
                # 插件卸载时被取消，正常退出
                break
            except Exception as e:
                logger.error(f"Auto send loop error: {e}")

    async def _auto_send_tick(self):
        cfg = self._load_runtime_config()
        if not isinstance(cfg, dict):
            return
        # 未启用则直接返回
        if not cfg.get("auto_send_enabled", False):
            return

        # 解析发送时间 HH:MM（北京时间）
        time_str = str(cfg.get("auto_send_time", "08:00")).strip()
        try:
            hour_str, minute_str = time_str.split(":")
            target_hour = int(hour_str)
            target_minute = int(minute_str)
            if not (0 <= target_hour <= 23 and 0 <= target_minute <= 59):
                raise ValueError
        except Exception:
            logger.warning(f"自动发送时间格式非法: {time_str}，应为 HH:MM")
            return

        # 当前北京时间
        utc_now = datetime.datetime.utcnow()
        beijing_now = utc_now + datetime.timedelta(hours=8)
        today_str = beijing_now.date().isoformat()

        # 未到点则跳过
        if not (beijing_now.hour == target_hour and beijing_now.minute == target_minute):
            return

        # 目标群号列表
        # 一键广播：开启后向所有已记录过消息的群发送，无需填写群号列表
        umo_map = self.data.get("umo_map", {})
        if cfg.get("auto_send_all_groups", False):
            # 遍历所有已记录的群（umo_map 的 key 即为 group_id）
            group_ids = [str(gid) for gid in umo_map.keys() if str(gid).strip()]
            logger.info(f"一键广播模式：将向 {len(group_ids)} 个群发送今日壁画王。")
        else:
            raw_groups = cfg.get("auto_send_groups", [])
            if not isinstance(raw_groups, list) or not raw_groups:
                return
            group_ids = [str(raw_gid).strip() for raw_gid in raw_groups if str(raw_gid).strip()]

        for group_id in group_ids:
            if not group_id:
                continue
            # 当天已发送过则跳过，避免同一分钟重复触发
            if self._auto_send_last_sent.get(group_id) == today_str:
                continue
            umo = umo_map.get(group_id)
            if not umo:
                logger.warning(f"自动发送跳过群 {group_id}：尚未记录该群的会话标识(umo)，请确保机器人已在群内接收过消息。")
                continue
            await self._send_auto_leaderboard(group_id, umo, today_str)

    async def _send_auto_leaderboard(self, group_id, umo, today_str):
        """向指定群主动推送今日壁画王图片。"""
        image_path = None
        try:
            # 发送前确保数据已按日期重置
            await self.check_reset()
            image_path = await self._render_leaderboard_image(group_id, "today")
            if not image_path or not os.path.exists(image_path):
                logger.warning(f"自动发送群 {group_id}：生成图片失败。")
                return
            chain = MessageChain().file_image(image_path)
            await self.context.send_message(umo, chain)
            # 标记当天已发送
            self._auto_send_last_sent[group_id] = today_str
            logger.info(f"已自动向群 {group_id} 发送今日壁画王。")
        except Exception as e:
            logger.error(f"自动向群 {group_id} 发送今日壁画王失败: {e}")
        finally:
            if image_path and os.path.exists(image_path):
                try:
                    os.remove(image_path)
                except OSError as cleanup_error:
                    logger.warning(f"Failed to remove temporary auto leaderboard image: {cleanup_error}")

    async def terminate(self):
        # 取消定时自动发送后台任务
        if self._auto_send_task is not None and not self._auto_send_task.done():
            self._auto_send_task.cancel()
            try:
                await self._auto_send_task
            except Exception:
                pass
        self._auto_send_started = False
        await self.save_data()
