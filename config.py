import os
import sys

# Determine application directories
if getattr(sys, "frozen", False):
    # Running as PyInstaller compiled executable
    APPLICATION_DIR = os.path.dirname(sys.executable)
    BUNDLE_DIR = getattr(sys, "_MEIPASS", APPLICATION_DIR)
else:
    # Running as script
    APPLICATION_DIR = os.path.dirname(os.path.abspath(__file__))
    BUNDLE_DIR = APPLICATION_DIR

ASSETS_DIR = os.path.join(BUNDLE_DIR, "assets")
DATA_DIR = os.path.join(APPLICATION_DIR, "data")
EXPORTS_DIR = os.path.join(APPLICATION_DIR, "exports")

# Ensure writable runtime directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(EXPORTS_DIR, exist_ok=True)

# Database path (persisted outside temporary PyInstaller extract dir)
DB_PATH = os.path.join(DATA_DIR, "attendance.db")

# Default Hardware & Security Settings
DEFAULT_API_KEY = "esp32_super_secure_token_98765"
DEFAULT_SERVER_HOST = "0.0.0.0"
DEFAULT_SERVER_PORT = 8000
DEFAULT_ESP32_IP = "192.168.1.50"
DEFAULT_ESP32_PORT = 80
DEFAULT_DEBOUNCE_MINUTES = 3
DEFAULT_COMPANY_NAME = "نظام إدارة الموارد البشرية والحضور الذكي"

# Visual Theme Defaults
WINDOW_TITLE = "نظام الموارد البشرية وإدارة الحضور البيومتري - الإصدار الذكي"
APP_VERSION = "5.0.0"
WINDOW_MIN_WIDTH = 1120
WINDOW_MIN_HEIGHT = 740
