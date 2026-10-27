# TripAgent AI

TripAgent AI is a travel-planning web application. A visitor describes a trip in the browser; the backend classifies the request, selects relevant research agents, gathers available travel information, drafts a plan, and pauses for the visitor to approve it or request a revision.

## 🚀 Live Demo

**Try TripAgent AI:** [Open the live application](https://tripagent-amii.onrender.com)

Explore the AI-powered travel planner by entering a travel request, reviewing the generated itinerary, and approving it or requesting revisions.

> **Note:** Flight information, weather data, hotel search results, and budget estimates depend on external API availability and configuration. Flight information represents current flight activity, not future schedules or live ticket prices.

## Features

- Travel-only request classification and dynamic selection of specialist agents.
- Flight activity lookup through Aviationstack, with route parsing, a local response cache, and a monthly request cap.
- Hotel research through Tavily's hosted MCP service.
- Current conditions and short-range forecasts through a local OpenWeatherMap MCP server.
- LLM-generated budget analysis and a combined day-by-day itinerary.
- Human review: approve a draft or send feedback before the final plan is generated.
- PostgreSQL-backed LangGraph checkpoints so an approval can resume the same graph thread.
- Browser UI with separate plan, flight, hotel, and budget panels, plus copy and PDF-download controls.

Flight snapshots describe activity around the time of the request, not the visitor's future travel dates or ticket prices. The application asks the LLM to label fare and budget figures as estimates.

## Technology stack

| Technology | Role |
| --- | --- |
| Python 3.11 | Runtime used by the supplied Dockerfile. No separate local Python version constraint is declared. |
| FastAPI, Uvicorn, Pydantic | HTTP application, ASGI server, and request-body validation. |
| LangGraph | Supervisor/specialist workflow, conditional routing, human approval interrupt, and graph state. |
| LangChain integrations | Gemini and Groq chat model clients and MCP tool adapters. |
| Google Gemini (`gemini-2.5-flash`) | Request classification, agent selection, destination extraction, and plan generation. |
| Groq (`qwen/qwen3.8-27b`) | Destination extraction in `mcp_client.py`; a Groq client is also initialized in the backend. |
| PostgreSQL / Psycopg | LangGraph checkpoint storage. The database URL is set up for SSL if it does not already specify `sslmode`. |
| Tavily MCP | Hosted web search used to find hotel information. |
| Model Context Protocol (MCP) | Tool adapter connecting the application to Tavily and its local weather server. |
| OpenWeatherMap | Current weather and forecast data returned by the local MCP server. |
| Aviationstack | Live flight-activity data fetched directly over HTTP by `tools/flight_tool.py` (not through MCP). |
| HTML, CSS, vanilla JavaScript | Browser interface, API requests, rendering, and interaction. |

The browser loads `marked`, DOMPurify, `html2pdf.js`, and Google Fonts from external CDNs.

## Architecture

```mermaid
flowchart LR
    Browser["Browser UI<br/>HTML / CSS / JavaScript"] -->|"GET /, POST /api/travel"| API["FastAPI app<br/>app.py"]
    Browser -->|"POST /api/travel/approve"| API
    API --> Backend["Travel workflow<br/>backend.py"]
    Backend --> Supervisor["Guardrail and supervisor"]
    Supervisor --> Agents["Selected specialist agents<br/>Flights · Hotels · Weather · Budget"]
    Agents --> Itinerary["Itinerary agent"]
    Itinerary --> Review["Human approval interrupt"]
    Review -->|"approve or feedback"| Final["Final response agent"]
    Final --> API
    Backend <-->|"checkpoint / resume by thread_id"| PostgreSQL["PostgreSQL"]
    Agents -->|"REST"| Aviationstack["Aviationstack"]
    Agents -->|"MCP over HTTPS"| Tavily["Tavily MCP"]
    Agents -->|"MCP over stdio"| Weather["Weather MCP server"]
    Weather -->|"REST"| OpenWeather["OpenWeatherMap"]
    Backend -->|"LLM calls"| Models["Gemini / Groq"]
```

### Project structure

```text
.
├── app.py                       # FastAPI app, routes, static/template mounting
├── backend.py                   # LangGraph state, agents, routing, checkpointing
├── mcp_client.py                # Tavily and local weather MCP client setup
├── custom_weather_mcp_server.py # OpenWeatherMap MCP tools
├── requirements.txt             # Pinned Python dependencies
├── Dockerfile                   # Container image and Uvicorn command
├── .dockerignore                # Current build-context exclusions
├── .gitignore
├── templates/
│   └── index.html               # Single-page application markup
├── static/
│   ├── script.js                # API calls, result rendering, review controls
│   └── style.css                # UI styling
└── tools/
    └── flight_tool.py           # Aviationstack route lookup, cache, and parser
```

The graph checkpointer initializes its schema through `PostgresSaver.setup()` when `backend.py` is imported. There are no separate database model or migration files in the repository. Flight response and request-usage cache files are created at runtime under `tools/.flight_cache/`; they are not source files.

## Prerequisites

- Python 3.11 (the version used by the Dockerfile; other local versions are not explicitly declared or verified).
- A reachable PostgreSQL database and a connection string. The backend's error message refers to Neon, but the code connects through Psycopg to PostgreSQL generally.
- API credentials for the model providers and the external services used by the agents you expect to run. See [Environment variables](#environment-variables).
- Internet access for the model APIs, Tavily MCP, Aviationstack, OpenWeatherMap, and the browser's CDN assets.

## Installation and setup

From PowerShell:

```powershell
git clone https://github.com/Nikil-Ralson/TripAgent.git
Set-Location TripAgent
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Create a `.env` file in the repository root and provide the values required for your setup. Do not commit it. The code calls `load_dotenv()` in the backend, MCP client, weather server, and flight tool.

The application needs `DATABASE_URL` and `GROQ_API_KEY` during backend initialization. Normal model operations also require a working `GEMINI_API_KEY`. Tavily, OpenWeatherMap, and Aviationstack credentials are needed when the corresponding integrations are used.

## Environment variables

Use the following as a **placeholder template**, not as working credentials:

```dotenv
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require
GROQ_API_KEY=replace-with-your-groq-key
GEMINI_API_KEY=replace-with-your-gemini-key
TAVILY_API_KEY=replace-with-your-tavily-key
OPENWEATHER_API_KEY=replace-with-your-openweathermap-key
AVIATION_STACK_API_KEY=replace-with-your-aviationstack-key
DEFAULT_ORIGIN_IATA=DEL
AVIATION_MONTHLY_BUDGET=90
AVIATION_CACHE_HOURS=6
```

| Variable | Required / default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | Required | PostgreSQL connection string for LangGraph checkpoints. `backend.py` adds `sslmode=require` if the URL does not contain `sslmode=`. |
| `GROQ_API_KEY` | Required by backend initialization | Groq credentials. `backend.py` raises an error at import if it is missing. |
| `GEMINI_API_KEY` | Required for Gemini requests | Credentials for the `gemini-2.5-flash` model. The code does not perform an explicit startup check for it. |
| `TAVILY_API_KEY` | Needed for hotel search | Appended to the hosted Tavily MCP URL by `mcp_client.py`. |
| `OPENWEATHER_API_KEY` | Needed for weather tools | Passed to the local weather MCP server for its OpenWeatherMap requests. |
| `AVIATION_STACK_API_KEY` | Optional until flight lookup | Aviationstack credential used by `tools/flight_tool.py`. That file also accepts the alternate spelling `AVIATIONSTACK_API_KEY`. |
| `DEFAULT_ORIGIN_IATA` | Optional; defaults to `DEL` | Used when a flight request identifies a destination but no departure airport. |
| `AVIATION_MONTHLY_BUDGET` | Optional; defaults to `90` | Maximum number of API requests counted by the local flight tool for a month. The local counter is an approximation of the provider's quota. |
| `AVIATION_CACHE_HOURS` | Optional; defaults to `6` | Flight response cache lifetime, in hours. |

Some environment names may exist in a developer's local `.env` without having a corresponding application read in this repository. For example, `DEFAULT_ORIGIN_DATA` is not read by the checked-in application code. LangSmith tracing behavior is not configured explicitly by the application code.

## Running locally

With the virtual environment active and `.env` configured, start the app from the repository root:

```powershell
python -m uvicorn app:app --reload
```

Open <http://127.0.0.1:8000>. The equivalent `python app.py` entry point also starts Uvicorn with reload enabled on `127.0.0.1:8000`.

The local weather MCP server is launched by the MCP client using the current Python executable and `custom_weather_mcp_server.py`; it does not require a separate terminal. Tavily is configured as a hosted MCP endpoint. `tools/flight_tool.py` calls Aviationstack directly over HTTP.

Useful built-in FastAPI endpoints include <http://127.0.0.1:8000/docs> and <http://127.0.0.1:8000/openapi.json>.

## How it works

1. The browser serves the TripAgent page and checks `GET /health` to show server status.
2. Submitting a request sends `POST /api/travel` with the user's message.
3. `backend.py` starts a graph run with a new UUID-based `thread_id` unless one was supplied. The UI starts each new plan without a thread ID.
4. The supervisor asks Gemini to classify the request. Unsupported requests end with a guardrail response. An allowed request is routed to selected specialist agents, in the fixed order flights, hotels, weather, budget, then itinerary. The itinerary agent is always included.
5. Specialist outputs are combined into a draft itinerary. The graph pauses at a LangGraph human-approval interrupt and the API returns that draft and its `thread_id`.
6. The browser presents the draft. The user approves it or submits revision feedback via `POST /api/travel/approve`.
7. The backend resumes the same checkpointed graph thread, runs the final response agent, and returns the completed plan.

The frontend retains the `thread_id` in page memory for the review action; it does not provide a persistent conversation browser or user account.

## Agent and tool workflow

The guardrail and supervisor are implemented together in `supervisor_agent`:

- The guardrail uses an LLM prompt and JSON parsing to decide whether the request is travel-related.
- The supervisor uses an LLM prompt to select applicable agents and extract constraints. Invalid supervisor output falls back to running the full workflow.
- The agent order is deterministic after selection. The specialist agents are not run in parallel.
- The flight agent calls `search_flights()` and then asks Gemini to produce flight guidance from the current flight-activity snapshot.
- The hotel agent extracts a destination and invokes Tavily's `tavily_search` MCP tool.
- The weather agent extracts a destination and invokes `get_current_weather` and `get_forecast` on the local weather MCP server.
- The budget agent uses the available request details and specialist results to generate an estimated cost analysis.
- The itinerary agent combines the request and specialist results. `human_approval_agent` then interrupts the graph; `resume_travel_agent()` resumes with the approval boolean and feedback. The final agent polishes the approved draft or applies the requested revision.

LangGraph state includes the message list, request, selected agents, extracted constraints, specialist results, approval state, final response, and LLM call count. PostgreSQL stores graph checkpoints keyed by `thread_id`, enabling the approval request to resume the paused run. The browser starts a new thread for each new trip and carries the current thread only through the review step.

## API

All endpoints are served by `app.py`. Pydantic validates JSON request bodies. Successful planning and approval responses include `"success": true` plus the serialized graph result. Error responses include `"success": false` and an `"error"` string.

### `GET /`

Returns the HTML application page.

### `GET /health`

Returns:

```json
{
  "status": "ok",
  "message": "AI Travel Planner API is running"
}
```

This is a simple process health response; it does not test the database or external providers.

### `POST /api/travel`

Request:

```json
{
  "message": "Plan 5 days in Tokyo from Delhi with hotels and sightseeing."
}
```

`message` is required. `thread_id` is optional; when omitted, the backend creates one. An empty or whitespace-only message returns HTTP 400. A successful response includes:

```json
{
  "success": true,
  "thread_id": "user_<generated-id>",
  "answer": "<draft itinerary or guardrail response>",
  "requires_approval": true,
  "approval_request": "<review instructions>",
  "flight_results": "<text or empty string>",
  "hotel_results": "<tool result or empty string>",
  "weather_results": "<text or empty string>",
  "budget_results": "<text or empty string>",
  "itinerary": "<draft itinerary or empty string>",
  "selected_agents": ["flight_agent", "hotel_agent", "itinerary_agent"],
  "trip_constraints": {
    "destination": "",
    "origin": "",
    "duration": "",
    "travel_styles": "",
    "special_preferences": []
  },
  "supervisor_reasoning": "<routing explanation>",
  "guardrail_allowed": true,
  "guardrail_reason": "<classification reason>",
  "approved": false,
  "human_feedback": "",
  "llm_calls": 0
}
```

The values above illustrate field names and types; extracted constraints, agent selection, and result contents depend on the request. For an accepted travel request, the initial workflow normally pauses for review and sets `requires_approval` to `true`. A blocked request does not require approval.

### `POST /api/travel/approve`

Request:

```json
{
  "thread_id": "user_<generated-id>",
  "approved": false,
  "feedback": "Use a lower-cost hotel and include a free afternoon."
}
```

`thread_id` must be a non-empty string and `approved` is required. `feedback` defaults to an empty string. If `approved` is `false`, the API requires non-empty feedback and returns HTTP 400 otherwise. On success, the endpoint returns the same serialized result shape as `/api/travel`, usually with the final response and `requires_approval: false`.

### `GET /favicon.ico`

Returns an empty JSON response.

Unexpected exceptions in the two POST handlers are logged with a traceback and returned as HTTP 500 with the exception text in the response. Do not expose those responses directly to untrusted clients in a public deployment without changing the error-handling policy.

## Docker and deployment

The supplied `Dockerfile` uses `python:3.11-slim`, installs `requirements.txt`, copies the application, exposes port `8000`, and starts Uvicorn bound to `0.0.0.0:8000`. PostgreSQL and the external provider APIs remain separate dependencies; the container does not start a database.

**Important build-context caveat:** the current `.dockerignore` excludes virtual-environment directories but does not exclude `.env`. Because the Dockerfile uses `COPY . .`, a `.env` file inside the build context can be copied into the image. Do not build an image from a context containing real secrets. Until the ignore configuration is corrected, build from a context that does not contain `.env`, and inject credentials at runtime using an env file located outside that build context or your deployment platform's secret mechanism.

The container's documented startup command is:

```powershell
docker build -t tripagent-ai .
docker run --rm -p 8000:8000 --env-file <path-to-env-file-outside-build-context> tripagent-ai
```

The `docker build` command is safe only when the build context has no secret-bearing `.env`. No hosting platform, production deployment manifest, reverse proxy, or production worker configuration is included in the repository; those would need to be chosen and configured separately.

## Testing and troubleshooting

No formal test suite or test-runner configuration is present among the tracked project files. `tools/flight_tool.py` has a manual `__main__` mode: run it with no arguments to print offline route-parser examples (no Aviationstack request), or with a search phrase to perform a live lookup. A live lookup consumes provider quota.

Common setup checks:

- **Startup fails for `DATABASE_URL`:** supply a reachable PostgreSQL connection URL. The graph checkpointer is created during backend import.
- **Startup fails for `GROQ_API_KEY`:** set the Groq credential before starting Uvicorn.
- **Model calls fail:** check `GEMINI_API_KEY` and `GROQ_API_KEY`, provider access, quotas, and model availability.
- **Hotel search is unavailable:** check `TAVILY_API_KEY` and connectivity to the hosted Tavily MCP service.
- **Weather is unavailable:** check `OPENWEATHER_API_KEY`, network access, and the weather server's response.
- **Flight details are missing:** confirm `AVIATION_STACK_API_KEY`, route detection, and the local usage/cache state. The cache and monthly counter are under `tools/.flight_cache/`.
- **Browser shows server unreachable:** confirm the process is running and that the browser is using the correct host and port.

## Security considerations

- Keep provider credentials and `DATABASE_URL` out of source control, logs, screenshots, and published images. `.gitignore` excludes `.env`, but `.dockerignore` currently does not.
- The Tavily key is included in the configured MCP URL as a query parameter. Treat any URL or diagnostic output containing that URL as sensitive.
- The LLM-based travel guardrail is not a hard security boundary: if classification or JSON parsing raises an error, the backend allows the request to continue.
- The API has no authentication or authorization layer in the checked-in code. Do not expose it publicly without adding appropriate access controls, request protections, and production error handling.
- The POST handlers return exception text to clients, which can reveal implementation details. Use a sanitized error response policy for public deployments.
- The page renders LLM and search results as HTML after DOMPurify sanitization when the CDN script is available; its rendering dependencies are externally hosted CDNs.
- This application provides planning assistance only. It does not book flights or hotels, and visa or entry guidance should be checked with official sources.

## Limitations and future improvements

Confirmed from the implementation:

- Flight results are current operational snapshots, not schedules for requested future dates or live fares.
- Weather data comprises current conditions and the first five forecast entries returned by OpenWeatherMap, not a forecast for arbitrary future travel dates.
- Budget and itinerary content is generated by LLMs; estimates and provider snippets are not reservations or guaranteed prices.
- The monthly flight counter is local to the application filesystem and is an approximation, not an account-wide or provider-authoritative quota meter.
- The graph agents run in sequence, and the route handlers invoke the synchronous graph directly. Long model/API calls can therefore occupy a request worker for their duration.
- If guardrail classification or parsing fails, `supervisor_agent` fails open and permits the request to proceed.
- `mcp_client.py` contains an unused `get_all_tools()` helper that requests an `aviationstack` MCP server not present in the client's configuration; the actual flight agent uses the direct Aviationstack REST tool instead.
- No application authentication, formal tests, migration framework, or production deployment configuration is included.

Potential improvements (not implemented) include adding automated tests, hardening API authentication and error responses, ensuring secrets are excluded from container build contexts, and adding production-grade concurrency, observability, and deployment configuration.

## License

No license has been specified in the repository.
