"""
Читач SQLite-маніфесту конфігурації 1С (артефакт onec_ctx (генератор)).

Відкриває manifest.sqlite у режимі read-only й віддає вузькі зрізи одним
SELECT кожен: жодного парсингу, жодного завантаження всього файла в пам'ять
(SQLite читає з диска лише сторінки під конкретний запит).

Ядро навмисно не залежить від решти vps_api — приймає шлях до БД прямо,
тож його можна тестувати окремо. Роутер передає шлях із runtime-конфігу.

Кожне з'єднання відкривається на час одного виклику (це дешево) і в режимі
mode=ro, тому паралельні читання з threadpool FastAPI безпечні, а випадковий
запис у похідний артефакт неможливий.
"""
from __future__ import annotations

import os
import sqlite3


class ManifestNotConfigured(Exception):
    """Шлях до маніфесту не заданий або файла немає на диску."""


# Відповідність типу об'єкта 1С -> тека у дереві вивантаження.
TYPE_TO_FOLDER = {
    "Справочник": "Catalogs",
    "Документ": "Documents",
    "РегістрВідомостей": "InformationRegisters",
    "РегистрСведений": "InformationRegisters",
    "РегістрНакопичення": "AccumulationRegisters",
    "РегистрНакопления": "AccumulationRegisters",
    "РегістрБухгалтерії": "AccountingRegisters",
    "РегистрБухгалтерии": "AccountingRegisters",
    "РегістрРозрахунку": "CalculationRegisters",
    "Перелічення": "Enums", "Перечисление": "Enums",
    "Звіт": "Reports", "Отчет": "Reports",
    "Обробка": "DataProcessors", "Обработка": "DataProcessors",
    "ПланВидівХарактеристик": "ChartsOfCharacteristicTypes",
    "ПланРахунків": "ChartsOfAccounts",
    "БізнесПроцес": "BusinessProcesses",
    "Задача": "Tasks",
    "ПланОбміну": "ExchangePlans",
    "Константа": "Constants",
    "ЖурналДокументів": "DocumentJournals",
}


def _like_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class ManifestReader:
    def __init__(self, db_path: str | None):
        self.db_path = db_path

    # --- внутрішнє ---
    def _connect(self) -> sqlite3.Connection:
        if not self.db_path or not os.path.exists(self.db_path):
            raise ManifestNotConfigured(
                "Маніфест cf_module не знайдено. Перевірте ONEC_CF_MODULE_MANIFEST.")
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def available(self) -> bool:
        return bool(self.db_path and os.path.exists(self.db_path))

    # --- зрізи ---
    def meta(self) -> dict:
        """Метадані артефакту (свіжість, лічильники)."""
        with self._connect() as c:
            return {r["key"]: r["value"] for r in c.execute(
                "SELECT key, value FROM meta")}

    def where_defined(self, name: str, export_only: bool = True,
                      limit: int = 50) -> list[dict]:
        """Де оголошено символ. За замовчуванням — серед експортних."""
        sql = ("SELECT name, kind, is_export, module_path, sig "
               "FROM symbols WHERE name = ?")
        params: list = [name]
        if export_only:
            sql += " AND is_export = 1"
        sql += " LIMIT ?"
        params.append(limit)
        with self._connect() as c:
            return [dict(r) for r in c.execute(sql, params)]

    def module_toc(self, module_path: str) -> dict | None:
        """Зміст модуля: роль + перелік процедур (найдешевший зріз)."""
        with self._connect() as c:
            m = c.execute(
                "SELECT module_path, role, source, proc_count, export_count "
                "FROM modules WHERE module_path = ?", (module_path,)).fetchone()
            if not m:
                return None
            procs = [dict(r) for r in c.execute(
                "SELECT name, kind, is_export, significant_lines "
                "FROM symbols WHERE module_path = ? ORDER BY start_line",
                (module_path,))]
            out = dict(m)
            out["procedures"] = procs
            return out

    def skeleton(self, module_path: str, level: str = "compact") -> str | None:
        """Кістяк модуля. level: 'compact' | 'full'."""
        col = "skeleton_full" if level == "full" else "skeleton_compact"
        with self._connect() as c:
            r = c.execute(
                f"SELECT {col} AS s FROM modules WHERE module_path = ?",
                (module_path,)).fetchone()
            return r["s"] if r else None

    def body(self, module_path: str, name: str) -> str | None:
        """Текст цілої процедури за модулем та іменем."""
        with self._connect() as c:
            r = c.execute(
                "SELECT body FROM symbols WHERE module_path = ? AND name = ? "
                "LIMIT 1", (module_path, name)).fetchone()
            return r["body"] if r else None

    def top_modules(self, limit: int = 20) -> list[dict]:
        """Найбільші модулі за кількістю процедур (для орієнтації)."""
        with self._connect() as c:
            return [dict(r) for r in c.execute(
                "SELECT module_path, role, proc_count, export_count "
                "FROM modules ORDER BY proc_count DESC LIMIT ?", (limit,))]

    def search_symbols(self, prefix: str, export_only: bool = True,
                       limit: int = 50) -> list[dict]:
        """Пошук символів за префіксом імені (для навігації/автодоповнення)."""
        sql = ("SELECT name, kind, is_export, module_path FROM symbols "
               "WHERE name LIKE ? ESCAPE '\\'")
        params: list = [prefix.replace("%", "\\%").replace("_", "\\_") + "%"]
        if export_only:
            sql += " AND is_export = 1"
        sql += " ORDER BY name LIMIT ?"
        params.append(limit)
        with self._connect() as c:
            return [dict(r) for r in c.execute(sql, params)]

    def object_modules(self, folder: str, name: str) -> list[dict]:
        """Усі модулі об'єкта за текою+іменем (напр. Catalogs, Контрагенты)."""
        like = f"{_like_escape(folder)}/{_like_escape(name)}/%"
        with self._connect() as c:
            return [dict(r) for r in c.execute(
                "SELECT module_path, role, source, proc_count, export_count "
                "FROM modules WHERE module_path LIKE ? ESCAPE '\\' "
                "ORDER BY module_path", (like,))]

    def object_modules_by_type(self, type_1c: str, name: str):
        """Те саме, але за типом 1С. None, якщо тип невідомий."""
        folder = TYPE_TO_FOLDER.get(type_1c)
        if folder is None:
            return None
        return self.object_modules(folder, name)