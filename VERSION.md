## 1.1.006 2026-09-25
- cf_module_router: усі 9 ендпоінтів на require_session_token_readonly (чисті читання; лок на спільному рядку tokens при паралельних MCP-викликах давав 7-21с)
- onec_router: /1c/metadata_objects, /1c/metadata_describe, /metadata/queries, /metadata/query_get, /metadata/generate_query, /forms/list, /forms/read, /docs/photos/list, /docs/photos/file — те саме

## 1.1.005 2026-09-24
- cf_module_reader: пул довгоживучих read-only SQLite-з'єднань до manifest.sqlite замість відкриття нового на кожен запит — виміряно, що саме відкриття 302МБ файлу було домінантною причиною затримок 6-17с (навіть у /cf_module/meta)

## 1.1.004 2026-09-24
- command_log: files тепер [{root, path}] замість вільного рядка-шляху — root фіксований ("html"|"queries1c"|"html_command_log"), помилка "забув префікс кореня" (сайдкар писався в осиротілу теку в корені проекту) стає неможливою на рівні схеми

## 1.1.003 2026-09-24
- Фікс MariaDB 1020 на /forms/version: readonly-токен замість require_session_token, щоб паралельні запити версії не бились за оновлення usage_count в одному рядку tokens

## 1.1.002 2026-08-21
-