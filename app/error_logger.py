# Error logger for file and RabbitMQ
import logging
from datetime import datetime
import pika
import json
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent

class ErrorLogger:
    def __init__(self, rabbitmq_url: str, queue_name: str = "sys_error.queue"):
        self.rabbitmq_url = rabbitmq_url
        self.queue_name = queue_name
        self.logger = logging.getLogger("api_error")
        logs_dir = project_root / "logs"
        logs_dir.mkdir(exist_ok=True)
        log_file = logs_dir / f"api_error_{datetime.now().strftime('%Y-%m-%d')}.log"
        handler = logging.FileHandler(log_file, encoding="utf-8")
        formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.ERROR)

    def log_error(self, message: str, responsibility: str = "vps_api"):
        # Log to file
        self.logger.error(message)
        # Send to RabbitMQ
        try:
            connection = pika.BlockingConnection(pika.URLParameters(self.rabbitmq_url))
            channel = connection.channel()
            channel.queue_declare(queue=self.queue_name, durable=True)
            error_msg = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "responsibility": responsibility,
                "message": message
            }
            channel.basic_publish(
                exchange='',
                routing_key=self.queue_name,
                body=json.dumps(error_msg),
                properties=pika.BasicProperties(delivery_mode=2)
            )
            connection.close()
        except Exception as e:
            self.logger.error(f"Failed to send error to RabbitMQ: {e}")
