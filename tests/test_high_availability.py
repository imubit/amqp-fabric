import asyncio
from datetime import datetime

import pytest
from aio_pika import connect_robust
from conftest import (
    AMQP_URL,
    RPC_EXCHANGE_NAME,
    SERVICE_DOMAIN,
    SERVICE_ID,
    SERVICE_TYPE,
)

from amqp_fabric.amq_broker_connector import AmqBrokerConnector, JsonRPC


@pytest.mark.asyncio
async def test_response():
    class TestApi:
        async def print_response_service(self, val):
            print(f"{datetime.now()}: {val} - start")
            await asyncio.sleep(1)
            print(f"{datetime.now()}: {val} - finish")

    api = TestApi()

    # Init 1st server
    serv1 = AmqBrokerConnector(
        amqp_uri=AMQP_URL,
        service_domain=SERVICE_DOMAIN,
        service_type=SERVICE_TYPE,
        service_id=SERVICE_ID,
    )
    await serv1.open()
    await serv1.rpc_register(api)
    print(serv1)

    serv2 = AmqBrokerConnector(
        amqp_uri=AMQP_URL,
        service_domain=SERVICE_DOMAIN,
        service_type=SERVICE_TYPE,
        service_id=SERVICE_ID,
    )
    await serv2.open()
    await serv2.rpc_register(api)

    client_conn = await connect_robust(
        AMQP_URL,
        client_properties={"connection_name": "caller"},
    )

    async with client_conn:
        # Creating channel
        channel = await client_conn.channel()

        rpc = await JsonRPC.create(channel, exchange=RPC_EXCHANGE_NAME)

        # Tasks should be handled 2each time until 1 connection is closed.
        # if a connection was closed before the task finished - it should be executed second time
        print(f"{datetime.now()}: start")
        asyncio.create_task(rpc.proxy.print_response_service(val="hello1"))
        asyncio.create_task(rpc.proxy.print_response_service(val="hello2"))
        asyncio.create_task(rpc.proxy.print_response_service(val="hello3"))
        await serv1.close()
        print(f"{datetime.now()}: serv1 closed")
        asyncio.create_task(rpc.proxy.print_response_service(val="hello4"))
        asyncio.create_task(rpc.proxy.print_response_service(val="hello5"))
        asyncio.create_task(rpc.proxy.print_response_service(val="hello6"))
        # await rpc.proxy.print_response_service(val='hello1')
        # await rpc.proxy.print_response_service(val='hello2')
        print(f"{datetime.now()}: scheduled")

        print(f"{datetime.now()}: finish")

        await asyncio.sleep(8)

        # Clienup
        await client_conn.close()

    await serv2.close()
    # await serv1.close()
