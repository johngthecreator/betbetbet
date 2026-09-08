import discord
import asyncio
from discord import app_commands
from discord.ext import commands

from tasks import agent_call

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Discord bot logged in as {bot.user}")

@bot.command()
async def benny(ctx, *,query: str):
    thread_id = ctx.channel.id
    msg = await ctx.send("Working on it...")   # starts as plain text
    result = agent_call.delay({"user_id": str(thread_id), "query": query})
    try:
        value = await asyncio.to_thread(result.get, timeout=60)   # give it real headroom
        embed = discord.Embed(description=value[:4096])
        await msg.edit(content=None, embed=embed)
    except Exception as e:
        await msg.edit(content=f"Something went wrong: {e}")


# @bot.command()
# async def search(ctx, session_title:str ,*, query: str):
#     await ctx.send(f"{ctx.author.id}-{session_title} || You said this: {query}")

@bot.tree.command(name="new-session", description="Show current sales for a department")
@app_commands.describe(
  session_name="the name for the session",
)
async def session(interaction: discord.Interaction, session_name: str):
    thread = await interaction.channel.create_thread(
        name=session_name,
        type=discord.ChannelType.public_thread,
    )
    await thread.send("Ok now you can start a conversation with me using !benny and I'll respond.")


# @bot.tree.command(name="sales", description="Show current sales for a department")
# @app_commands.describe(
#   chat_id="the id for chat",
#   query="Free-text search within that department",
# )
# @app_commands.choices(department=[
#   app_commands.Choice(name="Men", value="men"),
#   app_commands.Choice(name="Women", value="women"),
#   app_commands.Choice(name="Kids", value="kids"),
# ])
# async def sales(interaction: discord.Interaction, department: app_commands.Choice[str], query: str = ""):
# async def sales(interaction: discord.Interaction, chat_id: str="", query: str = ""):
#     await interaction.response.defer()   # buys time if the next part is slow
#     result = agent_call.delay({"user_id": chat_id, "query": query})
#     try:
#         value = await asyncio.to_thread(result.get, timeout=60)   # give it real headroom
#         embed = discord.Embed(description=value[:4096])
#         await interaction.followup.send(embed=embed)
#     except Exception as e:
#         await interaction.followup.send(f"Something went wrong: {e}")

    # await interaction.followup.send(f"Sorry that took so long I'm done now, you're looking for {department.value} and here's your query {query} ")
  # with Session(engine) as session:
  #     rows = session.exec(select(Sale).where(Sale.department == department)).all()
  # await interaction.response.send_message(f"{len(rows)} sales found in {department}")

# @bot.command() async def sales(ctx, *, query: str):
#     result = agent_call.delay(user_query.model_dump());
#     return {"result": result.get(timeout=10)}
#     await ctx.send(f"You said this: {query}")
