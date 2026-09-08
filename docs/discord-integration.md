# Getting Started with discord.py (in a FastAPI server)

This doc covers the discord.py basics and — more importantly — the specific things
that change when you run a Discord bot *inside* a FastAPI app instead of as its
own standalone script. It's written against your current `main.py`, which
already runs a `FastAPI` app with a `lifespan` context manager and an
`AsyncIOScheduler`. `discord.py` fits into that same pattern.

Docs reference: https://discordpy.readthedocs.io/en/stable/

---

## 1. The core concepts

- **`discord.Client`** — the low-level bot connection. You subscribe to Gateway
  events (`on_ready`, `on_message`, etc.) via `@client.event` or by subclassing.
- **`discord.ext.commands.Bot`** — a `Client` subclass that adds a command
  framework (prefix commands, cogs, extensions) and is what most real bots use.
- **Intents** — Discord requires you to explicitly declare which event
  categories you want (message content, members, presences, etc.). You toggle
  these in the [Developer Portal](https://discord.com/developers/applications)
  *and* in code.
- **Gateway connection** — the bot maintains a persistent WebSocket connection
  to Discord. This is a long-running coroutine, not a request/response call —
  that's the crux of why it interacts differently with FastAPI than a typical
  dependency.

### Standalone quickstart (for reference)

```python
import discord

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    if message.content.startswith("$hello"):
        await message.channel.send("Hello!")

client.run("YOUR_TOKEN")
```

`client.run(token)` is the standalone entry point: it creates its own event
loop, connects, and blocks forever. **This is the one thing you cannot use
inside FastAPI** — see below.

---

## 2. Intents, in detail

Intents tell Discord which categories of Gateway events to actually send you.
This isn't optional configuration — the bot silently won't receive events for
anything not enabled, and three of them ("privileged intents") require you to
flip a switch in the Developer Portal *and* enable them in code, or your bot
fails to log in at all.

**Standard intent flags** (`discord.Intents`), each maps to a slice of
Gateway events:

| Flag | Covers |
|---|---|
| `guilds` | guild create/update/delete, channel/role/thread updates |
| `members` ⚠️ privileged | member join/update/leave, role changes on members |
| `bans` | ban/unban events |
| `emojis` / `emojis_and_stickers` | emoji & sticker updates |
| `integrations` | integration create/update/delete |
| `webhooks` | webhook updates |
| `invites` | invite create/delete |
| `voice_states` | voice channel join/leave/mute/etc. |
| `presences` ⚠️ privileged | online/idle/dnd status and activity updates |
| `messages` | message create/edit/delete (metadata only) |
| `message_content` ⚠️ privileged | the actual text/embeds/attachments of a message |
| `reactions` | reaction add/remove |
| `typing` | typing-indicator events |
| `direct_messages` | the DM-channel equivalents of `messages`/`reactions`/`typing` |
| `scheduled_events` | guild scheduled event updates |
| `auto_moderation_configuration` / `auto_moderation_execution` | AutoMod rule and trigger events |

**Convenience constructors:**
- `Intents.default()` — everything except the 3 privileged intents. Good
  starting point for most bots.
- `Intents.all()` — every flag, including privileged ones (still requires
  Portal toggles or login fails).
- `Intents.none()` — everything off; flip on individually.

**Privileged intents** (`members`, `presences`, `message_content`) must be
enabled in **Developer Portal → your app → Bot → Privileged Gateway
Intents**, in addition to setting them in code:

```python
intents = discord.Intents.default()
intents.message_content = True   # needed to read message text for prefix commands
intents.members = True           # needed for on_member_join, member cache, etc.
```

**Rule of thumb:** only request what you use. Verified bots in 100+ servers
must be *approved* by Discord for privileged intents, and unused intents mean
extra Gateway traffic and cache memory for no benefit. If you're only doing
slash commands and never reading raw message text, you likely don't need
`message_content` or `members` at all — see §6, slash commands don't require
`message_content`.

---

## 3. Setup checklist

1. Create an application + bot user at the
   [Developer Portal](https://discord.com/developers/applications).
2. Copy the **bot token**, put it in `.env` (you already load `.env` via
   `python-dotenv` in `main.py`):
   ```
   DISCORD_BOT_TOKEN=...
   ```
3. Enable the intents you need (e.g. **Message Content Intent**) both in the
   Portal ("Bot" tab → Privileged Gateway Intents) and in code.
4. Invite the bot to a server using an OAuth2 URL with the `bot` (and
   `applications.commands` if you want slash commands) scope.
5. `discord-py` is already in your `pyproject.toml`, so `uv sync` gives you
   the library — nothing extra to install.

---

## 3. Why FastAPI changes things

A discord.py bot wants to **own the event loop and run forever**
(`client.run()`). A FastAPI/Uvicorn app is **also** an async program that owns
the event loop and runs forever. You can't have two processes both calling
`asyncio.run()` — you need the bot's Gateway connection to live *inside* the
same loop Uvicorn is already driving.

The fix: don't call `bot.run()`. Instead, start the bot with `await
bot.start(token)` as a background **task** on the loop FastAPI/Uvicorn already
created, using the exact `lifespan` pattern you're using for
`AsyncIOScheduler` in `main.py`.

### Pattern

```python
# discord_bot.py
import os
import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Discord bot logged in as {bot.user}")
```

```python
# main.py
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from dotenv import load_dotenv
import os

from discord_bot import bot

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(check_discounts, "cron", day_of_week="sun", hour=23, minute=0)
    scheduler.start()

    # Run the bot's gateway connection as a background task on the
    # SAME event loop FastAPI/Uvicorn is using — do NOT call bot.run().
    discord_task = asyncio.create_task(bot.start(DISCORD_TOKEN))

    yield

    scheduler.shutdown()
    await bot.close()          # graceful disconnect
    discord_task.cancel()
    try:
        await discord_task
    except asyncio.CancelledError:
        pass

app = FastAPI(lifespan=lifespan)
```

That's the entire integration. Everything else about discord.py — cogs,
commands, event handlers — works exactly like the standalone docs describe,
because it's still just coroutines on an event loop.

---

## 4. Practical consequences of this pattern

**`bot.start()` vs `bot.run()`**
`bot.run(token)` is literally sugar for "set up a new event loop, call
`start()`, block until done, tear down the loop, handle Ctrl+C." Since
Uvicorn already provides steps 1 and 3–4, you call `start()` directly and let
FastAPI's lifespan manage the lifecycle.

**Startup ordering / `on_ready` race**
`bot.start()` returns once the connection process kicks off, not once the bot
is actually connected. If a FastAPI route needs to talk to Discord
immediately after boot, guard it with `await bot.wait_until_ready()` or check
`bot.is_ready()` rather than assuming the bot is live the instant the app
starts serving requests.

**Calling Discord from your API routes**
Because the bot lives on the same loop, a route handler can just reach into
`bot` and await a coroutine directly — no queue, no HTTP call to itself:

```python
@app.post("/notify")
async def notify(channel_id: int, message: str):
    channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
    await channel.send(message)
    return {"ok": True}
```

This is the main payoff of embedding the bot in FastAPI: your scraping
pipeline (`check_discounts`, `tasks.py`, `parsers/`) can post directly to
Discord when it finds something, with no separate process or message broker.

**Don't block the shared event loop**
This matters *more* than in a standalone bot, because now a slow synchronous
call stalls both the Discord Gateway (risking heartbeat timeouts →
disconnects) and every FastAPI request being served concurrently. Your
`brightdata_scraper` in `utils.py` and the `requests`-based parsers are
synchronous — call them via `run_in_executor` / `asyncio.to_thread` from any
`async def` route or Discord event handler, don't `await` them directly or
call them inline in an `async def`:

```python
result = await asyncio.to_thread(brightdata_scraper, url)
```

`check_discounts` already runs as an APScheduler job in the same loop, so the
same rule applies there.

**Thread safety with APScheduler**
`AsyncIOScheduler` runs jobs on the same asyncio loop by default (good — it's
already compatible). If you ever switch to a scheduler that runs jobs in a
separate thread, you can't `await` bot coroutines directly from that thread;
you'd need `asyncio.run_coroutine_threadsafe(coro, loop)`.

**Graceful shutdown**
Always `await bot.close()` in the lifespan's teardown (after `yield`). Without
it, Uvicorn's shutdown can leave the Gateway WebSocket dangling and Discord
sees an unclean disconnect.

**One process, one bot instance**
If you run Uvicorn with multiple workers (`--workers N`) or under something
like Gunicorn with multiple processes, each process would try to log in the
*same* bot token to the Gateway independently — Discord allows this but it's
almost never what you want (duplicate event handling, sharding confusion).
Keep the Discord-bot-in-FastAPI pattern to a single worker process, or run the
bot as a separate service if you need multiple API workers.

---

## 5. Ways users can interact with the bot

Discord bots aren't limited to reading chat messages — discord.py exposes
several distinct interaction surfaces. None of this changes because you're in
FastAPI; it's all coroutines on the shared loop like everything else.

### 5.1 Cogs (organization, not an interaction type)

`Cog`s are just a way to group commands/listeners/state into a class, used
alongside whichever command styles below you pick:

```python
class Sales(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def sales(self, ctx, department: str = "men"):
        with Session(engine) as session:
            rows = session.exec(select(Sale).where(Sale.department == department)).all()
        await ctx.send(f"{len(rows)} sales found in {department}")

# inside an async setup step (e.g. before bot.start()):
await bot.add_cog(Sales(bot))
```

### 5.2 Prefix commands (`commands.Bot`, text-based)

The classic style: user types `!sales men` in a text channel, matched against
`command_prefix`. Requires the **`message_content`** privileged intent, since
the bot needs to read raw message text to find the prefix. This is the
easiest to prototype with but the least modern/discoverable — Discord's UI
doesn't autocomplete or document these for users.

```python
from discord.ext import commands

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.command()
async def hello(ctx):
    await ctx.send("Hello!")

@bot.command()
async def sales(ctx, department: str = "men"):
    with Session(engine) as session:
        rows = session.exec(select(Sale).where(Sale.department == department)).all()
    await ctx.send(f"{len(rows)} sales found in {department}")
```

No `on_message` written by you at all — typing `!hello` or `!sales women` in
a channel just works.

#### How this relates to `on_message`

`on_message` is the **raw** Gateway event: it fires for every message the bot
can see, with no concept of "commands" built in. A plain `discord.Client`
example like this is manually string-matching, not using the commands
framework at all:

```python
@client.event
async def on_message(message):
    if message.author == client.user:
        return
    if message.content.startswith("$hello"):
        await message.channel.send("Hello!")
```

`commands.Bot` gets you real command parsing (names, arguments, error
handling, help text) by registering **its own internal `on_message`
listener** the moment you instantiate it. For every incoming message it:

1. Checks whether the content starts with `command_prefix`.
2. If so, parses the command name and arguments.
3. Looks up a matching `@bot.command()` function and invokes it.
4. If nothing matches, it silently does nothing.

So yes — command dispatch runs on `on_message` under the hood, for *every*
message received (still gated by the `message_content` intent), it just
no-ops when there's no match.

#### ⚠️ The override gotcha

If you define your **own** `on_message` on a `commands.Bot`, you completely
replace the built-in one — and your `!commands` silently stop working, with
no error raised anywhere:

```python
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.command()
async def hello(ctx):
    await ctx.send("Hello!")

@bot.event
async def on_message(message):
    print(f"got: {message.content}")
    # !hello now does NOTHING — this overrode command dispatch
```

Fix it by manually forwarding to the dispatcher at the end of your override:

```python
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    print(f"got: {message.content}")
    await bot.process_commands(message)   # restores !command dispatch
```

**Better fix, usually:** use `@bot.listen()` instead of `@bot.event`. It
*adds* a listener rather than replacing the built-in one, so multiple
handlers can react to the same event without stepping on each other and
you don't have to remember `process_commands()`:

```python
@bot.listen("on_message")
async def log_all_messages(message):
    print(f"got: {message.content}")
    # built-in command dispatcher is untouched — !hello still works
```

#### Ignore the bot's own messages

Worth doing regardless of approach — without it, if the bot's own output
ever matches a trigger, or you're running multiple bots that react to each
other, you get infinite loops:

```python
if message.author == bot.user:   # or message.author.bot to ignore all bots
    return
```

### 5.3 Slash commands (`app_commands`, the modern standard)

Slash commands are registered with Discord itself (not just your bot), so
users get autocomplete, inline docs, and typed parameters in the Discord
client. They do **not** require `message_content` — the interaction payload
comes through a separate Gateway path.

```python
from discord import app_commands

@bot.tree.command(name="sales", description="Show current sales for a department")
@app_commands.describe(department="Which department to filter by")
@app_commands.choices(department=[
    app_commands.Choice(name="Men", value="men"),
    app_commands.Choice(name="Women", value="women"),
])
async def sales(interaction: discord.Interaction, department: app_commands.Choice[str]):
    with Session(engine) as session:
        rows = session.exec(select(Sale).where(Sale.department == department.value)).all()
    await interaction.response.send_message(f"{len(rows)} sales found in {department.name}")
```

**Syncing** — Discord needs to know the command exists before users see it.
Sync once (usually in `on_ready`, guarded so it only runs once):

```python
@bot.event
async def on_ready():
    await bot.tree.sync()   # global sync can take up to ~1hr to propagate
    # or, for instant updates during dev, sync to one guild:
    # await bot.tree.sync(guild=discord.Object(id=YOUR_TEST_GUILD_ID))
    print(f"Discord bot logged in as {bot.user}")
```

**Autocomplete** for dynamic choices (e.g. suggest live department names from
your DB as the user types):

```python
@sales.autocomplete("department")
async def department_autocomplete(interaction: discord.Interaction, current: str):
    options = ["men", "women", "kids"]
    return [
        app_commands.Choice(name=o, value=o)
        for o in options if current.lower() in o.lower()
    ]
```

**Interaction responses** — an interaction can only be responded to once via
`interaction.response`; anything after that goes through
`interaction.followup`:

```python
await interaction.response.send_message("Working on it...", ephemeral=True)
# later, possibly after an await that takes a while:
await interaction.followup.send("Done!")
```

If a handler might take longer than Discord's ~3s response window (e.g. it
calls `brightdata_scraper`), acknowledge immediately with
`await interaction.response.defer()`, do the (threaded) work, then
`await interaction.followup.send(...)`.

### 5.4 Context menu commands

Right-click commands on a user or a message, also registered via the command
tree:

```python
@bot.tree.context_menu(name="Flag as sale")
async def flag_message(interaction: discord.Interaction, message: discord.Message):
    await interaction.response.send_message(f"Flagged: {message.content[:100]}", ephemeral=True)
```

### 5.5 Buttons, select menus, and modals (`discord.ui`)

For richer interaction than "run a command and get text back," attach
persistent UI components to a message via a `View`:

```python
class SalesView(discord.ui.View):
    def __init__(self, department: str):
        super().__init__(timeout=180)
        self.department = department

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.primary)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        with Session(engine) as session:
            rows = session.exec(select(Sale).where(Sale.department == self.department)).all()
        await interaction.response.edit_message(content=f"{len(rows)} sales", view=self)

    @discord.ui.select(options=[
        discord.SelectOption(label="Men", value="men"),
        discord.SelectOption(label="Women", value="women"),
    ])
    async def pick_department(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.department = select.values[0]
        await interaction.response.edit_message(content=f"Switched to {self.department}")

await channel.send("Sales dashboard", view=SalesView("men"))
```

**Modals** are pop-up forms (text inputs) triggered from a button or slash
command — useful for anything that needs freeform input:

```python
class FeedbackModal(discord.ui.Modal, title="Feedback"):
    comment = discord.ui.TextInput(label="Your comment", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"Thanks: {self.comment.value}", ephemeral=True)

# trigger from a command or button callback:
await interaction.response.send_modal(FeedbackModal())
```

### 5.6 Reactions and raw events

You can also drive behavior off reactions or other low-level Gateway events
(needs the `reactions` intent, plus `message_content`/`guilds` as relevant):

```python
@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if str(payload.emoji) == "🔔":
        channel = bot.get_channel(payload.channel_id)
        await channel.send(f"<@{payload.user_id}> subscribed to alerts!")
```

Prefer the `on_raw_*` variants (`on_raw_reaction_add`, `on_raw_message_edit`,
etc.) over the plain `on_reaction_add`/`on_message_edit` when you can't
guarantee the message is in the bot's cache — the raw events fire regardless
of cache state.

### 5.7 Which style should you use?

- **Slash commands** — default choice for anything user-facing today; best
  discoverability, no `message_content` intent needed.
- **Prefix commands** — fine for quick internal/admin tooling where you
  control the server and don't mind the extra intent.
- **Buttons/selects/modals** — layer these on top of either, whenever a
  single text response isn't enough (dashboards, forms, pagination).
- **Context menus** — good for "act on this existing message/user" flows
  (e.g. "Flag as sale" on a message someone pasted).
- **Raw reaction/message events** — for passive automation that doesn't need
  an explicit command at all.

---

## 6. Summary

| Standalone script | Inside FastAPI |
|---|---|
| `client.run(token)` | `await bot.start(token)` inside `asyncio.create_task(...)` in `lifespan` |
| Owns its own event loop | Shares Uvicorn's event loop |
| Script exits on Ctrl+C | `await bot.close()` in lifespan teardown |
| Blocking calls are merely rude | Blocking calls stall the API *and* the Gateway heartbeat — use `asyncio.to_thread` |
| Bot is the whole program | Bot is one background task alongside your routes, scheduler, and DB |
