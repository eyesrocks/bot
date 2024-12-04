from __future__ import annotations

import datetime
from typing import TypedDict, Union, Optional, List, Any
from aiohttp.web import Application, Request, Response, _run_app, json_response
from discord.ext.commands import Cog, Group, Command
from prometheus_async import aio
import socket
import ujson
from tool.greed import Greed

def get_available_port(start: int = 8493) -> int:
    while True:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(('0.0.0.0', start))
            sock.close()
            return start
        except OSError:
            start += 1
            continue

SERVER_CONFIG = {
    "host": "0.0.0.0", 
    "port": get_available_port()
}

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

    def _setup_routes(self) -> None:
        routes = [
            ('GET', '/', self.index),
            ('GET', '/avatars/{id}', self.avatars),
            ('GET', '/commands', self.commands),
            ('GET', '/raw', self.command_dump),
            ('GET', '/status', self.status),
            ('GET', '/metrics', aio.web.server_stats)
        ]
        for method, path, handler in routes:
            self.app.router.add_route(method, path, handler)

    async def cog_load(self) -> None:
        self.bot.loop.create_task(self._run())

    async def cog_unload(self) -> None:
        await self.app.shutdown()

    async def _run(self) -> None:
        await _run_app(self.app, **SERVER_CONFIG, print=None, handle_signals=False)

    @staticmethod
    async def index(_: Request) -> Response:
        return Response(text="API endpoint operational", status=200)
    async def status(self, _: Request) -> Response:
        return json_response([{
            "uptime": self.bot.startup_time.timestamp(),
            "latency": round(shard.latency * 1000) if shard.latency != float('inf') else None,
            "servers": len([g for g in self.bot.guilds if g.shard_id == shard_id]),
            "users": sum(len(g.members) for g in self.bot.guilds if g.shard_id == shard_id),
            "shard": shard_id
        } for shard_id, shard in self.bot.shards.items()])

    async def avatars(self, request: Request) -> Response:
        try:
            user_id = int(request.match_info["id"])
            data = await self.bot.db.fetch(
                "SELECT * FROM avatars WHERE user_id = $1 ORDER BY time ASC",
                user_id
            )
            if not data:
                raise ValueError("No data found")

            user = self.bot.get_user(user_id)
            return json_response({
                "id": data[0]["user_id"],
                "avatars": [x["avatar"] for x in data],
                "time": datetime.datetime.fromtimestamp(int(data[0]["time"])).strftime("%Y-%m-%d %H:%M:%S"),
                "user": {
                    "name": user.name if user else data[0]["username"],
                    "discriminator": user.discriminator if user else "0000",
                    "id": user_id
                }
            })
        except (ValueError, KeyError) as e:
            return json_response({"error": str(e)}, status=404)

    def _get_permissions(self, command: Union[Command, Group], bot: bool = False) -> Optional[List[str]]:
        perms = command.bot_permissions if bot else command.permissions
        if not perms:
            return None

        permissions = []
        if isinstance(perms, list):
            permissions.extend(p.replace("_", " ").title() for p in perms)
        else:
            permissions.append(perms.replace("_", " ").title())

        if not bot and command.cog_name.title() == "Premium":
            permissions.append("Donator")
        return permissions
    async def command_dump(self, _: Request) -> Response:
        commands: List[CommandData] = []
        for cmd in self.bot.walk_commands():
            if cmd.hidden or (isinstance(cmd, Group) and not cmd.description) or cmd.qualified_name == "help":
                continue
            commands.append({
                "name": cmd.qualified_name,
                "description": cmd.brief,
                "permissions": self._get_permissions(cmd),
                "bot_permissions": self._get_permissions(cmd, True),
                "usage": cmd.usage,
                "example": cmd.example
            })
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

            commands = [format_command(cmd, level=1) for cmd in cog.walk_commands() if not cmd.hidden]
            if commands:
                output.extend([f"┌── {name}"] + commands)

        return json_response("\n".join(output))

async def setup(bot) -> None:
    await bot.add_cog(WebServer(bot))
