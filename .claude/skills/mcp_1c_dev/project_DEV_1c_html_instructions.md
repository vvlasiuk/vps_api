# Інструкції проєкту: Розробка vps_api 

Ти допомагаєш розробляти систему vps_api — FastAPI-бекенд + статичні HTML-сторінки,
що працюють із 1С 8.3 (УТП) через проміжний HTTP-сервіс. Інтерфейс українською.
У тебе є MCP-інструменти для доступу до системи (див. розділ «MCP» нижче) — користуйся
ними, щоб брати реальний контекст, а не вигадувати.

## Головні принципи роботи

- Аналізуй мовчки перед дією; роби мінімальні, точкові зміни строго в межах задачі.
- Не чіпай коментарі й закоментований код, якщо про це не просять.
- Перед блоком змін (запис запитів/форм) ПРОПОНУЙ зробити бекап (інструмент create_backup).
- Відповідай стисло й по суті. Українською.
- Не вигадуй структуру 1С, поля чи API компонентів — бери їх через MCP (describe_object,
  get_query, read_form).

## Архітектура (коротко)

HTML (компонент) → FastAPI (/1c/query, /1c/save_doc) → 1С HTTP-сервіс (hs/vps/...) → 1С

- Дані читаються через ІМЕНОВАНІ запити (queries1c/), не сирим текстом.
- Фронт працює з АЛІАСАМИ полів (латиниця), не знаючи структури 1С.
- Бекенд обгортає запит: ВЫБРАТЬ {fields} ИЗ ( <текст .sel> ) КАК Вложенный,
  і накладає зверху fields/filters/order по аліасах.

## Система запитів (.sel + .json)

Кожен запит — пара файлів у queries1c/<catalogs|documents>/<Обʼєкт>/:
- .sel — текст запиту 1С (російські ключові слова: ВЫБРАТЬ, ИЗ, ГДЕ, КАК). // — коментар.
- .json — метадані. Джерело правди. Структура:
  {
    "query_name": "<ASCII-ідентифікатор>",    // напр. cat_contractors_dropdown
    "object_type": "<Справочник|Документ>",
    "object_name": "<імʼя обʼєкта>",
    "source_name": "1C_UTP",
    "info": "<опис українською>",
    "fields": [ {"key":"<аліас>", "type":"<тип>", "info":"<опис>"} ]
  }

Порядок ключів у .json саме такий (query_name згори, fields внизу).

Типи полів (fields[].type) — СУВОРО одне з: ref, string, number, date, boolean.
  посилання (СправочникСсылка/ДокументСсылка/...) → ref
  Строка → string, Число → number, Дата → date, Булево → boolean

### Системні поля (обовʼязково, згори .sel і fields)

Псевдонім таблиці: дов (довідник), док (документ).

Довідник — завжди:
  дов.Ссылка КАК _ref (ref), дов.Код КАК _code (string),
  дов.Наименование КАК _description (string), дов.ПометкаУдаления КАК _marked (boolean)
Довідник — ДОДАТКОВО лише якщо ієрархічний (є Родитель/ЭтоГруппа в describe):
  дов.Родитель КАК _parent (ref), дов.ЭтоГруппа КАК _isfolder (boolean)

Документ — завжди:
  док.Ссылка КАК _ref (ref), док.ВерсияДанных КАК _version (string),
  док.Номер КАК _number (string), док.Дата КАК _date (date),
  ВЫБОР КОГДА док.Проведен ТОГДА 1 КОГДА док.ПометкаУдаления ТОГДА 2 ИНАЧЕ 0 КОНЕЦ КАК _status (number)

Спершу системні поля, далі прикладні. Аліаси прикладних — осмислена латиниця
(name, code, edrpou, brand_ref). Для поля-посилання, по якому фільтруватимуть,
виводь окремий аліас (напр. дов.ПСТ_Бренд КАК brand_ref).
Для довідників типово додавай ГДЕ НЕ дов.ПометкаУдаления.

ВАЖЛИВО: для генерації болванки використовуй інструмент generate_query (він дає
коректні системні поля, фільтрацію стандартних, source_name). Не відтворюй це вручну —
візьми болванку й допрацюй під задачу.

## Фронтенд — компоненти (html/components/)

Стиль: IIFE-модуль, init(config), працює через CONFIG.API_URL + AUTH (auth.js).
Перед генерацією форми ЧИТАЙ реальний код компонента (read_form), щоб узяти точний API —
нижче лише орієнтир.

- ref_select.js (RefSelect) — універсальний вибір посилання через /1c/query.
  Конфіг: container, query, refKey, displayKey, searchFields, fields[{key,label}],
  onSelect, minChars, matchMode, extraFilter, extraParams. Методи: init, getValue, clear,
  setExtra(id, filter, params), setEnabled(id, bool). CSS: contractor_select.css (класи cs-).
- contractor_select.js (ContractorSelect) — пресет над RefSelect (query=cat_contractors).
  Вимагає ref_select.js ПЕРЕД ним.
- doc_header.js (DocHeader) — шапка документа (сам інжектить CSS, класи dh-).
  Вид/Номер/Дата/Статус/кнопки дій. Дії за станом. Методи: init, setState, getState,
  getDate, setBusy.
- list_view.js (ListView) — універсальний список (таблиця/картки). Дані через /1c/query.
  Конфіг: container, query, columns[{key,label,sortable,width,align}], search{fields,...},
  pageSize, defaultOrder, onRowClick. CSS: list_view.css (класи lv-).

## Фронтенд — глобали

- CONFIG.API_URL (lib/config.js)
- AUTH (lib/auth.js): token, username, role, userId, headers {Authorization:Bearer, Content-Type},
  logout(). Немає/прострочений токен → редірект на login.

## Дизайн (з list_view.css — єдина візуальна мова)

Кольори (захардкоджені, не CSS-змінні):
  поверхня #fff, фон #f5f6f8/#f0f2f5, hairline #e5e7eb, текст #111827, мутед #9ca3af/#6b7280,
  акцент #2563eb, світлий акцент #eff6ff, виділення #DBEAFE, помилка #DC2626, успіх #059669.
Радіуси 7–10px. Заголовки: 11px, uppercase, letter-spacing .4px, колір мутед.
Мобільний брейк 600px (таблиця → картки). Формат дати відображення: дд.мм.рррр.
Шрифт: system-ui / Inter. Мінімум зайвого, чисто, службовий тон.

## Форми — як будувати

- Форма будується на ПОЛЯХ ЗАПИТУ (аліасах з .json), не на сирих реквізитах 1С.
- Підключення скриптів — абсолютними шляхами: /html/lib/config.js, /html/lib/auth.js,
  /html/components/<...>. Спершу залежності (ref_select.js), потім пресети.
- Кеш: при зміні JS/CSS версіонуй (?v=N) або Ctrl+Shift+R — стара версія в кеші маскує правки.
- getElementById для guid-id — БЕЗ CSS.escape (він ламає id з провідною цифрою).

## MCP — інструменти (бери контекст, не вигадуй)

Читання: list_objects, describe_object(object_type, object_name), list_queries, get_query(query_name),
  list_forms, read_form(path).
Запис: generate_query(object_type, object_name) — болванка запиту; save_query(sel, meta, file_name);
  write_form(path, content) — ЛИШЕ pages/ та menu/.
Бекап: create_backup(set_name="full_html") — перед блоком змін.

Типові цикли:
- Новий запит: describe_object → generate_query → допрацювати під задачу → показати → save_query.
- Редагувати запит: get_query → змінити ТІЛЬКИ потрібне → save_query (з тим самим file_name!).
- Нова форма: read_form кількох наявних (патерн) + get_query (поля) → згенерувати → write_form.

ВАЖЛИВО про save_query при редагуванні: передавай file_name = реальне імʼя файлу (з get_query.file),
інакше створиться дубль (імʼя файлу може відрізнятися від query_name).

## Обмеження

- write_form пише тільки в pages/ та menu/. lib/, components/, system/ — лише читання.
- Не пиши секрети у файли html/ (вони читаються через API).
- 1С через MCP — тільки читання (даних не змінюємо цим каналом).