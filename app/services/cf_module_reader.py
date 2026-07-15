"""
Читач SQLite-маніфесту конфігурації 1С (артефакт onec_ctx (генератор)).

Відкриває manifest.sqlite у режимі read-only й віддає вузькі зрізи одним
SELECT кожен: жодного парсингу, жодного завантаження всього файла в пам'ять
(SQLite читає з диска лише сторінки під конкретний запит).

Ядро навмисно не залежить від решти vps_api — приймає шлях до БД прямо,
тож його можна тестувати окремо. Роутер передає шлях із runtime-конфігу.

Кожне з'єднання відкривається на час одного виклику (це дешево) і в режимі
mode=ro, тому паралельні читання з threadpool FastAPI безпечні, а випадковий
запис у похідний артефакт неможливий. З'єднання закриваються ЯВНО (контекст-
менеджер _ro): `with sqlite3.connect(...) as c` завершує лише транзакцію, але
НЕ закриває файл — на Windows незакритий хендл блокує атомарну підміну
маніфесту під час регенерації.

Пошук по коду (find_usages) шукає у двох дослівних джерелах:
  - symbols.body        — усе всередині процедур;
  - modules.outside_text — усе поза процедурами (модульні Перем, головний
    розділ, вміст #Областей поза процедурами).
Разом це повне покриття тексту модуля. Пошук завжди регістронезалежний
(casefold), бо мова 1С регістронезалежна для ідентифікаторів.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager


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


def _norm_sep(p: str) -> str:
    """Нормалізує роздільник шляху (\\ -> /), бо module_path у маніфесті —
    з зворотними слешами (Windows-вивантаження), а фільтри зручніше писати з /."""
    return p.replace("\\", "/")


def _is_ident_char(ch: str) -> bool:
    """Символ, дозволений в ідентифікаторі 1С (літера/цифра/підкреслення).
    ch.isalnum() коректно охоплює кирилицю."""
    return ch.isalnum() or ch == "_"


def _line_matches(line_cf: str, needle_cf: str, match: str) -> bool:
    """Чи є в рядку збіг за заданим режимом. Обидва аргументи вже casefold-нуті.
    match: 'contains' (будь-де) | 'word' (по межах ідентифікатора) | 'prefix'
    (з початку слова)."""
    if not needle_cf:
        return False
    n = len(needle_cf)
    start = 0
    while True:
        i = line_cf.find(needle_cf, start)
        if i < 0:
            return False
        end = i + n
        left_ok = i == 0 or not _is_ident_char(line_cf[i - 1])
        right_ok = end >= len(line_cf) or not _is_ident_char(line_cf[end])
        if match == "contains":
            return True
        if match == "prefix" and left_ok:
            return True
        if match == "word" and left_ok and right_ok:
            return True
        start = i + 1


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

    @contextmanager
    def _ro(self):
        """Read-only з'єднання з ЯВНИМ закриттям (не лишає відкритого хендла)."""
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    def available(self) -> bool:
        return bool(self.db_path and os.path.exists(self.db_path))

    # --- зрізи ---
    def meta(self) -> dict:
        """Метадані артефакту (свіжість, лічильники)."""
        with self._ro() as c:
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
        with self._ro() as c:
            return [dict(r) for r in c.execute(sql, params)]

    def module_toc(self, module_path: str) -> dict | None:
        """Зміст модуля: роль + перелік процедур (найдешевший зріз)."""
        with self._ro() as c:
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
        with self._ro() as c:
            r = c.execute(
                f"SELECT {col} AS s FROM modules WHERE module_path = ?",
                (module_path,)).fetchone()
            return r["s"] if r else None

    def body(self, module_path: str, name: str) -> str | None:
        """Текст цілої процедури за модулем та іменем."""
        with self._ro() as c:
            r = c.execute(
                "SELECT body FROM symbols WHERE module_path = ? AND name = ? "
                "LIMIT 1", (module_path, name)).fetchone()
            return r["body"] if r else None

    def top_modules(self, limit: int = 20) -> list[dict]:
        """Найбільші модулі за кількістю процедур (для орієнтації)."""
        with self._ro() as c:
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
        with self._ro() as c:
            return [dict(r) for r in c.execute(sql, params)]

    def object_modules(self, folder: str, name: str) -> list[dict]:
        """Усі модулі об'єкта за текою+іменем (напр. Catalogs, Контрагенты).

        Порівняння шляху сепаратор-незалежне: module_path у маніфесті — зі
        зворотними слешами, тож нормалізуємо обидві сторони до '/'."""
        like = f"{_like_escape(folder)}/{_like_escape(name)}/%"
        with self._ro() as c:
            return [dict(r) for r in c.execute(
                "SELECT module_path, role, source, proc_count, export_count "
                "FROM modules WHERE replace(module_path, '\\', '/') LIKE ? "
                "ESCAPE '\\' ORDER BY module_path", (like,))]

    def object_modules_by_type(self, type_1c: str, name: str):
        """Те саме, але за типом 1С. None, якщо тип невідомий."""
        folder = TYPE_TO_FOLDER.get(type_1c)
        if folder is None:
            return None
        return self.object_modules(folder, name)

    # --- пошук використань по коду ---
    def find_usages(self, query: str, *, match: str = "word",
                    type_1c: str | None = None, type_name: str | None = None,
                    path_prefix: str | None = None, role: str | None = None,
                    max_modules: int = 200, max_per_module: int = 20,
                    context_lines: int = 0) -> dict:
        """Знайти всі текстові використання імені/рядка в коді конфігурації.

        Шукає у symbols.body (усередині процедур) І в modules.outside_text
        (поза процедурами). Завжди регістронезалежно (casefold).

        match: 'word' (типово; по межах ідентифікатора) | 'contains' | 'prefix'.
        Звуження (усі опційні): type_1c(+type_name) АБО path_prefix; role.

        Повертає {query, match, total_modules, total_hits, truncated, results},
        де results відсортовано за щільністю збігів; кожен елемент —
        {module_path, role, hit_count, hits:[{line_no, container, is_export,
        text, context?}]}. container=None означає рівень модуля (поза процедурою).
        """
        if match not in ("word", "contains", "prefix"):
            match = "word"
        needle_cf = query.casefold()
        if not needle_cf:
            return {"query": query, "match": match, "total_modules": 0,
                    "total_hits": 0, "truncated": False, "results": []}

        # Звуження за типом 1С -> префікс теки (сепаратор '/').
        if type_1c:
            folder = TYPE_TO_FOLDER.get(type_1c)
            if folder is None:
                raise ValueError(f"Невідомий тип об'єкта 1С: {type_1c}")
            path_prefix = f"{folder}/{type_name}/" if type_name else f"{folder}/"

        pfx = _norm_sep(path_prefix) if path_prefix else None

        # SQL-фільтри (звуження зменшує обсяг зчитуваного тексту).
        where = []
        params: list = []
        if pfx:
            where.append("replace(module_path, '\\', '/') LIKE ? ESCAPE '~'")
            params.append(pfx.replace("~", "~~").replace("%", "~%")
                          .replace("_", "~_") + "%")
        if role:
            where.append("role = ?")
            params.append(role)
        where_sql = (" WHERE " + " AND ".join(where)) if where else ""

        # module_path -> {"role":..., "hits":[...]}
        acc: dict[str, dict] = {}

        def _emit(module_path, role_val, line_no, container, is_export,
                  text, ctx):
            rec = acc.get(module_path)
            if rec is None:
                rec = {"role": role_val, "hits": []}
                acc[module_path] = rec
            hit = {"line_no": line_no, "container": container,
                   "is_export": is_export, "text": text.rstrip()}
            if ctx is not None:
                hit["context"] = ctx
            rec["hits"].append(hit)

        def _ctx(lines, idx):
            if context_lines <= 0:
                return None
            lo = max(0, idx - context_lines)
            hi = min(len(lines), idx + context_lines + 1)
            return [{"line_no": j + 1, "text": lines[j].rstrip()}
                    for j in range(lo, hi)]

        with self._ro() as c:
            # 1) поза процедурами (modules.outside_text) — рівень модуля.
            sql_out = ("SELECT module_path, role, outside_text FROM modules"
                       + where_sql)
            for r in c.execute(sql_out, params):
                text = r["outside_text"]
                if not text:
                    continue
                low = text.casefold()
                if needle_cf not in low:
                    continue
                lines = text.splitlines()
                lines_cf = low.splitlines()
                for idx, lcf in enumerate(lines_cf):
                    if _line_matches(lcf, needle_cf, match):
                        _emit(r["module_path"], r["role"], idx + 1, None,
                              None, lines[idx], _ctx(lines, idx))

            # 2) всередині процедур (symbols.body) — контейнер = ім'я процедури.
            # Той самий фільтр шляху/ролі через JOIN на modules (role/шлях).
            sql_sym = (
                "SELECT s.module_path AS mp, m.role AS role, s.name AS name, "
                "s.is_export AS is_export, s.start_line AS start_line, "
                "s.body AS body "
                "FROM symbols s JOIN modules m ON m.module_path = s.module_path"
                + (where_sql.replace("module_path", "s.module_path")
                   .replace("role = ?", "m.role = ?") if where_sql else ""))
            for r in c.execute(sql_sym, params):
                body = r["body"]
                if not body:
                    continue
                low = body.casefold()
                if needle_cf not in low:
                    continue
                start = r["start_line"] or 1
                lines = body.splitlines()
                lines_cf = low.splitlines()
                for idx, lcf in enumerate(lines_cf):
                    if _line_matches(lcf, needle_cf, match):
                        _emit(r["mp"], r["role"], start + idx, r["name"],
                              bool(r["is_export"]), lines[idx], _ctx(lines, idx))

        # Підсумки й сортування за щільністю збігів (найрелевантніші зверху).
        total_modules = len(acc)
        total_hits = sum(len(v["hits"]) for v in acc.values())

        ordered = sorted(acc.items(),
                         key=lambda kv: (-len(kv[1]["hits"]), kv[0]))
        truncated = total_modules > max_modules
        results = []
        for module_path, rec in ordered[:max_modules]:
            hits = sorted(rec["hits"], key=lambda h: h["line_no"])
            hit_count = len(hits)
            if hit_count > max_per_module:
                hits = hits[:max_per_module]
            results.append({
                "module_path": module_path,
                "role": rec["role"],
                "hit_count": hit_count,
                "hits": hits,
            })

        return {"query": query, "match": match,
                "total_modules": total_modules, "total_hits": total_hits,
                "truncated": truncated, "results": results}