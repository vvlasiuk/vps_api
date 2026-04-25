# Utility for sending commands to RabbitMQ
import pika
import json

def send_command_to_rabbitmq(queue_name: str, message: dict, connection_parameters: pika.ConnectionParameters):
    connection = pika.BlockingConnection(connection_parameters)
    channel = connection.channel()
    channel.basic_publish(
        exchange=queue_name,
        routing_key=queue_name,
        body=json.dumps(message),
        properties=pika.BasicProperties(delivery_mode=2)
    )
    connection.close()
