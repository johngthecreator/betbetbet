# Architecture: Discord Bot + Postgres/SQLite + Redis + Celery + RunPod/Replicate

This doc covers the general shape of a Discord bot that offloads slow work
(LLM agent calls, image/video/audio generation) to a task queue instead of
doing it inline on the Gateway connection, and how that setup scales.

It's written generically — the same pattern applies to any chat surface
(Discord, Slack, a web app) fronting slow background work, not just this repo.

---

## 1. Why you need this at all

A Discord bot's Gateway connection is a single persistent WebSocket, driven by
one asyncio event loop. Anything that blocks that loop — a slow HTTP call, a
CPU-bound task, waiting on an LLM or a GPU job — stalls **every other message
the bot is trying to process**, and risks missing heartbeats and getting
disconnected by Discord entirely.

Two problems follow from that:

1. **Slow work can't run inline.** An agent call or an image-generation job
   can take anywhere from a few seconds to several minutes. You can't
   `await` that directly in the event handler.
2. **The bot process shouldn't own retries, queuing, or scaling logic.** Its
   only job is: receive an interaction, hand off the work, respond when it's
   done (or acknowledge and follow up later).

The fix is the classic **producer/consumer split**: the bot enqueues work,
a separate pool of workers processes it, and results flow back asynchronously.

---

## 2. The pieces

```
Discord Gateway ─▶ discord.py bot (producer)
                        │
                        │ .delay(...)
                        ▼
                    Redis (broker + result backend)
                        │
                        ▼
              Celery workers (consumers)
               ┌──────────┴──────────┐
               │                     │
        LangChain agent        RunPod / Replicate
      (Postgres/SQLite for      (image/video/audio
       chat history, state)      model inference)
               │                     │
               └──────────┬──────────┘
                        result
                           │
                           ▼
              Discord followup / webhook
```

### Discord bot — producer, not worker
The bot's only responsibilities: parse the interaction, validate input,
enqueue a Celery task, and immediately free up the event loop
(`interaction.response.defer()`). It does no model inference and no
heavy I/O itself.

### Redis — broker + result backend
Two roles, and it's worth keeping them logically separate even if you point
both at the same Redis instance early on:
- **Broker** — the queue Celery pushes tasks onto and workers pull from.
- **Result backend** — where a task's return value is stored so
  `result.get()` (or polling) can retrieve it later.

Redis is a reasonable single point of infrastructure for both at small scale.
As you grow, you can split them (e.g. RabbitMQ as broker, Postgres or Redis
as backend) but there's no need to start there.

### Postgres / SQLite — durable state
Redis is not where you want anything you can't afford to lose — it's a queue
and a cache, not a database of record. Persistent things go in Postgres (or
SQLite for a single-process/dev setup):
- Chat/agent conversation history (what your LangChain `thread_id` config
  resolves against, if you're using a persistent checkpointer)
- User records, preferences, rate-limit counters
- A record of past media generation jobs (prompt, model used, output URL,
  timestamp) — useful for "regenerate" / "show me my last 5 images" type
  features, and for debugging when a model call went wrong

SQLite is fine to start (this repo currently uses it via `db.py` /
SQLModel), but a single SQLite file becomes a bottleneck once you have
**multiple concurrent Celery worker processes** writing to it — SQLite
serializes writes at the file level. Move to Postgres once you scale workers
past a handful, or once more than one process needs to write concurrently.

### Celery — task queue / consumer pool
Celery workers pull tasks off Redis and execute them. This is where the
actual work happens — either invoking the LangChain agent, or calling out to
RunPod/Replicate for media generation. Two independent task types can live
in the same `tasks.py`, dispatched by whichever Discord command was used:

```python
@app.task
def agent_call(user_query: dict):
    ...  # LangChain agent, reads/writes Postgres for history

@app.task
def media_call(media_request: dict):
    ...  # calls RunPod or Replicate, returns a URL
```

### RunPod / Replicate — the actual model inference
Neither of these is part of your infrastructure — they're external compute
you call into from a Celery task, same as any other third-party API.
RunPod = you own the container/handler, more control, more setup. Replicate
= hosted models, faster to integrate, less control. Either way, from
Celery's perspective it's just an HTTP call out and a poll/wait for
completion.

### Back to Discord
Two ways to return the result, matching how long the job takes:
- **Short jobs (~seconds):** block on `result.get(timeout=N)` inside the
  interaction handler (via `asyncio.to_thread`, since `.get()` is blocking),
  then `interaction.followup.send(...)`.
- **Long jobs (video, minutes):** don't hold the interaction open at all.
  Acknowledge immediately ("processing, I'll post when ready"), and have the
  Celery task (or a callback it triggers) push the result back via a
  **webhook** or by calling back into the bot process. Discord interaction
  tokens are valid for 15 minutes for followups, or use a channel webhook if
  you need longer.

---

## 3. Why this scales

The point of this split is that **each layer scales independently**, along a
different axis, without touching the others:

- **More Discord traffic (more servers/users issuing commands)** — the bot
  process itself rarely needs to scale; it's just enqueuing tasks, which is
  cheap. Scaling here means making sure Redis can handle the enqueue rate,
  which is a very high ceiling.
- **More concurrent work (many tasks in flight)** — scale Celery workers.
  This is the layer that actually needs more compute as load grows, and it
  scales horizontally: add more worker processes, on more machines if
  needed, all pulling from the same Redis queue.
- **More model-inference throughput** — scale RunPod (more workers /
  `max workers` on the endpoint) or rely on Replicate's own scaling. This is
  decoupled from your Celery layer entirely; you're just making more
  concurrent HTTP calls out.
- **More durable-state load** — scale Postgres (read replicas, connection
  pooling) independently of everything above.

None of these require touching the others. That's the whole value of the
queue-based split over doing everything inline in the bot process.

---

## 4. Concurrency within a single Celery worker: threads

Within *one* Celery worker process, you have a choice of execution pool.
For I/O-bound tasks — which describes almost everything here (waiting on a
DB query, an LLM API call, or a RunPod/Replicate HTTP response) — **threads**
are the right pool, not processes:

```bash
celery -A tasks worker --pool=threads --concurrency=10 --loglevel=info
```

- `--pool=threads` runs tasks in a thread pool inside one process, rather
  than the default prefork (multiple OS processes).
- `--concurrency=10` means up to 10 tasks execute concurrently *within that
  one process*, sharing memory.
- This works well here specifically because these tasks spend almost all
  their wall-clock time **waiting** (on a network response from
  RunPod/Replicate, on Postgres, on an LLM API) rather than burning CPU.
  Python's GIL doesn't get in the way for I/O-bound waiting — the thread
  releases the GIL while blocked on I/O, so other threads keep progressing.

Threads would be the *wrong* choice if your tasks were CPU-bound (e.g. doing
the actual tensor math locally instead of calling out to RunPod) — the GIL
would then serialize that work regardless of thread count, and you'd want
processes instead. But since the actual GPU work happens remotely on
RunPod/Replicate's infrastructure, your Celery task itself is just making
HTTP calls and polling — textbook I/O-bound, and threads give you high
concurrency per process cheaply (no per-task process spawn cost, shared
memory for things like a connection pool).

---

## 5. Scaling further: multiple processes, each with multiple threads

Threads alone cap out at what one process (one Python interpreter, one GIL)
can usefully juggle — in practice this is rarely a hard limit for I/O-bound
work, but you still want more than one process for:
- **Using more CPU cores** — one process pins to effectively one core for
  any CPU-bound slivers of work (JSON parsing, serialization, etc.) even if
  most of the task is I/O wait.
- **Fault isolation** — one process crashing (e.g. an unhandled exception
  that takes down a worker) doesn't take out all your capacity.
- **Running on multiple machines** — a single process is bound to one host;
  multiple worker *processes*, potentially on multiple hosts, is how you
  actually add capacity beyond a single machine.

Celery's answer to this is running **multiple worker instances**, each with
its own thread pool, all pointed at the same broker:

```bash
# machine A
celery -A tasks worker --pool=threads --concurrency=10 --hostname=worker1@%h

# machine B (or another process on the same machine)
celery -A tasks worker --pool=threads --concurrency=10 --hostname=worker2@%h
```

Or, on a single machine, Celery's `--autoscale` / running the default
**prefork** pool gives you N processes automatically, and you can combine
pools per-node if needed (though in practice, running several
`--pool=threads` worker instances side by side, one per core or a few per
machine, is simpler to reason about than mixing pool types). The key idea:

```
                         Redis (broker)
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
   Process 1              Process 2              Process 3
  (10 threads)           (10 threads)           (10 threads)
        │                     │                     │
        └─────────────────────┴─────────────────────┘
                              │
                    RunPod / Replicate / Postgres
```

Every process independently pulls tasks off the same Redis queue — Celery
handles the coordination so no two workers grab the same task. This gives
you two multiplied dials:

- **Threads per process** — cheap concurrency for I/O wait, bounded by how
  much one process can usefully manage (connection limits, memory for
  in-flight task state).
- **Number of processes** — real parallelism across cores and machines,
  bounded by how many workers you're willing to run (and by downstream
  limits — Postgres connection pool size, RunPod/Replicate rate limits).

Total concurrent task capacity ≈ `processes × threads-per-process`, and you
scale each dial independently based on where the real bottleneck is: more
threads per process if you're mostly waiting on network I/O and have RAM to
spare; more processes if you're CPU-limited or want the fault isolation of
independent worker instances (and the ability to spread them across
machines).

---

## 6. Summary

| Layer | Role | Scales by |
|---|---|---|
| Discord bot | Producer — enqueues work, never blocks | Rarely a bottleneck; scale Redis if needed |
| Redis | Broker + result backend | Redis clustering (rarely needed until very high volume) |
| Postgres/SQLite | Durable state (chat history, job records) | Move SQLite → Postgres once >1 writer; then replicas/pooling |
| Celery workers | Consumer — runs agent calls or media-generation calls | Threads per process (I/O concurrency) × number of processes (parallelism, fault isolation, multi-machine) |
| RunPod / Replicate | External model inference | Their own worker/endpoint scaling, independent of your stack |
