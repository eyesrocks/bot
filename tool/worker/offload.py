from __future__ import annotations

import asyncio
import os
from contextlib import suppress
from functools import partial
from typing import Awaitable, Callable, TypeVar
from typing_extensions import ParamSpec

import distributed.client
from tornado import gen
from loguru import logger
from .dask import get_dask, start_dask

P = ParamSpec("P")
T = TypeVar("T")


def strtobool(val: str | None) -> bool:
    if not val:
        return False
    val = str(val).strip().lower()
    if val in {"y", "yes", "t", "true", "on", "1"}:
        return True
    elif val in {"n", "no", "f", "false", "off", "0"}:
        return False
    else:
        raise ValueError(f"Invalid truth value: {val!r}")


DEBUG = strtobool(os.getenv("DEBUG", "OFF"))


@gen.coroutine
def cascade_future(dask_future: distributed.Future, cf_future: asyncio.Future):
    try:
        result = yield dask_future._result(raiseit=False)
        status = dask_future.status

        if status == "finished":
            with suppress(asyncio.InvalidStateError):
                cf_future.set_result(result)
        elif status == "cancelled":
            cf_future.cancel()
            cf_future.set_running_or_notify_cancel()
        else:
            try:
                exc_type, exc_value, traceback = result
                raise exc_value.with_traceback(traceback)
            except BaseException as exc:
                cf_future.set_exception(exc)
    except Exception as e:
        logger.exception("Error in cascading future: {}", e)
        cf_future.set_exception(e)


def cf_callback(cf_future: asyncio.Future):
    dask_future = getattr(cf_future, "dask_future", None)
    if cf_future.cancelled() and dask_future and dask_future.status != "cancelled":
        asyncio.ensure_future(dask_future.cancel())


def offloaded(f: Callable[P, T]) -> Callable[P, Awaitable[T]]:
    async def offloaded_task(*args: P.args, **kwargs: P.kwargs) -> T:
        loop = asyncio.get_running_loop()
        cf_future = loop.create_future()
        dask_client = get_dask()

        if not dask_client or dask_client.status == "closed":
            logger.info("Dask client is closed or unavailable. Restarting Dask...")
            await start_dask()

        dask_future = dask_client.submit(partial(f, *args, **kwargs), pure=False)
        cf_future.dask_future = dask_future
 
        dask_future.add_done_callback(lambda _: cf_callback(cf_future))
        cascade_future(dask_future, cf_future)

        return await cf_future

    return offloaded_task
