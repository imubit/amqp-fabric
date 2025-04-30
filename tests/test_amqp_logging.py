import asyncio

# import mock
import logging

import pytest
from aio_pika import IncomingMessage, connect_robust
from conftest import AMQP_URL, SERVICE_DOMAIN

from amqp_fabric.amq_broker_connector import AmqBrokerConnector
from amqp_fabric.logging_amqp_handler import AmqpHandler


@pytest.mark.asyncio
async def test_publish_log():
    srv_id = "test-srv"
    srv_type = "test-type"
    log_exchange_name = f"{SERVICE_DOMAIN}.log.records"

    log = logging.getLogger("test_app")
    log.setLevel(logging.DEBUG)

    # Init server
    srv_conn = AmqBrokerConnector(
        amqp_uri=AMQP_URL,
        service_domain=SERVICE_DOMAIN,
        service_type=srv_type,
        service_id=srv_id,
        keep_alive_seconds=1,
    )
    await srv_conn.open()

    ah = AmqpHandler()
    ah.setLevel(logging.INFO)
    log.addHandler(ah)
    await srv_conn.init_logging_handler(ah)

    await asyncio.sleep(0.1)

    # Init client
    global message_received
    message_received = False

    async def on_new_log_msg(message: IncomingMessage):
        global message_received
        message_received = True

    client_conn = await connect_robust(
        url=AMQP_URL, client_properties={"connection_name": "log_client"}, timeout=2
    )

    channel = await client_conn.channel()
    queue = await channel.declare_queue(auto_delete=True)

    await queue.bind(log_exchange_name)
    await queue.consume(on_new_log_msg)

    await asyncio.sleep(0.1)

    log.info("hi there")

    await asyncio.sleep(1)

    assert message_received

    await srv_conn.close()
    await client_conn.close()
