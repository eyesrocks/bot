from discord import (
    Guild,
    AutoModTrigger,
    AutoModRuleTriggerType,
    AutoModRuleAction,
    utils,
    TextChannel,
    AutoModRuleEventType,
    ForumChannel,
    Member,
    User,
    Role,
)
from discord.ext.commands import CommandError
from typing import Union, Optional, Literal, List

invite_regex = r"(?:https?://)?discord(?:app)?\.(?:com/invite|gg)/[a-zA-Z0-9]+/?"


def str_to_action(string: str):
    _ = string.lower()
    if _ in ["timeout", "mute"]:
        return AutoModAction.timeout
    elif _ == "block":
        return AutoModAction.block_message
    else:
        return AutoModAction.send_alert_message


async def add_keyword(
    guild: Guild, keyword: Union[str, List[str]], migrate: Optional[bool] = False
) -> bool:
    val = False
    automod_rules = await guild.fetch_automod_rules()
    if keyword_rule := utils.get(automod_rules, name="greed-keywords"):
        if migrate == True:
            raise CommandError("Your **keywords** have already been migrated")
        if keyword_rule.trigger.type == AutoModRuleTriggerType.keyword:
            new_keywords = keyword_rule.trigger.keyword_filter + [keyword[:59]]
            if len(new_keywords) > 1000:
                raise CommandError("You are limited to 1000 filtered words")
            else:
                trigger = AutoModTrigger(
                    type=AutoModRuleTriggerType.keyword, keyword_filter=new_keywords
                )
                await keyword_rule.edit(trigger=trigger)
                val = True
    else:
        if migrate:
            val = True
            if isinstance(keyword, str):
                keywords = [keyword]
            else:
                keywords = keyword
            await guild.create_automod_rule(
                name="greed-keywords",
                event_type=AutoModRuleEventType.message_send,
                trigger=AutoModTrigger(keyword_filter=keywords),
                enabled=True,
                actions=[
                    AutoModRuleAction(
                        custom_message="Greed Blocked you from saying this"
                    )
                ],
            )
    return val


async def clear_keywords(guild: Guild):
    automod_rules = await guild.fetch_automod_rules()
    if keyword_rule := utils.get(automod_rules, name="greed-keywords"):
        await keyword_rule.delete()
        return True
    return False


async def remove_keyword(guild: Guild, keyword: str) -> bool:
    val = False
    automod_rules = await guild.fetch_automod_rules()
    if keyword_rule := utils.get(automod_rules, name="greed-keywords"):
        if keyword_rule.trigger.type == AutoModRuleTriggerType.keyword:
            new_keywords = keyword_rule.trigger.keyword_filter
            new_keywords.remove(keyword[:59])
            trigger = AutoModTrigger(
                type=AutoModRuleTriggerType.keyword, keyword_filter=new_keywords
            )
            await keyword_rule.edit(trigger=trigger)
            val = True
    return val


async def exempt(guild: Guild, obj: Union[TextChannel, ForumChannel, Role]):
    rules = await guild.fetch_automod_rules()
    kwargs = {}
    for rule in rules:
        if isinstance(obj, (TextChannel, ForumChannel)):
            if len(rule.exempt_channels) > 0:
                rule.exempt_channels.append(obj)
                kwargs["exempt_channels"] = rule.exempt_channels
            else:
                kwargs["exempt_channels"] = [obj]
        else:
            if len(rule.exempt_roles) > 0:
                rule.exempt_roles.append(obj)
                kwargs["exempt_roles"] = rule.exempt_roles
            else:
                kwargs["exempt_roles"]

        await rule.edit(**kwargs)
        return True
