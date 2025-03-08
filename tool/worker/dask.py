import distributed
import asyncio
import os
import psutil
from tornado import gen
from typing import Callable
from loguru import logger
import os
import logging

GLOBAL_DASK = {}


def get_dask() -> distributed.Client:
    client = GLOBAL_DASK.get("client")
    # Check if client exists and is in a usable state
    if client is not None and client.status not in ("closed", "closing"):
        return client
    return None


async def start_dask(bot, address: str) -> distributed.Client:
    # First check if we already have a valid client
    client = get_dask()
    if client is not None:
        logger.info("Using existing Dask client")
        return client

    # If there's an invalid client in the global dict, clean it up
    if "client" in GLOBAL_DASK:
        old_client = GLOBAL_DASK["client"]
        try:
            if old_client.status not in ("closed", "closing"):
                await old_client.close()
        except Exception:
            pass  # Ignore errors when closing an already problematic client
        GLOBAL_DASK.pop("client", None)

    scheduler_file = "scheduler.json"

    # Check if port 8787 is already in use
    port_in_use = any(conn.laddr.port == 8787 for conn in psutil.net_connections())

    max_attempts = 5
    for attempt in range(max_attempts):
        try:
            if port_in_use:
                logger.info(f"Port in use, binding to existing Dask scheduler...")
                client = await distributed.Client(
                    scheduler_file=scheduler_file,
                    asynchronous=True,
                    name="greed",
                    set_as_default=True,
                )
            else:
                # Optimize worker configuration
                n_workers = psutil.cpu_count(logical=False)  # Use physical cores
                threads_per_worker = 2  # Balance between parallelism and overhead
                memory_limit = "16GB"  # Adjust based on system memory

                client = await distributed.Client(
                    distributed.LocalCluster(
                        dashboard_address="127.0.0.1:8787",
                        asynchronous=True,
                        processes=True,
                        n_workers=n_workers,
                        threads_per_worker=threads_per_worker,
                        memory_limit=memory_limit,
                        lifetime="1h",  # Restart workers periodically to prevent memory leaks
                        lifetime_stagger="5m",  # Stagger restarts
                        worker_class="distributed.Worker",  # Use process-based workers
                        silence_logs=logging.WARNING,  # Reduce log noise
                    ),
                    direct_to_workers=True,
                    asynchronous=True,
                    name="greed",
                    set_as_default=True,
                )
                client.write_scheduler_file(scheduler_file)

            # Verify client is in a good state
            if client.status == "running":
                GLOBAL_DASK["client"] = client
                logger.info("Dask client started successfully")
                return client
            else:
                logger.warning(f"Dask client in unexpected state: {client.status}")
                await asyncio.sleep(1)
        except Exception as e:
            logger.error(
                f"Error starting Dask client (attempt {attempt+1}/{max_attempts}): {e}"
            )
            if attempt == max_attempts - 1:
                raise
            await asyncio.sleep(3)

    raise RuntimeError("Failed to start Dask client after multiple attempts")


def submit_coroutine(func: Callable, *args, **kwargs):
    worker_loop: asyncio.AbstractEventLoop = distributed.get_worker().loop.asyncio_loop
    task = asyncio.run_coroutine_threadsafe(func(*args, **kwargs), loop=worker_loop)
    return task.result()
