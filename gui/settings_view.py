import os
import threading
from tkinter import filedialog
from typing import Optional
import customtkinter as ctk
from database import db
from esp32_client import esp32_client
from gui.components.toast import ToastNotification
from gui.fonts import font_bold, font_regular
from http_server import attendance_server
from telegram_bot import telegram_notifier


class SettingsView(ctk.CTkFrame):
    """إعدادات النظام وأمان الاتصال والتحكم بجهاز البصمة وتنبيهات تيليجرام وصيانة البيانات."""

    def __init__(self, parent: ctk.CTk, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.parent = parent
        self._build_ui()
        self.load_settings()

    def _build_ui(self):
        # 1. شريط العنوان العلوي
        top_bar = ctk.CTkFrame(self, fg_color="transparent")
        top_bar.pack(fill="x", padx=20, pady=(16, 14))

        title = ctk.CTkLabel(
            top_bar,
            text="⚙️ إعدادات النظام والأجهزة والربط السحابي",
            font=font_bold(20),
            text_color="#F8FAFC",
            justify="right",
        )
        title.pack(anchor="e")

        # 2. أقسام الإعدادات القابلة للتمرير
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20, pady=(0, 16))

        # القسم 1: خادم الاستماع المحلي وأمان الاتصال
        sec1 = self._create_section(scroll, "🔒 خادم الاستماع المحلي ومفتاح الأمان (API)", "إعدادات المنفذ الداخلي لاستقبال بصمات ESP32 اللحظية.")
        
        row_srv = ctk.CTkFrame(sec1, fg_color="transparent")
        row_srv.pack(fill="x", padx=16, pady=(10, 6))

        # مهلة تكرار البصمة
        self.entry_debounce = ctk.CTkEntry(row_srv, width=70, font=font_bold(12), justify="center")
        self.entry_debounce.pack(side="left")
        ctk.CTkLabel(row_srv, text="مهلة تكرار البصمة (دقائق):", font=font_bold(12)).pack(side="left", padx=(0, 20))

        # المنفذ
        self.entry_port = ctk.CTkEntry(row_srv, width=80, font=font_bold(12), justify="center")
        self.entry_port.pack(side="left")
        ctk.CTkLabel(row_srv, text="منفذ الاستماع (Port):", font=font_bold(12)).pack(side="left", padx=(0, 20))

        # عنوان الاستماع
        self.entry_host = ctk.CTkEntry(row_srv, width=130, font=font_bold(12), justify="center")
        self.entry_host.pack(side="left")
        ctk.CTkLabel(row_srv, text="عنوان الاستماع (Host):", font=font_bold(12)).pack(side="left", padx=(0, 10))

        # مفتاح الأمان
        row_key = ctk.CTkFrame(sec1, fg_color="transparent")
        row_key.pack(fill="x", padx=16, pady=(6, 14))

        ctk.CTkLabel(row_key, text="مفتاح الأمان السري (X-API-KEY Token):", font=font_bold(12)).pack(anchor="e", pady=(0, 2))
        self.entry_key = ctk.CTkEntry(row_key, placeholder_text="esp32_super_secure_token_98765", show="•", font=font_regular(12))
        self.entry_key.pack(fill="x")

        # القسم 2: جهاز البصمة ESP32
        sec2 = self._create_section(scroll, "📡 جهاز البصمة (ESP32) والتحكم عن بُعد", "عنوان الجهاز على الشبكة واختبار التنبيه الصوتي ومصابيح الإشارة.")
        
        row_hw = ctk.CTkFrame(sec2, fg_color="transparent")
        row_hw.pack(fill="x", padx=16, pady=(10, 14))

        self.btn_test_hw = ctk.CTkButton(
            row_hw,
            text="🔔 فحص الحساس / تشغيل الجرس",
            font=font_bold(12),
            fg_color="#0284C7",
            hover_color="#0369A1",
            command=self._test_hardware_connection,
        )
        self.btn_test_hw.pack(side="left", padx=(0, 14))

        self.entry_esp_port = ctk.CTkEntry(row_hw, width=70, placeholder_text="80", font=font_bold(12), justify="center")
        self.entry_esp_port.pack(side="left", padx=(0, 8))
        ctk.CTkLabel(row_hw, text="المنفذ:", font=font_bold(12)).pack(side="left", padx=(0, 16))

        self.entry_esp_ip = ctk.CTkEntry(row_hw, width=170, placeholder_text="192.168.1.50", font=font_bold(12), justify="center")
        self.entry_esp_ip.pack(side="left", padx=(0, 8))
        ctk.CTkLabel(row_hw, text="عنوان IP للجهاز:", font=font_bold(12)).pack(side="left")

        # القسم 3: إشعارات تيليجرام
        sec3 = self._create_section(scroll, "✈️ إشعارات تيليجرام الفورية (Telegram Bot)", "إرسال تنبيهات لحظية عند كل بصمة وتقارير الإغلاق اليومي ومسير الرواتب.")
        
        row_tg = ctk.CTkFrame(sec3, fg_color="transparent")
        row_tg.pack(fill="x", padx=16, pady=(10, 6))

        ctk.CTkLabel(row_tg, text="رمز البوت (Bot Token):", font=font_bold(12)).pack(anchor="e", pady=(0, 2))
        self.entry_tg_token = ctk.CTkEntry(row_tg, placeholder_text="مثال: 123456789:ABCdefGHIjklMNOpqrs", show="•", font=font_regular(12))
        self.entry_tg_token.pack(fill="x", pady=(0, 8))

        row_chat = ctk.CTkFrame(sec3, fg_color="transparent")
        row_chat.pack(fill="x", padx=16, pady=(0, 14))

        self.btn_send_summary = ctk.CTkButton(
            row_chat,
            text="📊 إرسال ملخص اليوم فوراً",
            font=font_bold(12),
            fg_color="#334155",
            hover_color="#475569",
            command=self._send_manual_summary,
        )
        self.btn_send_summary.pack(side="left", padx=(0, 8))

        self.btn_test_tg = ctk.CTkButton(
            row_chat,
            text="📨 إرسال رسالة تجريبية",
            font=font_bold(12),
            fg_color="#10B981",
            hover_color="#059669",
            command=self._test_telegram,
        )
        self.btn_test_tg.pack(side="left", padx=(0, 12))

        self.entry_tg_chat = ctk.CTkEntry(row_chat, width=220, placeholder_text="مثال: -100123456789", font=font_bold(12), justify="center")
        self.entry_tg_chat.pack(side="left", padx=(0, 8))
        ctk.CTkLabel(row_chat, text="معرف المحادثة / القناة (Chat ID):", font=font_bold(12)).pack(side="left")

        # القسم 4: بيانات المنشأة وقاعدة البيانات
        sec4 = self._create_section(scroll, "🏢 بيانات المنشأة وصيانة قاعدة البيانات", "اسم المنشأة في التقارير الرسمية وإجراءات النسخ الاحتياطي والاستعادة.")
        
        row_co = ctk.CTkFrame(sec4, fg_color="transparent")
        row_co.pack(fill="x", padx=16, pady=(10, 10))

        ctk.CTkLabel(row_co, text="اسم المنشأة أو الشركة (يظهر في تقارير الإكسيل):", font=font_bold(12)).pack(anchor="e", pady=(0, 2))
        self.entry_company = ctk.CTkEntry(row_co, placeholder_text="نظام إدارة الموارد البشرية والحضور الذكي", font=font_bold(12), justify="right")
        self.entry_company.pack(fill="x")

        row_db = ctk.CTkFrame(sec4, fg_color="transparent")
        row_db.pack(fill="x", padx=16, pady=(0, 14))

        btn_restore = ctk.CTkButton(
            row_db,
            text="📥 استعادة قاعدة البيانات من ملف",
            font=font_bold(12),
            fg_color="#7F1D1D",
            hover_color="#991B1B",
            command=self._restore_db,
        )
        btn_restore.pack(side="left", padx=(0, 10))

        btn_backup = ctk.CTkButton(
            row_db,
            text="💾 أخذ نسخة احتياطية للبيانات",
            font=font_bold(12),
            fg_color="#334155",
            hover_color="#475569",
            command=self._backup_db,
        )
        btn_backup.pack(side="left")

        # زر الحفظ وتطبيق التغييرات
        btn_save_all = ctk.CTkButton(
            scroll,
            text="💾 حفظ وتطبيق جميع الإعدادات فوراً",
            height=44,
            fg_color="#0284C7",
            hover_color="#0369A1",
            font=font_bold(14),
            command=self.save_settings,
        )
        btn_save_all.pack(fill="x", pady=(10, 20))

    def _create_section(self, parent, title, subtitle):
        sec = ctk.CTkFrame(parent, fg_color="#1E293B", corner_radius=10, border_color="#334155", border_width=1)
        sec.pack(fill="x", pady=(0, 14))

        header = ctk.CTkFrame(sec, fg_color="#0F172A", height=38, corner_radius=8)
        header.pack(fill="x", padx=8, pady=8)

        sub = ctk.CTkLabel(header, text=subtitle, font=font_regular(11), text_color="#64748B")
        sub.pack(side="left", padx=12, pady=6)

        lbl = ctk.CTkLabel(header, text=title, font=font_bold(13), text_color="#38BDF8")
        lbl.pack(side="right", padx=12, pady=6)
        return sec

    def load_settings(self):
        settings = db.get_all_settings()
        self.entry_host.delete(0, "end")
        self.entry_host.insert(0, settings.get("server_host", "0.0.0.0"))

        self.entry_port.delete(0, "end")
        self.entry_port.insert(0, settings.get("server_port", "8000"))

        self.entry_debounce.delete(0, "end")
        self.entry_debounce.insert(0, settings.get("debounce_minutes", "3"))

        self.entry_key.delete(0, "end")
        self.entry_key.insert(0, settings.get("api_key", "esp32_super_secure_token_98765"))

        self.entry_esp_ip.delete(0, "end")
        self.entry_esp_ip.insert(0, settings.get("esp32_ip", "192.168.1.50"))

        self.entry_esp_port.delete(0, "end")
        self.entry_esp_port.insert(0, settings.get("esp32_port", "80"))

        self.entry_tg_token.delete(0, "end")
        self.entry_tg_token.insert(0, settings.get("telegram_bot_token", ""))

        self.entry_tg_chat.delete(0, "end")
        self.entry_tg_chat.insert(0, settings.get("telegram_chat_id", ""))

        self.entry_company.delete(0, "end")
        self.entry_company.insert(0, settings.get("company_name", "نظام إدارة الموارد البشرية والحضور الذكي"))

    def save_settings(self):
        host = self.entry_host.get().strip()
        port_str = self.entry_port.get().strip()
        debounce_str = self.entry_debounce.get().strip()
        api_key = self.entry_key.get().strip()
        esp_ip = self.entry_esp_ip.get().strip()
        esp_port = self.entry_esp_port.get().strip()
        tg_token = self.entry_tg_token.get().strip()
        tg_chat = self.entry_tg_chat.get().strip()
        company = self.entry_company.get().strip()

        try:
            port = int(port_str)
            debounce = float(debounce_str)
        except ValueError:
            ToastNotification.show(
                self.parent,
                title="خطأ في الإدخال",
                message="يرجى إدخال قيم عددية صحيحة لرقم المنفذ ومهلة تكرار البصمة.",
                status="error",
            )
            return

        db.set_setting("server_host", host)
        db.set_setting("server_port", str(port))
        db.set_setting("debounce_minutes", str(debounce))
        db.set_setting("api_key", api_key)
        db.set_setting("esp32_ip", esp_ip)
        db.set_setting("esp32_port", esp_port)
        db.set_setting("telegram_bot_token", tg_token)
        db.set_setting("telegram_chat_id", tg_chat)
        db.set_setting("company_name", company)

        attendance_server.restart(host=host, port=port)

        ToastNotification.show(
            self.parent,
            title="تم حفظ الإعدادات",
            message="تم حفظ جميع التعديلات وإعادة تشغيل خادم الاستماع بنجاح.",
            status="success",
        )

    def _test_hardware_connection(self):
        self.btn_test_hw.configure(state="disabled", text="⏳ جاري الفحص...")
        ToastNotification.show(
            self.parent,
            title="فحص الاتصال بجهاز البصمة",
            message=f"جاري إرسال إشارة الاختبار إلى {esp32_client.get_base_url()}...",
            status="info",
        )

        def _worker():
            success, msg = esp32_client.test_hardware()
            self.after(0, lambda: self._on_hw_tested(success, msg))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_hw_tested(self, success: bool, msg: str):
        self.btn_test_hw.configure(state="normal", text="🔔 فحص الحساس / تشغيل الجرس")
        ar_msg = "تم استلام الرد وتشغيل التنبيه الصوتي بنجاح!" if success else f"فشل الاتصال بالجهاز: {msg}"
        ToastNotification.show(
            self.parent,
            title="جهاز البصمة متصل" if success else "الجهاز غير متاح",
            message=ar_msg,
            status="success" if success else "error",
        )

    def _test_telegram(self):
        token = self.entry_tg_token.get().strip()
        chat = self.entry_tg_chat.get().strip()

        self.btn_test_tg.configure(state="disabled", text="⏳ جاري الإرسال...")

        def _worker():
            success, msg = telegram_notifier.test_connection(bot_token=token, chat_id=chat)
            self.after(0, lambda: self._on_tg_tested(success, msg))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_tg_tested(self, success: bool, msg: str):
        self.btn_test_tg.configure(state="normal", text="📨 إرسال رسالة تجريبية")
        ar_msg = "تم إرسال الإشعار التجريبي بنجاح إلى تيليجرام!" if success else f"فشل الإرسال: {msg}"
        ToastNotification.show(
            self.parent,
            title="إشعار تيليجرام" if success else "خطأ في الاتصال",
            message=ar_msg,
            status="success" if success else "error",
        )

    def _send_manual_summary(self):
        telegram_notifier.send_daily_summary()
        ToastNotification.show(
            self.parent,
            title="تم جدولة التقرير",
            message="تم إدراج تقرير إغلاق اليوم في طابور إرسال تيليجرام.",
            status="info",
        )

    def _backup_db(self):
        dest = filedialog.asksaveasfilename(
            parent=self.parent,
            title="حفظ نسخة احتياطية من قاعدة البيانات",
            defaultextension=".db",
            filetypes=[("قاعدة بيانات SQLite", "*.db *.sqlite")],
            initialfile="نسخة_احتياطية_الحضور.db",
        )
        if not dest:
            return

        try:
            ok = db.backup_database(dest)
            if ok:
                ToastNotification.show(
                    self.parent,
                    title="النسخ الاحتياطي",
                    message=f"تم حفظ النسخة الاحتياطية في: {os.path.basename(dest)}",
                    status="success",
                )
        except Exception as e:
            ToastNotification.show(
                self.parent,
                title="خطأ في النسخ الاحتياطي",
                message=f"تعذر إنشاء النسخة الاحتياطية: {str(e)}",
                status="error",
            )

    def _restore_db(self):
        src = filedialog.askopenfilename(
            parent=self.parent,
            title="اختيار ملف قاعدة البيانات للاستعادة",
            filetypes=[("قاعدة بيانات SQLite", "*.db *.sqlite")],
        )
        if not src:
            return

        try:
            ok = db.restore_database(src)
            if ok:
                self.load_settings()
                ToastNotification.show(
                    self.parent,
                    title="استعادة قاعدة البيانات",
                    message="تم استعادة قاعدة البيانات بنجاح، يُفضل إعادة تشغيل التطبيق لتحديث الجداول.",
                    status="success",
                )
        except Exception as e:
            ToastNotification.show(
                self.parent,
                title="خطأ في الاستعادة",
                message=f"تعذر استعادة قاعدة البيانات: {str(e)}",
                status="error",
            )
