import warnings

from PIL import Image

# Sets the process-wide decompression bomb pixel limit.
# Imported by app/main.py before any router is loaded, and directly by
# badge_renderer.py as a belt-and-suspenders guard.
Image.MAX_IMAGE_PIXELS = 50_000_000

# Promote DecompressionBombWarning to an error so that images in the
# 50M–100M pixel range (which only warn by default) fail closed.
warnings.filterwarnings("error", category=Image.DecompressionBombWarning)
