[![PyPI-Server](https://img.shields.io/pypi/v/amqp-fabric.svg)](https://pypi.org/project/amqp-fabric/)
[![Coveralls](https://img.shields.io/coveralls/github/imubit/amqp-fabric/main.svg)](https://coveralls.io/r/imubit/amqp-fabric)
[![Wheel](https://img.shields.io/pypi/wheel/amqp-fabric.svg)](https://pypi.python.org/pypi/amqp-fabric/)
[![PyVersions](https://img.shields.io/pypi/pyversions/amqp-fabric.svg)](https://pypi.python.org/pypi/amqp-fabric/)

# amqp-fabric

AMQP Fabric is an AMQP based "one-stop-shop" microservice orchestration and communication framework.

## Description

AMQP Fabric is a very simple microservice communication and orchestration mechanism based on AMQ protocol. Instead of
relying on multiple technologies and orchestration frameworks - it's a "one-stop shop" library for implementing a
light-weight microservices topology.

Each service in the ecosystem can publish its own API and use API of another service. A service can send an
asynchronous stream of data that other services can subscribe to.
Services can optionally send periodic "keep-alives" to allow tracking its uptime.

## Features

* Microservice communication via synchronous API (RPC)
* Asynchronous data transmission
* Decentralized registry
* Remote logging based on standard Python logging mechanism
* High-availability
* Secure and firewall friendly access from remote locations

## Installation

```bash
pip install amqp-fabric
```

## Getting Started

Each service participating in the ecosystem is assigned with:
 * "Domain" - (i.e. `project1`) any string identifying a group services communicating with each other. Different domains can co-exist under the same AMQP broker.
 * "Service Type" - (i.e. `media_encoder`) - services holding the same service type, should have the same API.
 * "Service Id" - (i.e. `encoder1`) Multiple services of the same type can be distinguished by a different Id.
 * "Service Version" - evolution of the services and their API should be tracked by a version

### High Availability

Multiple services with the same Domain, Type and Id - will create a high-availability "clique" - API calls will be
redirected to the next available service.


### Server Side Example


```python
import asyncio
from amqp_fabric.amq_broker_connector import AmqBrokerConnector
from amqp_fabric.abstract_service_api import AbstractServiceApi

# API Definition
class MyServiceApi(AbstractServiceApi):

    def multiply(self, x, y):
        return x * y


class MyService:

    amq = None

    async def init(self):

        self.amq = AmqBrokerConnector(
            amqp_uri="amqp://guest:guest@127.0.0.1/",
            service_domain="my_project",
            service_id="my_app",
            service_type="server_app",
            keep_alive_seconds=5)
        await self.amq.open(timeout=10)

        api = MyServiceApi()
        await self.amq.rpc_register(api)

    async def close(self):
        await self.amq.close()


def run_event_loop():
    agent = MyService()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(agent.init())

    try:
        loop.run_forever()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        loop.run_until_complete(agent.close())
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()

if __name__ == "__main__":

    run_event_loop()
```


### Client Side Example


```python
import asyncio
from amqp_fabric.amq_broker_connector import AmqBrokerConnector


async def exec_multiply():

    amq = AmqBrokerConnector(
        amqp_uri="amqp://guest:guest@127.0.0.1/",
        service_domain="my_project",
        service_id="my_client",
        service_type="client_app",
        keep_alive_seconds=5)
    await amq.open(timeout=10)


    srv_proxy = await amq.rpc_proxy("my_project", "my_app", "server_app")

    result = await srv_proxy.multiply(x=5, y=7)
    print(f'result = {result}')

    await amq.close()


if __name__ == '__main__':

    task = exec_multiply()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(task)

```


### Uptime Tracking

```amq.list_services``` will return a list of currently available services. The list can optionally be filtered, by
service domain and/or service type.


### Publishing and Subscribing to asynchronous data streams

Data can be published along with one or more headers which can later be used to filter the received messages:

```python

items={'msg': 'Checkout committed', 'order_total': 55, 'products':['book']}

encoded_msg = json.dumps(items, sort_keys=True, default=str).encode()

amq.publish_data(encoded_msg,
                 headers={'msg_type': 'CUSTOMER_TRANSACTIONS', 'currency': 'USD'})
```

```python
amq.subscribe_data(subscriber_name='accountant',
                   headers={'msg_type': 'CUSTOMER_TRANSACTIONS'},
                   callback=process_data)
```

### Using logs

TBD
