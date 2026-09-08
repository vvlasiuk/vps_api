import os
import re

import pika

from .error_logger import ErrorLogger

ONEC_BASE_URL = os.getenv("ONEC_BASE_URL")
ONEC_SOURCE_NAME = os.getenv("ONEC_SOURCE_NAME", "1C_UTP")
ONEC_QUERY_URL = f"{ONEC_BASE_URL}/query"
ONEC_SAVE_DOC_URL = f"{ONEC_BASE_URL}/save_doc"
ONEC_SAVE_CAT_URL = f"{ONEC_BASE_URL}/save_cat"
ONEC_ACTION_URL = f"{ONEC_BASE_URL}/call"
ONEC_METADATA_OBJECTS_URL = f"{ONEC_BASE_URL}/metadata_objects"
ONEC_METADATA_DESCRIBE_URL = f"{ONEC_BASE_URL}/metadata_describe"
ONEC_TOKEN = os.getenv("ONEC_TOKEN", "")
ONEC_PHOTOS_DIR = os.getenv("ONEC_PHOTOS_DIR", "")
ONEC_CF_MODULE_MANIFEST = os.getenv("ONEC_CF_MODULE_MANIFEST", "")

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "guest")
RABBITMQ_VHOST = os.getenv("RABBITMQ_VHOST", "/")
RABBITMQ_INPUT_QUEUE = os.getenv("RABBITMQ_INPUT_QUEUE", "input.events")
RABBITMQ_ERROR_QUEUE = os.getenv("RABBITMQ_ERROR_QUEUE", "sys_error.queue")

RABBITMQ_PARAMETERS = pika.ConnectionParameters(
    host=RABBITMQ_HOST,
    port=RABBITMQ_PORT,
    virtual_host=RABBITMQ_VHOST,
    credentials=pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS),
)

error_logger = ErrorLogger(
    f"amqp://{RABBITMQ_USER}:{RABBITMQ_PASS}@{RABBITMQ_HOST}:{RABBITMQ_PORT}/{RABBITMQ_VHOST}",
    queue_name=RABBITMQ_ERROR_QUEUE,
)


# ── Версія API ────────────────────────────────────────────────
# Джерело правди — перший рядок VERSION.md (формат "## 1.1.001 2026-05-22").
# Читається ОДИН РАЗ при старті процесу (імпорт цього модуля) і кешується
# в пам'яті на весь час його життя — так само, як версія HTML фіксується
# в момент запису файлу, а не переобчислюється на кожен запит. Це свідомо:
# сенс версії API — "який код зараз реально виконується цим процесом",
# а не "що зараз лежить у VERSION.md на диску".
_VERSION_MD_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "VERSION.md"
)
_VERSION_LINE_RE = re.compile(r"^##\s*([\w.\-]+)\s+(\d{4}-\d{2}-\d{2})", re.MULTILINE)


def _read_api_version():
    try:
        with open(_VERSION_MD_PATH, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return None, None
    m = _VERSION_LINE_RE.search(content)
    return (m.group(1), m.group(2)) if m else (None, None)


API_VERSION, API_VERSION_DATE = _read_api_version()