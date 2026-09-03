import logging
import discord
from discord.ext import commands, tasks
from datetime import datetime

import config
from database import get_conn


class ActivityRolesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _build_roles_config(self):
        """Группирует правила по role_id. Для каждой роли список альтернатив (ИЛИ)."""
        roles = {}
        for rule in config.ACTIVITY_ROLES_CONFIG:
            role_id = rule.get("role_id")
            if not role_id:
                continue
            entry = roles.setdefault(role_id, {"prev_role_id": rule.get("prev_role_id"), "checks": []})
            check_type = rule.get("type")
            if check_type == "voice_hours":
                entry["checks"].append(("voice_seconds", rule.get("hours", 0) * 3600))
            elif check_type == "messages":
                entry["checks"].append(("messages", rule.get("count", 0)))
            elif check_type == "voice_joins":
                entry["checks"].append(("voice_joins", rule.get("count", 0)))
        return roles

    @tasks.loop(minutes=5)
    async def check_activity_roles(self):
        roles_conf = self._build_roles_config()
        if not roles_conf:
            return

        for guild in self.bot.guilds:
            conn = get_conn()

            # Перебираем роли в заданном порядке конфигурации (иерархия)
            ordered = [r for r in config.ACTIVITY_ROLES_CONFIG if r.get("role_id")]
            seen = set()
            for rule in ordered:
                role_id = rule["role_id"]
                if role_id in seen:
                    continue
                seen.add(role_id)

                conf = roles_conf[role_id]
                role = guild.get_role(role_id)
                if not role:
                    continue

                # Собираем eligible: для каждой альтернативы выбираем тех, кто прошёл проверку
                eligible_ids = set()
                for col, threshold in conf["checks"]:
                    rows = conn.execute(
                        f"SELECT user_id FROM member_stats WHERE {col} >= ?",
                        (threshold,),
                    ).fetchall()
                    for row in rows:
                        eligible_ids.add(row["user_id"])

                # Проходим по всем членам гильдии
                for member in guild.members:
                    if member.bot:
                        continue
                    has_role = any(r.id == role_id for r in member.roles)

                    if not has_role and member.id in eligible_ids:
                        try:
                            # Снимаем предыдущую роль (иерархия повышения)
                            prev_role_id = conf.get("prev_role_id")
                            if prev_role_id:
                                prev_role = guild.get_role(prev_role_id)
                                if prev_role and prev_role in member.roles:
                                    await member.remove_roles(prev_role, reason="Повышение: снята предыдущая роль")
                                    conn.execute(
                                        "INSERT INTO activity_roles_log (user_id, role_id, granted, timestamp) VALUES (?, ?, 0, ?)",
                                        (member.id, prev_role_id, datetime.utcnow().isoformat()),
                                    )
                            await member.add_roles(role, reason="Activity role: threshold met")
                            conn.execute(
                                "INSERT INTO activity_roles_log (user_id, role_id, granted, timestamp) VALUES (?, ?, 1, ?)",
                                (member.id, role_id, datetime.utcnow().isoformat()),
                            )
                            logging.info("Выдана роль %s → %s", role.name, member)
                        except Exception as e:
                            logging.error("Ошибка выдачи роли %s: %s", role.name, e)

            conn.commit()

    @check_activity_roles.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.check_activity_roles.is_running():
            self.check_activity_roles.start()


async def setup(bot: commands.Bot):
    await bot.add_cog(ActivityRolesCog(bot))
