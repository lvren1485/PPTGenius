"""Color, font, and spacing constants for PPT generation."""

from dataclasses import dataclass
from pptx.util import Inches, Pt


@dataclass
class SlideColors:
    bg: str = "#FFFFFF"
    text: str = "#1A1A2E"
    accent: str = "#16213E"
    highlight: str = "#0F3460"


@dataclass
class SlideFonts:
    title: str = "Calibri"
    body: str = "Calibri"
    title_size: int = 36
    subtitle_size: int = 20
    body_size: int = 18


# Common measurements
SLIDE_WIDTH = Inches(13.333)
SLIDE_HEIGHT = Inches(7.5)
MARGIN_LEFT = Inches(0.8)
MARGIN_TOP = Inches(0.5)
CONTENT_WIDTH = Inches(11.5)
TITLE_TOP = Inches(0.3)
TITLE_HEIGHT = Inches(1.0)
BODY_TOP = Inches(1.5)
BODY_HEIGHT = Inches(5.5)
