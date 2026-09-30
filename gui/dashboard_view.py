from datetime import datetime, timedelta
import tkinter as tk
from typing import Any, Dict, Optional
import customtkinter as ctk
from database import db
from esp32_client import esp32_client
from gui.components.toast import ToastNotification
from gui.fonts import font_bold, font_italic, font_regular


class DashboardView(ctk.CTkFrame):
    """لوحة التحكم والمتابعة اللحظية المباشرة لحركات الحضور والربط مع حساس البصمة."""

    def __init__(self, parent: ctk.CTk, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.parent = parent
        self.current_filter = "today"
        self._build_ui()
        self.refresh_data()
        self._start_telemetry_loop()

    def _build_ui(self):
        # 1. شريط العنوان العلوي والفلتر اللحظي
        top_bar = ctk.CTkFrame(self, fg_color="transparent")
        top_bar.pack(fill="x", padx=20, pady=(16, 12))

        # Filter Segment & Refresh (Left side)
        filter_bar = ctk.CTkFrame(top_bar, fg_color="transparent")
        filter_bar.pack(side="left")

        btn_refresh = ctk.CTkButton(
            filter_bar,
            text="🔄 تحديث البيانات",
            width=110,
            height=34,
            fg_color="#334155",
            hover_color="#475569",
            font=font_bold(12),
            command=self.refresh_data,
        )
        btn_refresh.pack(side="left", padx=(0, 10))

        self.filter_segment = ctk.CTkSegmentedButton(
            filter_bar,
            values=["اليوم", "هذا الأسبوع", "هذا الشهر"],
            command=self._on_filter_changed,
            height=34,
            font=font_bold(12),
        )
        self.filter_segment.set("اليوم")
        self.filter_segment.pack(side="left")

        # Header Titles (Right side for RTL)
        header_info = ctk.CTkFrame(top_bar, fg_color="transparent")
        header_info.pack(side="right")

        title = ctk.CTkLabel(
            header_info,
            text="⚡ لوحة المتابعة والتحكم المباشر",
            font=font_bold(20),
            text_color="#F8FAFC",
            justify="right",
        )
        title.pack(anchor="e")

        self.last_updated_lbl = ctk.CTkLabel(
            header_info,
            text="المراقبة اللحظية لنظام البصمة نشطة الآن",
            font=font_regular(12),
            text_color="#64748B",
            justify="right",
        )
        self.last_updated_lbl.pack(anchor="e")

        # 2. بطاقات الإحصاءات والمؤشرات (4 بطاقات)
        cards_grid = ctk.CTkFrame(self, fg_color="transparent")
        cards_grid.pack(fill="x", padx=20, pady=(0, 16))
        cards_grid.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="card")

        # Card 1: حالة جهاز البصمة
        self.card_hardware = self._create_hardware_card(cards_grid, col=0)
        # Card 2: بصمات غير مكتملة
        self.card_missed = self._create_metric_card(
            cards_grid, col=1, title="ورديات غير مكتملة", value="--", subtitle="نقص بصمة دخول أو خروج", icon="⚠️", accent="#F59E0B"
        )
        # Card 3: الحاضرون اليوم
        self.card_present = self._create_metric_card(
            cards_grid, col=2, title="الحاضرون اليوم", value="--", subtitle="سجلوا حضوراً فعلياً", icon="✅", accent="#10B981"
        )
        # Card 4: إجمالي الموظفين
        self.card_staff = self._create_metric_card(
            cards_grid, col=3, title="إجمالي الموظفين", value="--", subtitle="الموظفون النشطون بالدليل", icon="👥", accent="#38BDF8"
        )

        # 3. شريط وحاوية البصمات اللحظية
        stream_container = ctk.CTkFrame(self, fg_color="#1E293B", corner_radius=12)
        stream_container.pack(fill="both", expand=True, padx=20, pady=(0, 16))

        table_header = ctk.CTkFrame(stream_container, fg_color="transparent")
        table_header.pack(fill="x", padx=16, pady=(12, 8))

        self.stream_status_lbl = ctk.CTkLabel(
            table_header,
            text="خادم الاستماع نشط على المنفذ 8000...",
            font=font_bold(11),
            text_color="#10B981",
        )
        self.stream_status_lbl.pack(side="left")

        stream_title = ctk.CTkLabel(
            table_header,
            text="📡 شريط التسجيل المباشر للحضور والانصراف",
            font=font_bold(15),
            text_color="#F8FAFC",
        )
        stream_title.pack(side="right")

        # ترويسة الأعمدة
        col_headers_frame = ctk.CTkFrame(stream_container, fg_color="#0F172A", height=34, corner_radius=6)
        col_headers_frame.pack(fill="x", padx=16, pady=(0, 6))

        headers = [
            ("المصدر / التزامن", 0.12),
            ("نوع الحركة", 0.14),
            ("نظام الدوام", 0.14),
            ("اسم الموظف", 0.30),
            ("رقم البصمة", 0.10),
            ("الوقت والتاريخ", 0.20),
        ]
        for title_str, rel_w in headers:
            lbl = ctk.CTkLabel(
                col_headers_frame,
                text=title_str,
                font=font_bold(12),
                text_color="#94A3B8",
            )
            lbl.pack(side="left", fill="x", expand=True)

        # صفوف السجل القابلة للتمرير
        self.feed_scroll = ctk.CTkScrollableFrame(stream_container, fg_color="transparent")
        self.feed_scroll.pack(fill="both", expand=True, padx=16, pady=(0, 12))

    def _create_metric_card(self, parent, col, title, value, subtitle, icon, accent):
        card = ctk.CTkFrame(parent, fg_color="#1E293B", corner_radius=10, border_color="#334155", border_width=1)
        card.grid(row=0, column=col, padx=6, pady=4, sticky="nsew")

        content = ctk.CTkFrame(card, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=16, pady=14)

        top_line = ctk.CTkFrame(content, fg_color="transparent")
        top_line.pack(fill="x")

        lbl_icon = ctk.CTkLabel(top_line, text=icon, font=font_regular(16))
        lbl_icon.pack(side="left")

        lbl_title = ctk.CTkLabel(
            top_line, text=title, font=font_bold(12), text_color="#94A3B8", justify="right"
        )
        lbl_title.pack(side="right")

        lbl_val = ctk.CTkLabel(
            content, text=value, font=font_bold(26), text_color=accent, justify="right"
        )
        lbl_val.pack(anchor="e", pady=(4, 0))

        lbl_sub = ctk.CTkLabel(
            content, text=subtitle, font=font_regular(11), text_color="#64748B", justify="right"
        )
        lbl_sub.pack(anchor="e")

        card.lbl_val = lbl_val
        card.lbl_sub = lbl_sub
        return card

    def _create_hardware_card(self, parent, col):
        card = ctk.CTkFrame(parent, fg_color="#1E293B", corner_radius=10, border_color="#334155", border_width=1)
        card.grid(row=0, column=col, padx=6, pady=4, sticky="nsew")

        content = ctk.CTkFrame(card, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=16, pady=12)

        top_line = ctk.CTkFrame(content, fg_color="transparent")
        top_line.pack(fill="x")

        self.hw_status_badge = ctk.CTkLabel(
            top_line,
            text="● غير متصل",
            font=font_bold(10),
            text_color="#EF4444",
        )
        self.hw_status_badge.pack(side="left")

        lbl_title = ctk.CTkLabel(
            top_line, text="جهاز البصمة (ESP32)", font=font_bold(12), text_color="#94A3B8"
        )
        lbl_title.pack(side="right")

        self.hw_ip_lbl = ctk.CTkLabel(
            content,
            text="الجهاز غير متصل",
            font=font_bold(13),
            text_color="#F1F5F9",
            justify="right",
        )
        self.hw_ip_lbl.pack(anchor="e", pady=(4, 0))

        self.hw_meta_lbl = ctk.CTkLabel(
            content,
            text="الإشارة: -- | البصمات: 0",
            font=font_regular(11),
            text_color="#64748B",
            justify="right",
        )
        self.hw_meta_lbl.pack(anchor="e")

        return card

    def _on_filter_changed(self, choice):
        mapping = {"اليوم": "today", "هذا الأسبوع": "week", "هذا الشهر": "month"}
        self.current_filter = mapping.get(choice, "today")
        self.refresh_data()

    def refresh_data(self):
        summary = db.get_dashboard_summary()
        self.card_staff.lbl_val.configure(text=str(summary.get("total_staff", 0)))
        self.card_present.lbl_val.configure(text=str(summary.get("present_today", 0)))
        self.card_missed.lbl_val.configure(text=str(summary.get("missed_punches", 0)))

        now = datetime.now()
        if self.current_filter == "today":
            d_from = now.strftime("%Y-%m-%d")
        elif self.current_filter == "week":
            d_from = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
        else:
            d_from = now.strftime("%Y-%m-01")

        logs = db.get_attendance_logs(date_from=d_from, limit=50)
        self._populate_logs_table(logs)

        self.last_updated_lbl.configure(
            text=f"آخر تحديث: {datetime.now().strftime('%H:%M:%S')}"
        )

    def _populate_logs_table(self, logs):
        for child in self.feed_scroll.winfo_children():
            child.destroy()

        if not logs:
            empty_lbl = ctk.CTkLabel(
                self.feed_scroll,
                text="لا توجد حركات حضور مسجلة لهذه الفترة حتى الآن.",
                font=font_italic(13),
                text_color="#64748B",
            )
            empty_lbl.pack(pady=30)
            return

        for idx, log in enumerate(logs):
            bg = "#182234" if idx % 2 == 0 else "#1E293B"
            row = ctk.CTkFrame(self.feed_scroll, fg_color=bg, height=38, corner_radius=6)
            row.pack(fill="x", pady=2)

            ptype = log.get("punch_type", "IN_1")
            color_map = {
                "IN_1": ("#10B981", "#064E3B", "دخول وردية 1"),
                "OUT_1": ("#3B82F6", "#1E3A8A", "خروج وردية 1"),
                "IN_2": ("#14B8A6", "#134E4A", "دخول وردية 2"),
                "OUT_2": ("#A855F7", "#581C87", "خروج وردية 2"),
            }
            fg, border, label_text = color_map.get(ptype, ("#94A3B8", "#334155", ptype))

            # العمود 1: المصدر
            sync_txt = "⚡ مزامنة محلية" if log.get("is_offline_sync") else "🟢 مباشر عبر LAN"
            sync_col = "#F59E0B" if log.get("is_offline_sync") else "#10B981"
            ctk.CTkLabel(
                row, text=sync_txt, font=font_bold(10), text_color=sync_col
            ).pack(side="left", fill="x", expand=True)

            # العمود 2: شارة الحركة
            badge_frame = ctk.CTkFrame(row, fg_color=border, corner_radius=6, height=24)
            badge_frame.pack(side="left", fill="x", expand=True, padx=4)
            ctk.CTkLabel(
                badge_frame, text=label_text, font=font_bold(10), text_color=fg
            ).pack(padx=8, pady=2)

            # العمود 3: الدوام
            shift_raw = log.get("shift_type") or "single"
            shift_str = "دوام مفرد" if shift_raw == "single" else "دوام مزدوج"
            ctk.CTkLabel(
                row, text=shift_str, font=font_regular(11), text_color="#94A3B8"
            ).pack(side="left", fill="x", expand=True)

            # العمود 4: الاسم
            name_str = log.get("full_name") or "موظف غير معرف"
            ctk.CTkLabel(
                row, text=name_str, font=font_bold(12), text_color="#FFFFFF"
            ).pack(side="left", fill="x", expand=True)

            # العمود 5: رقم البصمة
            ctk.CTkLabel(
                row, text=f"#{log.get('fingerprint_id')}", font=font_bold(12), text_color="#38BDF8"
            ).pack(side="left", fill="x", expand=True)

            # العمود 6: الوقت
            t_str = f"{log.get('time', '')} ({log.get('date', '')})"
            ctk.CTkLabel(
                row, text=t_str, font=font_regular(11), text_color="#E2E8F0"
            ).pack(side="left", fill="x", expand=True)

    def _start_telemetry_loop(self):
        self._update_hardware_ui()
        self.after(3000, self._start_telemetry_loop)

    def _update_hardware_ui(self):
        state = esp32_client.get_telemetry()
        if state.get("is_online"):
            self.hw_status_badge.configure(text="● متصل بالشبكة", text_color="#10B981")
            self.hw_ip_lbl.configure(text=f"عنوان IP: {state.get('ip')}")
            rssi = state.get("rssi", "--")
            enrolled = state.get("enrolled_count", 0)
            fw = state.get("firmware", "5.0.0")
            self.hw_meta_lbl.configure(text=f"الإشارة: {rssi} dBm | البصمات: {enrolled} | النظام: {fw}")
        else:
            self.hw_status_badge.configure(text="● غير متصل", text_color="#EF4444")
            self.hw_ip_lbl.configure(text="الجهاز غير متاح حالياً")
            self.hw_meta_lbl.configure(text="تأكد من تشغيل ESP32 واتصاله بالشبكة")

    def handle_realtime_punch(self, punch_meta: Dict[str, Any]):
        emp = punch_meta.get("employee", {})
        name = emp.get("full_name", "موظف")
        ptype = punch_meta.get("db_punch_type", "IN_1")
        time_str = punch_meta.get("time", "")

        type_names = {
            "IN_1": "تسجيل دخول الوردية الأولى",
            "OUT_1": "تسجيل خروج الوردية الأولى",
            "IN_2": "تسجيل دخول الوردية الثانية",
            "OUT_2": "تسجيل خروج الوردية الثانية",
        }
        action_name = type_names.get(ptype, ptype)

        ToastNotification.show(
            self.parent,
            title="تم تسجيل البصمة بنجاح 🔔",
            message=f"{name} — {action_name} في تمام {time_str}",
            status="success",
            sound=True,
        )
        self.refresh_data()
