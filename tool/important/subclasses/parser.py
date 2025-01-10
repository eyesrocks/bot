from re import Match, compile, sub, DOTALL  # noqa: F401
from typing import Any, Callable, Dict, Optional, Union
from discord.ext.commands import CommandError, Context, Converter
from discord import Embed, Guild, User, Member, Message, ButtonStyle  # noqa: F401
from discord.abc import GuildChannel
from aiohttp import ClientSession
from typing_extensions import Type, NoReturn, Self
from discord.ext.commands import Context
from discord.ui import View, Button
from discord.utils import format_dt


image_link = compile(
    r"https?:\/\/(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&\/\/=]*(?:\.png|\.jpe?g|\.gif|\.jpg|))"
)


def ordinal(n):
    n = int(n)
    return "%d%s" % (n, "tsnrhtdd"[(n // 10 % 10 != 1) * (n % 10 < 4) * n % 10 :: 4])


class EmbedConverter(Converter):
    async def convert(self, ctx: Context, code: str) -> Optional[dict]:
        script = Script(code, ctx.author)
        try:
            await script.compile()
        except EmbedError as e:
            await ctx.warning(f"{e.message}")
            raise e
        return await script.send(ctx.channel, return_embed=True)


class EmbedError(CommandError):
    def __init__(self, message: str, **kwargs):
        self.message = message
        super().__init__(message, kwargs)


class Script:
    def __init__(self, template: str, user: Union[Member, User], lastfm_data: dict = {}):
        self.pattern = compile(r"\{([\s\S]*?)\}")  # compile(r"{(.*?)}")
        self.data: Dict[str, Union[Dict, str]] = {
            "embed": {},
        }
        self.replacements = {
            "{user}": str(user),
            "{user.mention}": user.mention,
            "{user.name}": user.name,
            "{user.avatar}": user.display_avatar.url,
            "{user.created_at}": format_dt(user.created_at, style="R"),
            "{whitespace}": "\u200e",
        }
        if isinstance(user, Member):
            self.replacements.update({
                "{user.joined_at}": format_dt(user.joined_at, style="R"),
                "{guild.name}": user.guild.name,
                "{guild.count}": str(user.guild.member_count),
                "{guild.count.format}": ordinal(len(user.guild.members)),
                "{guild.id}": user.guild.id,
                "{guild.created_at}": format_dt(user.guild.created_at, style="R"),
                "{guild.boost_count}": str(user.guild.premium_subscription_count),
                "{guild.booster_count}": str(len(user.guild.premium_subscribers)),
                "{guild.boost_count.format}": ordinal(
                    str(user.guild.premium_subscription_count)
                ),
                "{guild.booster_count.format}": ordinal(
                    str(user.guild.premium_subscription_count)
                ),
                "{guild.boost_tier}": str(user.guild.premium_tier),
                "{guild.icon}": user.guild.icon.url if user.guild.icon else "",
                "{guild.vanity}": user.guild.vanity_url,
                "{track}": lastfm_data.get("track", ""),
                "{track.duration}": lastfm_data.get("duration", ""),
                "{artist}": lastfm_data.get("artist", ""),
                "{user}": lastfm_data.get("user", ""),  # noqa: F601
                "{avatar}": lastfm_data.get("avatar", ""),
                "{track.url}": lastfm_data.get("track.url", ""),
                "{artist.url}": lastfm_data.get("artist.url", ""),
                "{scrobbles}": lastfm_data.get("scrobbles", ""),
                "{track.image}": lastfm_data.get("track.image", ""),
                "{username}": lastfm_data.get("username", ""),
                "{artist.plays}": lastfm_data.get("artist.plays", ""),
                "{track.plays}": lastfm_data.get("track.plays", ""),
                "{track.lower}": lastfm_data.get("track.lower", ""),
                "{artist.lower}": lastfm_data.get("artist.lower", ""),
                "{track.hyperlink}": lastfm_data.get("track.hyperlink", ""),
                "{track.hyperlink_bold}": lastfm_data.get("track.hyperlink_bold", ""),
                "{artist.hyperlink}": lastfm_data.get("artist.hyperlink", ""),
                "{artist.hyperlink_bold}": lastfm_data.get("artist.hyperlink_bold", ""),
                "{track.color}": lastfm_data.get("track.color", ""),
                "{artist.color}": lastfm_data.get("artist.color", ""),
                "{date}": lastfm_data.get("date", ""),
            })
        self.template = self._replace_placeholders(template)

    def get_color(self, color: str):
        try:
            return int(color, 16)
        except Exception:
            raise EmbedError(f"color `{color[:6]}` not a valid hex color")

    @property
    def components(self) -> Dict[str, Callable[[Any], None]]:
        return {
            "content": lambda value: self.data.update({"content": value}),
            "autodelete": lambda value: self.data.update({"delete_after": int(value)}),
            "url": lambda value: self.data["embed"].update({"url": value}),
            "color": lambda value: self.data["embed"].update(
                {"color": self.get_color(value.replace("#", ""))}
            ),
            "title": lambda value: self.data["embed"].update({"title": value}),
            "description": (
                lambda value: self.data["embed"].update({"description": value})
            ),
            "thumbnail": (
                lambda value: self.data["embed"].update({"thumbnail": {"url": value}})
            ),
            "fields": (lambda value: self.data["embed"].update({"fields": value})),
            "image": (
                lambda value: self.data["embed"].update({"image": {"url": value}})
            ),
            "footer": (
                lambda value: self.data["embed"]
                .setdefault("footer", {})
                .update({"text": value})
            ),
            "author": (
                lambda value: self.data["embed"]
                .setdefault("author", {})
                .update({"name": value})
            ),
        }

    # def parse_variable(self, match: Match) -> str:
    #     name = match.group(1)
    #     value = self.variables

    #     try:
    #         for attr in name.split("."):
    #             value = value[attr]

    #         return str(value)
    #     except (AttributeError, TypeError, KeyError):
    #         return match.group(1)

    def validate_keys(self: Self):
        stack = []
        template = self.template

        i = 0
        while i < len(template):
            char = template[i]

            if char == "{":
                if i + 1 < len(template) and (template[i + 1] == ":" or template[i + 1] == "$"):
                    stack.append("{:")
                    i += 1
                else:
                    stack.append("{")
            
            elif char == "}":
                if not stack:
                    raise EmbedError("Found a `}` without a matching `{`")
                opening = stack.pop()
                if opening == "{:" and i + 1 < len(template) and template[i + 1] != "}":
                    raise EmbedError("`{:` is missing a `}` at the end")
                elif opening != "{:" and opening != "{":
                    raise EmbedError("Mismatched braces found")

            i += 1

        if stack:
            raise EmbedError("Unmatched `{` found in the template")

    def validate_url(self: Self, url: str) -> Optional[bool]:
        import re

        regex_pattern = r"^https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+.*$"
        data = bool(re.match(regex_pattern, url))
        if not data:
            raise EmbedError(f"`{url}` is not a valid URL Format")
        return data

    async def validate_image(self: Self, url: str) -> Optional[bool]:
        if not image_link.match(url):
            raise EmbedError(f" 1 `{url}` is not a valid Image URL Format")
        async with ClientSession() as session:
            async with session.request("HEAD", url) as response:
                if int(response.headers.get("Content-Length", 15000)) > 240000000:
                    raise EmbedError(f"`{url}` is to large of a URL")
                if content_type := response.headers.get("Content-Type"):
                    if "image" not in content_type.lower():
                        raise EmbedError(
                            f"`{url}` is not a valid Image URL due to the content type being `{content_type}`"
                        )
                else:
                    raise EmbedError(f"`{url}` is not a valid Image URL")
        return True

    async def validate(self: Self) -> NoReturn:
        DICT = {}
        if thumbnail := self.data.get("embed").get("thumbnail", DICT).get("url"):
            await self.validate_image(thumbnail)
        if image := self.data.get("embed").get("image", DICT).get("url"):
            await self.validate_image(image)
        if author_icon := self.data.get("embed").get("author", DICT).get("icon_url"):
            await self.validate_image(author_icon)
        if footer_icon := self.data.get("embed").get("footer", DICT).get("icon_url"):
            await self.validate_image(footer_icon)
        if author_url := self.data.get("embed").get("author", DICT).get("url"):
            self.validate_url(author_url)
        if embed_url := self.data.get("embed").get("url"):
            self.validate_url(embed_url)
        author = self.data.get("embed").get("author", DICT).get("name", "")
        footer = self.data.get("embed").get("footer", DICT).get("text", "")
        title = self.data.get("embed").get("title", "")
        description = self.data.get("embed").get("description", "")
        fields = self.data.get("embed").get("fields", [])
        if len(author) >= 256:
            raise EmbedError(
                "field `author name` is to long the limit is 256 characters"
            )
        if len(footer) >= 2048:
            raise EmbedError(
                "field `footer text` is to long the limit is 2048 characters"
            )
        if len(description) >= 4096:
            raise EmbedError(
                "field `description` is to long the limit is 4096 characters"
            )
        for f in fields:
            if len(f.get("name", "")) >= 256:
                raise EmbedError("field `name` is to long the limit is 256 characters")
            if len(f.get("value", "")) >= 1024:
                raise EmbedError(
                    "field `value` is to long the limit is 1024 characters"
                )
        if len(title) >= 256:
            raise EmbedError("field `title` is to long the limit is 256 characters")
        if len(self.data.get("content", "")) >= 2000:
            raise EmbedError("field `content` is to long the limit is 2000 characters")
        if len(Embed.from_dict(self.data["embed"])) >= 6000:
            raise EmbedError("field `embed` is to long the limit is 6000 characters")
        keys = [k for k in self.data.get("embed", {}).keys()]
        if len(keys) == 1 and "color" in keys:
            raise EmbedError("A field or description is required if you provide a color")

    def _replace_placeholders(self: Self, template: str) -> str:
        template = (
            template.replace("{embed}", "").replace("$v", "").replace("} {", "}{")
        )
        for placeholder, value in self.replacements.items():
            template = template.replace(placeholder, str(value))
        return template

    async def compile(self: Self) -> None:
        """
        Compiles the template into structured data for an embed. Supports processing
        keys like 'footer', 'author', 'button', and 'field' with specific formatting rules.
        """
        self.template = self.template.replace(r"\n", "\n").replace("\\n", "\n")
        matches = self.pattern.findall(self.template)

        def parse_footer(value: str):
            """Parses footer data."""
            values = value.split("&&")
            footer_data = {"text": values[0].strip()}
            if len(values) > 1:
                footer_data["url"] = values[1].strip()
            if len(values) > 2:
                footer_data["icon_url"] = values[2].strip()
            self.data["embed"]["footer"] = footer_data

        def parse_author(value: str):
            """Parses author data."""
            values = value.split("&&")
            author_data = {"name": values[0].strip()}
            for v in values[1:]:
                v = v.strip()
                if any(ext in v for ext in [".jpg", ".png", ".gif", ".webp"]):
                    author_data["icon_url"] = v
                else:
                    author_data["url"] = v
            self.data["embed"]["author"] = author_data

        def parse_button(value: str):
            """Parses button data."""
            button_data = value.split("&&")
            if len(button_data) >= 2:
                label = button_data[0].strip()
                url = button_data[1].strip().replace("url: ", "").replace(" ", "")
                self.validate_url(url)
                self.data["button"] = {"label": label, "url": url}

        def parse_field(value: str):
            """Parses field data."""
            if "fields" not in self.data["embed"]:
                self.data["embed"]["fields"] = []
            field_data = value.split("&&")
            field = {
                "name": field_data[0].strip(),
                "value": field_data[1].strip().replace("value: ", "") if len(field_data) > 1 else None,
                "inline": bool(field_data[2].strip().replace("inline ", "")) if len(field_data) > 2 else False,
            }
            self.data["embed"]["fields"].append(field)

        for match in matches:
            parts = match.split(":", 1)
            if len(parts) != 2:
                continue
            key, value = parts[0], parts[1].strip()
            if key == "footer":
                parse_footer(value)
            elif key == "author":
                parse_author(value)
            elif key == "button":
                parse_button(value)
            elif key == "field":
                parse_field(value)
            elif key in self.components:
                self.components[key](value)

        if self.template.startswith("{"):
            self.validate_keys()
            await self.validate()
        else:
            self.data.pop("embed", None)
            self.data["content"] = self.template

        if not self.data.get("embed"):
            self.data.pop("embed", None)

    async def send(self: Self, target: Union[Context, GuildChannel], **kwargs) -> Message:
        # Handle button view
        button = self.data.pop("button", None)
        if button:
            view = View()
            view.add_item(
                Button(
                    style=ButtonStyle.link,
                    label=button["label"],
                    url=button["url"],
                )
            )
            kwargs["view"] = view
        else:
            if kwargs.get("view"):
                pass
            else:
                kwargs["view"] = None

        # Prepare embed
        if isinstance(self.data.get("embed"), Embed):
            embed = self.data["embed"]
        else:
            embed = (
                Embed.from_dict(self.data["embed"]) if self.data.get("embed") else None
            )
        if embed:
            kwargs["embed"] = embed

        # Add content if present
        if content := self.data.get("content"):
            kwargs["content"] = content

        # Handle return_embed early
        if kwargs.pop("return_embed", False):
            return kwargs

        # Handle message editing vs sending
        message = kwargs.pop("message", None)
        if message and hasattr(message, "edit"):
            # Filter kwargs to only include valid edit parameters
            edit_kwargs = {
                k: v for k, v in kwargs.items() 
                if k in ["content", "embed", "view"]
            }
            return await message.edit(**edit_kwargs)
        
        # Handle delete_after for new messages only
        if delete_after := self.data.get("delete_after"):
            kwargs["delete_after"] = delete_after

        return await target.send(**kwargs)

    @classmethod
    async def convert(cls: Type["Script"], ctx: Context, argument: str) -> "Script":
        data = cls(template=argument, user=ctx.author)
        await data.compile()
        return data

    def __repr__(self: Self) -> str:
        return f"<Parser template={self.template!r}>"

    def __str__(self: Self) -> str:
        return self.template


# type: ignore

