import threading
from typing import Any, Callable, Dict, Optional
import customtkinter as ctk
from database import db
from esp32_client import esp32_client
from gui.components.toast import ToastNotification
from gui.fonts import font_bold, font_regular


class EmployeeModal(ctk.CTkToplevel):
    """نافذة منبثقة لإضافة أو تعديل بيانات الموظف وتسجيل البصمة البيومترية مباشرة."""

    def __init__(
        self,
        parent: ctk.CTk,
        employee_data: Optional[Dict[str, Any]] = None,
        on_saved: Optional[Callable[[], None]] = None,
    ):
        super().__init__(parent)
        self.parent = parent
        self.emp = employee_data
        self.is_edit = employee_data is not None
        self.on_saved = on_saved

        self.title("تعديل بيانات الموظف" if self.is_edit else "إضافة موظف جديد")
        self.geometry("560x700")
        self.resizable(False, False)

        self.transient(parent)
        self.grab_set()

        self.configure(fg_color="#0F172A")
        self._build_ui()

    def _build_ui(self):
        # 1. شريط العنوان العلوي
        header = ctk.CTkFrame(self, fg_color="#1E293B", height=60, corner_radius=0)
        header.pack(fill="x")
        title_text = "👤 تعديل ملف الموظف" if self.is_edit else "➕ تسجيل موظف جديد بالنظام"
        title_lbl = ctk.CTkLabel(
            header,
            text=title_text,
            font=font_bold(17),
            text_color="#38BDF8",
        )
        title_lbl.pack(padx=24, pady=16, anchor="e")

        # 2. الحاوية القابلة للتمرير
        form = ctk.CTkScrollableFrame(self, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=24, pady=14)

        # الاسم الكامل
        ctk.CTkLabel(form, text="الاسم الكامل للموظف *", font=font_bold(13)).pack(anchor="e", pady=(4, 2))
        self.name_entry = ctk.CTkEntry(
            form, placeholder_text="مثال: أحمد محمد علي", height=40, font=font_regular(12), justify="right"
        )
        self.name_entry.pack(fill="x", pady=(0, 10))
        if self.emp:
            self.name_entry.insert(0, self.emp.get("full_name", ""))

        # رقم خانة البصمة وزر التسجيل عبر الجهاز
        ctk.CTkLabel(form, text="رقم خانة البصمة بالجهاز (ID) *", font=font_bold(13)).pack(anchor="e", pady=(4, 2))
        slot_frame = ctk.CTkFrame(form, fg_color="transparent")
        slot_frame.pack(fill="x", pady=(0, 10))

        self.btn_enroll_hw = ctk.CTkButton(
            slot_frame,
            text="📡 تسجيل البصمة على الجهاز",
            height=38,
            fg_color="#0284C7",
            hover_color="#0369A1",
            font=font_bold(12),
            command=self._enroll_on_hardware,
        )
        self.btn_enroll_hw.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.btn_next_slot = ctk.CTkButton(
            slot_frame,
            text="⚡ خانة شاغرة",
            width=110,
            height=38,
            fg_color="#334155",
            hover_color="#475569",
            font=font_bold(11),
            command=self._auto_next_slot,
        )
        self.btn_next_slot.pack(side="left", padx=(0, 8))

        self.slot_entry = ctk.CTkEntry(
            slot_frame, placeholder_text="1 - 127", height=38, width=100, font=font_bold(12), justify="center"
        )
        self.slot_entry.pack(side="right")

        if self.emp:
            self.slot_entry.insert(0, str(self.emp.get("fingerprint_id", "")))
        else:
            next_slot = db.get_next_available_slot()
            self.slot_entry.insert(0, str(next_slot))

        # الراتب الأساسي واحتساب الأجر اليومي المباشر
        ctk.CTkLabel(form, text="الراتب الشهري الأساسي *", font=font_bold(13)).pack(anchor="e", pady=(4, 2))
        salary_frame = ctk.CTkFrame(form, fg_color="transparent")
        salary_frame.pack(fill="x", pady=(0, 10))

        self.daily_rate_lbl = ctk.CTkLabel(
            salary_frame,
            text="الأجر اليومي: 0.00",
            font=font_bold(12),
            text_color="#10B981",
        )
        self.daily_rate_lbl.pack(side="left", padx=(0, 10))

        self.salary_entry = ctk.CTkEntry(
            salary_frame, placeholder_text="مثال: 6000", height=40, font=font_bold(12), justify="right"
        )
        self.salary_entry.pack(side="right", fill="x", expand=True)
        if self.emp:
            self.salary_entry.insert(0, str(self.emp.get("base_salary", "")))
        self.salary_entry.bind("<KeyRelease>", self._update_daily_rate_preview)

        # عدد أيام العمل الشهرية المقررة
        ctk.CTkLabel(form, text="أيام العمل الشهرية المقررة (لحساب الراتب) *", font=font_bold(13)).pack(anchor="e", pady=(4, 2))
        self.work_days_entry = ctk.CTkEntry(
            form, placeholder_text="الافتراضي: 30 يوم", height=40, font=font_bold(12), justify="right"
        )
        self.work_days_entry.pack(fill="x", pady=(0, 10))
        if self.emp:
            self.work_days_entry.insert(0, str(self.emp.get("required_work_days", 30)))
        else:
            self.work_days_entry.insert(0, "30")
        self.work_days_entry.bind("<KeyRelease>", self._update_daily_rate_preview)
        self._update_daily_rate_preview()

        # نوع نظام الدوام
        ctk.CTkLabel(form, text="نظام الدوام والورديات *", font=font_bold(13)).pack(anchor="e", pady=(6, 2))
        self.shift_type_var = ctk.StringVar(value=self.emp.get("shift_type", "single") if self.emp else "single")
        self.shift_segment = ctk.CTkSegmentedButton(
            form,
            values=["single", "double"],
            variable=self.shift_type_var,
            command=self._toggle_shift_inputs,
            height=38,
            font=font_bold(12),
        )
        # Custom display names
        self.shift_segment.configure(
            values=["single", "double"],
        )
        self.shift_segment.pack(fill="x", pady=(0, 12))

        # توقيت الوردية الأولى
        s1_frame = ctk.CTkFrame(form, fg_color="#1E293B", corner_radius=8)
        s1_frame.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(
            s1_frame, text="مواعيد الوردية الأولى (دخول / خروج):", font=font_bold(12), text_color="#94A3B8"
        ).pack(anchor="e", padx=12, pady=(8, 4))
        
        t1_box = ctk.CTkFrame(s1_frame, fg_color="transparent")
        t1_box.pack(fill="x", padx=12, pady=(0, 8))

        self.s1_end = ctk.CTkEntry(t1_box, placeholder_text="17:00", width=100, justify="center")
        self.s1_end.pack(side="left")
        self.s1_end.insert(0, self.emp.get("shift1_end", "17:00") if self.emp else "17:00")

        ctk.CTkLabel(t1_box, text="إلى", font=font_regular(12)).pack(side="left", padx=10)

        self.s1_start = ctk.CTkEntry(t1_box, placeholder_text="09:00", width=100, justify="center")
        self.s1_start.pack(side="left")
        self.s1_start.insert(0, self.emp.get("shift1_start", "09:00") if self.emp else "09:00")

        # توقيت الوردية الثانية (للورديات المزدوجة)
        self.s2_frame = ctk.CTkFrame(form, fg_color="#1E293B", corner_radius=8)
        self.s2_frame.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(
            self.s2_frame, text="مواعيد الوردية الثانية (دخول / خروج المسائي):", font=font_bold(12), text_color="#94A3B8"
        ).pack(anchor="e", padx=12, pady=(8, 4))
        
        t2_box = ctk.CTkFrame(self.s2_frame, fg_color="transparent")
        t2_box.pack(fill="x", padx=12, pady=(0, 8))

        self.s2_end = ctk.CTkEntry(t2_box, placeholder_text="22:00", width=100, justify="center")
        self.s2_end.pack(side="left")
        self.s2_end.insert(0, (self.emp.get("shift2_end") or "22:00") if self.emp else "22:00")

        ctk.CTkLabel(t2_box, text="إلى", font=font_regular(12)).pack(side="left", padx=10)

        self.s2_start = ctk.CTkEntry(t2_box, placeholder_text="18:00", width=100, justify="center")
        self.s2_start.pack(side="left")
        self.s2_start.insert(0, (self.emp.get("shift2_start") or "18:00") if self.emp else "18:00")

        self._toggle_shift_inputs(self.shift_type_var.get())

        # حالة تفعيل الموظف
        self.status_var = ctk.IntVar(value=self.emp.get("is_active", 1) if self.emp else 1)
        self.status_switch = ctk.CTkSwitch(
            form,
            text="الموظف نشط (مسموح له بتسجيل الحضور والانصراف)",
            variable=self.status_var,
            onvalue=1,
            offvalue=0,
            font=font_bold(12),
        )
        self.status_switch.pack(anchor="e", pady=(8, 12))

        # تنبيهات وحالة التحقق
        self.feedback_lbl = ctk.CTkLabel(
            form, text="", font=font_bold(12), text_color="#EF4444", justify="right"
        )
        self.feedback_lbl.pack(anchor="e", pady=(0, 6))

        # أزرار الإجراءات السفلية
        footer = ctk.CTkFrame(self, fg_color="#1E293B", height=60, corner_radius=0)
        footer.pack(fill="x", side="bottom")

        btn_save = ctk.CTkButton(
            footer,
            text="💾 حفظ البيانات" if self.is_edit else "➕ تسجيل الموظف",
            width=150,
            height=38,
            fg_color="#10B981",
            hover_color="#059669",
            font=font_bold(13),
            command=self._save_employee,
        )
        btn_save.pack(side="left", padx=20, pady=12)

        btn_cancel = ctk.CTkButton(
            footer,
            text="إلغاء",
            width=100,
            height=38,
            fg_color="#334155",
            hover_color="#475569",
            font=font_bold(12),
            command=self.destroy,
        )
        btn_cancel.pack(side="right", padx=20, pady=12)

    def _auto_next_slot(self):
        slot = db.get_next_available_slot()
        self.slot_entry.delete(0, "end")
        self.slot_entry.insert(0, str(slot))

    def _update_daily_rate_preview(self, event=None):
        try:
            val = float(self.salary_entry.get().strip() or 0)
            d_val = float(self.work_days_entry.get().strip() or 30)
            if d_val <= 0:
                d_val = 30
            daily = round(val / d_val, 2)
            self.daily_rate_lbl.configure(text=f"الأجر اليومي: {daily:,.2f} ({int(d_val)} يوم)")
        except ValueError:
            self.daily_rate_lbl.configure(text="الأجر اليومي: 0.00")

    def _toggle_shift_inputs(self, val):
        if val == "double":
            self.s2_frame.pack(fill="x", pady=(0, 10))
        else:
            self.s2_frame.pack_forget()

    def _enroll_on_hardware(self):
        slot_str = self.slot_entry.get().strip()
        if not slot_str.isdigit():
            self.feedback_lbl.configure(
                text="يرجى إدخال رقم صحيح لخانة البصمة (من 1 إلى 127) قبل البدء."
            )
            return

        slot_id = int(slot_str)
        self.btn_enroll_hw.configure(state="disabled", text="⏳ يرجى وضع الإصبع على الحساس...")
        self.feedback_lbl.configure(
            text=f"تم إرسال أمر المسح للخانة #{slot_id}. ضع الإصبع على حساس البصمة الآن!",
            text_color="#38BDF8",
        )

        def _worker():
            success, msg = esp32_client.trigger_enrollment(slot_id)
            self.after(0, lambda: self._on_enroll_done(success, msg))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_enroll_done(self, success: bool, msg: str):
        self.btn_enroll_hw.configure(state="normal", text="📡 تسجيل البصمة على الجهاز")
        color = "#10B981" if success else "#EF4444"
        ar_msg = "تم تسجيل البصمة بنجاح في ذاكرة الجهاز!" if success else f"فشل التسجيل: {msg}"
        self.feedback_lbl.configure(text=ar_msg, text_color=color)
        ToastNotification.show(
            self.parent,
            title="تسجيل البصمة البيومترية",
            message=ar_msg,
            status="success" if success else "error",
        )

    def _save_employee(self):
        name = self.name_entry.get().strip()
        slot_str = self.slot_entry.get().strip()
        salary_str = self.salary_entry.get().strip()
        work_days_str = self.work_days_entry.get().strip() or "30"
        shift_type = self.shift_type_var.get()
        s1_start = self.s1_start.get().strip()
        s1_end = self.s1_end.get().strip()
        s2_start = self.s2_start.get().strip() if shift_type == "double" else None
        s2_end = self.s2_end.get().strip() if shift_type == "double" else None
        is_active = self.status_var.get()

        if not name:
            self.feedback_lbl.configure(text="اسم الموظف حقل إلزامي لا يمكن تركه فارغاً.")
            return

        if not slot_str.isdigit():
            self.feedback_lbl.configure(text="رقم خانة البصمة يجب أن يكون رقماً صحيحاً موجباً.")
            return
        slot_id = int(slot_str)

        try:
            salary = float(salary_str)
            if salary < 0:
                raise ValueError()
        except ValueError:
            self.feedback_lbl.configure(text="الراتب الأساسي يجب أن يكون رقماً صحيحاً وموجباً.")
            return

        try:
            req_days = int(work_days_str)
            if req_days <= 0 or req_days > 31:
                raise ValueError()
        except ValueError:
            self.feedback_lbl.configure(text="أيام العمل المقررة يجب أن تكون رقماً صحيحاً بين 1 و 31 يوماً.")
            return

        existing_with_slot = db.get_employee_by_fingerprint(slot_id)
        if existing_with_slot:
            if not self.is_edit or existing_with_slot["id"] != self.emp["id"]:
                self.feedback_lbl.configure(
                    text=f"خانة البصمة #{slot_id} مسجلة مسبقاً للموظف '{existing_with_slot['full_name']}'."
                )
                return

        try:
            if self.is_edit:
                db.update_employee(
                    emp_id=self.emp["id"],
                    fingerprint_id=slot_id,
                    full_name=name,
                    base_salary=salary,
                    shift_type=shift_type,
                    shift1_start=s1_start,
                    shift1_end=s1_end,
                    shift2_start=s2_start,
                    shift2_end=s2_end,
                    required_work_days=req_days,
                    is_active=is_active,
                )
                ToastNotification.show(
                    self.parent,
                    title="تم تحديث البيانات",
                    message=f"تم حفظ التعديلات للموظف {name} ({req_days} يوم عمل).",
                    status="success",
                )
            else:
                db.add_employee(
                    fingerprint_id=slot_id,
                    full_name=name,
                    base_salary=salary,
                    shift_type=shift_type,
                    shift1_start=s1_start,
                    shift1_end=s1_end,
                    shift2_start=s2_start,
                    shift2_end=s2_end,
                    required_work_days=req_days,
                    is_active=is_active,
                )
                ToastNotification.show(
                    self.parent,
                    title="إضافة موظف بنجاح",
                    message=f"تم تسجيل الموظف {name} بالبصمة #{slot_id} ({req_days} يوم عمل).",
                    status="success",
                )

            if self.on_saved:
                self.on_saved()
            self.destroy()
        except Exception as e:
            self.feedback_lbl.configure(text=f"خطأ في قاعدة البيانات: {str(e)}")
