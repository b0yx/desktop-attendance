import os
import sys
import tkinter.font as tkfont
import customtkinter as ctk
from config import ASSETS_DIR

# Global font family name detected
ARABIC_FONT_FAMILY = "Noto Kufi Arabic"

def init_fonts():
    """Load bundled professional Arabic fonts into CustomTkinter and Tkinter."""
    global ARABIC_FONT_FAMILY
    fonts_dir = os.path.join(ASSETS_DIR, "fonts")
    
    # Attempt to load bundled TTF files
    ttf_files = [
        "NotoKufiArabic-Regular.ttf",
        "NotoKufiArabic-Bold.ttf",
        "NotoSansArabic-Regular.ttf",
        "NotoSansArabic-Bold.ttf",
    ]
    
    for f in ttf_files:
        p = os.path.join(fonts_dir, f)
        if os.path.exists(p):
            try:
                ctk.FontManager.load_font(p)
            except Exception:
                pass

    # Detect the best available font family
    try:
        available = [fam.lower() for fam in tkfont.families()]
        if "noto kufi arabic" in available:
            ARABIC_FONT_FAMILY = "Noto Kufi Arabic"
        elif "cairo" in available:
            ARABIC_FONT_FAMILY = "Cairo"
        elif "noto sans arabic" in available:
            ARABIC_FONT_FAMILY = "Noto Sans Arabic"
        elif "segoe ui" in available:
            ARABIC_FONT_FAMILY = "Segoe UI"
        elif "tahoma" in available:
            ARABIC_FONT_FAMILY = "Tahoma"
        else:
            ARABIC_FONT_FAMILY = "Arial"
    except Exception:
        ARABIC_FONT_FAMILY = "Noto Kufi Arabic"

def font_regular(size: int = 12) -> ctk.CTkFont:
    """Return regular Arabic UI font."""
    return ctk.CTkFont(family=ARABIC_FONT_FAMILY, size=size, weight="normal")

def font_bold(size: int = 12) -> ctk.CTkFont:
    """Return bold Arabic UI font."""
    return ctk.CTkFont(family=ARABIC_FONT_FAMILY, size=size, weight="bold")

def font_italic(size: int = 12) -> ctk.CTkFont:
    """Return italicized Arabic UI font."""
    return ctk.CTkFont(family=ARABIC_FONT_FAMILY, size=size, slant="italic")
