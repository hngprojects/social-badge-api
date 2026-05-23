from typing import Any

ROLE_SEED: list[str] = ["admin", "user"]
ADMIN_SEED_EMAILS: list[str] = []

PLATFORM_TEMPLATES_SEED: list[dict[str, Any]] = [
    # ── 1. Achieveher ─────────────────────────────────────────────────────
    {
        "title": "Achieveher",
        "category": "summit",
        "canvas_data": {
            "layout_id": "photo_gradient_v1",
            "background": {
                "type": "gradient",
                "gradient": {
                    "colors": ["#FF6B6B", "#FF8E53"],
                    "direction": "135deg",
                },
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
                "position": "top-center",
            },
            "fields": [
                {
                    "key": "event_date",
                    "type": "static",
                    "label": "Event Date",
                    "value": "JULY 21ST",
                    "visible": True,
                },
                {
                    "key": "event_location",
                    "type": "static",
                    "label": "Location",
                    "value": "ATLANTA",
                    "visible": True,
                },
                {
                    "key": "event_name",
                    "type": "static",
                    "label": "Event Name",
                    "value": "ACHIEVEHER SUMMIT",
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
                {
                    "key": "participant_name",
                    "type": "participant_input",
                    "label": "NAME",
                    "placeholder": "Your name",
                    "required": True,
                    "visible": True,
                },
            ],
            "output": {"width_px": 1080, "height_px": 1350, "format": "png"},
        },
        "thumbnail_url": "https://res.cloudinary.com/dr4shcu93/image/upload/v1779387600/fc41ebe7642dccf7907c36811f194b1d7a6f41c8_ftqoqi.png",
    },
    # ── 2. Dev Summit ─────────────────────────────────────────────────────
    {
        "title": "Dev Summit",
        "category": "conferences",
        "canvas_data": {
            "layout_id": "name_role_dark_v2",
            "background": {
                "type": "solid",
                "color": "#1A1A2E",
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
                "position": "top-right",
            },
            "fields": [
                {
                    "key": "event_name",
                    "type": "static",
                    "label": "Event Name",
                    "value": "DEV / SUMMIT",
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
                {
                    "key": "participant_name",
                    "type": "participant_input",
                    "label": "YOUR NAME",
                    "placeholder": "Your full name",
                    "required": True,
                    "visible": True,
                },
            ],
            "output": {"width_px": 1080, "height_px": 1350, "format": "png"},
        },
        "thumbnail_url": "https://res.cloudinary.com/dr4shcu93/image/upload/v1779387599/4f74e263830f11168b54d90e85dfa8642808d5c0_u6zjim.png",
    },
    # ── 3. Men's Summit ───────────────────────────────────────────────────
    {
        "title": "Men's Summit",
        "category": "conferences",
        "canvas_data": {
            "layout_id": "name_role_dark_v1",
            "background": {
                "type": "solid",
                "color": "#2D2D6B",
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
                "position": "top-right",
            },
            "fields": [
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
                    "placeholder": "e.g. Attendee",
                    "required": False,
                    "visible": True,
                },
                {
                    "key": "event_name",
                    "type": "static",
                    "label": "Event Name",
                    "value": "MENS SUMMIT 2026",
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
        "thumbnail_url": "https://res.cloudinary.com/dr4shcu93/image/upload/v1779387599/524ee616a511b354daeef77e6c4e4a0505e6fadb_e2qf7q.png",
    },
    # ── 4. Next Gen ───────────────────────────────────────────────────────
    {
        "title": "Next Gen",
        "category": "conferences",
        "canvas_data": {
            "layout_id": "next_gen_mint_v1",
            "background": {
                "type": "solid",
                "color": "#C8E6C9",
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
            },
            "fields": [
                {
                    "key": "event_name",
                    "type": "static",
                    "label": "Event Name",
                    "value": "NEXT GEN MEETUP",
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
                {
                    "key": "event_date",
                    "type": "participant_input",
                    "label": "Date",
                    "placeholder": "Date",
                    "required": False,
                    "visible": True,
                },
                {
                    "key": "event_time",
                    "type": "participant_input",
                    "label": "Time",
                    "placeholder": "Time",
                    "required": False,
                    "visible": True,
                },
                {
                    "key": "job_description",
                    "type": "participant_input",
                    "label": "Job Description",
                    "placeholder": "Job Description",
                    "required": False,
                    "visible": True,
                },
            ],
            "output": {"width_px": 1080, "height_px": 1350, "format": "png"},
        },
        "thumbnail_url": "https://res.cloudinary.com/dr4shcu93/image/upload/v1779387600/dce59118d742acfad384892ad4119a55c6bd74b6_i9ouot.png",
    },
]
