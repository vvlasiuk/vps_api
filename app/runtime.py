import os

import pika

from .error_logger import ErrorLogger

ONEC_BASE_URL = os.getenv("ONEC_BASE_URL")
ONEC_SOURCE_NAME = os.getenv("ONEC_SOURCE_NAME", "1C_UTP")
ONEC_QUERY_URL = f"{ONEC_BASE_URL}/query"
ONEC_SAVE_DOC_URL = f"{ONEC_BASE_URL}/save_doc"
ONEC_SAVE_CAT_URL = f"{ONEC_BASE_URL}/save_cat"
ONEC_METADATA_OBJECTS_URL = f"{ONEC_BASE_URL}/metadata_objects"
ONEC_METADATA_DESCRIBE_URL = f"{ONEC_BASE_URL}/metadata_describe"
ONEC_TOKEN = os.getenv("ONEC_TOKEN", "")

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
