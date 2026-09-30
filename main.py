import logging
import os
import signal
import sys
from config import APPLICATION_DIR, WINDOW_TITLE
from database import db
from gui.app import SmartHRApp
from http_server import attendance_server
from telegram_bot import telegram_notifier

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (%(name)s) %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("SmartHR_Main")


def handle_shutdown(signum=None, frame=None):
    """Graceful shutdown sequence for servers and worker threads."""
    logger.info("Initiating system shutdown...")
    try:
        attendance_server.stop()
    except Exception as e:
        logger.error(f"Error stopping HTTP server: {e}")

    try:
        telegram_notifier.stop_worker()
    except Exception as e:
        logger.error(f"Error stopping Telegram worker: {e}")

    logger.info("SmartHR Attendance System terminated safely.")
    sys.exit(0)


def main():
    logger.info(f"Starting {WINDOW_TITLE}...")
    logger.info(f"Application directory: {APPLICATION_DIR}")

    # Register OS signal handlers for graceful exit
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    # Ensure database schemas and defaults are initialized
    db.init_db()

    # Launch GUI
    app = SmartHRApp()
    app.protocol("WM_DELETE_WINDOW", lambda: (app.destroy(), handle_shutdown()))

    try:
        app.mainloop()
    except KeyboardInterrupt:
        handle_shutdown()


if __name__ == "__main__":
    main()
