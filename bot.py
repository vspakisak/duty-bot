import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import random
import os
from datetime import datetime, timezone
from flask import Flask

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

DUTY_CHANNEL_ID = 1386555864386764877  # replace with your duty channel ID
LOG_CHANNEL_ID = 1386555864831365191  # replace with your log channel ID
ADMIN_USER_ID = 848805899790581780    # replace with your own user ID

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

duty_data = {}
points_data = {}

class DutyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Start", style=discord.ButtonStyle.success, custom_id="start_button")
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        if user.id in duty_data:
            await interaction.response.send_message("You're already on duty!", ephemeral=True)
            return

        duty_data[user.id] = {
            "start_time": datetime.now(timezone.utc),
            "reminder_count": 0,
            "active": True
        }

        await interaction.response.send_message("Duty started.", ephemeral=True)
        await send_log("Duty Started", "User started a duty.", user, color=discord.Color.green())
        asyncio.create_task(schedule_reminder(user))

    @discord.ui.button(label="End", style=discord.ButtonStyle.danger, custom_id="end_button")
    async def end(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        if user.id not in duty_data:
            await interaction.response.send_message("You're not currently on duty.", ephemeral=True)
            return

        await end_duty(user, "Ended manually.")
        await interaction.response.send_message("Duty ended.", ephemeral=True)
        await send_log("Duty Ended", "User manually ended their duty.", user, color=discord.Color.red())

class ReminderView(discord.ui.View):
    def __init__(self, user):
        super().__init__(timeout=120)
        self.user = user
        self.responded = False

    @discord.ui.button(label="Continue", style=discord.ButtonStyle.primary)
    async def continue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("This isn't for you!", ephemeral=True)
            return

        self.responded = True
        await interaction.response.send_message("Reminder acknowledged. Continuing duty.", ephemeral=True)
        await send_log(
            "Reminder Continued",
            f"User responded to Reminder #{duty_data[self.user.id]['reminder_count']} and chose to continue.",
            self.user,
            color=discord.Color.blurple()
        )
        asyncio.create_task(schedule_reminder(self.user))

    @discord.ui.button(label="End", style=discord.ButtonStyle.danger)
    async def end_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("This isn't for you!", ephemeral=True)
            return

        self.responded = True
        await interaction.response.send_message("Duty ended from reminder.", ephemeral=True)
        await end_duty(self.user, "Ended from reminder.")
        await send_log("Duty Ended via Reminder", "User ended duty from reminder.", self.user, color=discord.Color.red())

async def schedule_reminder(user):
    delay = random.randint(1200, 1800)  # 20-30 minutes
    await asyncio.sleep(delay)

    if user.id not in duty_data or not duty_data[user.id]["active"]:
        return

    duty_data[user.id]["reminder_count"] += 1
    reminder_number = duty_data[user.id]["reminder_count"]
    start_time = duty_data[user.id]["start_time"]
    duty_duration = datetime.now(timezone.utc) - start_time

    embed = discord.Embed(
        title=f"Reminder #{reminder_number}",
        description=f"You are currently on duty for {str(duty_duration).split('.')[0]}",
        color=discord.Color.orange()
    )

    view = ReminderView(user)
    try:
        message = await user.send(embed=embed, view=view)
    except discord.Forbidden:
        return

    await view.wait()

    if not view.responded:
        await user.send(embed=discord.Embed(
            title="Duty Auto Ended",
            description="No response to reminder.",
            color=discord.Color.red()
        ))
        await send_log(
            "Duty Auto Ended",
            f"No response to Reminder #{reminder_number}. Duty auto-ended.",
            user,
            color=discord.Color.orange()
        )
        await end_duty(user, "No response to reminder.")

async def end_duty(user: discord.User, reason: str):
    data = duty_data.pop(user.id, None)
    if data:
        duration = (datetime.now(timezone.utc) - data["start_time"]).total_seconds()
        points_earned = int(duration // 240)

        if points_earned > 0:
            points_data[user.id] = points_data.get(user.id, 0) + points_earned

        total_points = points_data.get(user.id, 0)

        try:
            await user.send(embed=discord.Embed(
                title="Duty Ended",
                description=(
                    f"**Reason:** {reason}\n"
                    f"**Points earned this duty:** {points_earned}\n"
                    f"**Your total points:** {total_points}"
                ),
                color=discord.Color.green()
            ))
        except discord.Forbidden:
            pass

        await send_log(
            "Duty Ended",
            f"Reason: {reason}\nPoints earned: **{points_earned}**\nTotal points: **{total_points}**",
            user,
            color=discord.Color.dark_green()
        )

async def send_log(title: str, description: str, user: discord.User, color=discord.Color.greyple()):
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if not channel:
        return

    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_author(name=f"{user} ({user.id})", icon_url=user.avatar.url if user.avatar else None)
    embed.timestamp = datetime.now(timezone.utc)
    await channel.send(embed=embed)

@bot.tree.command(name="total", description="View total points of a user (Admin only)")
@app_commands.describe(user_id="The ID of the user")
async def total(interaction: discord.Interaction, user_id: str):
    if interaction.user.id != ADMIN_USER_ID:
        await interaction.response.send_message("You are not authorized to use this command.", ephemeral=True)
        return
    try:
        uid = int(user_id)
        points = points_data.get(uid, 0)
        await interaction.response.send_message(f"User ID `{uid}` has **{points}** point(s).", ephemeral=True)
    except ValueError:
        await interaction.response.send_message("Invalid user ID format.", ephemeral=True)

@bot.tree.command(name="resetpoints", description="Reset points of a user (Admin only)")
@app_commands.describe(user_id="The ID of the user")
async def resetpoints(interaction: discord.Interaction, user_id: str):
    if interaction.user.id != ADMIN_USER_ID:
        await interaction.response.send_message("You are not authorized to use this command.", ephemeral=True)
        return
    try:
        uid = int(user_id)
        points_data[uid] = 0
        await interaction.response.send_message(f"Points for user ID `{uid}` have been reset.", ephemeral=True)
    except ValueError:
        await interaction.response.send_message("Invalid user ID format.", ephemeral=True)

@bot.tree.command(name="addpoints", description="Add points to a user manually (Admin only)")
@app_commands.describe(
    user_id="The user ID to give points to",
    points="How many points to add"
)
async def addpoints(interaction: discord.Interaction, user_id: str, points: int):
    if interaction.user.id != ADMIN_USER_ID:
        await interaction.response.send_message("You are not authorized to use this command.", ephemeral=True)
        return
    try:
        uid = int(user_id)
        if points < 0:
            await interaction.response.send_message("You cannot add negative points.", ephemeral=True)
            return
        points_data[uid] = points_data.get(uid, 0) + points
        await interaction.response.send_message(
            f"Added **{points}** point(s) to user ID `{uid}`.\nNew total: **{points_data[uid]}** point(s).",
            ephemeral=True
        )
    except ValueError:
        await interaction.response.send_message("Invalid user ID format.", ephemeral=True)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}!")
    bot.add_view(DutyView())
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

    channel = bot.get_channel(DUTY_CHANNEL_ID)
    if channel:
        embed = discord.Embed(
            title="Start/End Your Duty",
            description="Click **Start** to begin your duty. Click **End** to end it.",
            color=discord.Color.blue()
        )
        await channel.send(embed=embed, view=DutyView())

if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))
