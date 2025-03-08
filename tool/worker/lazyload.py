from __future__ import annotations

import asyncio
import functools
import inspect
import warnings
from copy import deepcopy
from typing import Any, Callable, Dict, List, Optional, Set, TypeVar, Union, Sequence
from typing_extensions import ParamSpec
from dataclasses import dataclass, field
import graphviz
from loguru import logger
import dask
from dask.delayed import Delayed
from .dask import get_dask, start_dask

P = ParamSpec("P")
T = TypeVar("T")

GLOBAL_DELAYED_CACHE: Dict[str, Any] = {}

class LazyResult:
    """
    Represents a lazy computation result using Dask's delayed functionality.
    
    Best Practices:
    1. Always call lazy on functions, not on their results
    2. Collect multiple computations and compute them at once
    3. Avoid mutating input data
    4. Avoid global state
    5. Always ensure your lazy computations are eventually computed
    6. Break computations into appropriate-sized tasks (not too big, not too small)
    
    Example:
        @lazy
        def process_data(x):
            return x + 1
        
        # Create multiple lazy computations
        results = []
        for x in range(10):
            y = process_data(x)
            results.append(y)
        
        # Compute all results at once
        final_results = await compute_many(*results)
    """
    def __init__(
        self, 
        func: Callable,
        args: tuple,
        kwargs: dict,
        key: Optional[str] = None,
        pure: bool = True,
        batch_size: Optional[int] = None
    ):
        # Input validation
        if isinstance(func, LazyResult):
            raise ValueError(
                "Cannot create a lazy computation from an already lazy result. "
                "Use the original function with lazy decorator instead."
            )
        
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.key = key or f"{func.__name__}_{id(self)}"
        self.pure = pure
        self.batch_size = batch_size
        
        # Convert args and kwargs to delayed objects if they're LazyResults
        self.delayed_args = tuple(
            arg.delayed if isinstance(arg, LazyResult) else 
            dask.delayed(arg, pure=True) if self._should_delay(arg) else arg 
            for arg in args
        )
        
        self.delayed_kwargs = {
            k: v.delayed if isinstance(v, LazyResult) else 
            dask.delayed(v, pure=True) if self._should_delay(v) else v 
            for k, v in kwargs.items()
        }
        
        # Create the delayed object
        if inspect.iscoroutinefunction(func):
            # For coroutines, we need special handling
            self.delayed = dask.delayed(self._run_coroutine, pure=pure)(
                func, self.delayed_args, self.delayed_kwargs
            )
        else:
            self.delayed = dask.delayed(func, pure=pure)(
                *self.delayed_args, **self.delayed_kwargs
            )

    @staticmethod
    def _should_delay(obj: Any) -> bool:
        """Determines if an object should be wrapped in dask.delayed."""
        return (
            not isinstance(obj, (str, int, float, bool, type(None))) and
            hasattr(obj, '__dict__')
        )

    @staticmethod
    async def _run_coroutine(func: Callable, args: tuple, kwargs: dict) -> Any:
        """Helper to run coroutines in Dask."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return await func(*args, **kwargs)
        finally:
            loop.close()

    def visualize(self, filename: str = "task_graph") -> None:
        """Visualizes the computation graph using Dask's built-in visualization."""
        return self.delayed.visualize(filename=filename)

    async def compute(self) -> Any:
        """
        Computes the result of this lazy computation.
        
        Returns:
            The computed result
        """
        # Get or start Dask client
        dask_client = get_dask()
        if dask_client is None:
            dask_client = await start_dask("greed", "127.0.0.1:8787")
            
        try:
            # Use the Dask client for computation
            future = dask_client.compute(self.delayed)
            result = await future
            return result
        except Exception as e:
            logger.error(f"Error computing task {self.key}: {str(e)}")
            raise

def lazy(
    func: Optional[Callable[P, T]] = None,
    pure: bool = True,
    key: Optional[str] = None,
    batch_size: Optional[int] = None
) -> Union[Callable[P, LazyResult], LazyResult]:
    """
    Decorator that creates a lazy version of a function using Dask delayed.
    
    Args:
        func: The function to make lazy
        pure: Whether the function is pure (same inputs always give same outputs)
        key: Optional key to identify the task
        batch_size: Optional batch size for processing large sequences
    
    Returns:
        A wrapped function that returns a LazyResult instead of computing immediately
        
    Example:
        @lazy
        def process_data(x):
            return x + 1
            
        # This won't compute immediately
        result = process_data(5)
        
        # This will trigger computation
        value = await result.compute()
    """
    def decorator(f: Callable[P, T]) -> Callable[P, LazyResult]:
        @functools.wraps(f)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> LazyResult:
            return LazyResult(
                func=f,
                args=args,
                kwargs=kwargs,
                key=key or f"{f.__name__}_{id(wrapper)}",
                pure=pure,
                batch_size=batch_size
            )
        return wrapper

    if func is None:
        return decorator
    return decorator(func)

async def compute_many(*tasks: LazyResult) -> List[Any]:
    """
    Compute multiple lazy results efficiently using Dask.
    
    Args:
        *tasks: LazyResult objects to compute
        
    Returns:
        List of computed results
    """
    # Get or start Dask client
    dask_client = get_dask()
    if dask_client is None:
        dask_client = await start_dask("greed", "127.0.0.1:8787")

    try:
        # Collect all delayed objects
        delayed_tasks = [task.delayed for task in tasks]
        
        # Compute all tasks at once
        futures = dask_client.compute(delayed_tasks)
        results = await futures
        
        return list(results)
    except Exception as e:
        logger.error(f"Error in compute_many: {str(e)}")
        raise

def clear_cache() -> None:
    """Clears the global computation cache."""
    GLOBAL_DELAYED_CACHE.clear()
