import asyncio

from amqp_fabric.amq_broker_connector import AmqBrokerConnector


async def exec_multiply():
    amq = AmqBrokerConnector(
        amqp_uri="amqp://guest:guest@127.0.0.1/",
        service_domain="my_project",
        service_id="my_client",
        service_type="client_app",
        keep_alive_seconds=5,
    )
    await amq.open(timeout=10)

    srv_proxy = await amq.rpc_proxy("my_project", "my_app", "server_app")

    result = await srv_proxy.multiply(x=5, y=7)
    print(f"result = {result}")

    await amq.close()


if __name__ == "__main__":
    task = exec_multiply()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(task)
