import os
import sys
import threading
import tkinter as tk
import customtkinter as ctk
from config import ASSETS_DIR
from gui.fonts import font_bold, font_regular


class ToastNotification:
    """إشعار منبثق فوري غير معطل للواجهة مع تنبيه صوتي للحركات والعمليات."""

    @staticmethod
    def play_chime():
        """تشغيل نغمة التأكيد بنجاح صوتياً على مختلف الأنظمة."""
        wav_path = os.path.join(ASSETS_DIR, "chime.wav")
        try:
            if sys.platform == "win32":
                import winsound
                winsound.PlaySound(wav_path, winsound.SND_ASYNC | winsound.SND_FILENAME)
            else:
                def _play():
                    if os.system(f"paplay '{wav_path}' 2>/dev/null") != 0:
                        os.system(f"aplay -q '{wav_path}' 2>/dev/null")
                threading.Thread(target=_play, daemon=True).start()
        except Exception:
            pass

    @classmethod
    def show(
        cls,
        parent: ctk.CTk,
        title: str,
        message: str,
        status: str = "success",
        duration_ms: int = 4000,
        sound: bool = True,
    ):
        """
        عرض إشعار عائم في أسفل يسار أو يمين النافذة باللغة العربية.
        status: 'success' | 'info' | 'warning' | 'error'
        """
        if sound:
            cls.play_chime()

        colors = {
            "success": ("#10B981", "#064E3B", "🔔"),
            "info": ("#3B82F6", "#1E3A8A", "ℹ️"),
            "warning": ("#F59E0B", "#78350F", "⏳"),
            "error": ("#EF4444", "#7F1D1D", "⚠️"),
        }
        accent, bg_dark, icon = colors.get(status, colors["info"])

        toast_frame = ctk.CTkFrame(
            parent,
            fg_color="#1E293B",
            border_color=accent,
            border_width=2,
            corner_radius=10,
        )

        content_layout = ctk.CTkFrame(toast_frame, fg_color="transparent")
        content_layout.pack(padx=16, pady=10, fill="both", expand=True)

        header_layout = ctk.CTkFrame(content_layout, fg_color="transparent")
        header_layout.pack(fill="x", anchor="e")

        title_label = ctk.CTkLabel(
            header_layout,
            text=title,
            font=font_bold(13),
            text_color=accent,
            justify="right",
        )
        title_label.pack(side="right")

        icon_label = ctk.CTkLabel(
            header_layout,
            text=icon,
            font=font_regular(14),
            text_color=accent,
        )
        icon_label.pack(side="right", padx=(6, 0))

        msg_label = ctk.CTkLabel(
            content_layout,
            text=message,
            font=font_regular(12),
            text_color="#F1F5F9",
            wraplength=340,
            justify="right",
        )
        msg_label.pack(anchor="e", pady=(4, 0))

        # Place toast near bottom left
        toast_frame.place(relx=0.03, rely=0.96, anchor="sw")

        def destroy():
            try:
                toast_frame.destroy()
            except Exception:
                pass

        parent.after(duration_ms, destroy)
