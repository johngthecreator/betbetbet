from celery import Celery

from agent import shop_bot
from schemas import UserQuery

# Run it with
# spawns new threads instead of processes since agent orchestration is I/O bound
# uv run celery -A tasks worker --pool=threads --loglevel=info
# limit the number of concurrent worker processes
# uv run celery -A tasks worker --pool=threads --concurrency=10 --loglevel=info

app = Celery('tasks', broker='redis://localhost:6379/0', backend='redis://localhost:6379/1')

@app.task
def agent_call(user_query: dict):
    parsed = UserQuery.model_validate(user_query)
    res = shop_bot.invoke(
      [{"role": "user", "content": parsed.query}],
      config={"configurable": {"thread_id": parsed.user_id}},
    )

    content = res.content
    if isinstance(content, list):
      return "\n".join(
          block["text"] for block in content
          if isinstance(block, dict) and block.get("type") == "text"
      )

    return content
