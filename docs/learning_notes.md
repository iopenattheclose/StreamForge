# StreamForge — Learning Notes & Technical Architecture

## 1. Project Overview

StreamForge is a high-concurrency asynchronous streaming gateway built with Python, FastAPI, asyncio and Server-Sent Events (SSE).

Its objective is to explore how a Python backend can manage thousands of concurrent client connections while streaming generated tokens incrementally and handling slow consumers safely.

### Core objectives

- Target 10,000+ concurrent SSE connections.
- Stream tokens incrementally without blocking the event loop.
- Implement bounded buffering and backpressure.
- Handle client disconnections and cancellation.
- Track latency, throughput and resource usage.
- Benchmark performance under increasing concurrency.

The 10,000-connection target is a goal, not a proven performance claim.

### Initial scope

The first version uses a synthetic asynchronous token producer instead of a real LLM.

This allows us to benchmark the gateway independently of inference performance.

A real MLX-based producer may be integrated later without redesigning the gateway's core.

---

## 2. Processes, Threads and Concurrency

### Process

A process is an independently running program with its own memory space and operating-system resources.

Example: Running two independent Python applications creates two processes.

### Thread

A thread is an execution path inside a process.

Multiple threads within a process share its memory and resources.

### Multithreading

Multiple threads execute within one process.

Useful for:
- I/O operations.
- Background work.
- Responsiveness.
- Some forms of parallel execution.

In standard CPython builds, the GIL can limit parallel execution of Python bytecode across threads.

### Multiprocessing

Multiple processes execute independently.

Useful for CPU-intensive work that benefits from multiple CPU cores.

Tradeoffs include additional memory consumption and inter-process communication overhead.

### Concurrency vs. Parallelism

**Concurrency:** Multiple tasks make overlapping progress. They don't necessarily execute simultaneously.

**Parallelism:** Multiple tasks execute simultaneously, typically on different CPU cores.

### StreamForge application

Our initial deployment will use:

- One Uvicorn worker.
- One Python process.
- One asyncio event loop.
- One event-loop thread.
- Many concurrent asynchronous tasks.

We will benchmark before considering multiple workers.

---

## 3. Asyncio Fundamentals

### Event loop

The event loop coordinates asynchronous tasks.

Conceptually, it:

1. Executes tasks that are ready.
2. Suspends tasks waiting for I/O or timers.
3. Monitors I/O readiness and timers.
4. Resumes tasks when they become ready.

Operating systems provide mechanisms such as epoll on Linux and kqueue on macOS to notify the event loop about I/O readiness.

The event loop does not need one thread per network connection.

### Coroutine

A coroutine is an asynchronous computation.

A function declared using `async def` is a coroutine function.

Calling it creates a coroutine object; it does not immediately execute its body.

### Task

A Task wraps a coroutine and schedules it on an event loop.

Example:

- `await some_coroutine()` waits for that coroutine as part of the current task.
- `asyncio.create_task(some_coroutine())` schedules it as an independent task.

### Await

`await` allows the current coroutine to suspend while waiting for an asynchronous operation.

It does not automatically create a new thread or task.

### Blocking vs. non-blocking

Non-blocking:

`await asyncio.sleep(5)`

The task suspends and allows other tasks to progress.

Blocking:

`time.sleep(5)`

The event-loop thread is blocked for five seconds.

This is dangerous in StreamForge because thousands of other tasks may depend on the same event loop.

**Key takeaway:** Asyncio is particularly useful for I/O concurrency, not CPU parallelism.

---

## 4. ASGI, FastAPI and Uvicorn

### ASGI

ASGI stands for Asynchronous Server Gateway Interface.

It defines how asynchronous Python web servers communicate with applications.

### FastAPI

FastAPI is our web framework.

Responsibilities:
- HTTP endpoints.
- Request validation.
- Response construction.
- Dependency management.
- Streaming response integration.

### Uvicorn

Uvicorn is our ASGI server.

Responsibilities:
- Accepting network connections.
- Handling HTTP protocol communication.
- Communicating with the FastAPI application through ASGI.
- Transmitting response data to clients.

### Request flow

Client → TCP connection → Uvicorn → ASGI → FastAPI → application logic.

The response travels back through the ASGI server to the client.

FastAPI and Uvicorn are not interchangeable: one is the application framework; the other is the server.

---

## 5. TCP, HTTP and SSE

These technologies operate at different layers.

| Technology | Responsibility |
|---|---|
| TCP | Reliable, ordered byte delivery |
| Socket | Communication endpoint |
| HTTP | Request/response protocol |
| SSE | Event-stream formatting over HTTP |
| Uvicorn | Server and ASGI communication |
| FastAPI | Application logic |

TCP does not understand tokens or SSE events.

TCP packets and application-level SSE events do not necessarily have matching boundaries.

### Server-Sent Events

SSE is an HTTP-based mechanism for streaming events from a server to a client.

The response uses:

`Content-Type: text/event-stream`

An SSE event has a format such as:

```text
data: Hello

```

The blank line terminates the event.

Common SSE fields:

- `data`: Event content.
- `event`: Event type.
- `id`: Event identifier.
- `retry`: Suggested reconnection delay.

### SSE vs. WebSockets

| SSE | WebSockets |
|---|---|
| Server-to-client streaming | Bidirectional communication |
| HTTP-based | WebSocket protocol |
| Simpler for one-way updates | More flexible |
| Native browser EventSource | WebSocket client API |

StreamForge uses SSE because token generation is primarily server-to-client.

Separate HTTP endpoints handle creation and cancellation.

### Heartbeats

Some proxies close connections that remain inactive for too long.

We will send an SSE comment such as:

```text
: keep-alive

```

Heartbeats will be sent only when no tokens or other SSE events have been sent during the configured interval.

Heartbeats are not generated tokens.

### Important HTTP limitation

Once streaming response headers have been sent, the HTTP status code cannot be changed.

Errors occurring before streaming use normal HTTP error responses.

Errors occurring after streaming begins use SSE error events or connection termination.

---

## 6. Asyncio Queue and Producer-Consumer Pattern

### Queue

`asyncio.Queue` is an in-memory FIFO queue designed for communication between asynchronous tasks.

It:
- Stores items in RAM.
- Preserves insertion order.
- Supports multiple asynchronous producers and consumers.
- Is intended for use within an event loop, not as a thread-safe cross-thread queue.
- Does not provide persistence or distributed messaging.

### Bounded queue

A bounded queue has a maximum capacity.

For example:

`asyncio.Queue(maxsize=50)`

When full, this operation suspends:

`await queue.put(item)`

When empty, this operation suspends:

`await queue.get()`

A full queue does not automatically drop the oldest item.

### Producer-consumer architecture

Producer → Queue → Consumer

In StreamForge:

Token Producer → Bounded Queue → SSE Consumer → Client

The producer generates tokens, while the consumer sends them to the client.

### FIFO behavior

FIFO means First In, First Out.

If multiple consumers share one queue, they divide the items between themselves. They do not automatically receive broadcast copies.

This is why StreamForge uses one queue per generation.

### Queue capacity calculation

If:
- Maximum active generations = 1,000.
- Queue capacity = 50 items per generation.

Then:

1,000 × 50 = 50,000 maximum queued items.

This is a theoretical item-count bound, not a complete memory limit. Actual memory depends on token representation, Python object overhead and other application buffers.

---

## 7. Backpressure

Backpressure is a mechanism for controlling data flow when a consumer cannot process incoming data as quickly as a producer generates it.

### The problem

Suppose:

- Producer generates 20 tokens per second.
- Client consumes 5 tokens per second.

The queue grows because tokens arrive faster than they leave.

Without limits, buffering can consume increasing amounts of memory.

### StreamForge solution

Use bounded queues.

When the queue becomes full:

1. Producer reaches `await queue.put(token)`.
2. Producer suspends.
3. Consumer continues sending queued tokens.
4. Queue space becomes available.
5. Producer resumes.

This is producer throttling.

### Why not drop tokens?

Dropping generated tokens would corrupt the response.

For our initial LLM-style streaming use case, preserving token order and content is more important than silently discarding data.

### Slow-client policy

If the producer remains blocked because the queue is full beyond a configurable timeout:

- Terminate the generation.
- Cancel associated tasks.
- Clean up resources.
- Record the termination reason.

### Important distinction

A bounded application queue does not bound every other buffer.

Potential buffering layers include:

- Application queue.
- ASGI/server buffers.
- Operating-system buffers.
- Network infrastructure.
- Reverse proxies.
- Client buffers.

Real slow-client testing is therefore essential.

---

## 8. Cancellation and Resource Cleanup

Asyncio cancellation is cooperative.

A cancellation request does not forcibly terminate a coroutine at an arbitrary instruction.

It is normally delivered at a suspension point.

### Cancellation process

1. Request cancellation.
2. Task receives cancellation.
3. Cleanup executes.
4. Resources are released.
5. Generation state is updated.

Use `try/finally` for cleanup.

Avoid accidentally swallowing `asyncio.CancelledError`.

### StreamForge cancellation

When a client disconnects:

- Detect the disconnect.
- Cancel producer and consumer tasks.
- Release queue and connection state.
- Mark the generation cancelled.
- Release its active-generation slot.

A reconnect requires a new generation in v1.

There is no token replay or stream resumption.

### Important edge case

A producer may be blocked while trying to insert a completion or error signal into a full queue.

Cancellation must still be able to interrupt this operation.

Cleanup must not wait indefinitely for queue space.

---

## 9. StreamForge Architecture

### Main components

**1. API Layer**

Handles HTTP endpoints, request validation, response formatting and error mapping.

**2. Generation Manager**

Owns generation lifecycle and resources.

Responsibilities:
- Create generation IDs.
- Maintain generation registry.
- Enforce active-generation limits.
- Create per-generation queues.
- Coordinate producer and consumer tasks.
- Manage cancellation and cleanup.
- Track generation status.

**3. Connection Manager**

Tracks active SSE connections.

Responsibilities:
- Register connections.
- Track connection lifecycle.
- Detect disconnects.
- Remove connection state.

It does not own generation queues or producer tasks.

**4. Token Producer**

Initially a synthetic asynchronous producer.

Responsibilities:
- Generate simulated tokens.
- Simulate generation delay.
- Insert tokens into the bounded queue.
- Respect queue backpressure.

It has no HTTP or SSE knowledge.

**5. SSE Consumer**

Responsibilities:
- Read tokens from the queue.
- Format SSE events.
- Deliver events through the streaming response.
- Handle completion and error signals.

It does not generate tokens.

**6. Metrics Collector**

Maintains global and per-generation metrics.

**7. Configuration**

Loads typed configuration through Pydantic Settings and `.env`.

### Data flow

Client → API → Generation Manager → Generation State

Generation State coordinates:

Producer → Queue → SSE Consumer → Client

Connection Manager tracks the SSE connection.

Metrics Collector records activity throughout the lifecycle.

### Component communication

Use direct method calls and shared manager objects.

No event bus or message broker is required in v1.

### Shared application components

Initialize shared components once through FastAPI lifespan during application startup.

Do not instantiate the managers independently for every HTTP request.

---

## 10. Generation Lifecycle

### Generation definition

A generation represents one complete AI response for a prompt.

### Lifecycle states

- `created`
- `running`
- `completed`
- `cancelled`
- `failed`
- `expired`

Terminal states are retained temporarily for status queries.

### Normal lifecycle

1. Client creates generation.
2. Generation Manager creates UUID.
3. State is stored in an in-memory registry.
4. Generation waits for SSE connection.
5. Client connects to stream.
6. Producer and consumer tasks begin.
7. Tokens flow through the bounded queue.
8. Producer signals completion.
9. Consumer sends the completion event.
10. Resources are cleaned up.
11. Terminal status is retained temporarily.
12. Record expires and is removed.

### Unclaimed generations

A generation that is created but never claimed through SSE expires after a configurable timeout.

Its slot is released.

### Connection rules

- One SSE connection per generation.
- Duplicate stream connection returns HTTP 409.
- One generation has an independent queue.
- Client disconnect cancels the generation.
- Reconnection requires a new generation.

### Admission control

The maximum active-generation count includes both:
- Created but unclaimed generations.
- Running generations.

When capacity is reached, new generation requests receive HTTP 503 with a `Retry-After` header.

This prevents unlimited pending requests from consuming resources.

### In-memory registry

Use a Python dictionary managed by Generation Manager.

The registry stores generation metadata and references to active resources.

A process restart loses generation state. This is acceptable for v1.

---

## 11. API Design

All endpoints use `/api/v1`.

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/v1/generations` | Create generation |
| GET | `/api/v1/generations/{id}/stream` | Stream tokens |
| GET | `/api/v1/generations/{id}` | Retrieve generation status |
| POST | `/api/v1/generations/{id}/cancel` | Cancel generation |
| GET | `/api/v1/metrics` | Retrieve metrics |

### Create generation request

Example:

```json
{
  "prompt": "Explain Python asyncio",
  "max_tokens": 500
}
```

Validate before allocating resources:
- Prompt must not be empty.
- Prompt length must have a maximum.
- `max_tokens` must be positive.
- `max_tokens` must have an upper bound.

### Success response

```json
{
  "data": {
    "generation_id": "uuid",
    "status": "created"
  }
}
```

### Error response

```json
{
  "error": {
    "code": "GENERATION_NOT_FOUND",
    "message": "Generation does not exist"
  }
}
```

### HTTP status conventions

| Status | Meaning |
|---|---|
| 200 | Successful request |
| 201 | Generation created |
| 404 | Generation not found |
| 409 | Generation conflict |
| 422 | Invalid request |
| 503 | Server overloaded |

Cancellation is idempotent for known generations: repeated cancellation or cancellation after a terminal state does not trigger additional work.

---

## 12. Configuration

Configuration lives in `.env` and is loaded through Pydantic Settings.

Example values:

```env
MAX_ACTIVE_GENERATIONS=1000
QUEUE_MAX_SIZE=50

GENERATION_TTL=30
TERMINAL_RECORD_TTL=300

BACKPRESSURE_TIMEOUT=30
HEARTBEAT_INTERVAL=20
TOKEN_DELAY=0.05

HOST=127.0.0.1
PORT=8000
```

These are initial example values, not final benchmark-derived settings.

### Configuration responsibilities

- `.env`: Local configuration.
- `.env.example`: Safe sample values.
- `.gitignore`: Excludes `.env`.
- `app/config.py`: Typed configuration and validation.
- Other modules: Read configuration through the central settings object.

Use `pydantic-settings`.

---

## 13. Metrics and Observability

### Global metrics

- Active connections.
- Total connections.
- Active generations.
- Completed generations.
- Failed generations.
- Cancelled generations.
- Queue occupancy.
- Token throughput.
- Event-loop lag.
- Memory usage.

### Per-generation metrics

- Generation ID.
- Start time.
- Completion time.
- TTFT.
- Token count.
- Duration.
- Final status.
- Failure reason.

### Performance terminology

**TTFT:** Time from generation starting to first token delivery.

**Throughput:** Amount of work delivered per unit of time, such as tokens per second.

**P50/P95/P99:** Percentile measurements that show typical and tail latency.

**Event-loop lag:** Delay between when scheduled loop work should run and when it actually runs.

### Collection strategy

- Lightweight counters and timestamps update on relevant events.
- Expensive measurements such as memory usage are sampled periodically.
- Metrics are exposed through `GET /api/v1/metrics`.
- Metrics are initially maintained in memory.

The metrics endpoint is public in local development. Public deployment requires suitable access protection.

---

## 14. Project Structure

```text
streamforge/
├── app/
│   ├── api/
│   │   ├── routes.py
│   │   ├── schemas.py
│   │   └── errors.py
│   ├── generations/
│   │   ├── manager.py
│   │   └── models.py
│   ├── streaming/
│   │   └── sse.py
│   ├── producers/
│   │   └── synthetic.py
│   ├── connections/
│   │   └── manager.py
│   ├── metrics/
│   │   └── collector.py
│   ├── config.py
│   └── main.py
├── tests/
├── load_tests/
├── docs/
│   └── learning-notes.md
├── scripts/
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md
```

### Folder responsibilities

- `api/`: HTTP routes, schemas and error handling.
- `generations/`: Generation state and lifecycle management.
- `streaming/`: SSE formatting and streaming response logic.
- `producers/`: Synthetic token generation.
- `connections/`: SSE connection tracking.
- `metrics/`: Metrics collection.
- `tests/`: Unit and integration tests.
- `load_tests/`: Locust load scenarios.
- `docs/`: Architecture and learning documentation.
- `scripts/`: Development and benchmarking utilities.

`main.py` assembles the FastAPI application and manages startup and shutdown.

---

## 15. Testing Strategy

Testing happens incrementally alongside development.

### Unit tests

Test each component independently.

Examples:
- Generation creation.
- UUID generation.
- Queue capacity.
- Producer behavior.
- SSE event formatting.
- Cancellation.
- Metrics updates.

### Integration tests

Test component interactions.

Examples:
- Create generation and stream tokens.
- Retrieve generation status.
- Cancel active generation.
- Handle duplicate SSE connections.
- Detect client disconnects.
- Handle generation completion and failure.

### Edge-case tests

Especially important:
- Full queue.
- Slow client.
- Producer blocked on queue insertion.
- Disconnect during streaming.
- Cancellation during cleanup.
- Unclaimed generation expiry.
- Duplicate stream connection.
- Admission limit reached.
- Producer failure.
- Application shutdown.

### Load tests

Use Locust initially.

Correctness tests and load tests remain separate.

---

## 16. Benchmarking Strategy

Benchmark progressively:

| Stage | Concurrent connections |
|---|---:|
| 1 | 100 |
| 2 | 500 |
| 3 | 1,000 |
| 4 | 2,500 |
| 5 | 5,000 |
| 6 | 10,000 |

### Separate benchmark scenarios

**Scenario 1: Idle connections**

Many clients remain connected without active generations.

**Scenario 2: Active streams**

Clients receive synthetic token streams.

**Scenario 3: Slow consumers**

Clients read more slowly than the producer generates tokens.

**Scenario 4: Overload**

New generation requests arrive after capacity is reached.

### Measurements

- Successful connection count.
- Failed connections.
- CPU usage.
- Memory consumption.
- Event-loop lag.
- TTFT.
- Inter-token latency.
- Token throughput.
- P50/P95/P99 latency.
- Error rate.
- Disconnect rate.

### Benchmark validity

Record:
- Hardware and operating system.
- Python version.
- Uvicorn worker count.
- Configuration values.
- File descriptor limits.
- Load-generator resource consumption.
- Network conditions.
- Test duration.

An important distinction:

10,000 open SSE connections does not mean 10,000 simultaneous active LLM generations.

We will report idle connections, active streams and actual generation capacity separately.

Our MacBook M3 Pro is the initial development and benchmarking machine. Results will be reported as measured, with limitations clearly documented.

---

## 17. Development Roadmap

1. Finalize learning notes and architecture.
2. Set up project and dependencies.
3. Implement configuration and application startup.
4. Implement generation models and manager.
5. Implement synthetic producer.
6. Implement bounded queue and lifecycle.
7. Implement SSE consumer and endpoints.
8. Implement connection tracking.
9. Implement cancellation and backpressure handling.
10. Implement metrics.
11. Add unit and integration tests.
12. Add Locust scenarios.
13. Benchmark and optimize.
14. Build React + TypeScript dashboard after backend stabilization.
15. Consider optional MLX integration.

Redis, Kafka, PostgreSQL persistence, Prometheus and distributed inference are outside the initial scope.

---

## 18. Glossary

| Term | Meaning |
|---|---|
| ASGI | Asynchronous Server Gateway Interface |
| Asyncio | Python asynchronous programming framework |
| Coroutine | Asynchronous computation |
| Task | Scheduled coroutine |
| Event loop | Coordinates asynchronous task execution |
| TCP | Reliable, ordered transport protocol |
| Socket | Network communication endpoint |
| HTTP | Request/response protocol |
| SSE | Server-to-client event streaming |
| FIFO | First In, First Out |
| Producer | Generates data |
| Consumer | Processes generated data |
| Backpressure | Controls producer speed when consumers are slower |
| Bounded queue | Queue with a maximum capacity |
| Cancellation | Cooperative stopping of asynchronous work |
| TTFT | Time to First Token |
| Throughput | Work completed per unit of time |
| Event-loop lag | Delay in event-loop scheduling |
| Admission control | Limits accepted workload |
| ASGI server | Runs the application and handles network communication |
| Generation | One complete response for a prompt |

---

## 19. Important Design Principles

1. Keep API endpoints thin.
2. Keep business logic outside HTTP routes.
3. Give each generation an independent bounded queue.
4. Never block the event-loop thread with synchronous I/O or long CPU-bound work.
5. Preserve token ordering.
6. Cancel unnecessary work when clients disconnect.
7. Clean up tasks and resources reliably.
8. Measure before optimizing.
9. Keep configuration centralized.
10. Avoid adding infrastructure without a demonstrated need.
11. Distinguish connection capacity from active generation capacity.
12. Never claim benchmark performance without actual measurements.

**End of StreamForge learning notes.**

The final README will remain a separate document and will be updated after implementation, testing and real benchmarking.