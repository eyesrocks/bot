from __future__ import annotations

import datetime
import hashlib
import aiohttp
import discord
from typing import TypedDict, Union, Optional, List
from aiohttp.web import Application, Request, Response, _run_app, json_response
import aiohttp.web
from discord.ext.commands import Cog, Group, Command
from prometheus_async import aio
import socket
from tool.greed import Greed
import urllib.parse
from config import Authorization
import asyncio


class CommandData(TypedDict):
    name: str
    description: str
    permissions: Optional[List[str]]
    bot_permissions: Optional[List[str]]
    usage: Optional[str]
    example: Optional[str]


class WebServer(Cog):
    def __init__(self, bot: Greed) -> None:
        self.bot = bot
        self.app = Application()
        self._setup_routes()
        self.server_task = None

    def _setup_routes(self) -> None:
        routes = [
            ("GET", "/", self.index),
            ("GET", "/commands", self.commands),
            ("GET", "/raw", self.command_dump),
            ("GET", "/status", self.status),
            ("GET", "/metrics", aio.web.server_stats),
            ("GET", "/callback", self.lastfm_callback),
        ]
        for method, path, handler in routes:
            self.app.router.add_route(method, path, handler)

    async def cog_load(self) -> None:
        if self.bot.connection.local_name != "cluster1":
            return
        self.server_task = self.bot.loop.create_task(self._run())

    async def cog_unload(self) -> None:
        if self.server_task:
            self.server_task.cancel()
            try:
                await self.server_task
            except asyncio.CancelledError:
                pass

        await self.app.shutdown()
        await self.app.cleanup()

    async def _run(self) -> None:
        runner = aiohttp.web.AppRunner(self.app)
        await runner.setup()
        site = aiohttp.web.TCPSite(runner, "0.0.0.0", 2027)
        self.runner = runner
        await site.start()

        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            await runner.cleanup()
            raise

    @staticmethod
    async def index(_: Request) -> Response:
        return Response(text="API endpoint operational", status=200)

    async def status(self, _: Request) -> Response:
        shards = await self.bot.ipc.roundtrip("get_shards")
        return json_response({"shards": shards})

    def _get_permissions(
        self, command: Union[Command, Group], bot: bool = False
    ) -> Optional[List[str]]:
        perms = command.bot_permissions if bot else command.permissions
        if not perms:
            return None

        permissions = []
        if isinstance(perms, list):
            permissions.extend(p.replace("_", " ").title() for p in perms)
        else:
            permissions.append(perms.replace("_", " ").title())
        return permissions

    async def command_dump(self, _: Request) -> Response:
        commands: List[CommandData] = []
        for cmd in self.bot.walk_commands():
            if (
                cmd.hidden
                or (isinstance(cmd, Group) and not cmd.description)
                or cmd.qualified_name == "help"
            ):
                continue
            commands.append(
                {
                    "name": cmd.qualified_name,
                    "description": cmd.brief,
                    "permissions": self._get_permissions(cmd),
                    "bot_permissions": self._get_permissions(cmd, True),
                    "usage": cmd.usage,
                    "example": cmd.example,
                }
            )
        return json_response(commands)

    async def commands(self, _: Request) -> Response:
        def format_command(cmd: Command, level: int = 0) -> str:
            prefix = "|    " * level
            aliases = f"({', '.join(cmd.aliases)})" if cmd.aliases else ""
            usage = f" {cmd.usage}" if cmd.usage else ""
            return f"{prefix}├── {cmd.qualified_name}{aliases}{usage}: {cmd.brief or 'No description'}"

        output = []
        for name, cog in sorted(self.bot.cogs.items(), key=lambda x: x[0].lower()):
            if name.lower() in ("jishaku", "developer"):
                continue

            commands = [
                format_command(cmd, level=1)
                for cmd in cog.walk_commands()
                if not cmd.hidden
            ]
            if commands:
                output.extend([f"┌── {name}"] + commands)

        return json_response("\n".join(output))

    async def lastfm_callback(self, request: Request) -> Response:
        """Handle the callback from LastFM OAuth authentication"""
        # This is the token returned by LastFM after authorization
        lastfm_token = request.query.get("token")
        if not lastfm_token:
            return Response(text="No token provided", status=400)

        tracking_id = request.query.get("tracking_id")
        if not tracking_id:
            return Response(text="No tracking ID provided", status=400)

        # Get user ID from Redis
        user_id_str = await self.bot.redis.get(f"lastfm:auth:{tracking_id}")
        if not user_id_str:
            return Response(text="Invalid or expired tracking ID", status=400)

        user_id = int(user_id_str)

        try:
            # Generate signature for LastFM API
            api_sig = hashlib.md5(
                f"api_key{Authorization.LastFM.api_key}methodauth.getSessiontoken{lastfm_token}{Authorization.LastFM.api_secret}".encode()
            ).hexdigest()

            # Get session key from LastFM
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "http://ws.audioscrobbler.com/2.0/",
                    params={
                        "method": "auth.getSession",
                        "api_key": Authorization.LastFM.api_key,
                        "token": lastfm_token,
                        "api_sig": api_sig,
                        "format": "json",
                    },
                ) as resp:
                    data = await resp.json()

                    if "error" in data:
                        return Response(text="Failed to get session key", status=400)

                    session_key = data["session"]["key"]
                    username = data["session"]["name"]

                    # Ensure the schema exists
                    try:
                        await self.bot.db.execute("CREATE SCHEMA IF NOT EXISTS lastfm")
                    except Exception:
                        pass

                    # Check if the table exists, create it if not
                    try:
                        await self.bot.db.execute(
                            """
                            CREATE TABLE IF NOT EXISTS lastfm.conf (
                                user_id BIGINT PRIMARY KEY,
                                username TEXT NOT NULL,
                                session_key TEXT
                            )
                        """
                        )
                    except Exception:
                        pass

                    # Store in database with error handling
                    try:
                        # Try to insert/update the record
                        await self.bot.db.execute(
                            """INSERT INTO lastfm.conf (user_id, username, session_key) 
                               VALUES ($1, $2, $3) 
                               ON CONFLICT (user_id) 
                               DO UPDATE SET username = $2, session_key = $3""",
                            user_id,
                            username,
                            session_key,
                        )
                    except Exception as e:
                        # If that fails, try to close and reset the connection pool
                        try:
                            # Close all connections in the pool
                            await self.bot.db.execute(
                                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = current_database()"
                            )

                            # Try the insert/update again
                            await self.bot.db.execute(
                                """INSERT INTO lastfm.conf (user_id, username, session_key) 
                                   VALUES ($1, $2, $3) 
                                   ON CONFLICT (user_id) 
                                   DO UPDATE SET username = $2, session_key = $3""",
                                user_id,
                                username,
                                session_key,
                            )
                        except Exception as e2:
                            return Response(
                                text=f"Database error: {str(e2)}", status=500
                            )

                    # Send DM to user
                    user = self.bot.get_user(user_id)
                    if user:
                        embed = discord.Embed(
                            title="LastFM Authentication Successful",
                            description=f"You have been successfully logged in as **{username}**",
                            color=0x2B2D31,
                        )
                        try:
                            await user.send(embed=embed)
                        except discord.Forbidden:
                            pass

                    # Delete the tracking ID from Redis
                    await self.bot.redis.delete(f"lastfm:auth:{tracking_id}")

                    return Response(
                        text="LastFM Authorized - You can close this window", status=200
                    )

        except Exception as e:
            return Response(text=f"An error occurred: {str(e)}", status=500)


async def setup(bot) -> None:
    await bot.add_cog(WebServer(bot))
