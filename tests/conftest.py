# -*- coding: utf-8 -*-
"""
    Dummy conftest.py for amqp_fabric.

    If you don't know what this is for, just leave it empty.
    Read more about conftest.py under:
    - https://docs.pytest.org/en/stable/fixture.html
    - https://docs.pytest.org/en/stable/writing_plugins.html
"""

import os

AMQP_URL = os.environ.get("AMQP_URL", "amqp://guest:guest@localhost/")
SERVICE_ID = os.environ.get("SERVICE_ID", "amqp-fabric")
SERVICE_TYPE = os.environ.get("SERVICE_TYPE", "no-type")
SERVICE_DOMAIN = os.environ.get("SERVICE_DOMAIN", "some-domain")
RPC_EXCHANGE_NAME = os.environ.get(
    "RPC_EXCHANGE_NAME", f"{SERVICE_DOMAIN}.api.{SERVICE_TYPE}.{SERVICE_ID}"
)
DATA_EXCHANGE_NAME = os.environ.get("DATA_EXCHANGE_NAME", f"{SERVICE_DOMAIN}.daq.data")
