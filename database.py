import os
import shutil
import sqlite3
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from config import (
    DB_PATH,
    DEFAULT_API_KEY,
    DEFAULT_COMPANY_NAME,
    DEFAULT_DEBOUNCE_MINUTES,
    DEFAULT_ESP32_IP,
    DEFAULT_ESP32_PORT,
    DEFAULT_SERVER_HOST,
    DEFAULT_SERVER_PORT,
)


class DatabaseManager:
    """إدارة قاعدة بيانات SQLite3 بنمط WAL Mode لضمان التزامن السلس بين السيرفر والواجهة."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._lock = threading.RLock()
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        """إنشاء وتكوين اتصال آمن مع تفعيل WAL Mode ومؤقت الانتظار."""
        conn = sqlite3.connect(
            self.db_path,
            timeout=15.0,
            check_same_thread=False,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA busy_timeout = 10000;")
        return conn

    def init_db(self) -> None:
        """إنشاء الجداول والفهارس والإعدادات الافتراضية مع الترقية التلقائية للهيكل."""
        with self._lock, self.get_connection() as conn:
            cursor = conn.cursor()

            # 1. جدول الموظفين
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS employees (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fingerprint_id INTEGER UNIQUE NOT NULL,
                    full_name TEXT NOT NULL,
                    base_salary REAL NOT NULL,
                    shift_type TEXT CHECK(shift_type IN ('single', 'double')) DEFAULT 'single',
                    shift1_start TIME DEFAULT '09:00',
                    shift1_end TIME DEFAULT '17:00',
                    shift2_start TIME DEFAULT '18:00',
                    shift2_end TIME DEFAULT '22:00',
                    required_work_days INTEGER DEFAULT 30,
                    is_active INTEGER DEFAULT 1
                );
                """
            )

            # الترقية التلقائية إذا كان العمود required_work_days غير موجود
            cursor.execute("PRAGMA table_info(employees);")
            columns = [row["name"] for row in cursor.fetchall()]
            if "required_work_days" not in columns:
                cursor.execute(
                    "ALTER TABLE employees ADD COLUMN required_work_days INTEGER DEFAULT 30;"
                )

            # 2. جدول سجلات حركات الحضور والانصراف
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS attendance_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fingerprint_id INTEGER NOT NULL,
                    employee_id INTEGER REFERENCES employees(id) ON DELETE CASCADE,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    date DATE NOT NULL,
                    time TIME NOT NULL,
                    punch_type TEXT CHECK(punch_type IN ('IN_1', 'OUT_1', 'IN_2', 'OUT_2')),
                    is_offline_sync INTEGER DEFAULT 0
                );
                """
            )

            # 3. جدول أيام العطلات الطارئة والاستثنائية الرسمية
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS emergency_days_off (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date DATE NOT NULL,
                    reason TEXT NOT NULL,
                    employee_id INTEGER REFERENCES employees(id) ON DELETE CASCADE,
                    is_paid INTEGER DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

            # 4. جدول الإعدادات العامة
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
                """
            )

            # الفهارس لتسريع الاستعلامات
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_emp_fingerprint ON employees(fingerprint_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_date ON attendance_logs(date);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_emp_date ON attendance_logs(employee_id, date);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON attendance_logs(timestamp);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_emergency_date ON emergency_days_off(date);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_emergency_emp ON emergency_days_off(employee_id);")

            # تعيين الإعدادات الافتراضية
            default_settings = {
                "api_key": DEFAULT_API_KEY,
                "server_host": DEFAULT_SERVER_HOST,
                "server_port": str(DEFAULT_SERVER_PORT),
                "esp32_ip": DEFAULT_ESP32_IP,
                "esp32_port": str(DEFAULT_ESP32_PORT),
                "telegram_bot_token": "",
                "telegram_chat_id": "",
                "debounce_minutes": str(DEFAULT_DEBOUNCE_MINUTES),
                "company_name": DEFAULT_COMPANY_NAME,
            }

            for key, val in default_settings.items():
                cursor.execute(
                    "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?);",
                    (key, val),
                )

            conn.commit()

    # ==================== SETTINGS METHODS ====================

    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with self._lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row["value"] if row else default

    def set_setting(self, key: str, value: Any) -> None:
        with self._lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, str(value)),
            )
            conn.commit()

    def get_all_settings(self) -> Dict[str, str]:
        with self._lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM settings")
            return {row["key"]: row["value"] for row in cursor.fetchall()}

    # ==================== EMPLOYEE METHODS ====================

    def _format_emp_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        """Format an employee row and dynamically calculate daily salary."""
        data = dict(row)
        req_days = data.get("required_work_days") or 30
        if req_days <= 0:
            req_days = 30
        data["required_work_days"] = req_days
        base_s = float(data.get("base_salary") or 0.0)
        data["daily_salary"] = round(base_s / req_days, 2)
        return data

    def add_employee(
        self,
        fingerprint_id: int,
        full_name: str,
        base_salary: float,
        shift_type: str = "single",
        shift1_start: str = "09:00",
        shift1_end: str = "17:00",
        shift2_start: Optional[str] = None,
        shift2_end: Optional[str] = None,
        required_work_days: int = 30,
        is_active: int = 1,
    ) -> int:
        req_days = int(required_work_days) if required_work_days and int(required_work_days) > 0 else 30
        with self._lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO employees (
                    fingerprint_id, full_name, base_salary, shift_type,
                    shift1_start, shift1_end, shift2_start, shift2_end,
                    required_work_days, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(fingerprint_id),
                    full_name.strip(),
                    float(base_salary),
                    shift_type,
                    shift1_start or "09:00",
                    shift1_end or "17:00",
                    shift2_start if shift_type == "double" else None,
                    shift2_end if shift_type == "double" else None,
                    req_days,
                    int(is_active),
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def update_employee(
        self,
        emp_id: int,
        fingerprint_id: int,
        full_name: str,
        base_salary: float,
        shift_type: str = "single",
        shift1_start: str = "09:00",
        shift1_end: str = "17:00",
        shift2_start: Optional[str] = None,
        shift2_end: Optional[str] = None,
        required_work_days: int = 30,
        is_active: int = 1,
    ) -> bool:
        req_days = int(required_work_days) if required_work_days and int(required_work_days) > 0 else 30
        with self._lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE employees
                SET fingerprint_id = ?, full_name = ?, base_salary = ?, shift_type = ?,
                    shift1_start = ?, shift1_end = ?, shift2_start = ?, shift2_end = ?,
                    required_work_days = ?, is_active = ?
                WHERE id = ?
                """,
                (
                    int(fingerprint_id),
                    full_name.strip(),
                    float(base_salary),
                    shift_type,
                    shift1_start or "09:00",
                    shift1_end or "17:00",
                    shift2_start if shift_type == "double" else None,
                    shift2_end if shift_type == "double" else None,
                    req_days,
                    int(is_active),
                    int(emp_id),
                ),
            )
            conn.commit()
            return cursor.rowcount > 0

    def delete_employee(self, emp_id: int) -> bool:
        with self._lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM employees WHERE id = ?", (int(emp_id),))
            conn.commit()
            return cursor.rowcount > 0

    def toggle_employee_active(self, emp_id: int) -> Optional[int]:
        with self._lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT is_active FROM employees WHERE id = ?", (int(emp_id),))
            row = cursor.fetchone()
            if not row:
                return None
            new_status = 0 if row["is_active"] == 1 else 1
            cursor.execute(
                "UPDATE employees SET is_active = ? WHERE id = ?",
                (new_status, int(emp_id)),
            )
            conn.commit()
            return new_status

    def get_employee_by_id(self, emp_id: int) -> Optional[Dict[str, Any]]:
        with self._lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM employees WHERE id = ?", (int(emp_id),))
            row = cursor.fetchone()
            return self._format_emp_row(row) if row else None

    def get_employee_by_fingerprint(self, fingerprint_id: int) -> Optional[Dict[str, Any]]:
        with self._lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM employees WHERE fingerprint_id = ?",
                (int(fingerprint_id),),
            )
            row = cursor.fetchone()
            return self._format_emp_row(row) if row else None

    def get_all_employees(self, active_only: bool = False) -> List[Dict[str, Any]]:
        with self._lock, self.get_connection() as conn:
            cursor = conn.cursor()
            if active_only:
                cursor.execute(
                    "SELECT * FROM employees WHERE is_active = 1 ORDER BY fingerprint_id ASC"
                )
            else:
                cursor.execute("SELECT * FROM employees ORDER BY fingerprint_id ASC")
            return [self._format_emp_row(row) for row in cursor.fetchall()]

    def get_next_available_slot(self) -> int:
        with self._lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT fingerprint_id FROM employees ORDER BY fingerprint_id ASC")
            used_ids = {row["fingerprint_id"] for row in cursor.fetchall()}
            slot = 1
            while slot in used_ids:
                slot += 1
            return slot

    # ==================== EMERGENCY DAYS OFF ====================

    def add_emergency_day_off(
        self, date_str: str, reason: str, employee_id: Optional[int] = None, is_paid: int = 1
    ) -> int:
        """تسجيل عطلة طارئة أو استثنائية (عامة لكل الموظفين أو لموظف محدد)."""
        with self._lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO emergency_days_off (date, reason, employee_id, is_paid)
                VALUES (?, ?, ?, ?)
                """,
                (date_str, reason.strip(), employee_id, int(is_paid)),
            )
            conn.commit()
            return cursor.lastrowid

    def delete_emergency_day_off(self, day_id: int) -> bool:
        """حذف إجازة طارئة مسجلة."""
        with self._lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM emergency_days_off WHERE id = ?", (int(day_id),))
            conn.commit()
            return cursor.rowcount > 0

    def get_emergency_days_off(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        employee_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """جلب جميع الإجازات الطارئة والاستثنائية المسجلة في فترة محددة."""
        query = """
            SELECT edo.*, e.full_name AS employee_name
            FROM emergency_days_off edo
            LEFT JOIN employees e ON edo.employee_id = e.id
            WHERE 1=1
        """
        params: List[Any] = []
        if date_from:
            query += " AND edo.date >= ?"
            params.append(date_from)
        if date_to:
            query += " AND edo.date <= ?"
            params.append(date_to)
        if employee_id is not None:
            query += " AND (edo.employee_id = ? OR edo.employee_id IS NULL)"
            params.append(int(employee_id))
        query += " ORDER BY edo.date DESC"

        with self._lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def is_emergency_day_off(
        self, date_str: str, employee_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """التحقق مما إذا كان التاريخ المحدد يمثل إجازة طارئة للمنشأة أو للموظف."""
        with self._lock, self.get_connection() as conn:
            cursor = conn.cursor()
            if employee_id:
                cursor.execute(
                    """
                    SELECT * FROM emergency_days_off 
                    WHERE date = ? AND (employee_id = ? OR employee_id IS NULL)
                    LIMIT 1
                    """,
                    (date_str, int(employee_id)),
                )
            else:
                cursor.execute(
                    "SELECT * FROM emergency_days_off WHERE date = ? AND employee_id IS NULL LIMIT 1",
                    (date_str,),
                )
            row = cursor.fetchone()
            return dict(row) if row else None

    # ==================== ATTENDANCE & PUNCH PROCESSING ====================

    def process_punch(
        self,
        fingerprint_id: int,
        device_id: Optional[str] = None,
        punch_dt: Optional[datetime] = None,
        is_offline_sync: int = 0,
    ) -> Tuple[bool, str, int, Optional[Dict[str, Any]]]:
        with self._lock, self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                "SELECT * FROM employees WHERE fingerprint_id = ?",
                (int(fingerprint_id),),
            )
            emp = cursor.fetchone()
            if not emp:
                return False, "unlinked", 404, None

            emp_data = self._format_emp_row(emp)

            if emp_data["is_active"] != 1:
                return False, "inactive", 403, emp_data

            now = punch_dt or datetime.now()
            date_str = now.strftime("%Y-%m-%d")
            time_str = now.strftime("%H:%M:%S")
            timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S")

            debounce_min = float(self.get_setting("debounce_minutes", str(DEFAULT_DEBOUNCE_MINUTES)))
            cursor.execute(
                """
                SELECT timestamp FROM attendance_logs 
                WHERE employee_id = ? 
                ORDER BY timestamp DESC LIMIT 1
                """,
                (emp_data["id"],),
            )
            last_punch_row = cursor.fetchone()

            if last_punch_row and last_punch_row["timestamp"] and is_offline_sync == 0:
                try:
                    last_time = datetime.strptime(
                        str(last_punch_row["timestamp"]).split(".")[0],
                        "%Y-%m-%d %H:%M:%S",
                    )
                    diff_seconds = abs((now - last_time).total_seconds())
                    if diff_seconds < (debounce_min * 60):
                        return True, "DEBOUNCED", 200, {
                            "employee": emp_data,
                            "timestamp": timestamp_str,
                            "ignored": True,
                        }
                except Exception:
                    pass

            cursor.execute(
                """
                SELECT punch_type FROM attendance_logs 
                WHERE employee_id = ? AND date = ? 
                ORDER BY timestamp ASC
                """,
                (emp_data["id"], date_str),
            )
            today_punches = [r["punch_type"] for r in cursor.fetchall()]
            punch_count = len(today_punches)
            shift_type = emp_data["shift_type"]

            if shift_type == "single":
                if punch_count == 0:
                    db_punch_type = "IN_1"
                    api_punch_type = "IN"
                elif punch_count == 1:
                    db_punch_type = "OUT_1"
                    api_punch_type = "OUT"
                else:
                    if punch_count % 2 == 0:
                        db_punch_type = "IN_1"
                        api_punch_type = "IN"
                    else:
                        db_punch_type = "OUT_1"
                        api_punch_type = "OUT"
            else:  # Double shift
                if punch_count == 0:
                    db_punch_type = "IN_1"
                    api_punch_type = "IN"
                elif punch_count == 1:
                    db_punch_type = "OUT_1"
                    api_punch_type = "OUT"
                elif punch_count == 2:
                    db_punch_type = "IN_2"
                    api_punch_type = "IN"
                elif punch_count == 3:
                    db_punch_type = "OUT_2"
                    api_punch_type = "OUT"
                else:
                    if punch_count % 2 == 0:
                        db_punch_type = "IN_2"
                        api_punch_type = "IN"
                    else:
                        db_punch_type = "OUT_2"
                        api_punch_type = "OUT"

            cursor.execute(
                """
                INSERT INTO attendance_logs (
                    fingerprint_id, employee_id, timestamp, date, time, punch_type, is_offline_sync
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(fingerprint_id),
                    emp_data["id"],
                    timestamp_str,
                    date_str,
                    time_str,
                    db_punch_type,
                    int(is_offline_sync),
                ),
            )
            log_id = cursor.lastrowid
            conn.commit()

            result_info = {
                "log_id": log_id,
                "employee": emp_data,
                "fingerprint_id": int(fingerprint_id),
                "timestamp": timestamp_str,
                "date": date_str,
                "time": time_str,
                "db_punch_type": db_punch_type,
                "api_punch_type": api_punch_type,
                "is_offline_sync": is_offline_sync,
            }
            return True, api_punch_type, 200, result_info

    def process_bulk_punches(
        self, punches: List[Dict[str, Any]]
    ) -> Tuple[int, List[Dict[str, Any]]]:
        now = datetime.now()
        successful_count = 0
        synced_records = []

        for item in punches:
            try:
                fid = int(item.get("fingerprint_id", 0))
                sec_ago = int(item.get("seconds_ago", 0))
                dev_id = item.get("device_id", "")
                punch_dt = now - timedelta(seconds=max(0, sec_ago))

                success, p_type, code, meta = self.process_punch(
                    fingerprint_id=fid,
                    device_id=dev_id,
                    punch_dt=punch_dt,
                    is_offline_sync=1,
                )

                if success and code == 200 and meta and not meta.get("ignored"):
                    successful_count += 1
                    synced_records.append(meta)
            except Exception as e:
                print(f"[DatabaseManager] Error in bulk punch item {item}: {e}")

        return successful_count, synced_records

    # ==================== QUERYING & ANALYTICS ====================

    def get_attendance_logs(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        employee_id: Optional[int] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        query = """
            SELECT 
                l.id, l.fingerprint_id, l.employee_id, l.timestamp, l.date, l.time, 
                l.punch_type, l.is_offline_sync,
                e.full_name, e.shift_type, e.base_salary, e.required_work_days
            FROM attendance_logs l
            LEFT JOIN employees e ON l.employee_id = e.id
            WHERE 1=1
        """
        params: List[Any] = []

        if date_from:
            query += " AND l.date >= ?"
            params.append(date_from)
        if date_to:
            query += " AND l.date <= ?"
            params.append(date_to)
        if employee_id:
            query += " AND l.employee_id = ?"
            params.append(int(employee_id))

        query += " ORDER BY l.timestamp DESC LIMIT ?"
        params.append(limit)

        with self._lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            results = []
            for row in cursor.fetchall():
                d = dict(row)
                req_d = d.get("required_work_days") or 30
                base_s = float(d.get("base_salary") or 0.0)
                d["daily_salary"] = round(base_s / req_d, 2)
                results.append(d)
            return results

    def get_dashboard_summary(self) -> Dict[str, Any]:
        today = datetime.now().strftime("%Y-%m-%d")

        with self._lock, self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) AS total FROM employees WHERE is_active = 1")
            total_active_staff = cursor.fetchone()["total"]

            cursor.execute(
                """
                SELECT COUNT(DISTINCT employee_id) AS present_count 
                FROM attendance_logs 
                WHERE date = ? AND employee_id IS NOT NULL
                """,
                (today,),
            )
            present_today = cursor.fetchone()["present_count"]

            cursor.execute(
                """
                SELECT e.id, e.shift_type, COUNT(l.id) AS punch_count
                FROM employees e
                LEFT JOIN attendance_logs l ON e.id = l.employee_id AND l.date = ?
                WHERE e.is_active = 1
                GROUP BY e.id
                """,
                (today,),
            )
            missed_or_incomplete = 0
            for row in cursor.fetchall():
                required = 2 if row["shift_type"] == "single" else 4
                actual = row["punch_count"]
                if actual < required:
                    missed_or_incomplete += 1

            cursor.execute(
                """
                SELECT 
                    l.id, l.fingerprint_id, l.employee_id, l.timestamp, l.time, 
                    l.punch_type, l.is_offline_sync,
                    COALESCE(e.full_name, 'موظف غير معرف') AS full_name,
                    COALESCE(e.shift_type, 'single') AS shift_type
                FROM attendance_logs l
                LEFT JOIN employees e ON l.employee_id = e.id
                WHERE l.date = ?
                ORDER BY l.timestamp DESC LIMIT 30
                """,
                (today,),
            )
            recent_logs = [dict(r) for r in cursor.fetchall()]

            return {
                "total_staff": total_active_staff,
                "present_today": present_today,
                "missed_punches": missed_or_incomplete,
                "recent_logs": recent_logs,
            }

    # ==================== BACKUP & RESTORE ====================

    def backup_database(self, dest_path: str) -> bool:
        with self._lock:
            with self.get_connection() as conn:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")

            shutil.copy2(self.db_path, dest_path)
            return os.path.exists(dest_path)

    def restore_database(self, src_path: str) -> bool:
        if not os.path.exists(src_path):
            return False

        with self._lock:
            test_conn = sqlite3.connect(src_path)
            cursor = test_conn.cursor()
            cursor.execute("PRAGMA integrity_check;")
            res = cursor.fetchone()
            test_conn.close()

            if not res or res[0] != "ok":
                raise ValueError("ملف قاعدة البيانات تالف أو غير صالح")

            shutil.copy2(src_path, self.db_path)
            self.init_db()
            return True


db = DatabaseManager()
