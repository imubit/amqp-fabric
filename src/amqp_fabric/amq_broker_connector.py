import asyncio as aio
import gzip
import json
import os
import re
from functools import wraps
from logging import getLogger
from pydoc import locate
from types import MethodType
from typing import Any

from aio_pika import ExchangeType, IncomingMessage, Message, connect_robust
from aio_pika.abc import AbstractIncomingMessage
from aio_pika.patterns import JsonRPC
from aio_pika.patterns.rpc import JsonRPCError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from cachetools import TTLCache

log = getLogger(__name__)


class CustomJsonRPC(JsonRPC):
    def serialize_exception(self, exception: Exception) -> Any:
        return {
            "error": {
                "type": f"{exception.__module__}." f"{exception.__class__.__name__}"
                if hasattr(exception, "__module__")
                else exception.__class__.__name__,
                "message": repr(exception),
                "args": exception.args,
            },
        }

    async def deserialize_message(
        self,
        message: AbstractIncomingMessage,
    ) -> Any:
        payload = await super().deserialize_message(message)
        if isinstance(payload, JsonRPCError):
            cls = locate(payload.args[1]["error"]["type"])
            if cls:
                payload = cls(
                    payload.args[1]["error"]["message"],
                    payload.args[1]["error"]["args"],
                )
        return payload


class JsonGZipRPC(CustomJsonRPC):
    CONTENT_TYPE = "application/octet-stream"

    def serialize(self, data: Any) -> bytes:
        return gzip.compress(super().serialize(data))

    def deserialize(self, data: Any) -> bytes:
        return super().deserialize(gzip.decompress(data))


MSG_TYPE_KEEP_ALIVE = "keep_alive"
MAX_DISCOVERY_CACHE_ENTRIES = os.environ.get("MAX_DISCOVERY_CACHE_ENTRIES", 100)
DISCOVERY_CACHE_TTL = os.environ.get("DISCOVERY_CACHE_TTL", 5)
DATA_EXCHANGE_NAME = os.environ.get("DATA_EXCHANGE_NAME", "data")
DISCOVERY_EXCHANGE_NAME = os.environ.get("DISCOVERY_EXCHANGE_NAME", "msc.discovery")
REGEX_FQN_PATTERN = r"^(?:[A-Za-z0-9-_]{1,63}\.){1,255}[A-Za-z0-9-_]{1,63}$"


def broker_fqn(domain, stype, sid, item=None):
    return f"{domain}.{stype}.{sid}.{item}" if item else f"{domain}.{stype}.{sid}"


def awaitify(func):
    if aio.iscoroutinefunction(func):
        return func

    """Wrap a synchronous callable to allow ``await``'ing it"""

    @wraps(func)
    async def async_func(*args, **kwargs):
        return func(*args, **kwargs)

    return async_func


class AmqBrokerConnector:
    def __init__(
        self,
        amqp_uri,
        service_domain,
        service_type,
        service_id,
        keep_alive_seconds=False,
        keep_alive_listen=False,
        discovery_cache_ttl=DISCOVERY_CACHE_TTL,
        discovery_exchange=DISCOVERY_EXCHANGE_NAME,
    ):
        if not re.match(
            REGEX_FQN_PATTERN, broker_fqn(service_domain, service_type, service_id)
        ):
            raise AttributeError("Invalid service domain/type/id pattern")

        self._amqp_uri = amqp_uri
        self._service_domain = service_domain
        self._service_id = service_id
        self._service_type = service_type
        self._keep_alive_seconds = keep_alive_seconds
        self._keep_alive_listen = keep_alive_listen
        self._discovery_cache_ttl = discovery_cache_ttl
        self._discovery_exchange_name = discovery_exchange
        self._rpc_server_exchange_name = (
            f"{service_domain}.api.{service_type}.{service_id}"
        )
        self._data_exchange_name = f"{service_domain}.{DATA_EXCHANGE_NAME}"
        self._subscriber_name = broker_fqn(
            service_domain, service_type, service_id, "subscriber"
        )
        self._broker_conn = None
        self._data_exchange = None
        self._discovery_exchange = None
        self._scheduler = None
        self._discovery_cache = None

        self._keepalive_subscriber_name = None
        self._keepalive_subscriber_callback = None
        self._keepalive_subscriber_service_domain = None
        self._keepalive_subscriber_service_type = None
        self._keepalive_subscriber_service_id = None

    @property
    def domain(self):
        return self._service_domain

    @property
    def service_type(self):
        return self._service_type

    @property
    def service_id(self):
        return self._service_id

    @property
    def data_exchange(self):
        return self._data_exchange_name

    @property
    def fqn(self):
        return broker_fqn(self._service_domain, self._service_type, self._service_id)

    async def open(self, **kwargs: Any):
        self._broker_conn = await connect_robust(
            url=self._amqp_uri,
            client_properties={"connection_name": "rpc_srv"},
            **kwargs,
        )

        # This will create the exchange if it doesn't already exist.
        channel = await self._broker_conn.channel()

        self._data_exchange = await channel.declare_exchange(
            name=self._data_exchange_name, type=ExchangeType.HEADERS, durable=True
        )
        self._discovery_exchange = await channel.declare_exchange(
            name=self._discovery_exchange_name, type=ExchangeType.HEADERS, durable=True
        )
        await aio.sleep(0.1)

        # Initialize keep-alive messages
        if self._keep_alive_seconds:
            self._scheduler = AsyncIOScheduler(
                {
                    "apscheduler.executors.service_discovery": {
                        "class": "apscheduler.executors.asyncio:AsyncIOExecutor",
                    }
                },
                logger=log,
            )

            trigger = IntervalTrigger(seconds=self._keep_alive_seconds)
            self._scheduler.add_job(
                self._on_send_keep_alive, trigger=trigger, executor="service_discovery"
            )
            self._scheduler.start()

        # Initialize keep-alive listener
        if self._keep_alive_listen:
            self._discovery_cache = TTLCache(
                maxsize=MAX_DISCOVERY_CACHE_ENTRIES, ttl=self._discovery_cache_ttl
            )
            queue = await channel.declare_queue(self._subscriber_name, auto_delete=True)
            headers = {"msg_type": MSG_TYPE_KEEP_ALIVE}

            arguments = {**{"x-match": "all"}, **headers}

            await queue.bind(self._discovery_exchange_name, arguments=arguments)
            await queue.consume(self._on_get_keep_alive)

        log.info(
            f"Endpoint '{self.fqn}' initialized on broker {self._broker_conn.url.host}:{self._broker_conn.url.port}"
        )

    async def close(self):
        if self._keep_alive_seconds:
            self._scheduler.shutdown(wait=True)
            self._scheduler = None

        await self._broker_conn.close()

    # --- Service management routines ---

    async def rpc_register(self, api):
        # Creating channel
        channel = await self._broker_conn.channel()
        await channel.set_qos(prefetch_count=1)

        rpc = await CustomJsonRPC.create(
            channel, auto_delete=True, exchange=self._rpc_server_exchange_name
        )

        for api_name in dir(api):
            callee = getattr(api, api_name)
            if isinstance(callee, MethodType) and not api_name.startswith("_"):
                log.debug("Registering '%s' API function.", api_name)
                await rpc.register(api_name, awaitify(callee), auto_delete=True)

        log.info(
            'RPC Server Registered on Exchange "{}"'.format(
                self._rpc_server_exchange_name
            )
        )

    async def rpc_proxy(self, service_domain, service_id, service_type):
        rpc_exchange = f"{service_domain}.api.{service_type}.{service_id}"

        # Creating channel
        channel = await self._broker_conn.channel()
        rpc = await CustomJsonRPC.create(
            channel, auto_delete=True, exchange=rpc_exchange
        )
        return rpc.proxy

    def list_services(self, service_domain=None, service_type=None, health_check=True):
        if self._discovery_cache is None:
            return []

        services = []
        for k in self._discovery_cache.keys():
            if service_domain and not k.startswith(service_domain):
                continue

            if service_type and f".{service_type}." not in k:
                continue

            services.append(
                {
                    "domain": k.rsplit(".")[0],
                    "type": k.rsplit(".")[1],
                    "id": k.rsplit(".")[2],
                }
            )

        return services

    def subscribe_service_keepalives(
        self,
        subscriber_name,
        callback,
        service_domain=None,
        service_type=None,
        service_id=None,
    ):
        if not self._keep_alive_listen:
            raise AssertionError(
                'Subscribing to keepalive callbacks requires enabling "keep_alive_listen" option.'
            )

        self._keepalive_subscriber_name = subscriber_name
        self._keepalive_subscriber_callback = callback
        self._keepalive_subscriber_service_domain = service_domain
        self._keepalive_subscriber_service_type = service_type
        self._keepalive_subscriber_service_id = service_id

    # --- Data routines ---

    def publish_data(self, data, headers):
        headers["service_id"] = self._service_id
        headers["service_type"] = self._service_type

        aio.create_task(
            self._data_exchange.publish(
                message=Message(
                    body=data,
                    headers=headers,
                ),
                routing_key="",
            )
        )

        log.debug(
            f"Total {len(data)} bytes published to exchange {self._data_exchange_name} with headers: {headers}"
        )

    async def subscribe_data(self, subscriber_name, headers, callback):
        channel = await self._broker_conn.channel()
        queue = await channel.declare_queue(subscriber_name, auto_delete=True)

        arguments = {**{"x-match": "all"}, **headers}

        await queue.bind(self._data_exchange_name, arguments=arguments)
        await queue.consume(callback)

    async def _on_send_keep_alive(self):
        try:
            headers = {
                "msg_type": MSG_TYPE_KEEP_ALIVE,
                "service_domain": self._service_domain,
                "service_id": self._service_id,
                "service_type": self._service_type,
            }

            aio.create_task(
                self._discovery_exchange.publish(
                    message=Message(body="".encode(), headers=headers), routing_key=""
                )
            )
        except Exception as e:
            log.error(e)

    async def _on_get_keep_alive(self, message: IncomingMessage):
        try:
            async with message.process():
                headers = dict(message.headers)
                self._discovery_cache[
                    broker_fqn(
                        headers["service_domain"],
                        headers["service_type"],
                        headers["service_id"],
                    )
                ] = (
                    json.loads(message.body) if len(message.body) else ""
                )

                # Callback coroutine
                if (
                    self._keepalive_subscriber_callback
                    and (
                        not self._keepalive_subscriber_service_domain
                        or headers["service_domain"]
                        == self._keepalive_subscriber_service_domain
                    )
                    and (
                        not self._keepalive_subscriber_service_type
                        or headers["service_type"]
                        == self._keepalive_subscriber_service_type
                    )
                    and (
                        not self._keepalive_subscriber_service_id
                        or headers["service_id"] == self._keepalive_service_service_id
                    )
                ):
                    aio.create_task(self._keepalive_subscriber_callback(headers))

        except Exception as e:
            log.error(e)

    # --- Logging routines ---

    async def init_logging_handler(self, handler):
        await handler.init_connection(
            self._broker_conn,
            self._service_domain,
            self._service_type,
            self._service_id,
        )
