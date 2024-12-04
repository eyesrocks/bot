import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Callable, Coroutine, Optional
from discord.ext import commands
from watchfiles import Change, awatch  # type: ignore


class RebootRunner:
    """Manages cog reloading and file change watching for a Discord bot."""

    def __init__(
        self,
        client: commands.Bot,
        path: str = "commands",
        debug: bool = True,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        default_logger: bool = True,
        preload: bool = False,
        auto_commit: bool = True,
        colors: bool = True,
    ) -> None:
        self.client: commands.Bot = client
        self.path: Path = Path(path).resolve()  # Ensure absolute path
        self.debug: bool = debug
        self.loop: asyncio.AbstractEventLoop = loop or asyncio.get_event_loop()
        self.default_logger: bool = default_logger
        self.preload: bool = preload
        self.auto_commit: bool = auto_commit
        self.started: bool = False
        self.colors: bool = colors
        self._setup_logger()

    def _setup_logger(self) -> None:
        """Configures the logger."""
        self.logger: logging.Logger = logging.getLogger("RebootRunner")
        if self.default_logger:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(
                logging.Formatter("[%(name)s] %(levelname)s: %(message)s")
            )
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.DEBUG if self.debug else logging.INFO)

    @staticmethod
    def get_cog_name(file_path: Path) -> str:
        """Extracts the cog name from a file path."""
        return file_path.stem

    def get_dotted_path(self, file_path: Path) -> str:
        """Generates the dotted module path for a cog."""
        try:
            relative_path: Path = file_path.relative_to(self.path.parent)
            return ".".join(relative_path.with_suffix("").parts)
        except ValueError:
            raise ValueError(f"Invalid path: {file_path} not within {self.path.parent}")

    async def start(self) -> bool:
        """Initializes the cog watcher."""
        if self.started:
            self.logger.warning("Watcher already started.")
            return False
        if not self.path.exists() or not self.path.is_dir():
            self.logger.error(f"Directory {self.path} does not exist or is not valid.")
            return False

        if self.preload:
            await self._preload_cogs()

        if self.debug or not __debug__:
            self.logger.info(f"Watching directory: {self.path}")
            self.loop.create_task(self._watch_cogs())

        self.started = True
        return True

    async def _watch_cogs(self) -> None:
        """Monitors the directory for file changes and handles reloads."""
        async for changes in awatch(self.path):
            for change_type, file_path in changes:
                file_path = Path(file_path)
                if file_path.suffix != ".py":
                    continue
                try:
                    cog_name: str = self.get_cog_name(file_path)
                    cog_path: str = self.get_dotted_path(file_path)

                    if change_type == Change.deleted:
                        await self._unload_cog(cog_path)
                    elif change_type == Change.added:
                        await self._load_cog(cog_path)
                    elif change_type == Change.modified:
                        await self._reload_cog(cog_path)
                except Exception as e:
                    self.logger.error(f"Error processing change {change_type} for {file_path}: {e}")

    async def _preload_cogs(self) -> None:
        """Loads all cogs on startup."""
        self.logger.info("Preloading cogs...")
        for file in self.path.rglob("*.py"):
            cog_path: str = self.get_dotted_path(file)
            await self._load_cog(cog_path)

    async def _load_cog(self, cog_path: str) -> None:
        """Loads a cog."""
        try:
            await self.client.load_extension(cog_path)
            self.logger.info(f"Loaded cog: {cog_path}")
        except commands.ExtensionAlreadyLoaded:
            self.logger.info(f"Cog already loaded: {cog_path}")
        except commands.ExtensionFailed as e:
            self.logger.error(f"Failed to load cog {cog_path}: {e}")

    async def _unload_cog(self, cog_path: str) -> None:
        """Unloads a cog."""
        try:
            await self.client.unload_extension(cog_path)
            self.logger.info(f"Unloaded cog: {cog_path}")
        except commands.ExtensionNotLoaded:
            self.logger.warning(f"Cog not loaded: {cog_path}")

    async def _reload_cog(self, cog_path: str) -> None:
        """Reloads a cog."""
        if self.auto_commit:
            await self._auto_commit_changes()
        try:
            await self.client.reload_extension(cog_path)
            self.logger.info(f"Reloaded cog: {cog_path}")
        except commands.ExtensionNotLoaded:
            self.logger.info(f"Cog not loaded, loading instead: {cog_path}")
            await self._load_cog(cog_path)
        except commands.ExtensionFailed as e:
            self.logger.error(f"Failed to reload cog {cog_path}: {e}")

    async def _auto_commit_changes(self) -> None:
        """Automatically commits changes using git."""
        try:
            process = await asyncio.create_subprocess_shell(
                "git add . && git commit -m 'Auto commit' && git push --force",
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await process.communicate()
            if stderr:
                self.logger.warning(f"Git error: {stderr.decode()}")
        except Exception as e:
            self.logger.error(f"Git commit failed: {e}")


def watch(**kwargs: Any) -> Callable[[Callable[[commands.Bot], Coroutine[Any, Any, Any]]], Callable[[commands.Bot], Coroutine[Any, Any, Any]]]:
    """Decorator for initializing and starting a RebootRunner."""
    def decorator(func: Callable[[commands.Bot], Coroutine[Any, Any, Any]]) -> Callable[[commands.Bot], Coroutine[Any, Any, Any]]:
        @wraps(func)
        async def wrapper(client: commands.Bot) -> Any:
            runner = RebootRunner(client, **kwargs)
            if await runner.start():
                return await func(client)
        return wrapper
    return decorator
