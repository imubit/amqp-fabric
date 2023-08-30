import asyncio as aio
import json
import logging

from aio_pika import ExchangeType, Message


class AmqpHandler(logging.Handler):
    """
    A handler that acts as a RabbitMQ publisher
    Requires the kombu module.

    Example setup::

       handler = RabbitMQHandler('amqp://guest:guest@localhost//', queue='my_log')
    """

    def __init__(self):
        logging.Handler.__init__(self)
        self._service_domain = ""
        self._service_type = ""
        self._service_id = ""
        self._log_exchange_name = ""
        self._log_exchange = None

    async def init_connection(self, conn, service_domain, service_type, service_id):
        self._service_domain = service_domain
        self._service_type = service_type
        self._service_id = service_id
        self._log_exchange_name = f"{self._service_domain}.log.records"

        channel = await conn.channel()
        self._log_exchange = await channel.declare_exchange(
            name=self._log_exchange_name, type=ExchangeType.HEADERS, durable=True
        )

    def emit(self, record):
        if not self._log_exchange:
            return

        arguments = {
            "service_id": self._service_id,
            "service_type": self._service_type,
            "level_name": record.levelname,
        }

        # entry = {
        #     'msg': record.getMessage(),
        #     'funcName': record.funcName,
        #     'lineno': record.lineno,
        #     'levelname': record.levelname,
        #     'pathname': record.pathname
        # }
        # print(entry)

        aio.create_task(
            self._log_exchange.publish(
                message=Message(
                    body=json.dumps(
                        record.getMessage(), sort_keys=True, default=str
                    ).encode(),
                    headers=arguments,
                ),
                routing_key="",
            )
        )
