import asyncio

from amqp_fabric.abstract_service_api import AbstractServiceApi
from amqp_fabric.amq_broker_connector import AmqBrokerConnector


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
            keep_alive_seconds=5,
        )
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
