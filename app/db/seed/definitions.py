from typing import Any

ROLE_SEED: list[str] = ["admin", "user"]
ADMIN_SEED_EMAILS: list[str] = []

PLATFORM_TEMPLATES_SEED: list[dict[str, Any]] = [
    # ── 1. Dark Name Card (DesignWeekLagos) ───────────────────────────────
    {
        "title": "Dark Name Card",
        "category": "conferences",
        "canvas_data": {
            "layout_id": "dark_name_photo_v1",
            "background": {
                "type": "solid",
                "color": "#1a1a1a",
            },
            "typography": {
                "font_family": "DM Sans",
                "size_px": 42,
                "weight": "bold",
                "italic": False,
                "underline": False,
            },
            "logo": {
                "url": None,
                "public_id": None,
                "position": "top-left",
                "has_logo": True,
            },
            "fields": [
                {
                    "key": "event_name",
                    "type": "static",
                    "label": "Event Name",
                    "value": "DESIGNWEEKLAGOS",
                    "visible": True,
                },
                {
                    "key": "participant_name",
                    "type": "participant_input",
                    "label": "NAME",
                    "placeholder": "Your full name",
                    "required": True,
                    "visible": True,
                },
                {
                    "key": "role_title",
                    "type": "participant_input",
                    "label": "ROLE / TITLE",
                    "placeholder": "e.g. Product Designer",
                    "required": False,
                    "visible": True,
                },
                {
                    "key": "participant_photo",
                    "type": "participant_upload",
                    "label": "YOUR PHOTO",
                    "required": False,
                    "accepted_formats": ["jpg", "png", "webp"],
                    "max_size_mb": 5,
                    "visible": True,
                },
            ],
            "output": {"width_px": 1080, "height_px": 1350, "format": "png"},
        },
        "thumbnail_url": "https://res.cloudinary.com/dr4shcu93/image/upload/v1780184750/template_7_3x_kerhur.webp",
    },
    # ── 2. Dark Circle ────────────────────────────────────────────────────
    {
        "title": "Dark Circle",
        "category": "conferences",
        "canvas_data": {
            "layout_id": "circle_photo_dark_v1",
            "background": {
                "type": "split",
                "top_color": "#1e1e1e",
                "bottom_color": "#e0e0e0",
                "split_ratio": 0.65,
            },
            "typography": {
                "font_family": "DM Sans",
                "size_px": 38,
                "weight": "bold",
                "italic": False,
                "underline": False,
            },
            "logo": {
                "url": None,
                "public_id": None,
                "position": "top-center",
                "has_logo": True,  # ← added
            },
            "fields": [
                {
                    "key": "participant_photo",
                    "type": "participant_upload",
                    "label": "YOUR PHOTO",
                    "required": False,
                    "accepted_formats": ["jpg", "png", "webp"],
                    "max_size_mb": 5,
                    "visible": True,
                },
                {
                    "key": "participant_name",
                    "type": "participant_input",
                    "label": "NAME",
                    "placeholder": "Your full name",
                    "required": True,
                    "visible": True,
                },
                {
                    "key": "role_title",
                    "type": "participant_input",
                    "label": "ROLE / TITLE",
                    "placeholder": "e.g. Product Designer",
                    "required": False,
                    "visible": True,
                },
            ],
            "output": {"width_px": 1080, "height_px": 1350, "format": "png"},
        },
        "thumbnail_url": "https://res.cloudinary.com/dr4shcu93/image/upload/v1780184751/template_4_3x_yk8sav.webp",
    },
    # ── 3. Design Week Pink ───────────────────────────────────────────────
    {
        "title": "Design Week Pink",
        "category": "summit",
        "canvas_data": {
            "layout_id": "bold_name_pink_v1",
            "background": {
                "type": "solid",
                "color": "#f5c6d0",
            },
            "typography": {
                "font_family": "DM Sans",
                "size_px": 56,
                "weight": "bold",
                "italic": False,
                "underline": False,
            },
            "logo": {
                "url": None,
                "public_id": None,
                "position": None,
                "has_logo": False,  # ← no logo in this template
            },
            "fields": [
                {
                    "key": "participant_photo",
                    "type": "participant_upload",
                    "label": "YOUR PHOTO",
                    "required": False,
                    "accepted_formats": ["jpg", "png", "webp"],
                    "max_size_mb": 5,
                    "visible": True,
                },
                {
                    "key": "participant_name",
                    "type": "participant_input",
                    "label": "NAME",
                    "placeholder": "Your full name",
                    "required": True,
                    "visible": True,
                },
                {
                    "key": "role_title",
                    "type": "participant_input",
                    "label": "ROLE / TITLE",
                    "placeholder": "e.g. Product Designer",
                    "required": False,
                    "visible": True,
                },
                {
                    "key": "event_hashtag",
                    "type": "static",
                    "label": "Event Hashtag",
                    "value": "#DesignWeekLagos",
                    "visible": True,
                },
            ],
            "output": {"width_px": 1080, "height_px": 1350, "format": "png"},
        },
        "thumbnail_url": "https://res.cloudinary.com/dr4shcu93/image/upload/v1780184750/template_1_3x_tygy1h.webp",
    },
    # ── 4. Design Week Purple Teal ────────────────────────────────────────
    {
        "title": "Design Week Purple Teal",
        "category": "summit",
        "canvas_data": {
            "layout_id": "split_purple_teal_v1",
            "background": {
                "type": "split",
                "top_color": "#6b3fa0",
                "bottom_color": "#3ecfbf",
                "split_ratio": 0.45,
            },
            "typography": {
                "font_family": "DM Sans",
                "size_px": 42,
                "weight": "bold",
                "italic": False,
                "underline": False,
            },
            "logo": {
                "url": None,
                "public_id": None,
                "position": "top-left",
                "has_logo": True,  # ← added
            },
            "fields": [
                {
                    "key": "event_name",
                    "type": "static",
                    "label": "Event Name",
                    "value": "DESIGNWEEKLAGOS",
                    "visible": True,
                },
                {
                    "key": "participant_name",
                    "type": "participant_input",
                    "label": "NAME",
                    "placeholder": "Your full name",
                    "required": True,
                    "visible": True,
                },
                {
                    "key": "role_title",
                    "type": "participant_input",
                    "label": "ROLE / TITLE",
                    "placeholder": "e.g. Product Designer",
                    "required": False,
                    "visible": True,
                },
                {
                    "key": "participant_photo",
                    "type": "participant_upload",
                    "label": "YOUR PHOTO",
                    "required": False,
                    "accepted_formats": ["jpg", "png", "webp"],
                    "max_size_mb": 5,
                    "visible": True,
                },
            ],
            "output": {"width_px": 1080, "height_px": 1350, "format": "png"},
        },
        "thumbnail_url": "https://res.cloudinary.com/dr4shcu93/image/upload/v1780184750/template_9_3x_ngj43r.webp",
    },
]
