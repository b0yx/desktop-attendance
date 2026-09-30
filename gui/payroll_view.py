from datetime import datetime
import os
import subprocess
import sys
from tkinter import filedialog
from typing import Any, Dict, List, Optional
import customtkinter as ctk
from database import db
from gui.components.toast import ToastNotification
from gui.fonts import font_bold, font_italic, font_regular
from payroll_engine import payroll_engine
from telegram_bot import telegram_notifier


class PayrollView(ctk.CTkFrame):
    """محرك حساب الأجور والرواتب الشهرية واستعراض سجلات الحضور وإدارة العطلات والإجازات الطارئة."""

    def __init__(self, parent: ctk.CTk, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.parent = parent
        self.calculated_data: List[Dict[str, Any]] = []

        now = datetime.now()
        self.selected_year = now.year
        self.selected_month = now.month

        self._build_ui()
        self.run_payroll_calculation()

    def _build_ui(self):
        # 1. شريط العنوان وأزرار الإجراءات
        top_bar = ctk.CTkFrame(self, fg_color="transparent")
        top_bar.pack(fill="x", padx=20, pady=(16, 12))

        # أزرار الإجراءات واختيار الفترة (الجانب الأيسر)
        controls = ctk.CTkFrame(top_bar, fg_color="transparent")
        controls.pack(side="left")

        # زر التصدير لإكسيل
        btn_export = ctk.CTkButton(
            controls,
            text="📊 تصدير إكسيل (.xlsx)",
            height=36,
            fg_color="#10B981",
            hover_color="#059669",
            font=font_bold(12),
            command=self._export_to_excel,
        )
        btn_export.pack(side="left", padx=(0, 6))

        # زر تشغيل الحساب
        btn_calc = ctk.CTkButton(
            controls,
            text="⚡ احتساب المسير",
            height=36,
            fg_color="#0284C7",
            hover_color="#0369A1",
            font=font_bold(12),
            command=self.run_payroll_calculation,
        )
        btn_calc.pack(side="left", padx=(0, 8))

        # قائمة الشهور بالعربية
        months_arabic = [
            "01 - يناير", "02 - فبراير", "03 - مارس", "04 - أبريل", "05 - مايو", "06 - يونيو",
            "07 - يوليو", "08 - أغسطس", "09 - سبتمبر", "10 - أكتوبر", "11 - نوفمبر", "12 - ديسمبر"
        ]
        self.month_menu = ctk.CTkOptionMenu(
            controls,
            values=months_arabic,
            command=self._on_period_changed,
            width=125,
            height=36,
            font=font_bold(11),
        )
        self.month_menu.set(months_arabic[self.selected_month - 1])
        self.month_menu.pack(side="left", padx=(0, 6))

        # قائمة السنوات
        current_year = datetime.now().year
        year_options = [str(y) for y in range(current_year - 2, current_year + 3)]
        self.year_menu = ctk.CTkOptionMenu(
            controls,
            values=year_options,
            command=self._on_period_changed,
            width=90,
            height=36,
            font=font_bold(11),
        )
        self.year_menu.set(str(self.selected_year))
        self.year_menu.pack(side="left")

        # عناوين القسم (الجانب الأيمن)
        title_box = ctk.CTkFrame(top_bar, fg_color="transparent")
        title_box.pack(side="right")

        title = ctk.CTkLabel(
            title_box,
            text="💰 محرك حساب الأجور ومسير الرواتب",
            font=font_bold(20),
            text_color="#F8FAFC",
            justify="right",
        )
        title.pack(anchor="e")

        sub = ctk.CTkLabel(
            title_box,
            text="دعم أيام العمل المخصصة ونظام احتساب الإجازات والعطلات الطارئة",
            font=font_regular(12),
            text_color="#64748B",
            justify="right",
        )
        sub.pack(anchor="e")

        # 2. تبويبات المسير وسجل الحركات والعطلات الطارئة
        self.tabview = ctk.CTkTabview(self, fg_color="#1E293B", corner_radius=12)
        self.tabview.pack(fill="both", expand=True, padx=20, pady=(0, 16))

        self.tab_payroll = self.tabview.add("ملخص مسير الرواتب الشهري")
        self.tab_logs = self.tabview.add("سجل حركات الحضور التفصيلي")
        self.tab_emergency = self.tabview.add("🚨 العطلات والإجازات الطارئة")

        self._build_payroll_tab()
        self._build_logs_tab()
        self._build_emergency_tab()

    def _build_payroll_tab(self):
        # شريط مؤشرات الأداء المالي (KPI)
        kpi_bar = ctk.CTkFrame(self.tab_payroll, fg_color="#0F172A", height=45, corner_radius=8)
        kpi_bar.pack(fill="x", padx=12, pady=10)

        self.lbl_kpi_net = ctk.CTkLabel(
            kpi_bar, text="صافي الرواتب المستحقة: 0.00", font=font_bold(13), text_color="#10B981"
        )
        self.lbl_kpi_net.pack(side="left", padx=16)

        self.lbl_kpi_ded = ctk.CTkLabel(
            kpi_bar, text="إجمالي الخصومات: 0.00", font=font_bold(12), text_color="#EF4444"
        )
        self.lbl_kpi_ded.pack(side="left", padx=16)

        self.lbl_kpi_sal = ctk.CTkLabel(
            kpi_bar, text="إجمالي الأساسي: 0.00", font=font_bold(12), text_color="#CBD5E1"
        )
        self.lbl_kpi_sal.pack(side="right", padx=16)

        self.lbl_kpi_staff = ctk.CTkLabel(
            kpi_bar, text="الموظفون: 0", font=font_bold(12), text_color="#38BDF8"
        )
        self.lbl_kpi_staff.pack(side="right", padx=16)

        # ترويسة أعمدة جدول الرواتب
        col_frame = ctk.CTkFrame(self.tab_payroll, fg_color="#0B132B", height=36, corner_radius=6)
        col_frame.pack(fill="x", padx=12, pady=(0, 6))

        headers = [
            ("صافي المستحق", 0.11),
            ("إجمالي الخصومات", 0.11),
            ("أيام الغياب", 0.09),
            ("أيام العمل المحتسبة", 0.10),
            ("الأجر اليومي", 0.10),
            ("أيام العمل المقررة", 0.10),
            ("الراتب الأساسي", 0.11),
            ("نظام الدوام", 0.08),
            ("اسم الموظف", 0.20),
        ]
        for title_str, rel in headers:
            lbl = ctk.CTkLabel(
                col_frame,
                text=title_str,
                font=font_bold(11),
                text_color="#94A3B8",
            )
            lbl.pack(side="left", fill="x", expand=True)

        self.payroll_scroll = ctk.CTkScrollableFrame(self.tab_payroll, fg_color="transparent")
        self.payroll_scroll.pack(fill="both", expand=True, padx=12, pady=(0, 10))

    def _build_logs_tab(self):
        filter_bar = ctk.CTkFrame(self.tab_logs, fg_color="transparent")
        filter_bar.pack(fill="x", padx=12, pady=(10, 8))

        btn_refresh_logs = ctk.CTkButton(
            filter_bar,
            text="🔄 تحديث السجل",
            width=110,
            fg_color="#334155",
            hover_color="#475569",
            font=font_bold(11),
            command=self._load_filtered_logs,
        )
        btn_refresh_logs.pack(side="left")

        self.emp_filter_menu = ctk.CTkOptionMenu(
            filter_bar,
            values=["جميع الموظفين"],
            width=180,
            font=font_bold(11),
            command=lambda _: self._load_filtered_logs(),
        )
        self.emp_filter_menu.pack(side="right", padx=(10, 0))

        ctk.CTkLabel(
            filter_bar, text="تصفية حسب الموظف:", font=font_bold(12), text_color="#E2E8F0"
        ).pack(side="right")

        col_header = ctk.CTkFrame(self.tab_logs, fg_color="#0F172A", height=34, corner_radius=6)
        col_header.pack(fill="x", padx=12, pady=(0, 6))

        for name in [
            "طريقة التسجيل", "نوع الحركة", "نظام الدوام", "اسم الموظف", "رقم البصمة", "الوقت", "التاريخ"
        ]:
            ctk.CTkLabel(
                col_header,
                text=name,
                font=font_bold(11),
                text_color="#94A3B8",
            ).pack(side="left", fill="x", expand=True)

        self.logs_scroll = ctk.CTkScrollableFrame(self.tab_logs, fg_color="transparent")
        self.logs_scroll.pack(fill="both", expand=True, padx=12, pady=(0, 10))

    def _build_emergency_tab(self):
        # 1. نموذج إضافة إجازة أو عطلة طارئة
        form_box = ctk.CTkFrame(self.tab_emergency, fg_color="#0F172A", corner_radius=10, border_color="#334155", border_width=1)
        form_box.pack(fill="x", padx=12, pady=10)

        header_bar = ctk.CTkFrame(form_box, fg_color="transparent")
        header_bar.pack(fill="x", padx=16, pady=(12, 6))

        ctk.CTkLabel(
            header_bar,
            text="🚨 تسجيل واعتماد عطلة استثنائية أو إجازة طارئة (احتسابها كدوام مدفوع)",
            font=font_bold(13),
            text_color="#38BDF8",
        ).pack(anchor="e")

        fields_row = ctk.CTkFrame(form_box, fg_color="transparent")
        fields_row.pack(fill="x", padx=16, pady=(0, 12))

        # زر الإضافة
        btn_add_em = ctk.CTkButton(
            fields_row,
            text="➕ اعتماد الإجازة",
            width=130,
            height=36,
            fg_color="#0284C7",
            hover_color="#0369A1",
            font=font_bold(12),
            command=self._save_emergency_day,
        )
        btn_add_em.pack(side="left", padx=(0, 10))

        # نوع الإجازة (مدفوعة / غير مدفوعة)
        self.em_paid_var = ctk.IntVar(value=1)
        self.em_paid_switch = ctk.CTkSwitch(
            fields_row,
            text="مدفوعة الأجر (بدون خصم)",
            variable=self.em_paid_var,
            onvalue=1,
            offvalue=0,
            font=font_bold(11),
        )
        self.em_paid_switch.pack(side="left", padx=(0, 12))

        # سبب الحالة الطارئة
        self.em_reason_entry = ctk.CTkEntry(
            fields_row, placeholder_text="سبب العطلة (مثل: أمطار غزيرة / تعليق عمل)", width=240, font=font_regular(12), justify="right"
        )
        self.em_reason_entry.pack(side="left", padx=(0, 10))

        # نطاق الإجازة (عامة لكل الموظفين أو موظف محدد)
        self.em_scope_menu = ctk.CTkOptionMenu(
            fields_row,
            values=["عامة لجميع الموظفين"],
            width=180,
            font=font_bold(11),
        )
        self.em_scope_menu.pack(side="left", padx=(0, 10))

        # التاريخ
        today_str = datetime.now().strftime("%Y-%m-%d")
        self.em_date_entry = ctk.CTkEntry(
            fields_row, placeholder_text="YYYY-MM-DD", width=110, font=font_bold(12), justify="center"
        )
        self.em_date_entry.insert(0, today_str)
        self.em_date_entry.pack(side="left")

        # 2. جدول الإجازات الطارئة المسجلة
        col_bar = ctk.CTkFrame(self.tab_emergency, fg_color="#0B132B", height=34, corner_radius=6)
        col_bar.pack(fill="x", padx=12, pady=(8, 4))

        for name in ["إجراءات", "نوع الأجر", "سبب الحالة الطارئة", "النطاق المستفيد", "التاريخ"]:
            ctk.CTkLabel(
                col_bar,
                text=name,
                font=font_bold(11),
                text_color="#94A3B8",
            ).pack(side="left", fill="x", expand=True)

        self.emergency_scroll = ctk.CTkScrollableFrame(self.tab_emergency, fg_color="transparent")
        self.emergency_scroll.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        self._load_emergency_list()

    def _save_emergency_day(self):
        d_str = self.em_date_entry.get().strip()
        reason = self.em_reason_entry.get().strip()
        scope = self.em_scope_menu.get()
        is_paid = self.em_paid_var.get()

        if not d_str or not reason:
            ToastNotification.show(
                self.parent,
                title="حقول غير مكتملة",
                message="يرجى إدخال التاريخ وسبب الإجازة الطارئة.",
                status="error",
            )
            return

        try:
            datetime.strptime(d_str, "%Y-%m-%d")
        except ValueError:
            ToastNotification.show(
                self.parent,
                title="صيغة تاريخ خاطئة",
                message="يرجى كتابة التاريخ بالصيغة الصحيحة (السنة-الشهر-اليوم).",
                status="error",
            )
            return

        emp_id = None
        if scope != "عامة لجميع الموظفين":
            try:
                emp_id = int(scope.split(" - ")[0])
            except Exception:
                pass

        try:
            db.add_emergency_day_off(
                date_str=d_str,
                reason=reason,
                employee_id=emp_id,
                is_paid=is_paid,
            )
            ToastNotification.show(
                self.parent,
                title="تم اعتماد الإجازة الطارئة",
                message=f"تم تسجيل إجازة ({reason}) لتاريخ {d_str}.",
                status="success",
            )
            self.em_reason_entry.delete(0, "end")
            self._load_emergency_list()
            self.run_payroll_calculation()
        except Exception as e:
            ToastNotification.show(
                self.parent,
                title="خطأ في الحفظ",
                message=f"تعذر تسجيل الإجازة: {str(e)}",
                status="error",
            )

    def _load_emergency_list(self):
        for child in self.emergency_scroll.winfo_children():
            child.destroy()

        # تحديث قائمة الموظفين بنطاق الإجازة
        all_emps = db.get_all_employees()
        scope_options = ["عامة لجميع الموظفين"] + [f"{e['id']} - {e['full_name']}" for e in all_emps]
        if hasattr(self, "em_scope_menu"):
            self.em_scope_menu.configure(values=scope_options)

        start_date = f"{self.selected_year:04d}-{self.selected_month:02d}-01"
        end_date = f"{self.selected_year:04d}-{self.selected_month:02d}-31"
        records = db.get_emergency_days_off(date_from=start_date, date_to=end_date)

        if not records:
            ctk.CTkLabel(
                self.emergency_scroll,
                text="لا توجد عطلات أو إجازات طارئة مسجلة في هذا الشهر.",
                font=font_italic(12),
                text_color="#64748B",
            ).pack(pady=30)
            return

        for idx, rec in enumerate(records):
            bg = "#182234" if idx % 2 == 0 else "#1E293B"
            row = ctk.CTkFrame(self.emergency_scroll, fg_color=bg, height=36, corner_radius=6)
            row.pack(fill="x", pady=2)

            btn_del = ctk.CTkButton(
                row,
                text="🗑️ حذف",
                width=65,
                height=26,
                font=font_bold(10),
                fg_color="#7F1D1D",
                hover_color="#991B1B",
                command=lambda rid=rec["id"]: self._delete_emergency_day(rid),
            )
            btn_del.pack(side="left", padx=10)

            paid_str = "مدفوعة الأجر (100%)" if rec.get("is_paid", 1) == 1 else "غير مدفوعة"
            paid_col = "#10B981" if rec.get("is_paid", 1) == 1 else "#EF4444"
            ctk.CTkLabel(row, text=paid_str, font=font_bold(11), text_color=paid_col).pack(side="left", fill="x", expand=True)

            ctk.CTkLabel(row, text=rec["reason"], font=font_regular(11), text_color="#FFFFFF").pack(side="left", fill="x", expand=True)

            target = f"الموظف: {rec.get('employee_name')}" if rec.get("employee_id") else "جميع الموظفين (عطلة للمنشأة)"
            target_col = "#F59E0B" if rec.get("employee_id") else "#38BDF8"
            ctk.CTkLabel(row, text=target, font=font_bold(11), text_color=target_col).pack(side="left", fill="x", expand=True)

            ctk.CTkLabel(row, text=rec["date"], font=font_bold(11), text_color="#E2E8F0").pack(side="left", fill="x", expand=True)

    def _delete_emergency_day(self, record_id: int):
        db.delete_emergency_day_off(record_id)
        ToastNotification.show(
            self.parent,
            title="تم الحذف",
            message="تم إلغاء الإجازة الطارئة وإعادة احتساب المسير.",
            status="info",
        )
        self._load_emergency_list()
        self.run_payroll_calculation()

    def _on_period_changed(self, _=None):
        try:
            self.selected_year = int(self.year_menu.get())
            m_str = self.month_menu.get().split(" - ")[0]
            self.selected_month = int(m_str)
        except Exception:
            pass
        if hasattr(self, "emergency_scroll"):
            self._load_emergency_list()

    def run_payroll_calculation(self):
        self._on_period_changed()
        self.calculated_data = payroll_engine.calculate_monthly_payroll(
            year=self.selected_year, month=self.selected_month
        )

        for child in self.payroll_scroll.winfo_children():
            child.destroy()

        total_base = 0.0
        total_ded = 0.0
        total_net = 0.0

        if not self.calculated_data:
            ctk.CTkLabel(
                self.payroll_scroll,
                text="لا يوجد موظفون نشطون مسجلون لاحتساب المسير.",
                font=font_italic(13),
                text_color="#64748B",
            ).pack(pady=40)
            return

        for idx, item in enumerate(self.calculated_data):
            bg = "#182234" if idx % 2 == 0 else "#1E293B"
            row = ctk.CTkFrame(self.payroll_scroll, fg_color=bg, height=38, corner_radius=6)
            row.pack(fill="x", pady=2)

            # صافي المستحق
            ctk.CTkLabel(
                row, text=f"{item['net_pay']:,.2f}", font=font_bold(12), text_color="#10B981"
            ).pack(side="left", fill="x", expand=True)

            # الخصومات
            ctk.CTkLabel(
                row, text=f"{item['total_deductions']:,.2f}", font=font_bold(11), text_color="#EF4444"
            ).pack(side="left", fill="x", expand=True)

            # أيام الغياب
            ctk.CTkLabel(
                row, text=f"{item['days_absent']} يوم", font=font_regular(11), text_color="#F59E0B"
            ).pack(side="left", fill="x", expand=True)

            # أيام العمل المحتسبة
            ctk.CTkLabel(
                row, text=f"{item['days_worked']} يوم", font=font_bold(11), text_color="#10B981"
            ).pack(side="left", fill="x", expand=True)

            # الأجر اليومي
            ctk.CTkLabel(
                row, text=f"{item['daily_salary']:,.2f}", font=font_regular(11), text_color="#CBD5E1"
            ).pack(side="left", fill="x", expand=True)

            # أيام العمل المقررة
            ctk.CTkLabel(
                row, text=f"{item['required_work_days']} يوم", font=font_bold(11), text_color="#38BDF8"
            ).pack(side="left", fill="x", expand=True)

            # الراتب الأساسي
            ctk.CTkLabel(
                row, text=f"{item['base_salary']:,.2f}", font=font_regular(11), text_color="#CBD5E1"
            ).pack(side="left", fill="x", expand=True)

            # الدوام
            shift_text = "مفرد" if item["shift_type"] == "single" else "مزدوج"
            ctk.CTkLabel(
                row, text=shift_text, font=font_regular(11), text_color="#94A3B8"
            ).pack(side="left", fill="x", expand=True)

            # الاسم ورقم البصمة
            ctk.CTkLabel(
                row,
                text=f"{item['full_name']} (#{item['fingerprint_id']})",
                font=font_bold(12),
                text_color="#FFFFFF",
            ).pack(side="left", fill="x", expand=True)

            total_base += item["base_salary"]
            total_ded += item["total_deductions"]
            total_net += item["net_pay"]

        self.lbl_kpi_staff.configure(text=f"الموظفون المسجلون: {len(self.calculated_data)}")
        self.lbl_kpi_sal.configure(text=f"إجمالي الأساسي: {total_base:,.2f}")
        self.lbl_kpi_ded.configure(text=f"إجمالي الخصومات: {total_ded:,.2f}")
        self.lbl_kpi_net.configure(text=f"صافي المستحق للصرف: {total_net:,.2f}")

        all_emps = db.get_all_employees()
        names = ["جميع الموظفين"] + [f"{e['id']} - {e['full_name']}" for e in all_emps]
        self.emp_filter_menu.configure(values=names)
        self._load_filtered_logs()

    def _load_filtered_logs(self):
        for child in self.logs_scroll.winfo_children():
            child.destroy()

        selected = self.emp_filter_menu.get()
        emp_id = None
        if selected != "جميع الموظفين":
            try:
                emp_id = int(selected.split(" - ")[0])
            except Exception:
                pass

        start_date = f"{self.selected_year:04d}-{self.selected_month:02d}-01"
        end_date = f"{self.selected_year:04d}-{self.selected_month:02d}-31"
        logs = db.get_attendance_logs(date_from=start_date, date_to=end_date, employee_id=emp_id, limit=300)

        if not logs:
            ctk.CTkLabel(
                self.logs_scroll,
                text="لا توجد حركات مسجلة للموظف المختار في هذا الشهر.",
                font=font_italic(12),
                text_color="#64748B",
            ).pack(pady=30)
            return

        punch_trans = {
            "IN_1": "دخول وردية 1",
            "OUT_1": "خروج وردية 1",
            "IN_2": "دخول وردية 2",
            "OUT_2": "خروج وردية 2",
        }

        for idx, l in enumerate(logs):
            bg = "#182234" if idx % 2 == 0 else "#1E293B"
            row = ctk.CTkFrame(self.logs_scroll, fg_color=bg, height=34, corner_radius=4)
            row.pack(fill="x", pady=1)

            sync_lbl = "مزامنة ذاكرة" if l.get("is_offline_sync") else "مباشر عبر LAN"
            ctk.CTkLabel(row, text=sync_lbl, font=font_bold(10), text_color="#F59E0B" if l.get("is_offline_sync") else "#64748B").pack(side="left", fill="x", expand=True)

            raw_ptype = l.get("punch_type", "")
            ptype_ar = punch_trans.get(raw_ptype, raw_ptype)
            ctk.CTkLabel(row, text=ptype_ar, font=font_bold(11), text_color="#10B981").pack(side="left", fill="x", expand=True)

            shift_ar = "مفرد" if l.get("shift_type") == "single" else "مزدوج"
            ctk.CTkLabel(row, text=shift_ar, font=font_regular(11), text_color="#94A3B8").pack(side="left", fill="x", expand=True)

            ctk.CTkLabel(row, text=str(l.get("full_name", "")), font=font_bold(11), text_color="#FFFFFF").pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(row, text=f"#{l.get('fingerprint_id')}", font=font_bold(11), text_color="#38BDF8").pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(row, text=str(l.get("time", "")), font=font_regular(11), text_color="#E2E8F0").pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(row, text=str(l.get("date", "")), font=font_regular(11), text_color="#E2E8F0").pack(side="left", fill="x", expand=True)

    def _export_to_excel(self):
        if not self.calculated_data:
            self.run_payroll_calculation()

        if not self.calculated_data:
            ToastNotification.show(
                self.parent,
                title="تنبيه التصدير",
                message="لا توجد بيانات مسير متاحة للتصدير حالياً.",
                status="warning",
            )
            return

        period_label = f"{self.selected_year:04d}-{self.selected_month:02d}"
        default_name = f"مسير_رواتب_{period_label}.xlsx"
        target_path = filedialog.asksaveasfilename(
            parent=self.parent,
            title="حفظ مسير الرواتب بصيغة إكسيل",
            initialfile=default_name,
            filetypes=[("مصنف إكسيل", "*.xlsx")],
        )

        if not target_path:
            return

        try:
            exported_file = payroll_engine.export_payroll_to_excel(
                payroll_data=self.calculated_data,
                year=self.selected_year,
                month=self.selected_month,
                custom_filepath=target_path,
            )

            total_net = sum(x["net_pay"] for x in self.calculated_data)
            telegram_notifier.send_payroll_notification(
                period_label=period_label,
                total_net=total_net,
                total_staff=len(self.calculated_data),
            )

            ToastNotification.show(
                self.parent,
                title="تم تصدير الإكسيل بنجاح",
                message=f"تم حفظ الملف في: {os.path.basename(exported_file)}",
                status="success",
            )

            if sys.platform == "win32":
                os.startfile(exported_file)
            elif sys.platform == "linux":
                subprocess.Popen(["xdg-open", exported_file])
        except Exception as e:
            ToastNotification.show(
                self.parent,
                title="فشل التصدير",
                message=f"حدث خطأ أثناء إنشاء ملف الإكسيل: {str(e)}",
                status="error",
            )
