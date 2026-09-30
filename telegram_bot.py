import html
import logging
import queue
import threading
from datetime import datetime
from typing import Any, Dict, Optional, Tuple
import requests
from database import db

logger = logging.getLogger("TelegramNotifier")


class TelegramNotifier:
    """خادم إرسال إشعارات تيليجرام الفورية بتنسيق HTML ودعم كامل للغة العربية في خلفية النظام."""

    def __init__(self):
        self._queue: queue.Queue = queue.Queue()
        self._worker_thread: Optional[threading.Thread] = None
        self._running = False
        self.start_worker()

    def start_worker(self) -> None:
        if self._running:
            return
        self._running = True
        self._worker_thread = threading.Thread(target=self._process_queue, daemon=True)
        self._worker_thread.start()

    def _process_queue(self) -> None:
        while self._running:
            try:
                task = self._queue.get(timeout=1.0)
                if task is None:
                    break
                func, args, kwargs = task
                try:
                    func(*args, **kwargs)
                except Exception as e:
                    logger.error(f"Error executing queued telegram task: {e}")
                finally:
                    self._queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Telegram worker error: {e}")

    def stop_worker(self) -> None:
        self._running = False
        self._queue.put(None)

    def test_connection(
        self, bot_token: Optional[str] = None, chat_id: Optional[str] = None
    ) -> Tuple[bool, str]:
        token = bot_token or db.get_setting("telegram_bot_token", "")
        chat = chat_id or db.get_setting("telegram_chat_id", "")

        if not token or not chat:
            return False, "رمز البوت (Token) ومعرف المحادثة (Chat ID) لا يمكن تركهما فارغين."

        url = f"https://api.telegram.org/bot{token.strip()}/sendMessage"
        payload = {
            "chat_id": chat.strip(),
            "text": "🟢 <b>نظام الحضور والانصراف الذكي</b>\n\nتم التحقق من ربط قناة إشعارات تيليجرام بنجاح والخدمة جاهزة للعمل!",
            "parse_mode": "HTML",
        }

        try:
            resp = requests.post(url, json=payload, timeout=8)
            data = resp.json()
            if resp.status_code == 200 and data.get("ok"):
                return True, "تم إرسال رسالة الاختبار بنجاح إلى تيليجرام!"
            else:
                desc = data.get("description", "خطأ غير معروف في واجهة تيليجرام")
                return False, f"خطأ تيليجرام: {desc}"
        except requests.exceptions.Timeout:
            return False, "انتهت مهلة الاتصال بخوادم تيليجرام، تحقق من اتصال الإنترنت."
        except Exception as e:
            return False, f"تعذر الوصول لخوادم تيليجرام: {str(e)}"

    def _send_raw_message(self, text: str) -> bool:
        token = db.get_setting("telegram_bot_token", "")
        chat = db.get_setting("telegram_chat_id", "")

        if not token or not chat:
            return False

        url = f"https://api.telegram.org/bot{token.strip()}/sendMessage"
        payload = {
            "chat_id": chat.strip(),
            "text": text,
            "parse_mode": "HTML",
        }
        try:
            resp = requests.post(url, json=payload, timeout=10)
            return resp.status_code == 200 and resp.json().get("ok", False)
        except Exception as e:
            logger.error(f"Error sending Telegram message: {e}")
            return False

    def notify_punch(self, punch_meta: Dict[str, Any]) -> None:
        self._queue.put((self._dispatch_punch_alert, (punch_meta,), {}))

    def _dispatch_punch_alert(self, meta: Dict[str, Any]) -> None:
        emp = meta.get("employee", {})
        full_name = html.escape(emp.get("full_name", "موظف"))
        time_str = meta.get("time") or datetime.now().strftime("%H:%M:%S")
        date_str = meta.get("date") or datetime.now().strftime("%Y-%m-%d")
        db_type = meta.get("db_punch_type", "IN_1")
        is_offline = meta.get("is_offline_sync", 0)

        type_labels = {
            "IN_1": "تسجيل دخول الوردية الأولى",
            "OUT_1": "تسجيل خروج الوردية الأولى",
            "IN_2": "تسجيل دخول الوردية الثانية",
            "OUT_2": "تسجيل خروج الوردية الثانية",
        }
        status_label = type_labels.get(db_type, db_type)
        offline_tag = "\n<i>[⚡ تم المزامنة تلقائياً من الذاكرة المحلية للجهاز]</i>" if is_offline else ""

        message = (
            f"🔔 <b>تسجيل حضور / انصراف</b>\n\n"
            f"الموظف: <b>{full_name}</b>\n"
            f"نوع الحركة: <b>{status_label}</b>\n"
            f"الوقت: <code>{time_str}</code>\n"
            f"التاريخ: <code>{date_str}</code>"
            f"{offline_tag}"
        )
        self._send_raw_message(message)

    def send_daily_summary(self) -> None:
        self._queue.put((self._dispatch_daily_summary, (), {}))

    def _dispatch_daily_summary(self) -> None:
        summary = db.get_dashboard_summary()
        today_str = datetime.now().strftime("%Y-%m-%d")

        total = summary.get("total_staff", 0)
        present = summary.get("present_today", 0)
        incomplete = summary.get("missed_punches", 0)
        absent = max(0, total - present)

        message = (
            f"📊 <b>التقرير اليومي لإغلاق الحضور والانصراف</b>\n"
            f"التاريخ: <code>{today_str}</code>\n"
            f"────────────────────\n"
            f"👥 إجمالي الموظفين النشطين: <b>{total}</b>\n"
            f"✅ إجمالي الحاضرين: <b>{present}</b>\n"
            f"❌ إجمالي الغائبين: <b>{absent}</b>\n"
            f"⚠️ بصمات غير مكتملة: <b>{incomplete}</b>\n"
            f"────────────────────\n"
            f"<i>نظام الحضور الذكي المؤتمت</i>"
        )
        self._send_raw_message(message)

    def send_payroll_notification(self, period_label: str, total_net: float, total_staff: int) -> None:
        def _dispatch():
            message = (
                f"💰 <b>إشعار اعتماد مسير الرواتب الشهري</b>\n\n"
                f"الفترة: <b>{period_label}</b>\n"
                f"عدد الموظفين: <b>{total_staff}</b>\n"
                f"إجمالي صافي الرواتب المستحقة: <b>{total_net:,.2f}</b>\n\n"
                f"<i>تم تصدير ملف الإكسيل الرسمي وهو جاهز للصرف والمراجعة.</i>"
            )
            self._send_raw_message(message)

        self._queue.put((_dispatch, (), {}))


telegram_notifier = TelegramNotifier()
