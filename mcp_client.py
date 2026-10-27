import os
import sys
from pathlib import Path
import re

from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI


load_dotenv()
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
AVIATION_STACK_API_KEY = os.getenv("AVIATION_STACK_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0.3,
    api_key=os.getenv("GEMINI_API_KEY"),
)

llm_groq = ChatGroq(
    model="qwen/qwen3.8-27b",
    api_key=GROQ_API_KEY
)

extractor_llm = ChatGroq(model="qwen/qwen3.8-27b", temperature=0, max_tokens=30)

# Automatically find the current project folder.
# This replaces the hard-coded Windows paths.
PROJECT_DIR = Path(__file__).resolve().parent
WEATHER_SERVER_PATH = PROJECT_DIR / "custom_weather_mcp_server.py"


OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")


# MCP client configuration

client = MultiServerMCPClient(
    {
        "tavily": {
            "transport": "streamable_http",
            "url": f"https://mcp.tavily.com/mcp/?tavilyApiKey={TAVILY_API_KEY}",
        },
        "weather": {
            "transport": "stdio",
            "command": sys.executable,
            "args": [str(WEATHER_SERVER_PATH)],
            "env": {
                "OPENWEATHER_API_KEY": OPENWEATHER_API_KEY or "",
            },
        },
    }
)

async def get_all_tools():
    """
    Load each MCP server separately.

    A broken server will no longer prevent the other
    working servers from loading.
    """
    all_tools = []

    for server_name in("tavily", "aviationstack"):
        try:
            tools = await client.get_tools(
                server_name=server_name
            )
            all_tools.extend(tools)

            print(
                f"\nAvailable tools from"
                f"{server_name} MCP:\n"
            )

            for tool in tools:
                print(tool.name)

        except Exception as error:
            print(
                f"\nCould not connect to "
                f"{server_name} MCP:\n{error}\n"
            )

    return all_tools


# Tavily MCP tool

search_tool = None

async def initialize_mcp():
    """
    Initialize only Tavily.

    Previously this function initialized all MCP servers,
    so an AviationStack or Weather failure also caused
    Tavily hotel search to fail.
    """

    global search_tool
    if search_tool is not None:
        return

    tools = await client.get_tools(
        server_name = "tavily"
    )

    tools_by_name = {
        tool.name:tool
        for tool in tools
    }

    search_tool = tools_by_name.get("tavily_search")

    if search_tool is None:
        available_tools = ", ".join(tools_by_name.keys())

        raise RuntimeError(
            "Tavily MCP connected, but the "
            "'tavily_search' tool was not found. "
            f"Available tools: "
            f"{available_tools or 'none'}"
        )

async def tavily_mcp_search(query:str):
    await initialize_mcp()

    result = await search_tool.ainvoke(
        {
            "query": query
        }
    )
    return result

# Weather MCP tools

weather_tool = None
forecast_tool = None

async def initialize_weather_tools():
    global weather_tool
    global forecast_tool

    if (
        weather_tool is not None
        and forecast_tool is not None
    ):
        return

    if not WEATHER_SERVER_PATH.exists():
        raise FileNotFoundError(
            "Weather MCP server file was not found: "
            f"{WEATHER_SERVER_PATH}"
        )

    tools = await client.get_tools(
        server_name="weather"
    )

    tools_by_name = {
        tool.name: tool
        for tool in tools
    }

    weather_tool = tools_by_name.get(
        "get_current_weather"
    )

    forecast_tool = tools_by_name.get(
        "get_forecast"
    )

    missing_tools = []

    if weather_tool is None:
        missing_tools.append(
            "get_current_weather"
        )

    if forecast_tool is None:
        missing_tools.append(
            "get_forecast"
        )

    if missing_tools:
        available_tools = ", ".join(
            tools_by_name.keys()
        )

        raise RuntimeError(
            "Missing Weather MCP tools: "
            f"{', '.join(missing_tools)}. "
            f"Available tools: "
            f"{available_tools or 'none'}"
        )

async def weather_mcp_search(city:str):
    await initialize_weather_tools()

    result = await weather_tool.ainvoke(
        {
            "city": city
        }
    )

    return result


async def forecast_mcp_search(city: str):
    await initialize_weather_tools()

    result = await forecast_tool.ainvoke(
        {
            "city": city
        }
    )

    return result

COUNTRY_TO_CITY = {"england": "London,GB", "uk": "London,GB", "united kingdom": "London,GB",
                   "britain": "London,GB", "japan": "Tokyo,JP", "france": "Paris,FR"}

def extract_destination(query: str) -> str:
    prompt = ("From the travel request, return ONLY the main destination city and its "
              "2-letter country code as City,CC (example: London,GB). If only a country "
              "is given, pick its most popular tourist city. No other text.\n\n"
              f"Request: {query}")
    text = extractor_llm.invoke(prompt).content
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    text = text.splitlines()[-1].strip().strip(".\"'")
    return COUNTRY_TO_CITY.get(text.lower(), text)