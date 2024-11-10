import discord
from tuuid import tuuid
from discord.ext import commands
from discord.ext.commands import Context, Command, Group
from discord import Embed
import inspect
from discord.ui import View
from urllib.parse import quote_plus as urlencode
import datetime
from fast_string_match import closest_match
from typing import List, Generator, Optional
from tool.exceptions import InvalidSubCommand
from logging import getLogger
from rust_requests import Client, Request
from contextlib import asynccontextmanager
from typing import Literal, Optional, Dict, Any, Mapping
GLOBAL_COMMANDS = {}

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.3"
}

METHOD = Optional[Literal["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]]
HEADERS = Optional[Dict[str, Any]]

@asynccontextmanager
async def request(
    url: str,
    method: METHOD = "GET", 
    headers: HEADERS = DEFAULT_HEADERS
):
    # Create the client with the provided headers
    client = Client(headers=headers)
    
    # Create the request object with the provided method and URL
    req = Request(method, url)
    
    try:
        # Send the request and await the response
        response = await client.send(req)
        yield response
    except Exception as error:
        # Re-raise exceptions that occur during the request
        raise error
    finally:
        # Cleanup resources if needed
        pass

logger = getLogger(__name__)

class OnCooldown(Exception):
    pass

def check_command(command) -> bool:
    source_lines, _ = inspect.getsourcelines(command.callback)
    for line in source_lines:
        if "if ctx.invoked_subcommand is None:" in line:
            if len(source_lines[source_lines.index(line):]) < 3:
                return False
    return True
    

def find_command(bot, query):
    query = query.lower()
    if len(GLOBAL_COMMANDS) == 4000:
        _commands = [c for c in bot.walk_commands()]
        commands = {}
        # commands = [c for c in _commands if c.qualified_name.startswith(query) or query in c.qualified_name]
        for command in _commands:
            if isinstance(command, Group):
                aliases = command.aliases
                for cmd in command.walk_commands():
                    for a in aliases:
                        commands[f"{cmd.qualified_name.replace(f'{command.qualified_name}', f'{a}')}"] = cmd
                    commands[cmd.qualified_name] = cmd
                if check_command(command):
                    commands[command.qualified_name] = command
            else:
                commands[command.qualified_name] = command
                for alias in command.aliases:
                    commands[alias] = command
        GLOBAL_COMMANDS.update(commands)
    if not bot.command_dict: bot.get_command_dict()
    if query in bot.command_dict:
        return bot.get_command(query)
#    if HARD_MATCH := bot.command_dict.get(query):
 #       return HARD_MATCH
    if MATCH := closest_match(query, bot.command_dict):
        return bot.get_command(MATCH)
    else:
        return None



    if not command:
        match = closest_match(query, [c.qualified_name.lower() for c in _commands])
        if not match:
            return None
        command = discord.utils.find(lambda m: m.qualified_name == match, _commands)
    return command


class HelpModal(discord.ui.Modal, title="Help"):
    def __init__(self, bot, ctx):
        super().__init__()
        self.bot = bot
        self.ctx = ctx

    firstfield = discord.ui.TextInput(
        label="Required",
        placeholder="Search for a command...",
        min_length=1,
        max_length=500,
        style=discord.TextStyle.short,
    )

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.data["components"][0]["components"][0]["value"]:
            name = interaction.data["components"][0]["components"][0]["value"]
            command = find_command(self.bot, name)
            if not command:
                await interaction.message.edit(embed = Embed(color = 0xffffff, description = f"no command could be found close to `{name}`"), view = BotHelpView(self.bot, self.ctx))
                return await interaction.response.defer()
            embed = Embed(color=0xffffff, timestamp=datetime.datetime.now())

            embed.set_author(
                name=self.ctx.author.display_name,
                icon_url=self.ctx.author.display_avatar.url,
            )
            if self.ctx.author.name == "aiohttp":
                embed.description = command.qualified_name
            embed.set_image(url = f"https://greed.my/{command.qualified_name.replace(' ', '_')}.png?{tuuid()}")
            await interaction.message.edit(view = BotHelpView(self.bot, self.ctx), embed = embed)
            return await interaction.response.defer()

class BotHelpView(View):
    def __init__(self, bot, ctx):
        super().__init__(timeout = None)
        self.bot = bot
        self.ctx = ctx
    
    @discord.ui.button(
        style=discord.ButtonStyle.grey,
        label="Search for commands...",
        emoji="<:greedsearch:1274197214603907164>",
        custom_id="search_button",
    )
    async def search(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author:
            embed = discord.Embed(
                description=f"> You aren't the **author**", color=0x2d2b31)
            return await interaction.response.send_message(
                embed=embed, ephemeral=True
            )
        return await interaction.response.send_modal(HelpModal(self.bot, self.ctx))



def shorten(text: str, limit: int) -> str:
    try:
        if len(text) >= limit:
            return text[: limit - 3] + "..."
        else:
            return text
    except Exception:
        return text


class HelpInterface(View):
    def __init__(self, bot, options):
        super().__init__(timeout=None)
        self.bot = bot
        self.options = options

        self.add_item(HelpSelectMenu(self.bot, self.options))


class HelpSelectMenu(discord.ui.Select):
    def __init__(self, bot, options: dict, placeholder: Optional[str] = "options..."):
        self.bot = bot
        self._options = options
        options = [
            discord.SelectOption(
                label=_["name"],
                description=shorten(_["description"], 100),
                value=_["name"],
            )
            for k, _ in options.items()
        ]
        super().__init__(
            custom_id="Help:Select",
            placeholder="Options...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        value = self.values[0]
        self.values.clear()
        await interaction.response.defer()
        self.view.children[0].placeholder = value
        return await interaction.message.edit(
            embed=self._options[value]["embed"], view=self.view
        )


def generate(ctx: Context, c: Command, example: str = "", usage=False) -> str:
    params = None
    try:
        if len(c.clean_params.keys()) == 1:
            if "_" in list(c.clean_params.keys())[0]:
                params = " ".join(
                    f"<{p}>" for p in list(c.clean_params.keys())[0].split("_")
                )
    except Exception:
        pass
    if not params:
        params = " ".join(f"<{param}>" for param in c.clean_params.keys())
    if usage is True:
        if example != "":
            ex = f"\n> [**Example:**](https://greed.my) **{example}**"
        else:
            ex = ""
        return f"> [**Syntax:**](https://greed.my) **{ctx.prefix}{c.qualified_name} {params}**{ex}"
    if len(c.qualified_name.lower().split(" ")) > 2:
        m = f" for {c.qualified_name.lower().split(' ')[-1]}s"
    else:
        m = ""
    if "add" in c.qualified_name.lower() or "create" in c.qualified_name.lower():
        if c.brief is None:
            return f"create a new {c.qualified_name.lower().split(' ')[0]}{m}"
    elif "remove" in c.qualified_name.lower() or "delete" in c.qualified_name.lower():
        if c.brief is None:
            return f"delete a {c.qualified_name.lower().split(' ')[0]}{m}"
    elif "clear" in c.qualified_name.lower():
        if c.brief is None:
            return f"clear {c.qualified_name.lower().split(' ')[0]}{m}"
    else:
        if c.brief is None:
            if m == "":
                if c.root_parent is not None:
                    m = f" {c.root_parent.name.lower()}"
            if len(c.clean_params.keys()) == 0:
                n = "view "
            else:
                n = "change "
            return f"{n}the {c.name.lower()}{m}"


def chunks(array: List, chunk_size: int) -> Generator[List, None, None]:
    for i in range(0, len(array), chunk_size):
        yield array[i : i + chunk_size]


class CogConverter(commands.Converter):
    async def convert(self, ctx: Context, argument: str):
        cogs = [i for i in ctx.bot.cogs]
        for cog in cogs:
            if cog.lower() == argument.lower():
                return ctx.bot.cogs.get(cog)
        return None

class CommandSelect(discord.ui.Select):
    def __init__(self, categories):
        options = [
            discord.SelectOption(label=category, description=f"View commands in {category}")
            for category in categories
        ]
        super().__init__(placeholder="Choose a category", options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_category = self.values[0]
        commands_list = self.get_commands_by_category(selected_category)
        embed = discord.Embed(
            title=f"**Commands in {selected_category}**",
            color=0xffffff,
            description="\n".join(f"**{cmd}**" for cmd in commands_list) or "No commands available in this category."
        )
        embed.set_thumbnail(url=self.view.bot.user.avatar.url)
        embed.set_footer(text="Use the dropdown to switch categories.")

        await interaction.response.edit_message(embed=embed)

    def get_commands_by_category(self, category):
        commands_list = []
        for command in self.view.bot.commands:
            if command.cog_name and command.cog_name.lower() == category.lower():
                if isinstance(command, discord.ext.commands.Group) and command.commands:
                    commands_list.append(f"{command.name}*")
                else:
                    commands_list.append(command.name)

        return commands_list


class CommandMenuView(discord.ui.View):
    def __init__(self, bot, categories):
        super().__init__()
        self.bot = bot
        self.add_item(CommandSelect(categories))

class HelpView(discord.ui.View):
    def __init__(self, bot, categories):
        super().__init__()
        self.bot = bot
        self.add_item(CommandSelect(categories))

class MyHelpCommand(commands.HelpCommand):
    async def send_bot_help(self, mapping: Optional[Mapping[str, commands.Command]]):
        if retry_after := await self.context.bot.glory_cache.ratelimited(
            f"rl:user_commands{self.context.author.id}", 2, 4
        ):
            raise commands.CommandOnCooldown(None, retry_after, None)

        embed = discord.Embed(
            title="Help",
            description="<:luma_info:1302336751599222865> **support: [/pomice](https://discord.gg/pomice)**\n<a:loading:1302351366584270899> **site: [greed](http://greed.my)**\n\n Use **,help [command name]** or select a category from the dropdown",
            color=0xffffff,
        )

        # Set the author for the embed (bot's username and avatar)
        embed.set_author(
            name=self.context.bot.user.name,  # Bot's name
            icon_url=self.context.bot.user.avatar  # Bot's avatar
        )
        
        categories = set()
        for command in self.context.bot.walk_commands():
            if command.cog_name and command.cog_name.lower() not in ["owner", "jishaku", "errors", "webserver"]:
                categories.add(command.cog_name)

        view = HelpView(self.context.bot, sorted(categories))
        await self.context.send(embed=embed, view=view)


    async def send_cog_help(self, cog):
        return

    def subcommand_not_found(self, command, string):
        if isinstance(command, Group) and len(command.all_commands) > 0:
            raise InvalidSubCommand(
                f'**Command** "{command.qualified_name}" has **no subcommand named** `{string}`'
            )
        raise InvalidSubCommand(
            f'**Command** "{command.qualified_name}" **has** `no subcommands.`'
        )

    def check_command(self, command):
        return check_command(command)

    async def send_group_help(self, group):
        if retry_after := await self.context.bot.glory_cache.ratelimited(
            f"rl:user_commands{self.context.author.id}", 2, 4
        ):
            raise commands.CommandOnCooldown(None, retry_after, None)

        embed: Embed = Embed(color=0xffffff, timestamp=datetime.datetime.now())
        ctx = self.context
        commands: List = []
        embeds = {}
        commands = [c for c in group.walk_commands()]
        commands.append(group)
        commands = [c for c in commands if self.check_command(c)]
        for i, command in enumerate(commands, start=1):
            embed = Embed(color=0xffffff, timestamp=datetime.datetime.now())
            #embed.set_image(url = f"https://greed.my/api/static/{command.qualified_name.replace(' ', '_')}.png?{tuuid()}&{tuuid()}")
            if command.brief is not None and command.brief != "":
                brief = command.brief
            else:
                brief = generate(ctx, command)
            if len(command.clean_params.keys()) > 0:
                params = "".join(f"{c}, " for c in command.clean_params.keys())
                params = params[:-2]
                params = params.replace("_", ", ")
                embed.add_field(name="Parameters", value=params, inline=True)
            try:
                if perms[0].lower() != "send_messages":
                    embed.add_field(
                        name="Permissions",
                        value=f"`{perms[0].replace('_',' ').title()}`",
                        inline=True,
                    )
            except Exception:
                pass
            if command.example is not None:
                example = command.example.replace(",", self.context.prefix)
            else:
                example = ""
            embed.description = brief
            embed.add_field(
                name="Usage", value=generate(ctx, command, example, True), inline=False
            )
            if flags := command.parameters:
                d = []
                descriptions = []
                for flag_name, flag in flags.items():
                    if (
                        flag.get("description")
                        and flag.get("description") not in descriptions
                    ):
                        descriptions.append(flag.get("description"))
                        if flag.get("converter", None) == int:
                            flag_value = "number"
                        if flag.get("converter", None) == bool:
                             flag_value = "true/false"
                        else:
                            flag_value = "text"
                        if default := flag.get("default"):
                            if "{embed}" not in str(default):
                                 m = f"(default: `{flag['default']}`)"
                            else:
                                m = "(default: `embed object`)"
                        else:
                            m = ""
                        if description := flag.get("description"):
                            f = f"{description} "
                        else:
                            f = ""
                        d.append(
                            f"> [**{flag_name.title()}:**](https://greed.my) **{f}{flag_value} {m}**"
                        )
                embed.add_field(
                    name="Flags", value="".join(f"{_}\n" for _ in d), inline=True
                )
            if len(command.aliases) > 0:
                aliases = "".join(f"{a}, " for a in command.aliases)
                aliases = aliases[:-2]
            else:
                aliases = "N/A"
            embed.set_footer(
                text=f"Aliases: {aliases}・Module: {command.cog_name.replace('.py','')}・{i}/{len(commands)}"
            )
            embed.set_author(
                name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url
            )
            embeds[command.qualified_name] = {
                "embed": embed,
                "name": command.qualified_name,
                "description": command.brief,
            }
            # embeds.append(embed)
            continue
        return await self.context.send(
            embed=Embed(
                color=0xffffff,
                title=f'**Need help with {group.qualified_name}?**',
                url='https://greed.my/Commands',
                description=f"<:settings_icon:1302207796737085533> **Usage**\n> **{group.qualified_name}** has {len([i for i in group.walk_commands()])} sub commands that can be used.To view all commands for **{group.qualified_name}**, Use the help menu below or visit our [**website**](https://greed.my/)",
            ),
            view=HelpInterface(self.context.bot, embeds)
        )

    def get_example(self, command):
        if len(command.clean_params.keys()) == 0:
            return ""
        ex = f"{self.context.prefix}{command.qualified_name} "
        for key, value in command.clean_params.items():
            if "user" in repr(value).lower() or "member" in repr(value).lower():
                ex += "@lim "
            elif "role" in repr(value).lower():
                ex += "@mod "
            elif "image" in repr(value).lower() or "attachment" in repr(value).lower():
                ex += "https://gyazo.com/273.png "
            elif "channel" in repr(value).lower():
                ex += "#text "
            elif key.lower() == "reason":
                ex += "being annoying "
            else:
                ex += f"<{key}> "
        return ex

    def get_usage(self, command):
        if len(command.clean_params.keys()) == 0:
            return ""
        usage = f"{self.context.prefix}{command.qualified_name} "
        for key, value in command.clean_params.items():
            usage += f"<{key}> "
        return usage

    async def command_not_found(self, string):
        # if string.lower() == "music":
        #     return await self.send_cog_help(self.context.bot.cogs.get("Music"))
        if retry_after := await self.context.bot.glory_cache.ratelimited(  # noqa: F841
            f"cnf:{self.context.guild.id}", 1, 3
        ):
            raise OnCooldown()
        raise discord.ext.commands.CommandError(
            f"**No command** named **{string}** exists"
        )

    async def send_command_help(self, command):
        if retry_after := await self.context.bot.glory_cache.ratelimited(
            f"rl:user_commands{self.context.author.id}", 2, 4
        ):
            raise commands.CommandOnCooldown(None, retry_after, None)

        embed = Embed(color=0xffffff, timestamp=datetime.datetime.now())

        aliases: str = ", ".join(command.aliases)

        embed.set_author(
            name=self.context.author.display_name,
            icon_url=self.context.author.display_avatar.url,
        )
        ctx = self.context
        perms = command.perms
   #     if command.cog_name.lower() == "premium":
   #         if command.perms:
   #             perms = command.perms
   #             perms.append("Donator")
   #         else:
   #             perms = ["Donator"]
   #     embed.set_footer(text=command.cog_name)
        if command.perms is None or len(command.perms) == 0:
            try:
                await command.can_run(ctx)
            except Exception:
                pass
        embed.title = f"{command.qualified_name}"
        if command.brief is not None and command.brief != "":
            brief = command.brief
        else:
            brief = generate(ctx, command)
        if len(command.clean_params.keys()) > 0:
            params = "".join(f"{c}, " for c in command.clean_params.keys())
            params = params[:-2]
            params = params.replace("_", ", ")
            embed.add_field(name="Parameters", value=params, inline=True)
        try:
            if perms:
                if perms[0].lower() != "send_messages":
                    embed.add_field(
                        name="Permissions",
                        value=f"`{perms[0].replace('_',' ').title()}`",
                        inline=True,
                    )
        except Exception:
            pass
        if command.example is not None:
            example = command.example.replace(",", self.context.prefix)
        else:
            example = self.get_example(command)
        embed.description = brief
        embed.add_field(
            name="Usage", value=generate(ctx, command, example, True), inline=False
        )
        if flags := command.parameters:
            d = []
            descriptions = []
            for flag_name, flag in flags.items():
                if (
                    flag.get("description")
                    and flag.get("description") not in descriptions
                ):
                    descriptions.append(flag.get("description"))
                    if flag.get("converter", None) == int:
                        flag_value = "number"
                    if flag.get("converter", None) == bool:
                        flag_value = "true/false"
                    else:
                        flag_value = "text"
                    if default := flag.get("default"):
                        if "{embed}" not in default:
                            m = f"(default: `{flag['default']}`)"
                        else:
                            m = "(default: `embed object`)"
                    else:
                        m = ""
                    if description := flag.get("description"):
                        f = f"{description} "
                    else:
                        f = ""
                    d.append(
                        f"> [**{flag_name.title()}:**](https://greed.my) **{f}{flag_value} {m}**"
                    )
            embed.add_field(
                name="Flags", value="".join(f"{_}\n" for _ in d), inline=True
            )
        if len(command.aliases) > 0:
            aliases = "".join(f"{a}, " for a in command.aliases)
            aliases = aliases[:-2]
        else:
            aliases = "N/A"

        try:
            embed.set_footer(
                text=f"Aliases: {aliases}・Module: {command.cog_name.replace('.py','')}"
            )
#       embed.set_image(url = f"https://greed.my/api/static/{command.qualified_name.replace(' ', '_')}.png?{tuuid()}&{tuuid()}")
        except AttributeError:
            pass
        return await ctx.send(embed=embed)
