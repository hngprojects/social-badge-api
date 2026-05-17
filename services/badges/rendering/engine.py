from PIL import Image, ImageDraw, ImageFont
import httpx
from io import BytesIO


def render_badge(profile_img_url: str) -> BytesIO:
    """Render a professional-looking certificate badge"""
    
    width, height = 1080, 1080
    
    # Create background with gradient effect (blue to darker blue)
    canvas = Image.new("RGB", (width, height), "#1a3a52")
    draw = ImageDraw.Draw(canvas)
    
    # Add a decorative gradient-like background pattern
    for i in range(height):
        color_value = 26 + int((58 - 26) * (i / height))
        draw.line([(0, i), (width, i)], fill=(color_value, int(color_value * 1.5), int(color_value * 2)))
    
    # Draw decorative border
    border_width = 8
    border_color = "#d4af37"  # Gold
    draw.rectangle(
        [(border_width, border_width), (width - border_width, height - border_width)],
        outline=border_color,
        width=border_width
    )
    
    # Second inner border
    inner_border = border_width + 10
    draw.rectangle(
        [(inner_border, inner_border), (width - inner_border, height - inner_border)],
        outline=border_color,
        width=2
    )
    
    try:
        # Load and process profile image
        res = httpx.get(profile_img_url, timeout=5)
        res.raise_for_status()
        profile = Image.open(BytesIO(res.content)).convert("RGB")
        
        # Create circular mask for profile image
        profile_size = 350
        profile = profile.resize((profile_size, profile_size), Image.Resampling.LANCZOS)
        
        # Create circular image
        mask = Image.new("L", (profile_size, profile_size), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse([(0, 0), (profile_size, profile_size)], fill=255)
        profile.putalpha(mask)
        
        # Create circular frame with gold border
        frame_size = profile_size + 20
        frame = Image.new("RGBA", (frame_size, frame_size), (0, 0, 0, 0))
        frame_draw = ImageDraw.Draw(frame)
        frame_draw.ellipse([(0, 0), (frame_size, frame_size)], fill="#d4af37")
        
        # Paste profile into frame
        frame.paste(profile, (10, 10), profile)
        
        # Convert back to RGB and paste onto canvas
        frame_rgb = frame.convert("RGB")
        canvas.paste(frame_rgb, ((width - frame_size) // 2, 250), frame)
        
    except Exception as e:
        raise RuntimeError(f"Failed to download or process profile image: {str(e)}")
    
    draw = ImageDraw.Draw(canvas)
    
    # Load a better font (use default if custom fonts not available)
    try:
        title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 72)
        subtitle_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 48)
        footer_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32)
    except:
        title_font = ImageFont.load_default()
        subtitle_font = ImageFont.load_default()
        footer_font = ImageFont.load_default()
    
    # Draw title at top
    title = "CERTIFICATE OF ACHIEVEMENT"
    title_bbox = draw.textbbox((0, 0), title, font=title_font)
    title_width = title_bbox[2] - title_bbox[0]
    draw.text(
        ((width - title_width) // 2, 80),
        title,
        fill="#d4af37",
        font=title_font
    )
    
    # Draw subtitle below profile
    subtitle = "Async Engine"
    subtitle_bbox = draw.textbbox((0, 0), subtitle, font=subtitle_font)
    subtitle_width = subtitle_bbox[2] - subtitle_bbox[0]
    draw.text(
        ((width - subtitle_width) // 2, 650),
        subtitle,
        fill="white",
        font=subtitle_font
    )
    
    # Draw footer
    footer = "HNG Internship Program"
    footer_bbox = draw.textbbox((0, 0), footer, font=footer_font)
    footer_width = footer_bbox[2] - footer_bbox[0]
    draw.text(
        ((width - footer_width) // 2, 850),
        footer,
        fill="#d4af37",
        font=footer_font
    )
    
    buffer = BytesIO()
    canvas.save(buffer, format="PNG")
    buffer.seek(0)
    
    return buffer