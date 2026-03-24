# Rakuten Travel MCP Server

An MCP server that wraps all 7 [Rakuten Travel APIs](https://webservice.rakuten.co.jp/documentation), letting any LLM search hotels, check real-time availability, browse area codes, and get rankings across Japan.

Built with [FastMCP](https://gofastmcp.com) and [httpx](https://www.python-httpx.org).

## Tools

| Tool | API | What it does |
|------|-----|-------------|
| `search_hotels` | SimpleHotelSearch | Find hotels by coordinates, area code, or hotel number |
| `get_hotel_detail` | HotelDetailSearch | Full details for a hotel — facilities, ratings, policies |
| `search_vacant_hotels` | VacantHotelSearch | Real-time room availability with dates and pricing |
| `get_area_classes` | GetAreaClass | Area code hierarchy: country → prefecture → city → station |
| `search_hotels_by_keyword` | KeywordHotelSearch | Search by keyword — "ski", "onsen", "ペット", "camping" |
| `get_hotel_chain_list` | GetHotelChainList | All 309 hotel chain codes (ANA, Hilton, etc.) |
| `get_hotel_ranking` | HotelRanking | Top 10 ranked hotels by genre (overall / onsen / premium) |

## Quick Start

### 1. Get API credentials

Sign up at [Rakuten Developers](https://webservice.rakuten.co.jp/app/create) and create an app to get your **Application ID** and **Access Key**.

### 2. Set environment variables

```bash
export RAKUTEN_APP_ID="your_app_id"
export RAKUTEN_ACCESS_KEY="your_access_key"

# Optional — enables affiliate links in hotel URLs
export RAKUTEN_AFFILIATE_ID="your_affiliate_id"
```

### 3. Run

```bash
# Install dependencies
uv sync

# Run as HTTP server
uv run python server.py

# Or use the FastMCP CLI
uv run fastmcp run server.py --transport http
```

The server starts at `http://localhost:8000/mcp`.

### 4. Deploy to FastMCP Cloud

```bash
uv run fastmcp deploy server.py
```

## Example Queries

Once connected to an LLM, you can ask things like:

- *"Find the top 3 cheapest hotels within 1km of Tokyo Station"*
- *"Find onsen hotels near ski resorts in Nagano"*
- *"Are there any rooms available in Niseko for April 10–12 under ¥15,000/night?"*
- *"What are the top-rated onsen hotels in Japan?"*
- *"Show me pet-friendly hotels in Hokkaido"*

The LLM will call the appropriate tools, translate Japanese responses, and present results.

## Tool Details

### search_hotels

Search by **coordinates**, **area codes**, or **hotel number**.

```
latitude/longitude  — WGS84 degrees (e.g. 35.6812, 139.7671 for Tokyo Station)
search_radius       — 0.1–3.0 km (default 1)
large_class_code    — almost always "japan"
middle_class_code   — prefecture (e.g. "hokkaido", "tokyo", "nagano")
small_class_code    — city/area (e.g. "niseko", "shinjuku")
detail_class_code   — station/sub-area
hotel_no            — comma-separated Rakuten hotel IDs, up to 15
squeeze_condition   — kinen (non-smoking), internet, daiyoku (large bath), onsen
sort                — "standard", "+roomCharge" (cheapest), "-roomCharge" (priciest)
hits                — 1–30 results per page
response_type       — "small", "middle", or "large"
```

### search_vacant_hotels

Same location params as above, plus availability filters:

```
checkin_date / checkout_date  — YYYY-MM-DD (required)
adult_num                     — guests per room (1–10)
room_num                      — number of rooms (1–10)
max_charge / min_charge       — price range in yen
squeeze_condition             — adds: breakfast, dinner
search_pattern                — 0 = by hotel, 1 = by plan
```

### search_hotels_by_keyword

```
keyword             — min 2 chars, space-separated = AND (e.g. "温泉 スキー")
middle_class_code   — optional prefecture filter
hotel_chain_code    — optional chain filter (comma-separated, up to 5)
search_field        — 0 = all fields, 1 = hotel name only
```

### get_hotel_ranking

```
genre  — "all" (default), "onsen", "premium" — comma-separated for multiple
```

### get_hotel_detail, get_area_classes, get_hotel_chain_list

These take minimal or no parameters — see the tool docstrings for details.

## Project Structure

```
server.py          — MCP server with all 7 tools (single file)
pyproject.toml     — project config and dependencies
.env.example       — template for environment variables
```

## Requirements

- Python 3.10+
- `fastmcp`
- `httpx`
