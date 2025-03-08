from __future__ import annotations

import datetime
import hashlib
import aiohttp
import discord
import json
import uuid
from typing import TypedDict, Union, Optional, List, Dict, Any
from aiohttp.web import Application, Request, Response, _run_app, json_response
import aiohttp.web
from aiohttp_cors import setup as setup_cors, ResourceOptions, CorsViewMixin
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


class OutageData(TypedDict):
    id: str
    title: str
    description: str
    status: str
    createdAt: str
    updatedAt: str
    affectedComponents: List[str]


class WebServer(Cog):
    def __init__(self, bot: Greed) -> None:
        self.bot = bot
        self.app = Application(middlewares=[self.cors_middleware])
        self._setup_routes()
        self._setup_cors()
        self.server_task = None
        self.api_key = Authorization.Outages.api_key

    def _setup_routes(self) -> None:
        routes = [
            ("GET", "/", self.index),
            ("GET", "/commands", self.commands),
            ("GET", "/raw", self.command_dump),
            ("GET", "/status", self.status),
            ("GET", "/outages", self.get_outages),
            ("POST", "/outages", self.post_outage),
            ("PATCH", "/outages/{outage_id}", self.update_outage),
            ("OPTIONS", "/outages", self.options_handler),
            ("OPTIONS", "/outages/{outage_id}", self.options_handler),
            ("GET", "/metrics", aio.web.server_stats),
            ("GET", "/callback", self.lastfm_callback),
        ]
        for method, path, handler in routes:
            self.app.router.add_route(method, path, handler)

    def _setup_cors(self) -> None:
        # Setup CORS for all routes with a simpler configuration
        # that won't conflict with our middleware
        cors = setup_cors(
            self.app,
            defaults={
                # Allow specific origins including localhost development server
                "http://localhost:3000": ResourceOptions(
                    allow_credentials=True,
                    expose_headers="*",
                    allow_headers="*",
                    allow_methods=["GET", "POST", "OPTIONS"],
                ),
                # Also allow all origins as a fallback
                "*": ResourceOptions(
                    allow_credentials=True,
                    expose_headers="*",
                    allow_headers="*",
                    allow_methods=["GET", "POST", "OPTIONS"],
                ),
            },
        )

        # We don't need to add CORS to each route manually
        # as we're using middleware for that

    async def cog_load(self) -> None:
        if self.bot.connection.local_name != "cluster1":
            return
        # Create outages table if it doesn't exist
        await self._create_outages_table()
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
    async def index(request: Request) -> Response:
        response = Response(text="API endpoint operationaeeeeeeeeeeeeel", status=200)
        # Add CORS headers explicitly for better compatibility
        origin = request.headers.get("Origin", "")

        # If there's an origin header, reflect it back to allow any origin
        if origin:
            # For localhost and other trusted origins, allow credentials
            if origin == "http://localhost:3000" or origin.endswith(".greed.rocks"):
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Credentials"] = "true"
            else:
                # For other origins, allow the request but without credentials
                response.headers["Access-Control-Allow-Origin"] = origin
        else:
            # Fallback to wildcard if no origin is specified
            response.headers["Access-Control-Allow-Origin"] = "*"

        response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "*"
        response.headers["Access-Control-Expose-Headers"] = "*"
        return response

    async def status(self, request: Request) -> Response:
        shards = await self.bot.ipc.roundtrip("get_shards")
        response = json_response({"shards": shards})
        # Add CORS headers explicitly for better compatibility
        origin = request.headers.get("Origin", "")

        # If there's an origin header, reflect it back to allow any origin
        if origin:
            # For localhost and other trusted origins, allow credentials
            if origin == "http://localhost:3000" or origin.endswith(".greed.rocks"):
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Credentials"] = "true"
            else:
                # For other origins, allow the request but without credentials
                response.headers["Access-Control-Allow-Origin"] = origin
        else:
            # Fallback to wildcard if no origin is specified
            response.headers["Access-Control-Allow-Origin"] = "*"

        response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "*"
        response.headers["Access-Control-Expose-Headers"] = "*"
        return response

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

    async def command_dump(self, request: Request) -> Response:
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
        response = json_response(commands)
        # Add CORS headers explicitly for better compatibility
        origin = request.headers.get("Origin", "")

        # If there's an origin header, reflect it back to allow any origin
        if origin:
            # For localhost and other trusted origins, allow credentials
            if origin == "http://localhost:3000" or origin.endswith(".greed.rocks"):
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Credentials"] = "true"
            else:
                # For other origins, allow the request but without credentials
                response.headers["Access-Control-Allow-Origin"] = origin
        else:
            # Fallback to wildcard if no origin is specified
            response.headers["Access-Control-Allow-Origin"] = "*"

        response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "*"
        response.headers["Access-Control-Expose-Headers"] = "*"
        return response

    async def commands(self, request: Request) -> Response:
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

        response = json_response("\n".join(output))
        # Add CORS headers explicitly for better compatibility
        origin = request.headers.get("Origin", "")

        # If there's an origin header, reflect it back to allow any origin
        if origin:
            # For localhost and other trusted origins, allow credentials
            if origin == "http://localhost:3000" or origin.endswith(".greed.rocks"):
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Credentials"] = "true"
            else:
                # For other origins, allow the request but without credentials
                response.headers["Access-Control-Allow-Origin"] = origin
        else:
            # Fallback to wildcard if no origin is specified
            response.headers["Access-Control-Allow-Origin"] = "*"

        response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "*"
        response.headers["Access-Control-Expose-Headers"] = "*"
        return response

    async def lastfm_callback(self, request: Request) -> Response:
        """Handle the callback from LastFM OAuth authentication"""
        # This is the token returned by LastFM after authorization
        lastfm_token = request.query.get("token")

        # Helper function to add CORS headers to responses
        def add_cors_headers(response):
            origin = request.headers.get("Origin", "")

            # If there's an origin header, reflect it back to allow any origin
            if origin:
                # For localhost and other trusted origins, allow credentials
                if origin == "http://localhost:3000" or origin.endswith(".greed.rocks"):
                    response.headers["Access-Control-Allow-Origin"] = origin
                    response.headers["Access-Control-Allow-Credentials"] = "true"
                else:
                    # For other origins, allow the request but without credentials
                    response.headers["Access-Control-Allow-Origin"] = origin
            else:
                # Fallback to wildcard if no origin is specified
                response.headers["Access-Control-Allow-Origin"] = "*"

            response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "*"
            response.headers["Access-Control-Expose-Headers"] = "*"
            return response

        try:
            # If no token is provided, return an error
            if not lastfm_token:
                response = Response(text="No token provided", status=400)
                return add_cors_headers(response)

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
                            return Response(
                                text="Failed to get session key", status=400
                            )

                        session_key = data["session"]["key"]
                        username = data["session"]["name"]

                        # Ensure the schema exists
                        try:
                            await self.bot.db.execute(
                                "CREATE SCHEMA IF NOT EXISTS lastfm"
                            )
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
                                response = Response(
                                    text=f"Database error: {str(e2)}", status=500
                                )
                                return add_cors_headers(response)

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

                        response = Response(
                            text="LastFM Authorized - You can close this window",
                            status=200,
                        )
                        return add_cors_headers(response)

            except Exception as e:
                response = Response(text=f"An error occurred: {str(e)}", status=500)
                return add_cors_headers(response)

        except Exception as e:
            response = Response(text=f"An error occurred: {str(e)}", status=500)
            return add_cors_headers(response)

    @staticmethod
    async def cors_middleware(app, handler):
        async def middleware_handler(request):
            response = await handler(request)
            origin = request.headers.get("Origin", "")

            # If there's an origin header, reflect it back to allow any origin
            if origin:
                # For localhost and other trusted origins, allow credentials
                if origin == "http://localhost:3000" or origin.endswith(".greed.rocks"):
                    response.headers["Access-Control-Allow-Origin"] = origin
                    response.headers["Access-Control-Allow-Credentials"] = "true"
                else:
                    # For other origins, allow the request but without credentials
                    response.headers["Access-Control-Allow-Origin"] = origin
            else:
                # Fallback to wildcard if no origin is specified
                response.headers["Access-Control-Allow-Origin"] = "*"

            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "*"
            response.headers["Access-Control-Expose-Headers"] = "*"
            return response

        return middleware_handler

    async def _create_outages_table(self) -> None:
        """Create the outages table if it doesn't exist"""
        try:
            # Create schema if it doesn't exist
            await self.bot.db.execute("CREATE SCHEMA IF NOT EXISTS status")

            # Create outages table
            await self.bot.db.execute(
                """
                CREATE TABLE IF NOT EXISTS status.outages (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    affected_components TEXT[] NOT NULL
                )
            """
            )
        except Exception as e:
            self.bot.logger.error(f"Failed to create outages table: {e}")

    async def get_outages(self, request: Request) -> Response:
        """Get all outages"""
        try:
            # Query the database for outages
            outages = await self.bot.db.fetch(
                """
                SELECT 
                    id, 
                    title, 
                    description, 
                    status, 
                    created_at, 
                    updated_at, 
                    affected_components
                FROM status.outages
                ORDER BY updated_at DESC
            """
            )

            # Format the outages for the response
            formatted_outages = []
            for outage in outages:
                formatted_outages.append(
                    {
                        "id": outage["id"],
                        "title": outage["title"],
                        "description": outage["description"],
                        "status": outage["status"],
                        "createdAt": outage["created_at"].isoformat(),
                        "updatedAt": outage["updated_at"].isoformat(),
                        "affectedComponents": outage["affected_components"],
                    }
                )

            response = json_response(formatted_outages)

            # Add CORS headers
            origin = request.headers.get("Origin", "")
            if origin:
                if origin == "http://localhost:3000" or origin.endswith(".greed.rocks"):
                    response.headers["Access-Control-Allow-Origin"] = origin
                    response.headers["Access-Control-Allow-Credentials"] = "true"
                else:
                    response.headers["Access-Control-Allow-Origin"] = origin
            else:
                response.headers["Access-Control-Allow-Origin"] = "*"

            response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "*"
            response.headers["Access-Control-Expose-Headers"] = "*"
            return response

        except Exception as e:
            self.bot.logger.error(f"Error getting outages: {e}")
            response = json_response(
                {"error": "Failed to retrieve outages"}, status=500
            )

            # Add CORS headers
            origin = request.headers.get("Origin", "")
            if origin:
                if origin == "http://localhost:3000" or origin.endswith(".greed.rocks"):
                    response.headers["Access-Control-Allow-Origin"] = origin
                    response.headers["Access-Control-Allow-Credentials"] = "true"
                else:
                    response.headers["Access-Control-Allow-Origin"] = origin
            else:
                response.headers["Access-Control-Allow-Origin"] = "*"

            response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "*"
            response.headers["Access-Control-Expose-Headers"] = "*"
            return response

    async def post_outage(self, request: Request) -> Response:
        """Create a new outage"""
        # Check API key for authentication
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            response = json_response({"error": "Unauthorized"}, status=401)
            return self._add_cors_headers(response, request)

        api_key = auth_header.replace("Bearer ", "")
        if api_key != self.api_key:
            response = json_response({"error": "Invalid API key"}, status=401)
            return self._add_cors_headers(response, request)

        try:
            # Parse the request body
            body = await request.json()

            # Validate required fields
            required_fields = ["title", "description", "status"]
            for field in required_fields:
                if field not in body:
                    response = json_response(
                        {"error": f"Missing required field: {field}"}, status=400
                    )
                    return self._add_cors_headers(response, request)

            # Validate status
            valid_statuses = ["investigating", "identified", "monitoring", "resolved"]
            if body["status"] not in valid_statuses:
                response = json_response(
                    {
                        "error": f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
                    },
                    status=400,
                )
                return self._add_cors_headers(response, request)

            # Generate a unique ID
            outage_id = str(uuid.uuid4())

            # Get current timestamp
            now = datetime.datetime.now()

            # Extract affected components or use empty array
            affected_components = body.get("affectedComponents", [])
            if not isinstance(affected_components, list):
                response = json_response(
                    {"error": "affectedComponents must be an array"}, status=400
                )
                return self._add_cors_headers(response, request)

            # Insert the outage into the database
            await self.bot.db.execute(
                """
                INSERT INTO status.outages (
                    id, 
                    title, 
                    description, 
                    status, 
                    created_at, 
                    updated_at, 
                    affected_components
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
                outage_id,
                body["title"],
                body["description"],
                body["status"],
                now,
                now,
                affected_components,
            )

            # Return the created outage
            outage = {
                "id": outage_id,
                "title": body["title"],
                "description": body["description"],
                "status": body["status"],
                "createdAt": now.isoformat(),
                "updatedAt": now.isoformat(),
                "affectedComponents": affected_components,
            }

            response = json_response(outage, status=201)
            return self._add_cors_headers(response, request)

        except json.JSONDecodeError:
            response = json_response({"error": "Invalid JSON"}, status=400)
            return self._add_cors_headers(response, request)
        except Exception as e:
            self.bot.logger.error(f"Error creating outage: {e}")
            response = json_response({"error": "Failed to create outage"}, status=500)
            return self._add_cors_headers(response, request)

    def _add_cors_headers(self, response: Response, request: Request) -> Response:
        """Helper method to add CORS headers to a response"""
        origin = request.headers.get("Origin", "")

        if origin:
            if origin == "http://localhost:3000" or origin.endswith(".greed.rocks"):
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Credentials"] = "true"
            else:
                response.headers["Access-Control-Allow-Origin"] = origin
        else:
            response.headers["Access-Control-Allow-Origin"] = "*"

        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "*"
        response.headers["Access-Control-Expose-Headers"] = "*"
        return response

    async def update_outage(self, request: Request) -> Response:
        """Update an existing outage"""
        # Check API key for authentication
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            response = json_response({"error": "Unauthorized"}, status=401)
            return self._add_cors_headers(response, request)

        api_key = auth_header.replace("Bearer ", "")
        if api_key != self.api_key:
            response = json_response({"error": "Invalid API key"}, status=401)
            return self._add_cors_headers(response, request)

        # Get outage ID from URL
        outage_id = request.match_info.get("outage_id")
        if not outage_id:
            response = json_response({"error": "Missing outage ID"}, status=400)
            return self._add_cors_headers(response, request)

        try:
            # Parse the request body
            body = await request.json()

            # Check if outage exists
            existing = await self.bot.db.fetchrow(
                """
                SELECT * FROM status.outages WHERE id = $1
            """,
                outage_id,
            )

            if not existing:
                response = json_response({"error": "Outage not found"}, status=404)
                return self._add_cors_headers(response, request)

            # Prepare update fields
            update_fields = {}

            # Title
            if "title" in body:
                update_fields["title"] = body["title"]

            # Description
            if "description" in body:
                update_fields["description"] = body["description"]

            # Status
            if "status" in body:
                valid_statuses = [
                    "investigating",
                    "identified",
                    "monitoring",
                    "resolved",
                ]
                if body["status"] not in valid_statuses:
                    response = json_response(
                        {
                            "error": f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
                        },
                        status=400,
                    )
                    return self._add_cors_headers(response, request)
                update_fields["status"] = body["status"]

            # Affected components
            if "affectedComponents" in body:
                if not isinstance(body["affectedComponents"], list):
                    response = json_response(
                        {"error": "affectedComponents must be an array"}, status=400
                    )
                    return self._add_cors_headers(response, request)
                update_fields["affected_components"] = body["affectedComponents"]

            # If no fields to update, return error
            if not update_fields:
                response = json_response({"error": "No fields to update"}, status=400)
                return self._add_cors_headers(response, request)

            # Add updated_at timestamp
            now = datetime.datetime.now()
            update_fields["updated_at"] = now

            # Build SQL query
            set_clauses = []
            params = [outage_id]

            for i, (key, value) in enumerate(update_fields.items(), start=2):
                set_clauses.append(f"{key} = ${i}")
                params.append(value)

            query = f"""
                UPDATE status.outages 
                SET {', '.join(set_clauses)}
                WHERE id = $1
                RETURNING id, title, description, status, created_at, updated_at, affected_components
            """

            # Execute update
            updated = await self.bot.db.fetchrow(query, *params)

            # Return updated outage
            outage = {
                "id": updated["id"],
                "title": updated["title"],
                "description": updated["description"],
                "status": updated["status"],
                "createdAt": updated["created_at"].isoformat(),
                "updatedAt": updated["updated_at"].isoformat(),
                "affectedComponents": updated["affected_components"],
            }

            response = json_response(outage)
            return self._add_cors_headers(response, request)

        except json.JSONDecodeError:
            response = json_response({"error": "Invalid JSON"}, status=400)
            return self._add_cors_headers(response, request)
        except Exception as e:
            self.bot.logger.error(f"Error updating outage: {e}")
            response = json_response({"error": "Failed to update outage"}, status=500)
            return self._add_cors_headers(response, request)

    async def options_handler(self, request: Request) -> Response:
        """Handle OPTIONS requests for CORS preflight"""
        response = Response(status=204)  # No content
        return self._add_cors_headers(response, request)


async def setup(bot) -> None:
    await bot.add_cog(WebServer(bot))
