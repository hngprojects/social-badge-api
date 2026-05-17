import os


BADGE_DIR = os.environ.get("BADGE_DIR", "badges")


def save_image(file_buffer, filename: str) -> str:
    """
    Saves image buffer to local filesystem and returns public URL path.
    """

    # ensure directory exists
    os.makedirs(BADGE_DIR, exist_ok=True)

    filepath = os.path.join(BADGE_DIR, filename)

    # reset buffer pointer just in case
    file_buffer.seek(0)

    with open(filepath, "wb") as f:
        f.write(file_buffer.read())

    # return public URL (served by FastAPI static mount)
    return f"/badges/{filename}"