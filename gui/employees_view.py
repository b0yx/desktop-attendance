import threading
from typing import Any, Dict, List, Optional
import customtkinter as ctk
from database import db
from esp32_client import esp32_client
from gui.components.modal import EmployeeModal
from gui.components.toast import ToastNotification
from gui.fonts import font_bold, font_italic, font_regular


class EmployeesView(ctk.CTkFrame):
    """دليل الموظفين وإدارة الهويات البيومترية وأنظمة الورديات والتحكم بأجهزة البصمة."""

    def __init__(self, parent: ctk.CTk, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.parent = parent
        self.search_term = ""
        self._build_ui()
        self.load_employees()

    def _build_ui(self):
        # 1. شريط الإجراءات العلوي
        top_bar = ctk.CTkFrame(self, fg_color="transparent")
        top_bar.pack(fill="x", padx=20, pady=(16, 14))

        # أزرار البحث والإضافة (الجانب الأيسر)
        actions_box = ctk.CTkFrame(top_bar, fg_color="transparent")
        actions_box.pack(side="left")

        btn_add = ctk.CTkButton(
            actions_box,
            text="➕ إضافة موظف جديد",
            height=36,
            fg_color="#0284C7",
            hover_color="#0369A1",
            font=font_bold(13),
            command=self._open_add_modal,
        )
        btn_add.pack(side="left", padx=(0, 10))

        self.search_entry = ctk.CTkEntry(
            actions_box,
            placeholder_text="🔍 بحث بالاسم أو رقم البصمة...",
            width=240,
            height=36,
            font=font_regular(12),
            justify="right",
        )
        self.search_entry.pack(side="left")
        self.search_entry.bind("<KeyRelease>", self._on_search_typed)

        # العنوان وعدد الموظفين (الجانب الأيمن)
        title_box = ctk.CTkFrame(top_bar, fg_color="transparent")
        title_box.pack(side="right")

        title = ctk.CTkLabel(
            title_box,
            text="👥 دليل الموظفين والربط البيومتري",
            font=font_bold(20),
            text_color="#F8FAFC",
            justify="right",
        )
        title.pack(anchor="e")

        self.count_lbl = ctk.CTkLabel(
            title_box,
            text="0 موظف مسجل في النظام",
            font=font_regular(12),
            text_color="#64748B",
            justify="right",
        )
        self.count_lbl.pack(anchor="e")

        # 2. جدول الموظفين
        table_container = ctk.CTkFrame(self, fg_color="#1E293B", corner_radius=12)
        table_container.pack(fill="both", expand=True, padx=20, pady=(0, 16))

        # ترويسة الأعمدة
        headers_frame = ctk.CTkFrame(table_container, fg_color="#0F172A", height=38, corner_radius=8)
        headers_frame.pack(fill="x", padx=14, pady=10)

        col_defs = [
            ("إجراءات وتحكم", 0.14),
            ("حالة التفعيل", 0.10),
            ("الراتب الأساسي / اليومي", 0.18),
            ("مواعيد الورديات", 0.18),
            ("نوع الدوام", 0.12),
            ("الاسم الكامل للموظف", 0.20),
            ("رقم البصمة", 0.08),
        ]
        for name, rel in col_defs:
            lbl = ctk.CTkLabel(
                headers_frame,
                text=name,
                font=font_bold(12),
                text_color="#94A3B8",
            )
            lbl.pack(side="left", fill="x", expand=True)

        # قائمة الموظفين القابلة للتمرير
        self.list_scroll = ctk.CTkScrollableFrame(table_container, fg_color="transparent")
        self.list_scroll.pack(fill="both", expand=True, padx=14, pady=(0, 12))

    def _on_search_typed(self, event=None):
        self.search_term = self.search_entry.get().strip().lower()
        self.load_employees()

    def load_employees(self):
        for child in self.list_scroll.winfo_children():
            child.destroy()

        all_emps = db.get_all_employees()

        if self.search_term:
            filtered = [
                e for e in all_emps
                if self.search_term in e["full_name"].lower()
                or self.search_term in str(e["fingerprint_id"])
            ]
        else:
            filtered = all_emps

        self.count_lbl.configure(
            text=f"إجمالي الموظفين: {len(all_emps)} موظفاً ({len(filtered)} معروض حالياً)"
        )

        if not filtered:
            empty = ctk.CTkLabel(
                self.list_scroll,
                text="لا يوجد موظفون مطابقون لمعايير البحث الحالية.",
                font=font_italic(13),
                text_color="#64748B",
            )
            empty.pack(pady=40)
            return

        for idx, emp in enumerate(filtered):
            bg = "#182234" if idx % 2 == 0 else "#1E293B"
            row = ctk.CTkFrame(self.list_scroll, fg_color=bg, height=44, corner_radius=6)
            row.pack(fill="x", pady=2)

            # العمود 1: الإجراءات (حذف، بصمة، تعديل)
            actions_frame = ctk.CTkFrame(row, fg_color="transparent")
            actions_frame.pack(side="left", fill="x", expand=True, padx=4)

            btn_del = ctk.CTkButton(
                actions_frame,
                text="🗑️",
                width=32,
                height=28,
                fg_color="#7F1D1D",
                hover_color="#991B1B",
                command=lambda eid=emp["id"], name=emp["full_name"], slot=emp["fingerprint_id"]: self._confirm_delete(eid, name, slot),
            )
            btn_del.pack(side="left", padx=2)

            btn_hw = ctk.CTkButton(
                actions_frame,
                text="📡",
                width=32,
                height=28,
                fg_color="#0369A1",
                hover_color="#0284C7",
                command=lambda slot=emp["fingerprint_id"], name=emp["full_name"]: self._quick_enroll(slot, name),
            )
            btn_hw.pack(side="left", padx=2)

            btn_edit = ctk.CTkButton(
                actions_frame,
                text="✏️",
                width=32,
                height=28,
                fg_color="#334155",
                hover_color="#475569",
                command=lambda e=emp: self._open_edit_modal(e),
            )
            btn_edit.pack(side="left", padx=2)

            # العمود 2: حالة التفعيل
            is_active = emp["is_active"] == 1
            st_text = "نشط" if is_active else "معطل"
            st_fg = "#065F46" if is_active else "#374151"
            st_col = "#34D399" if is_active else "#9CA3AF"

            btn_status = ctk.CTkButton(
                row,
                text=st_text,
                width=65,
                height=26,
                fg_color=st_fg,
                text_color=st_col,
                font=font_bold(11),
                command=lambda eid=emp["id"]: self._toggle_status(eid),
            )
            btn_status.pack(side="left", fill="x", expand=True, padx=4)

            # العمود 3: الراتب وأيام العمل المقررة
            base_s = float(emp["base_salary"])
            req_days = int(emp.get("required_work_days") or 30)
            daily_s = float(emp.get("daily_salary") or (base_s / req_days))
            sal_str = f"{base_s:,.0f} ({req_days}يوم | {daily_s:,.1f}/يوم)"
            ctk.CTkLabel(
                row, text=sal_str, font=font_bold(11), text_color="#10B981"
            ).pack(side="left", fill="x", expand=True)

            # العمود 4: مواعيد الورديات
            shift_type = emp.get("shift_type", "single")
            s1 = f"{emp.get('shift1_start') or '09:00'}-{emp.get('shift1_end') or '17:00'}"
            if shift_type == "double":
                s2 = f" | {emp.get('shift2_start') or '18:00'}-{emp.get('shift2_end') or '22:00'}"
                windows_str = s1 + s2
            else:
                windows_str = s1
            ctk.CTkLabel(
                row, text=windows_str, font=font_regular(11), text_color="#94A3B8"
            ).pack(side="left", fill="x", expand=True)

            # العمود 5: نوع الدوام
            shift_badge = "مفرد (2 بصمات)" if shift_type == "single" else "مزدوج (4 بصمات)"
            ctk.CTkLabel(
                row, text=shift_badge, font=font_regular(11), text_color="#CBD5E1"
            ).pack(side="left", fill="x", expand=True)

            # العمود 6: الاسم الكامل
            name_lbl = ctk.CTkLabel(
                row,
                text=emp["full_name"],
                font=font_bold(12),
                text_color="#FFFFFF" if emp["is_active"] else "#94A3B8",
            )
            name_lbl.pack(side="left", fill="x", expand=True)

            # العمود 7: رقم البصمة
            ctk.CTkLabel(
                row,
                text=f"#{emp['fingerprint_id']}",
                font=font_bold(12),
                text_color="#38BDF8",
            ).pack(side="left", fill="x", expand=True)

    def _open_add_modal(self):
        EmployeeModal(self.parent, employee_data=None, on_saved=self.load_employees)

    def _open_edit_modal(self, emp: Dict[str, Any]):
        EmployeeModal(self.parent, employee_data=emp, on_saved=self.load_employees)

    def _toggle_status(self, emp_id: int):
        new_st = db.toggle_employee_active(emp_id)
        status_label = "تفعيل الموظف بنجاح" if new_st == 1 else "تعطيل الموظف عن تسجيل الحضور"
        ToastNotification.show(
            self.parent,
            title="تحديث حالة الموظف",
            message=status_label,
            status="info",
        )
        self.load_employees()

    def _quick_enroll(self, slot_id: int, name: str):
        ToastNotification.show(
            self.parent,
            title="تسجيل البصمة البيومترية",
            message=f"تم إرسال أمر المسح للموظف {name} (خانة #{slot_id}). ضع الإصبع على الحساس الآن!",
            status="info",
        )

        def _worker():
            success, msg = esp32_client.trigger_enrollment(slot_id)
            ar_msg = f"تم تسجيل بصمة {name} بنجاح!" if success else f"تعذر التسجيل: {msg}"
            self.after(
                0,
                lambda: ToastNotification.show(
                    self.parent,
                    title="اكتمال التسجيل" if success else "فشل مسح البصمة",
                    message=ar_msg,
                    status="success" if success else "error",
                ),
            )

        threading.Thread(target=_worker, daemon=True).start()

    def _confirm_delete(self, emp_id: int, name: str, slot_id: int):
        dialog = ctk.CTkToplevel(self.parent)
        dialog.title("تأكيد حذف الموظف")
        dialog.geometry("440x220")
        dialog.resizable(False, False)
        dialog.transient(self.parent)
        dialog.grab_set()
        dialog.configure(fg_color="#0F172A")

        ctk.CTkLabel(
            dialog,
            text="⚠️ تأكيد حذف سجل الموظف",
            font=font_bold(16),
            text_color="#EF4444",
        ).pack(pady=(20, 8))

        ctk.CTkLabel(
            dialog,
            text=f"هل أنت متأكد من رغبتك في حذف الموظف '{name}' (خانة #{slot_id})؟\n"
            "سيتم حذف سجلات الحضور الخاصة به، ويمكنك تفريغ قالب البصمة من حساس ESP32.",
            wraplength=380,
            justify="center",
            font=font_regular(12),
            text_color="#E2E8F0",
        ).pack(pady=(0, 16))

        btn_box = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_box.pack()

        def do_delete(del_from_hw: bool = False):
            db.delete_employee(emp_id)
            if del_from_hw:
                threading.Thread(
                    target=lambda: esp32_client.delete_fingerprint(slot_id), daemon=True
                ).start()

            dialog.destroy()
            ToastNotification.show(
                self.parent,
                title="تم الحذف",
                message=f"تم حذف الموظف {name} من قاعدة البيانات.",
                status="warning",
            )
            self.load_employees()

        ctk.CTkButton(
            btn_box,
            text="إلغاء",
            width=90,
            font=font_bold(12),
            fg_color="#334155",
            hover_color="#475569",
            command=dialog.destroy,
        ).pack(side="right", padx=6)

        ctk.CTkButton(
            btn_box,
            text="حذف وحذف من الجهاز",
            width=160,
            font=font_bold(12),
            fg_color="#991B1B",
            hover_color="#7F1D1D",
            command=lambda: do_delete(del_from_hw=True),
        ).pack(side="left", padx=6)
