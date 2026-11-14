"""Check a photo a player attaches to a treasure. Owner: A.

Plain Python with no Flask and no files, so it is easy to test.
We look at the first bytes of the file (the "magic number") instead of trusting
the file name, because a browser can send any name with any content.
"""

MAX_PHOTO_BYTES = 5 * 1024 * 1024  # 5 MB is plenty for a phone photo

# The first bytes of each picture type we accept -> the file extension we save it with
SIGNATURES = (
    (b"\xff\xd8\xff", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
)


def photo_type(data):
    """Return "jpg", "png" or "webp" for the picture bytes, or None if it is not one."""
    for start, extension in SIGNATURES:
        if data.startswith(start):
            return extension
    # WebP files start with "RIFF", four size bytes, then "WEBP"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def check_photo(data):
    """Return the extension to save the photo with, or raise ValueError."""
    if not data:
        raise ValueError("Choose a photo first")
    if len(data) > MAX_PHOTO_BYTES:
        raise ValueError(f"The photo must be at most {MAX_PHOTO_BYTES // (1024 * 1024)} MB")
    extension = photo_type(data)
    if extension is None:
        raise ValueError("The photo must be a JPG, PNG or WebP picture")
    return extension
