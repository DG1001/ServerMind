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
    print(f"🤖 AI Host ist online als {bot.user}")


@bot.command(name="do")
async def do_task(ctx, *, task):
    """
    Nimmt den Befehl, packt die Instruktionen dazu und feuert ab.
    """
    await ctx.send(f"🫡 Verstanden: `{task}`. Ich arbeite dran...")

    # Wir bauen den Prompt zusammen:
    # Instruktionen + User Task
    # Hinweis: Viele Tools lesen CLAUDE.md automatisch, wenn es im Ordner liegt.
    # Wir gehen hier auf Nummer sicher und übergeben es explizit oder vertrauen auf CWD.

    command = [
        CLAUDE_CLI_PATH,  # Claude CLI path from config
        "-p",
        task,  # Der Prompt
        "--dangerously-skip-permissions",  # Der YOLO Mode (Syntax variiert je nach Tool version)
        # Ggf. explizit Kontext files angeben, falls das Tool das braucht:
        # "--context", "host.md", "CLAUDE.md"
    ]

    try:
        # Async subprocess to avoid blocking Discord heartbeat
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=WORKDIR,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "NO_COLOR": "1"},  # Keine Farbcodes für Discord
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

        # Kombinierter Output
        full_response = output
        if error:
            full_response += f"\n\n⚠️ STDERR:\n{error}"

        # Discord Limit Check (2000 Zeichen)
        if len(full_response) > MAX_OUTPUT_LENGTH:
            # Splitten oder Datei senden
            summary = (
                full_response[:TRUNCATE_LENGTH] + "\n... [Output truncated, see file]"
            )
            with open(f"{WORKDIR}/last_output.txt", "w") as f:
                f.write(full_response)

            await ctx.send(
                f"✅ Fertig:\n```\n{summary}\n```",
                file=discord.File(f"{WORKDIR}/last_output.txt"),
            )
        else:
            if not full_response.strip():
                full_response = "Task erledigt (Kein Output)."
            await ctx.send(f"✅ Fertig:\n```\n{full_response}\n```")

    except subprocess.TimeoutExpired:
        await ctx.send(
            f"⏰ Timeout: Der Agent hat länger als {CLAUDE_TIMEOUT / 60:.0f} Min gebraucht. Prüfe den Server manuell."
        )
    except Exception as e:
        await ctx.send(f"💥 Interner Fehler: {str(e)}")


bot.run(DISCORD_TOKEN)
