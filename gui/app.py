from datetime import datetime
import os
import sys
from typing import Any, Dict
import customtkinter as ctk
from PIL import Image
from config import (
    APP_VERSION,
    ASSETS_DIR,
    WINDOW_MIN_HEIGHT,
    WINDOW_MIN_WIDTH,
    WINDOW_TITLE,
)
from database import db
from esp32_client import esp32_client
from gui.components.toast import ToastNotification
from gui.dashboard_view import DashboardView
from gui.employees_view import EmployeesView
from gui.fonts import font_bold, font_regular, init_fonts
from gui.payroll_view import PayrollView
from gui.settings_view import SettingsView
from http_server import attendance_server
from telegram_bot import telegram_notifier


class SmartHRApp(ctk.CTk):
    """النافذة الرئيسية لنظام الموارد البشرية وإدارة الحضور البيومتري بواجهة عربية كاملة."""

    def __init__(self):
        super().__init__()

        # تهيئة الخطوط العربية الاحترافية
        init_fonts()

        # المظهر العام
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        # خصائص النافذة
        self.title(WINDOW_TITLE)
        self.geometry(f"{WINDOW_MIN_WIDTH}x{WINDOW_MIN_HEIGHT}")
        self.minsize(1020, 680)
        self.configure(fg_color="#0B132B")

        self._set_window_icon()
        self._build_layout()
        self._start_clock_ticker()
        self._bind_server_events()

    def _set_window_icon(self):
        ico_path = os.path.join(ASSETS_DIR, "app_icon.ico")
        png_path = os.path.join(ASSETS_DIR, "app_icon.png")

        try:
            if sys.platform == "win32" and os.path.exists(ico_path):
                self.iconbitmap(ico_path)
            elif os.path.exists(png_path):
                from PIL import ImageTk
                img = Image.open(png_path)
                self.iconphoto(False, ImageTk.PhotoImage(img))
        except Exception:
            pass

    def _build_layout(self):
        # تخطيط واجهة من اليمين إلى اليسار (RTL):
        # العمود 1: القائمة الجانبية في أقصى اليمين
        # العمود 0: مساحة العرض الرئيسية في اليسار
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)

        # 1. القائمة الجانبية (Sidebar) - على اليمين للغة العربية
        self.sidebar = ctk.CTkFrame(self, width=240, corner_radius=0, fg_color="#1E293B")
        self.sidebar.grid(row=0, column=1, sticky="nsew")
        self.sidebar.grid_rowconfigure(5, weight=1)

        # عنوان وشعار المنظومة
        brand_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        brand_frame.grid(row=0, column=0, padx=16, pady=(20, 20), sticky="ew")

        brand_title = ctk.CTkLabel(
            brand_frame,
            text="نظام الحضور الذكي",
            font=font_bold(18),
            text_color="#38BDF8",
            justify="right",
        )
        brand_title.pack(anchor="e")

        brand_sub = ctk.CTkLabel(
            brand_frame,
            text=f"إدارة الموارد البشرية v{APP_VERSION}",
            font=font_regular(11),
            text_color="#94A3B8",
            justify="right",
        )
        brand_sub.pack(anchor="e")

        # أزرار التنقل الرئيسية
        self.nav_buttons: Dict[str, ctk.CTkButton] = {}
        nav_items = [
            ("dashboard", "⚡  لوحة التحكم الرئيسية", 1),
            ("employees", "👥  دليل الموظفين", 2),
            ("payroll", "💰  مسير الرواتب والحضور", 3),
            ("settings", "⚙️  إعدادات النظام", 4),
        ]

        for key, text, row_idx in nav_items:
            btn = ctk.CTkButton(
                self.sidebar,
                text=text,
                height=44,
                corner_radius=8,
                fg_color="transparent",
                text_color="#CBD5E1",
                hover_color="#334155",
                anchor="e",
                font=font_bold(13),
                command=lambda k=key: self.select_view(k),
            )
            btn.grid(row=row_idx, column=0, padx=12, pady=4, sticky="ew")
            self.nav_buttons[key] = btn

        # بطاقة حالة الاتصال السفلية في القائمة الجانبية
        status_box = ctk.CTkFrame(self.sidebar, fg_color="#0F172A", corner_radius=8)
        status_box.grid(row=6, column=0, padx=12, pady=(0, 14), sticky="sew")

        self.sidebar_hw_status = ctk.CTkLabel(
            status_box,
            text="خادم الاستماع: نشط",
            font=font_bold(11),
            text_color="#10B981",
            justify="right",
        )
        self.sidebar_hw_status.pack(padx=12, pady=(8, 2), anchor="e")

        self.clock_lbl = ctk.CTkLabel(
            status_box,
            text="--:--:--",
            font=font_regular(11),
            text_color="#64748B",
            justify="right",
        )
        self.clock_lbl.pack(padx=12, pady=(0, 8), anchor="e")

        # 2. الحاوية الرئيسية للشاشات - في اليسار
        self.main_container = ctk.CTkFrame(self, fg_color="#0F172A", corner_radius=0)
        self.main_container.grid(row=0, column=0, sticky="nsew")
        self.main_container.grid_rowconfigure(0, weight=1)
        self.main_container.grid_columnconfigure(0, weight=1)

        # تهيئة الشاشات الفرعية
        self.views: Dict[str, ctk.CTkFrame] = {
            "dashboard": DashboardView(self.main_container),
            "employees": EmployeesView(self.main_container),
            "payroll": PayrollView(self.main_container),
            "settings": SettingsView(self.main_container),
        }

        for v in self.views.values():
            v.grid(row=0, column=0, sticky="nsew")

        self.select_view("dashboard")

    def select_view(self, name: str):
        for key, btn in self.nav_buttons.items():
            if key == name:
                btn.configure(fg_color="#0284C7", text_color="#FFFFFF")
            else:
                btn.configure(fg_color="transparent", text_color="#CBD5E1")

        view = self.views.get(name)
        if view:
            view.tkraise()
            if hasattr(view, "refresh_data"):
                view.refresh_data()
            elif hasattr(view, "load_employees"):
                view.load_employees()

    def _start_clock_ticker(self):
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.clock_lbl.configure(text=now_str)

        port = db.get_setting("server_port", "8000")
        state = esp32_client.get_telemetry()
        if state.get("is_online"):
            self.sidebar_hw_status.configure(
                text="جهاز ESP32: متصل بالشبكة", text_color="#10B981"
            )
        else:
            self.sidebar_hw_status.configure(
                text=f"الخادم: المنفذ {port}", text_color="#38BDF8"
            )

        self.after(1000, self._start_clock_ticker)

    def _bind_server_events(self):
        def on_punch(meta: Dict[str, Any]):
            self.after(0, lambda: self._on_punch_main_thread(meta))

        def on_heartbeat(data: Dict[str, Any]):
            pass

        def on_bulk(count: int, punches: list):
            self.after(0, lambda: self._on_bulk_main_thread(count, punches))

        host = db.get_setting("server_host", "0.0.0.0")
        port = int(db.get_setting("server_port", "8000"))
        attendance_server.start(
            host=host,
            port=port,
            on_punch=on_punch,
            on_heartbeat=on_heartbeat,
            on_bulk=on_bulk,
        )

    def _on_punch_main_thread(self, meta: Dict[str, Any]):
        dashboard = self.views.get("dashboard")
        if isinstance(dashboard, DashboardView):
            dashboard.handle_realtime_punch(meta)
        telegram_notifier.notify_punch(meta)

    def _on_bulk_main_thread(self, count: int, punches: list):
        ToastNotification.show(
            self,
            title="مزامنة الحركات المحلية",
            message=f"تم استلام ومزامنة {count} حركة حضور مسجلة في ذاكرة الجهاز بنجاح.",
            status="info",
        )
        dashboard = self.views.get("dashboard")
        if isinstance(dashboard, DashboardView):
            dashboard.refresh_data()
