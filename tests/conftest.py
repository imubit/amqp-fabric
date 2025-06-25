# -*- coding: utf-8 -*-
"""
    Dummy conftest.py for amqp_fabric.

    If you don't know what this is for, just leave it empty.
    Read more about conftest.py under:
    - https://docs.pytest.org/en/stable/fixture.html
    - https://docs.pytest.org/en/stable/writing_plugins.html
"""

import os
from typing import Type

import pytest
from aiomisc_pytest import TCPProxy

AMQP_HOST = os.environ.get("AMQP_HOST", "localhost")
AMQP_PORT = os.environ.get("AMQP_PORT", "5672")
AMQP_URL = os.environ.get("AMQP_URL", f"amqp://guest:guest@{AMQP_HOST}:{AMQP_PORT}/")
SERVICE_ID = os.environ.get("SERVICE_ID", "amqp-fabric")
SERVICE_TYPE = os.environ.get("SERVICE_TYPE", "no-type")
SERVICE_DOMAIN = os.environ.get("SERVICE_DOMAIN", "some-domain")
RPC_EXCHANGE_NAME = os.environ.get(
    "RPC_EXCHANGE_NAME", f"{SERVICE_DOMAIN}.api.{SERVICE_TYPE}.{SERVICE_ID}"
)
DATA_EXCHANGE_NAME = os.environ.get("DATA_EXCHANGE_NAME", f"{SERVICE_DOMAIN}.data")


@pytest.fixture
async def proxy(tcp_proxy: Type[TCPProxy]):
    p = tcp_proxy(
        AMQP_HOST,
        AMQP_PORT,
        buffered=False,
    )

    await p.start()
    try:
        yield p
    finally:
        await p.close()
