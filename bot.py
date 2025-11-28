import discord
import subprocess
import asyncio
import os
from discord.ext import commands
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- KONFIGURATION ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
WORKDIR = os.getenv("WORKDIR", "/workspace")
CLAUDE_CLI_PATH = os.getenv("CLAUDE_CLI_PATH", "claude")
CLAUDE_TIMEOUT = int(os.getenv("CLAUDE_TIMEOUT", "600"))
MAX_OUTPUT_LENGTH = int(os.getenv("MAX_OUTPUT_LENGTH", "1900"))
TRUNCATE_LENGTH = int(os.getenv("TRUNCATE_LENGTH", "1000"))

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"🤖 AI Host is online as {bot.user}")


@bot.command(name="do")
async def do_task(ctx, *, task):
    """
    Takes the command, adds instructions, and executes.
    """
    await ctx.send(f"🫡 Understood: `{task}`. Working on it...")

    # Build the prompt:
    # Instructions + User Task
    # Note: Many tools auto-read CLAUDE.md when it's in the directory.
    # We trust CWD or can explicitly pass context files if needed.

    command = [
        CLAUDE_CLI_PATH,  # Claude CLI path from config
        "-p",
        task,  # The prompt
        "--dangerously-skip-permissions",  # YOLO mode (syntax varies by tool version)
        # Optionally specify context files explicitly if needed:
        # "--context", "host.md", "CLAUDE.md"
    ]

    try:
        # Async subprocess to avoid blocking Discord heartbeat
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=WORKDIR,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "NO_COLOR": "1"},  # No color codes for Discord
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=CLAUDE_TIMEOUT
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise subprocess.TimeoutExpired(command, CLAUDE_TIMEOUT)

        output = stdout.decode("utf-8", errors="replace")
        error = stderr.decode("utf-8", errors="replace")

        # Combined output
        full_response = output
        if error:
            full_response += f"\n\n⚠️ STDERR:\n{error}"

        # Discord Limit Check (2000 characters)
        if len(full_response) > MAX_OUTPUT_LENGTH:
            # Split or send as file
            summary = (
                full_response[:TRUNCATE_LENGTH] + "\n... [Output truncated, see file]"
            )
            with open(f"{WORKDIR}/last_output.txt", "w") as f:
                f.write(full_response)

            await ctx.send(
                f"✅ Done:\n{summary}",
                file=discord.File(f"{WORKDIR}/last_output.txt"),
            )
        else:
            if not full_response.strip():
                full_response = "Task completed (no output)."
            # Send without code blocks to allow Discord markdown rendering
            await ctx.send(f"✅ Done:\n{full_response}")

    except subprocess.TimeoutExpired:
        await ctx.send(
            f"⏰ Timeout: The agent took longer than {CLAUDE_TIMEOUT / 60:.0f} min. Check the server manually."
        )
    except Exception as e:
        await ctx.send(f"💥 Internal error: {str(e)}")


bot.run(DISCORD_TOKEN)
