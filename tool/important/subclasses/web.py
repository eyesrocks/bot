import datetime
import ujson
from discord.ext.commands import Cog, Group, Command
from typing import Union, Optional, List
from aiohttp.web import Application, Request, Response, _run_app, json_response
from prometheus_async import aio  # type: ignore
import socket

def find_available_port(start_port=8493):
    port = start_port
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('localhost', port)) != 0:
                return port
        port += 1

ADDRESS = {
    "host": "0.0.0.0",
    "port": find_available_port(),
}

class WebServer(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.app = Application()
        self.setup_routes()

    def setup_routes(self):
        self.app.router.add_get("/", self.index)
        self.app.router.add_get("/avatars/{id}", self.avatars)
        self.app.router.add_get("/commands", self.commandz)
        self.app.router.add_get("/raw", self.command_dump)
        self.app.router.add_get("/status", self.status)
        self.app.router.add_get("/metrics", aio.web.server_stats)

    async def cog_load(self):
        self.bot.loop.create_task(self.run())

    async def cog_unload(self):
        await self.app.shutdown()

    async def run(self):
        await _run_app(self.app, **ADDRESS, print=None)  # type: ignore

    @staticmethod
    async def index(request: Request) -> Response:
        return Response(text="hey this site belongs to icy.com kid", status=200)

    async def status(self, request: Request) -> Response:
        data = [
            {
                "uptime": self.bot.startup_time.timestamp(),
                "latency": round(shard.latency * 1000),
                "servers": len([g for g in self.bot.guilds if g.shard_id == shard_id]),
                "users": sum(len(g.members) for g in self.bot.guilds if g.shard_id == shard_id),
                "shard": shard_id,
            }
            for shard_id, shard in self.bot.shards.items()
        ]
        return json_response(data)

    async def avatars(self, request: Request) -> Response:
        id = int(request.match_info["id"])
        data = await self.bot.db.fetch("SELECT * FROM avatars WHERE user_id = $1 ORDER BY time ASC", id)
        if not data:
            return json_response({"error": "No data found"}, status=404)

        user = self.bot.get_user(id)
        data2 = {
            "id": data[0]["user_id"],
            "avatars": [x["avatar"] for x in data],
            "time": datetime.datetime.fromtimestamp(int(data[0]["time"])).strftime("%Y-%m-%d %H:%M:%S"),
            "user": {
                "name": user.name if user else data[0]["username"],
                "discriminator": user.discriminator if user else "0000",
                "id": id,
            }
        }
        return json_response(data2)

    def get_permissions(self, command: Union[Command, Group], bot: Optional[bool] = False) -> Optional[List[str]]:
        permissions = []
        perms = command.bot_permissions if bot else command.permissions
        if perms:
            if isinstance(perms, list):
                permissions.extend([c.replace("_", " ").title() for c in perms])
            else:
                permissions.append(perms.replace("_", " ").title())
            if not bot and command.cog_name.title() == "Premium":
                permissions.append("Donator")
        return permissions

    async def command_dump(self, request: Request) -> Response:
        commands = [
            {
                "name": command.qualified_name,
                "description": command.brief,
                "permissions": self.get_permissions(command),
                "bot_permissions": self.get_permissions(command, True),
                "usage": command.usage,
                "example": command.example,
            }
            for command in self.bot.walk_commands()
            if not command.hidden and (not isinstance(command, Group) or command.description) and command.qualified_name != "help"
        ]
        return json_response(commands)

    async def commandz(self, req: Request) -> Response:
        output = ""
        for name, cog in sorted(self.bot.cogs.items(), key=lambda cog: cog[0].lower()):
            if name.lower() in ("jishaku", "Develoepr"):
                continue

            _commands = []
            for command in cog.walk_commands():
                if command.hidden:
                    continue

                usage = f" {command.usage}" if command.usage else ""
                aliases = f"({', '.join(command.aliases)})" if command.aliases else ""
                if isinstance(command, Group) and not command.root_parent:
                    _commands.append(f"|    ├── {command.name}{aliases}: {command.brief or 'No description'}")
                elif not isinstance(command, Group) and command.root_parent:
                    _commands.append(f"|    |   ├── {command.qualified_name}{aliases}{usage}: {command.brief or 'No description'}")
                elif isinstance(command, Group) and command.root_parent:
                    _commands.append(f"|    |   ├── {command.qualified_name}{aliases}: {command.brief or 'No description'}")
                else:
                    _commands.append(f"|    ├── {command.qualified_name}{aliases}{usage}: {command.brief or 'No description'}")

            if _commands:
                output += f"┌── {name}\n" + "\n".join(_commands) + "\n"

        out = ujson.dumps(output)
        return Response(text=out, content_type="application/json")

async def setup(bot):
    await bot.add_cog(WebServer(bot))
