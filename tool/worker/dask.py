import distributed
import asyncio
import os
import psutil
from tornado import gen
from typing import Callable

try:
    GLOBAL_DASK  # type: ignore
except NameError:
    GLOBAL_DASK = {}

from loguru import logger


def get_dask() -> distributed.Client:
    return GLOBAL_DASK.get("client")

async def start_dask(bot, address: str) -> distributed.Client:
    scheduler_file = "scheduler.json"

    # Check if port 8787 is already in use
    port_in_use = any(conn.laddr.port == 8787 for conn in psutil.net_connections())

    if port_in_use:
        # Load from scheduler file
        logger.info("checking..")
        client = await distributed.Client(
            scheduler_file=scheduler_file, asynchronous=True, name=bot.user.name
        )
        logger.info("port is in use loading scheduler")
    else:
        logger.info("port not in use starting scheduler")
        # Start Dask scheduler regularly
        client = await distributed.Client(
            distributed.LocalCluster(
                dashboard_address="127.0.0.1:8787",
                asynchronous=True,
                processes=False,
                threads_per_worker=2,
                n_workers=5,
            ),
            direct_to_workers=True,
            asynchronous=True,
            name=bot.user.name,
        )
        client.write_scheduler_file(scheduler_file)

    logger.info("started client")
    # Write scheduler file
    logger.info("Dask successfully sinked and loaded!")
    GLOBAL_DASK["client"] = client
    return client


def submit_coroutine(func: Callable, *args, **kwargs):
    worker_loop: asyncio.AbstractEventLoop = distributed.get_worker().loop.asyncio_loop
    task = asyncio.run_coroutine_threadsafe(func(*args, **kwargs), loop=worker_loop)
    return task.result()
