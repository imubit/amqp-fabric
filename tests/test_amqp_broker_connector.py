import asyncio
import datetime as dt
import json

import pytest
from aio_pika import IncomingMessage, connect_robust
from aio_pika.exceptions import MessageProcessError
from aio_pika.patterns.rpc import JsonRPCError
from conftest import (
    AMQP_URL,
    RPC_EXCHANGE_NAME,
    SERVICE_DOMAIN,
    SERVICE_ID,
    SERVICE_TYPE,
)

from amqp_fabric.abstract_service_api import AbstractServiceApi
from amqp_fabric.amq_broker_connector import AmqBrokerConnector, CustomJsonRPC


class TestApi(AbstractServiceApi):
    class SomeException(Exception):
        pass

    def multiply(self, x, y):
        return x * y

    def something_wrong(self):
        raise TestApi.SomeException("there is a problem here")


@pytest.mark.asyncio
async def test_rpc_server():
    api = TestApi()

    srv_conn = AmqBrokerConnector(
        amqp_uri=AMQP_URL,
        service_domain=SERVICE_DOMAIN,
        service_type=SERVICE_TYPE,
        service_id=SERVICE_ID,
    )
    await srv_conn.open()

    assert srv_conn.fqn == f"{SERVICE_DOMAIN}.{SERVICE_TYPE}.{SERVICE_ID}"
    assert srv_conn.service_id == SERVICE_ID
    assert srv_conn.service_type == SERVICE_TYPE
    assert srv_conn.domain == SERVICE_DOMAIN
    assert srv_conn.data_exchange == f"{SERVICE_DOMAIN}.data"

    # Init server
    await srv_conn.rpc_register(api)

    client_conn = await connect_robust(
        AMQP_URL,
        client_properties={"connection_name": "caller"},
    )

    async with client_conn:
        # Creating channel
        channel = await client_conn.channel()

        rpc = await CustomJsonRPC.create(channel, exchange=RPC_EXCHANGE_NAME)

        # Creates tasks by proxy object
        for i in range(100):
            assert await rpc.proxy.multiply(x=100, y=i) == 100 * i

        # Or using create_task method
        for i in range(100):
            assert await rpc.call("multiply", kwargs=dict(x=100, y=i)) == 100 * i

        # Call invalid function
        with pytest.raises(MessageProcessError):
            await rpc.proxy.abc(x=100)

        # Wrong argument
        with pytest.raises(TypeError):
            await rpc.proxy.multiply(c=100)

        # API exception
        with pytest.raises(JsonRPCError) as exp:
            await rpc.proxy.something_wrong()

        assert (
            exp.value.args[1]["error"]["type"]
            == "test_amqp_broker_connector.SomeException"
        )

        # Cleanup
        await client_conn.close()

    await srv_conn.close()


@pytest.mark.asyncio
async def test_rpc_server_invalid_exchange():
    api = TestApi()

    srv_conn = AmqBrokerConnector(
        amqp_uri=AMQP_URL,
        service_domain=SERVICE_DOMAIN,
        service_type=SERVICE_TYPE,
        service_id=SERVICE_ID,
    )
    await srv_conn.open()

    # Init server
    await srv_conn.rpc_register(api)

    client_conn = await connect_robust(
        AMQP_URL,
        client_properties={"connection_name": "caller"},
    )

    async with client_conn:
        # Creating channel
        channel = await client_conn.channel()

        rpc = await CustomJsonRPC.create(channel, exchange="NON_EXIST")

        # Creates tasks by proxy object
        with pytest.raises(MessageProcessError):
            await rpc.proxy.multiply(x=100, y=1)

        # Clienup
        await client_conn.close()

    await srv_conn.close()


@pytest.mark.asyncio
async def test_list_services():
    srv_id = "test-srv"
    srv_type = "test-type"
    api = TestApi()

    # Init server
    srv_conn = AmqBrokerConnector(
        amqp_uri=AMQP_URL,
        service_domain=SERVICE_DOMAIN,
        service_type=srv_type,
        service_id=srv_id,
        keep_alive_seconds=1,
    )
    await srv_conn.open()
    await srv_conn.rpc_register(api)

    # Init client
    client_id = "client1"
    client_type = "client_type"
    client_conn = AmqBrokerConnector(
        amqp_uri=AMQP_URL,
        service_domain=SERVICE_DOMAIN,
        service_type=client_type,
        service_id=client_id,
        keep_alive_seconds=1,
        keep_alive_listen=True,
        discovery_cache_ttl=2,
    )
    await client_conn.open()

    # Test server for health
    proxy = await client_conn.rpc_proxy(SERVICE_DOMAIN, srv_id, srv_type)
    assert await proxy.health_check()

    # List services
    await asyncio.sleep(1.5)
    assert client_conn.list_services() == [
        {"domain": "some-domain", "type": "test-type", "id": "test-srv"},
        {"domain": "some-domain", "type": "client_type", "id": "client1"},
    ]
    assert client_conn.list_services(service_type=srv_type) == [
        {"domain": "some-domain", "type": "test-type", "id": "test-srv"}
    ]
    assert client_conn.list_services(service_domain=SERVICE_DOMAIN) == [
        {"domain": "some-domain", "type": "test-type", "id": "test-srv"},
        {"domain": "some-domain", "type": "client_type", "id": "client1"},
    ]

    await srv_conn.close()

    await asyncio.sleep(2.1)

    assert client_conn.list_services() == [
        {"domain": "some-domain", "type": "client_type", "id": "client1"}
    ]

    await client_conn.close()


@pytest.mark.asyncio
async def test_keepalive_subscribe():
    srv_id = "test-srv"
    srv_type = "test-type"
    api = TestApi()

    # Init server
    srv_conn = AmqBrokerConnector(
        amqp_uri=AMQP_URL,
        service_domain=SERVICE_DOMAIN,
        service_type=srv_type,
        service_id=srv_id,
        keep_alive_seconds=1,
    )
    await srv_conn.open()
    await srv_conn.rpc_register(api)

    # Init client
    client_id = "client1"
    client_type = "client_type"
    client_conn = AmqBrokerConnector(
        amqp_uri=AMQP_URL,
        service_domain=SERVICE_DOMAIN,
        service_type=client_type,
        service_id=client_id,
        keep_alive_seconds=1,
        keep_alive_listen=True,
        discovery_cache_ttl=2,
    )
    await client_conn.open()

    async def on_service_keepalive(headers):
        print(headers)

    client_conn.subscribe_service_keepalives(
        "dummy", on_service_keepalive, service_type=srv_type
    )

    await asyncio.sleep(2.1)

    await srv_conn.close()
    await client_conn.close()


@pytest.mark.asyncio
async def test_publish_data():
    srv_id = "test-srv"
    srv_type = "test-type"
    api = TestApi()

    # Init server
    srv_conn = AmqBrokerConnector(
        amqp_uri=AMQP_URL,
        service_domain=SERVICE_DOMAIN,
        service_type=srv_type,
        service_id=srv_id,
        keep_alive_seconds=1,
    )
    await srv_conn.open()
    await srv_conn.rpc_register(api)

    # Init client
    client_id = "client1"
    client_type = "client_type"
    client_conn = AmqBrokerConnector(
        amqp_uri=AMQP_URL,
        service_domain=SERVICE_DOMAIN,
        service_type=client_type,
        service_id=client_id,
        keep_alive_seconds=1,
        keep_alive_listen=True,
        discovery_cache_ttl=2,
    )
    await client_conn.open()

    # Mock callback
    publish_headers = {"header1": "header_value"}
    subscribe_headers = {
        "header1": "header_value",
        "service_id": srv_id,
        "service_type": srv_type,
    }

    global message_received
    message_received = False

    async def on_new_data(message: IncomingMessage):
        global message_received
        message_received = True

    # Mock callback
    # callback_mock = AsyncMock()
    # await callback_mock("foo", bar=123)

    # callback_mock.my_method.assert_called_with("foo", bar=123)
    await client_conn.subscribe_data(
        "client", headers=subscribe_headers, callback=on_new_data
    )
    msg = {
        "field1": "some_data",
        "field2": 6,
        "field3": None,
        "field4": dt.datetime(2021, 7, 22, 20, 33, 14, 492753),
        "field5": {"a": "b"},
    }

    encoded_msg = json.dumps(msg, sort_keys=True, default=str).encode()

    srv_conn.publish_data(encoded_msg, headers=publish_headers)
    await asyncio.sleep(0.1)

    assert message_received

    # Test non existing header
    message_received = False
    publish_headers["header1"] = "non-existing"
    srv_conn.publish_data(encoded_msg, headers=publish_headers)
    await asyncio.sleep(0.1)

    assert not message_received

    # callback_mock.assert_called_with(message='msg')
    # assert _test_value['exchange'] == 'some-domain.data'
    # assert _test_value['headers'] == {'header1': b'header_value', 'service_id': b'test-srv'}

    await srv_conn.close()
    await client_conn.close()
