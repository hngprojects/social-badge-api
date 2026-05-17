from services.badges.rendering.engine import render_badge


def generate_badge_image(profile_img_url: str):
    return render_badge(profile_img_url)