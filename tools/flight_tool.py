
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
 
import airportsdata
import certifi
import pycountry
import requests
from dotenv import load_dotenv
 
load_dotenv()
 
os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
 
API_KEY = os.getenv("AVIATION_STACK_API_KEY") or os.getenv("AVIATIONSTACK_API_KEY")
DEFAULT_ORIGIN_IATA = os.getenv("DEFAULT_ORIGIN_IATA", "DEL").upper()
MONTHLY_BUDGET = int(os.getenv("AVIATION_MONTHLY_BUDGET", "90"))
CACHE_TTL_SECONDS = int(os.getenv("AVIATION_CACHE_HOURS", "6")) * 3600
 
BASE_URL = "https://api.aviationstack.com/v1/flights"
CACHE_DIR = Path(__file__).resolve().parent / ".flight_cache"
 
AIRPORTS = airportsdata.load("IATA")
 
 
# ---------------------------------------------------------------------------
# Lookup tables
# ---------------------------------------------------------------------------
 
COUNTRY_ALIASES = {
    "usa": "US",
    "america": "US",
    "united states": "US",
    "uk": "GB",
    "britain": "GB",
    "england": "GB",
    "uae": "AE",
    "dubai": "AE",
    "south korea": "KR",
    "korea": "KR",
    "russia": "RU",
    "vietnam": "VN",
    "turkey": "TR",
}
 
# Preferred main airport for country-level searches
COUNTRY_MAIN_AIRPORT = {
    "BD": "DAC", "IN": "DEL", "JP": "NRT", "US": "JFK", "GB": "LHR",
    "AE": "DXB", "SG": "SIN", "MY": "KUL", "TH": "BKK", "ID": "CGK",
    "CN": "PEK", "KR": "ICN", "NP": "KTM", "QA": "DOH", "SA": "JED",
    "TR": "IST", "CA": "YYZ", "AU": "SYD", "DE": "FRA", "FR": "CDG",
    "IT": "FCO", "ES": "MAD", "LK": "CMB", "MV": "MLE", "NL": "AMS",
    "CH": "ZRH", "VN": "SGN", "NZ": "AKL", "ZA": "JNB", "BR": "GRU",
}
 
CITY_MAIN_AIRPORT = {
    "dhaka": "DAC", "delhi": "DEL", "new delhi": "DEL", "mumbai": "BOM",
    "kolkata": "CCU", "chennai": "MAA", "bangalore": "BLR", "bengaluru": "BLR",
    "hyderabad": "HYD", "pune": "PNQ", "goa": "GOI", "kochi": "COK",
    "ahmedabad": "AMD", "tokyo": "NRT", "osaka": "KIX", "kyoto": "KIX",
    "new york": "JFK", "london": "LHR", "manchester": "MAN",
    "birmingham": "BHX", "edinburgh": "EDI", "dubai": "DXB",
    "singapore": "SIN", "kuala lumpur": "KUL", "bangkok": "BKK",
    "doha": "DOH", "istanbul": "IST", "toronto": "YYZ", "sydney": "SYD",
    "paris": "CDG", "rome": "FCO", "madrid": "MAD", "frankfurt": "FRA",
}
 
STOP_WORDS = {
    "flight", "flights", "ticket", "tickets", "trip", "travel", "plan",
    "complete", "days", "day", "including", "hotel", "hotels", "sightseeing",
    "under", "budget", "info", "information", "the",
}
 
GLOBAL_KEYWORDS = (
    "all country", "all countries", "global flight", "worldwide flight",
    "all flight",
)
 
 
# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------
 
def clean_text(text: str) -> str:
    text = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    words = [w for w in text.split() if w not in STOP_WORDS and not w.isdigit()]
    return " ".join(words)
 
 
def country_name_to_code(text: str):
    """Country name/alias -> ISO2 code. Codes like 'it' or 'in' are NOT accepted."""
    text = clean_text(text)
    if not text:
        return None
    if text in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[text]
    if len(text) <= 3:
        return None
    try:
        return pycountry.countries.lookup(text).alpha_2
    except LookupError:
        return None
 
 
def airport_country_matches(airport: dict, country_code: str) -> bool:
    airport_country = str(airport.get("country", "")).upper().strip()
    if airport_country == country_code:
        return True
    try:
        country = pycountry.countries.get(alpha_2=country_code)
        if country and airport_country.lower() == country.name.lower():
            return True
    except Exception:
        pass
    return False
 
 
def get_best_airport_for_country(country_code: str):
    preferred = COUNTRY_MAIN_AIRPORT.get(country_code)
    if preferred and preferred in AIRPORTS:
        return preferred
 
    candidates = []
    for iata, airport in AIRPORTS.items():
        if not iata or not airport_country_matches(airport, country_code):
            continue
        name = str(airport.get("name", "")).lower()
        score = 0
        if "international" in name:
            score += 50
        if "intl" in name:
            score += 40
        if "capital" in name:
            score += 20
        if airport.get("city"):
            score += 5
        candidates.append((score, iata))
 
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]
 
 
def find_location_mentions(query: str):
    """Country / city names found in the text, IN THE ORDER THEY APPEAR."""
    q = query.lower()
 
    names = set(COUNTRY_ALIASES) | set(CITY_MAIN_AIRPORT)
    for country in pycountry.countries:
        for name in (country.name, getattr(country, "common_name", None)):
            if name and len(name) >= 4:
                names.add(name.lower())
 
    spans = []
    for name in names:
        for m in re.finditer(rf"\b{re.escape(name)}\b", q):
            spans.append((m.start(), m.end(), name))
 
    # earliest first; at the same start the longest wins ("south korea" > "korea")
    spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))
 
    mentions, last_end = [], -1
    for start, end, name in spans:
        if start >= last_end:
            mentions.append(name)
            last_end = end
    return mentions
 
 
def resolve_location_to_iata(location: str):
    """
    City / country / airport name / IATA code -> IATA code.
    Bangladesh -> DAC, Japan -> NRT, Dhaka -> DAC, usa -> JFK, DEL -> DEL
    """
    if not location:
        return None
 
    raw = location.strip()
    cleaned = clean_text(raw)
    if not cleaned:
        return None
 
    # 1. preferred city airport
    if cleaned in CITY_MAIN_AIRPORT:
        return CITY_MAIN_AIRPORT[cleaned]
 
    # 2. country (checked before raw IATA, because "USA" is also an airport code)
    country_code = country_name_to_code(cleaned)
    if country_code:
        airport = get_best_airport_for_country(country_code)
        if airport:
            return airport
 
    # 3. direct IATA code
    if re.fullmatch(r"[A-Za-z]{3}", raw) and raw.upper() in AIRPORTS:
        return raw.upper()
 
    # 4. airport database (whole-word matches only, avoids "rome" in "jerome")
    if len(cleaned) < 4:
        return None
 
    pattern = re.compile(rf"\b{re.escape(cleaned)}\b")
    matches = []
    for iata, airport in AIRPORTS.items():
        city = str(airport.get("city", "")).lower().strip()
        name = str(airport.get("name", "")).lower().strip()
 
        score = 0
        if city == cleaned:
            score = 100
        elif pattern.search(city):
            score = 60
        elif pattern.search(name):
            score = 40
        if score and "international" in name:
            score += 10
        if score:
            matches.append((score, iata))
 
    if matches:
        matches.sort(reverse=True)
        return matches[0][1]
    return None
 
 
def _resolve_chunk(text: str):
    """Resolve a phrase like 'go to usa' by trying it whole, then its place names."""
    code = resolve_location_to_iata(text)
    if code:
        return code
    for mention in find_location_mentions(text):
        code = resolve_location_to_iata(mention)
        if code:
            return code
    return None
 
 
# ---------------------------------------------------------------------------
# Route parsing
# ---------------------------------------------------------------------------
 
_END = r"(?:\s+(?:on|for|under|including|with|in|at|during|and|by|via|then)\b|[.,!?;]|$)"
FROM_TO = re.compile(rf"\bfrom\s+(.+?)\s+to\s+(.+?){_END}")
TO_FROM = re.compile(rf"\bto\s+(.+?)\s+from\s+(.+?){_END}")
FROM_ONLY = re.compile(rf"\bfrom\s+(.+?){_END}")
TO_ONLY = re.compile(rf"\bto\s+(.+?){_END}")
 
 
def parse_route(query: str):
    """
    Returns (dep_iata, arr_iata). Either can be None; (None, None) means
    "could not work out a route", and no API request should be made.
    """
    q = query.strip()
    q_lower = q.lower()
 
    if any(k in q_lower for k in GLOBAL_KEYWORDS):
        return None, None
 
    # Explicit airport codes, e.g. "DEL to LHR". Country shorthands such as
    # USA / UAE are not airport codes here.
    codes = [
        c for c in re.findall(r"\b[A-Z]{3}\b", q)
        if c in AIRPORTS and c.lower() not in COUNTRY_ALIASES
    ]
    if len(codes) >= 2:
        return codes[0], codes[1]
 
    dep = arr = None
 
    m = FROM_TO.search(q_lower)
    if m:
        dep, arr = _resolve_chunk(m.group(1)), _resolve_chunk(m.group(2))
    else:
        m = TO_FROM.search(q_lower)
        if m:
            arr, dep = _resolve_chunk(m.group(1)), _resolve_chunk(m.group(2))
        else:
            m = FROM_ONLY.search(q_lower)
            if m:
                dep = _resolve_chunk(m.group(1))
            m = TO_ONLY.search(q_lower)
            if m:
                arr = _resolve_chunk(m.group(1))
 
    # Fallback: use any place names that were mentioned but not yet assigned
    if dep is None or arr is None:
        found = []
        for name in find_location_mentions(q):
            code = resolve_location_to_iata(name)
            if code and code not in found and code not in (dep, arr):
                found.append(code)
 
        if dep is None and arr is None:
            if len(found) >= 2:
                dep, arr = found[0], found[1]
            elif found:
                arr = found[0]
        elif arr is None and found:
            arr = found[0]
        elif dep is None and found:
            dep = found[0]
 
    # Only a destination known -> assume the traveller's home airport
    if arr and not dep:
        dep = DEFAULT_ORIGIN_IATA
 
    if dep and dep == arr:
        return None, None
 
    return dep, arr
 
 
# ---------------------------------------------------------------------------
# Request budget + cache
# ---------------------------------------------------------------------------
 
def _usage_file() -> Path:
    return CACHE_DIR / "usage.json"
 
 
def _calls_this_month() -> int:
    # Counts only calls made through this tool. Aviationstack's quota resets on
    # your billing date, so this is an approximation, not an exact meter.
    try:
        data = json.loads(_usage_file().read_text(encoding="utf-8"))
        if data.get("month") == datetime.now().strftime("%Y-%m"):
            return int(data.get("calls", 0))
    except Exception:
        pass
    return 0
 
 
def _record_call() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _usage_file().write_text(
        json.dumps({
            "month": datetime.now().strftime("%Y-%m"),
            "calls": _calls_this_month() + 1,
        }),
        encoding="utf-8",
    )
 
 
# ---------------------------------------------------------------------------
# API call + formatting
# ---------------------------------------------------------------------------
 
def _route_label(dep, arr) -> str:
    if dep and arr:
        return f"{dep} -> {arr}"
    if dep:
        return f"departures from {dep}"
    if arr:
        return f"arrivals to {arr}"
    return "unknown route"
 
 
def _fmt_time(value) -> str:
    return f"{value[:16].replace('T', ' ')} UTC" if value else "unknown time"
 
 
def format_flight(flight: dict) -> str:
    airline = (flight.get("airline") or {}).get("name") or "Unknown airline"
    number = (flight.get("flight") or {}).get("iata") or "?"
    dep = flight.get("departure") or {}
    arr = flight.get("arrival") or {}
    status = flight.get("flight_status") or "unknown"
 
    delay = dep.get("delay")
    delay_text = f", delay {delay} min" if delay else ""
 
    return (
        f"- {number} ({airline}): "
        f"{dep.get('iata') or '?'} (terminal {dep.get('terminal') or 'n/a'}) -> "
        f"{arr.get('iata') or '?'} (terminal {arr.get('terminal') or 'n/a'}), "
        f"departs {_fmt_time(dep.get('scheduled'))}, status {status}{delay_text}"
    )
 
 
def _fetch(dep, arr, limit):
    """One real API call. Returns (text, cacheable)."""
    route = _route_label(dep, arr)
    params = {
        "access_key": API_KEY,
        # one request costs the same whatever the limit, so ask for extra and
        # drop codeshare duplicates afterwards
        "limit": min(max(limit * 4, 20), 100),
    }
    if dep:
        params["dep_iata"] = dep
    if arr:
        params["arr_iata"] = arr
 
    try:
        response = requests.get(BASE_URL, params=params, timeout=30)
        data = response.json()
    except requests.exceptions.RequestException as e:
        # the request URL contains the API key, so never pass it on
        message = str(e).replace(API_KEY or "", "***")
        return f"Live flight lookup failed for {route}: {message}", False
    except ValueError:
        return f"Live flight lookup failed for {route}: API returned invalid JSON.", False
 
    _record_call()
 
    if "error" in data:
        error = data["error"] or {}
        return (
            f"Live flight data unavailable for {route} "
            f"({error.get('code', 'unknown')}: {error.get('message', 'no message')}).",
            False,
        )
 
    flights = [
        f for f in data.get("data", [])
        if not (f.get("flight") or {}).get("codeshared")
    ]
 
    if not flights:
        return (
            f"No live flights found for {route} in the current snapshot. "
            "(Live data only, not fares or future schedules.)",
            True,
        )
 
    lines = [format_flight(f) for f in flights[:limit]]
    header = (
        f"Live flight activity for {route} "
        f"(real-time data, NOT fares; {len(lines)} sample flights):"
    )
    return header + "\n" + "\n".join(lines), True
 
 
def search_flights(query: str, limit: int = 5, allow_global: bool = False) -> str:
    """
    Main entry point. Always returns a plain string that is safe to put in a
    prompt (errors included), never raises, and spends at most one API
    request per route per cache period.
    """
    dep, arr = parse_route(query)
 
    if not dep and not arr and not allow_global:
        return (
            "Live flight lookup skipped: could not work out a route "
            "from the request."
        )
 
    route = _route_label(dep, arr)
    cache_file = CACHE_DIR / f"{dep or 'ANY'}_{arr or 'ANY'}_{limit}.txt"
 
    if cache_file.exists() and time.time() - cache_file.stat().st_mtime < CACHE_TTL_SECONDS:
        return cache_file.read_text(encoding="utf-8")
 
    if not API_KEY:
        return (
            "Live flight data unavailable: AVIATION_STACK_API_KEY is missing "
            "from the .env file."
        )
 
    if _calls_this_month() >= MONTHLY_BUDGET:
        return (
            f"Live flight lookup skipped for {route}: monthly request budget "
            f"({MONTHLY_BUDGET}) reached."
        )
 
    text, cacheable = _fetch(dep, arr, limit)
    if cacheable:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(text, encoding="utf-8")
    return text
 
 
# ---------------------------------------------------------------------------
# Manual tests
# ---------------------------------------------------------------------------
 
if __name__ == "__main__":
    if len(sys.argv) > 1:
        # ONE real API call (uses 1 of your monthly requests, then cached)
        print(search_flights(" ".join(sys.argv[1:])))
    else:
        # Offline parser test: makes NO API requests
        print(f"Default origin: {DEFAULT_ORIGIN_IATA} | key loaded: {bool(API_KEY)}\n")
        tests = [
            "plan a trip from India to England",
            "Plan a 7 days Japan trip from Bangladesh",
            "trip to England from India",
            "I want to go to USA from UAE",
            "DEL to LHR next month",
            "Plan a 5 day trip to Tokyo for under 2 lakh",
            "flights from Mumbai to Paris on 5 November",
            "plan a trip to India",
            "all country flight info",
        ]
        for t in tests:
            print(f"{t!r:60} -> {parse_route(t)}")