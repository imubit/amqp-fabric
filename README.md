# amqp-fabric

AMQP Fabric is an AMQP based microservice orchestration and communication framework.

## Description

Microservice Bridge is a very simple microservice orchestration mechanism based on AMQ protocol.

It supports:

* Micro-service communication via synchronous API (RPC)
* Asynchronous data transmission
* Decentralized registry
* Remote logging
* High-availability

## Installation

```bash
pip install amqp-fabric
```

## Getting Started


### Server Side


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


### Client Side


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

    result = await srv_proxy.func(method_name='multiply', kwargs={'x': 5, 'y': 7}, expiration=3)
    print(f'result = {result}')

    await amq.close()


if __name__ == '__main__':

    task = exec_multiply()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(task)

```
