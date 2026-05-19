from typing import Any

ROLE_SEED: list[str] = ["admin", "user"]
ADMIN_SEED_EMAILS: list[str] = []

_GRADIENT_OPTIONS = [
    {"colors": ["#FF6B6B", "#FF8E53"], "direction": "135deg"},  # red/orange
    {"colors": ["#2D2D6B", "#4B4BA0"], "direction": "135deg"},  # dark blue/purple
    {"colors": ["#FF3CAC", "#784BA0"], "direction": "135deg"},  # pink/purple
    {"colors": ["#1a1a1a", "#2d2d2d"], "direction": "135deg"},  # near-black
]

_SOLID_OPTIONS = [
    "#1A1A2E",  # dark navy (default)
    "#F5C518",  # yellow
    "#2ECC71",  # teal
    "#9B59B6",  # purple
    "#3498DB",  # blue
    "#000000",  # black
    "#F0F0F0",  # off-white
]


def _photo_gradient_canvas(
    event_name: str = "",
    event_date: str = "",
    gradient_index: int = 0,
) -> dict[str, Any]:
    """
    Layout: logo top-center · event date + event name · photo slot · name field.
    """
    return {
        "layout_id": "photo_gradient_v1",
        "background": {
            "type": "gradient",
            "gradient": _GRADIENT_OPTIONS[gradient_index],
            "options": _GRADIENT_OPTIONS,
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
                "value": event_date,
                "visible": bool(event_date),
            },
            {
                "key": "event_name",
                "type": "static",
                "label": "Event Name",
                "value": event_name,
                "visible": True,
            },
            {
                "key": "participant_name",
                "type": "participant_input",
                "label": "NAME",
                "placeholder": "Nickname",
                "required": True,
                "visible": True,
            },
            {
                "key": "role_title",
                "type": "participant_input",
                "label": "ROLE / TITLE",
                "placeholder": "Placeholder text",
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
    }


def _name_role_dark_canvas(
    event_name: str = "",
    solid_index: int = 0,
) -> dict[str, Any]:
    """
    Layout: logo top-right · event name · name + role · photo slot.
    """
    return {
        "layout_id": "name_role_dark_v1",
        "background": {
            "type": "solid",
            "color": _SOLID_OPTIONS[solid_index],
            "options": _SOLID_OPTIONS,
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
                "value": event_name,
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
                "placeholder": "e.g. Attendee",
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
    }


def _speaker_card_canvas(
    event_name: str = "",
    gradient_index: int = 1,
) -> dict[str, Any]:
    """
    Layout: logo top-left · event name · speaker name · talk title.
    No participant_photo — speaker identity is text-only.
    """
    return {
        "layout_id": "speaker_card_v1",
        "background": {
            "type": "gradient",
            "gradient": _GRADIENT_OPTIONS[gradient_index],
            "options": _GRADIENT_OPTIONS,
        },
        "typography": {
            "font_family": "Playfair Display",
            "size_px": 52,
            "weight": "bold",
            "italic": False,
            "underline": False,
        },
        "logo": {
            "url": None,
            "public_id": None,
            "position": "top-left",
        },
        "fields": [
            {
                "key": "event_name",
                "type": "static",
                "label": "Event",
                "value": event_name,
                "visible": True,
            },
            {
                "key": "participant_name",
                "type": "participant_input",
                "label": "SPEAKER NAME",
                "placeholder": "Full name",
                "required": True,
                "visible": True,
            },
            {
                "key": "role_title",
                "type": "participant_input",
                "label": "TALK TITLE",
                "placeholder": "e.g. The Future of Open Source",
                "required": False,
                "visible": True,
            },
        ],
        "output": {"width_px": 1080, "height_px": 1080, "format": "png"},
    }


PLATFORM_TEMPLATES_SEED: list[dict[str, Any]] = [
    # ── Festivals ──────────────────────────────────────────────────────────
    {
        "title": "Achieveher",
        "category": "festivals",
        "canvas_data": _photo_gradient_canvas(
            event_name="ACHIEVEHER SUMMIT",
            event_date="JULY 21ST",
            gradient_index=0,
        ),
        "thumbnail_url": None,
    },
    {
        "title": "Web3 Summit",
        "category": "festivals",
        "canvas_data": _photo_gradient_canvas(
            event_name="WEB3 SUMMIT",
            event_date="",
            gradient_index=0,
        ),
        "thumbnail_url": None,
    },
    # ── Hackathons ─────────────────────────────────────────────────────────
    {
        "title": "Dev Hackathon",
        "category": "hackathons",
        "canvas_data": _photo_gradient_canvas(
            event_name="DEV HACKATHON 2026",
            event_date="",
            gradient_index=2,
        ),
        "thumbnail_url": None,
    },
    {
        "title": "Builder Blitz",
        "category": "hackathons",
        "canvas_data": _name_role_dark_canvas(
            event_name="BUILDER BLITZ 2026",
            solid_index=4,
        ),
        "thumbnail_url": None,
    },
    # ── Conferences ────────────────────────────────────────────────────────
    {
        "title": "Founder's Circle",
        "category": "conferences",
        "canvas_data": _name_role_dark_canvas(
            event_name="FOUNDER'S CIRCLE",
            solid_index=0,
        ),
        "thumbnail_url": None,
    },
    {
        "title": "Men's Summit 2026",
        "category": "conferences",
        "canvas_data": _name_role_dark_canvas(
            event_name="MENS SUMMIT 2026",
            solid_index=0,
        ),
        "thumbnail_url": None,
    },
    {
        "title": "Harvesta 2026",
        "category": "conferences",
        "canvas_data": _name_role_dark_canvas(
            event_name="HARVESTA 2026",
            solid_index=5,
        ),
        "thumbnail_url": None,
    },
    {
        "title": "Reddit Summit",
        "category": "conferences",
        "canvas_data": _photo_gradient_canvas(
            event_name="REDDIT SUMMIT",
            event_date="JULY 21ST",
            gradient_index=0,
        ),
        "thumbnail_url": None,
    },
    # ── Community ──────────────────────────────────────────────────────────
    {
        "title": "Community Connect",
        "category": "community",
        "canvas_data": _photo_gradient_canvas(
            event_name="COMMUNITY CONNECT",
            event_date="",
            gradient_index=1,
        ),
        "thumbnail_url": None,
    },
    {
        "title": "Open Source Day",
        "category": "community",
        "canvas_data": _name_role_dark_canvas(
            event_name="OPEN SOURCE DAY",
            solid_index=4,
        ),
        "thumbnail_url": None,
    },
    # ── Bootcamp ───────────────────────────────────────────────────────────
    {
        "title": "Bootcamp Badge",
        "category": "bootcamp",
        "canvas_data": _name_role_dark_canvas(
            event_name="BOOTCAMP 2026",
            solid_index=0,
        ),
        "thumbnail_url": None,
    },
    {
        "title": "Graduate Cohort",
        "category": "bootcamp",
        "canvas_data": _photo_gradient_canvas(
            event_name="GRADUATE COHORT",
            event_date="",
            gradient_index=3,
        ),
        "thumbnail_url": None,
    },
    # ── Meetups ────────────────────────────────────────────────────────────
    {
        "title": "Next Gen Meetup",
        "category": "meetups",
        "canvas_data": _name_role_dark_canvas(
            event_name="NEXT GEN MEETUP",
            solid_index=2,
        ),
        "thumbnail_url": None,
    },
    {
        "title": "Meetup Connect",
        "category": "meetups",
        "canvas_data": _photo_gradient_canvas(
            event_name="MEETUP CONNECT",
            event_date="",
            gradient_index=2,
        ),
        "thumbnail_url": None,
    },
    # ── Speakers ───────────────────────────────────────────────────────────
    {
        "title": "Spark Support",
        "category": "speakers",
        "canvas_data": _speaker_card_canvas(
            event_name="SPARK SUPPORT 2026",
            gradient_index=1,
        ),
        "thumbnail_url": None,
    },
    {
        "title": "Meet Our Speaker",
        "category": "speakers",
        "canvas_data": _speaker_card_canvas(
            event_name="MEET OUR SPEAKER",
            gradient_index=0,
        ),
        "thumbnail_url": None,
    },
    {
        "title": "Keynote Speaker",
        "category": "speakers",
        "canvas_data": _speaker_card_canvas(
            event_name="KEYNOTE 2026",
            gradient_index=2,
        ),
        "thumbnail_url": None,
    },
]
