"""
Rakuten Travel MCP Server

Exposes all 7 Rakuten Travel APIs as MCP tools so an LLM can search hotels,
check availability, look up area codes, and get rankings across Japan.

Environment variables (required):
    RAKUTEN_APP_ID      – Rakuten API application ID
    RAKUTEN_ACCESS_KEY  – Rakuten API access key

Optional:
    RAKUTEN_AFFILIATE_ID – enables affiliate URLs in responses
"""

from __future__ import annotations

import os

import httpx
from fastmcp import FastMCP, Context
from fastmcp.server.lifespan import lifespan

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

RAKUTEN_APP_ID = os.environ.get("RAKUTEN_APP_ID", "")
RAKUTEN_ACCESS_KEY = os.environ.get("RAKUTEN_ACCESS_KEY", "")
RAKUTEN_AFFILIATE_ID = os.environ.get("RAKUTEN_AFFILIATE_ID", "")

BASE_URL = "https://openapi.rakuten.co.jp/engine/api/Travel"

# ---------------------------------------------------------------------------
# Lifespan – shared httpx client
# ---------------------------------------------------------------------------


@lifespan
async def app_lifespan(server: FastMCP):
    async with httpx.AsyncClient(timeout=30.0) as client:
        yield {"http_client": client}


mcp = FastMCP(
    name="Rakuten Travel",
    instructions=(
        "You are a helpful travel assistant for Japan. "
        "Use these tools to search for hotels, check room availability, "
        "look up area codes, and get hotel rankings from Rakuten Travel. "
        "All coordinates use WGS84 degrees (e.g. latitude=35.6762, longitude=139.6503 for Tokyo). "
        "Use get_area_classes to discover valid area codes before searching by area. "
        "Use search_hotels_by_keyword for natural-language style queries (e.g. 'onsen ski'). "
        "Use search_vacant_hotels to check real-time availability for specific dates. "
        "Translate Japanese hotel names, descriptions, and reviews for the user."
    ),
    lifespan=app_lifespan,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _call_api(ctx: Context, endpoint: str, params: dict) -> dict:
    """Call a Rakuten Travel API endpoint and return the parsed JSON."""
    client: httpx.AsyncClient = ctx.lifespan_context["http_client"]

    params["applicationId"] = RAKUTEN_APP_ID
    params["accessKey"] = RAKUTEN_ACCESS_KEY
    params["format"] = "json"
    params["formatVersion"] = 2

    if RAKUTEN_AFFILIATE_ID:
        params["affiliateId"] = RAKUTEN_AFFILIATE_ID

    # Strip None values so the API doesn't see empty params
    params = {k: v for k, v in params.items() if v is not None}

    url = f"{BASE_URL}/{endpoint}"
    resp = await client.get(url, params=params)

    # Return Rakuten's own error JSON when available, otherwise raise
    if resp.status_code >= 400:
        try:
            body = resp.json()
        except Exception:
            body = {}
        return {
            "error": True,
            "status_code": resp.status_code,
            "error_type": body.get("error", "unknown_error"),
            "error_description": body.get(
                "error_description",
                f"HTTP {resp.status_code} from Rakuten API",
            ),
        }

    return resp.json()


# ---------------------------------------------------------------------------
# Tool 1 – Simple Hotel Search
# ---------------------------------------------------------------------------


@mcp.tool
async def search_hotels(
    ctx: Context,
    latitude: float | None = None,
    longitude: float | None = None,
    search_radius: float | None = None,
    large_class_code: str | None = None,
    middle_class_code: str | None = None,
    small_class_code: str | None = None,
    detail_class_code: str | None = None,
    hotel_no: str | None = None,
    squeeze_condition: str | None = None,
    sort: str | None = None,
    page: int = 1,
    hits: int = 30,
    response_type: str = "large",
) -> dict:
    """Search Rakuten Travel hotels by location, area code, or hotel number.

    You must provide at least ONE of these three search methods:
      1. Coordinates: latitude + longitude (WGS84 degrees, e.g. 35.6762 / 139.6503)
      2. Area codes: large_class_code (+ middle/small/detail as available).
         Use get_area_classes to discover valid codes.
      3. Hotel number(s): hotel_no — comma-separated, up to 15 (e.g. "12345,67890")

    Priority when multiple are provided: hotel_no > lat/lng > area codes.

    Args:
        latitude:  WGS84 latitude in degrees (e.g. 35.6762 for Tokyo).
        longitude: WGS84 longitude in degrees (e.g. 139.6503 for Tokyo).
        search_radius: Radius in km for coordinate search (0.1–3.0, default 1).
        large_class_code: Country code, almost always "japan".
        middle_class_code: Prefecture code (e.g. "tokyo", "hokkaido", "akita").
        small_class_code: City/area code (e.g. "shinjuku", "tazawa").
        detail_class_code: Station/sub-area code (e.g. "A").
        hotel_no: Rakuten hotel number(s), comma-separated, up to 15.
        squeeze_condition: Filter — comma-separated values from:
            kinen (non-smoking), internet, daiyoku (large bath), onsen (hot spring).
        sort: "standard" (default), "+roomCharge" (cheapest first), "-roomCharge" (most expensive first).
        page: Page number (1–100).
        hits: Results per page (1–30).
        response_type: "small", "middle", or "large" (default) — controls detail level.
    """
    params: dict = {
        "datumType": 1,
        "latitude": latitude,
        "longitude": longitude,
        "searchRadius": search_radius,
        "largeClassCode": large_class_code,
        "middleClassCode": middle_class_code,
        "smallClassCode": small_class_code,
        "detailClassCode": detail_class_code,
        "hotelNo": hotel_no,
        "squeezeCondition": squeeze_condition,
        "sort": sort,
        "page": page,
        "hits": hits,
        "responseType": response_type,
    }
    return await _call_api(ctx, "SimpleHotelSearch/20170426", params)


# ---------------------------------------------------------------------------
# Tool 2 – Hotel Detail Search
# ---------------------------------------------------------------------------


@mcp.tool
async def get_hotel_detail(
    ctx: Context,
    hotel_no: int,
    response_type: str = "large",
) -> dict:
    """Get full details for a specific Rakuten Travel hotel.

    Returns basic info, ratings (overall + per-category), facilities, bath/onsen
    details, meal info, policies, cancellation rules, and accepted credit cards.

    Args:
        hotel_no: The Rakuten hotel number (get this from search results).
        response_type: "small", "middle", or "large" (default) — controls detail level.
    """
    params: dict = {
        "datumType": 1,
        "hotelNo": hotel_no,
        "responseType": response_type,
    }
    return await _call_api(ctx, "HotelDetailSearch/20170426", params)


# ---------------------------------------------------------------------------
# Tool 3 – Vacant Hotel Search (availability)
# ---------------------------------------------------------------------------


@mcp.tool
async def search_vacant_hotels(
    ctx: Context,
    checkin_date: str,
    checkout_date: str,
    adult_num: int = 1,
    latitude: float | None = None,
    longitude: float | None = None,
    search_radius: float | None = None,
    large_class_code: str | None = None,
    middle_class_code: str | None = None,
    small_class_code: str | None = None,
    detail_class_code: str | None = None,
    hotel_no: str | None = None,
    max_charge: int | None = None,
    min_charge: int | None = None,
    room_num: int = 1,
    squeeze_condition: str | None = None,
    sort: str | None = None,
    search_pattern: int = 0,
    page: int = 1,
    hits: int = 30,
    response_type: str = "small",
    up_class_num: int = 0,
    low_class_num: int = 0,
    infant_with_mb_num: int = 0,
    infant_with_m_num: int = 0,
    infant_with_b_num: int = 0,
    infant_without_mb_num: int = 0,
) -> dict:
    """Search for hotels with real-time room availability on Rakuten Travel.

    Requires check-in/check-out dates AND at least one location method
    (coordinates, area codes, or hotel number — same as search_hotels).

    Args:
        checkin_date:  Check-in date as YYYY-MM-DD (e.g. "2025-07-01").
        checkout_date: Check-out date as YYYY-MM-DD (e.g. "2025-07-02").
        adult_num: Number of adult guests per room (1–10, default 1).
        latitude:  WGS84 latitude in degrees.
        longitude: WGS84 longitude in degrees.
        search_radius: Radius in km (0.1–3.0, default 1).
        large_class_code: Country code, almost always "japan".
        middle_class_code: Prefecture code.
        small_class_code: City/area code.
        detail_class_code: Station/sub-area code.
        hotel_no: Rakuten hotel number(s), comma-separated, up to 15.
        max_charge: Maximum price per night (yen).
        min_charge: Minimum price per night (yen).
        room_num: Number of rooms (1–10, default 1).
        squeeze_condition: Filters — comma-separated:
            kinen (non-smoking), internet, daiyoku (large bath), onsen,
            breakfast, dinner.
        sort: "standard", "+roomCharge" (cheapest), "-roomCharge" (priciest).
        search_pattern: 0 = group by hotel (default), 1 = group by plan.
        page: Page number (1–100).
        hits: Results per page (1–30).
        response_type: "small" (default), "middle", or "large".
        up_class_num: Upper-grade elementary school children (0–10).
        low_class_num: Lower-grade elementary school children (0–10).
        infant_with_mb_num: Infants with meal & bedding (0–10).
        infant_with_m_num:  Infants with meal only (0–10).
        infant_with_b_num:  Infants with bedding only (0–10).
        infant_without_mb_num: Infants without meal or bedding (0–10).
    """
    params: dict = {
        "datumType": 1,
        "checkinDate": checkin_date,
        "checkoutDate": checkout_date,
        "adultNum": adult_num,
        "latitude": latitude,
        "longitude": longitude,
        "searchRadius": search_radius,
        "largeClassCode": large_class_code,
        "middleClassCode": middle_class_code,
        "smallClassCode": small_class_code,
        "detailClassCode": detail_class_code,
        "hotelNo": hotel_no,
        "maxCharge": max_charge,
        "minCharge": min_charge,
        "roomNum": room_num,
        "squeezeCondition": squeeze_condition,
        "sort": sort,
        "searchPattern": search_pattern,
        "page": page,
        "hits": hits,
        "responseType": response_type,
        "upClassNum": up_class_num,
        "lowClassNum": low_class_num,
        "infantWithMBNum": infant_with_mb_num,
        "infantWithMNum": infant_with_m_num,
        "infantWithBNum": infant_with_b_num,
        "infantWithoutMBNum": infant_without_mb_num,
    }
    return await _call_api(ctx, "VacantHotelSearch/20170426", params)


# ---------------------------------------------------------------------------
# Tool 4 – Get Area Class (area code hierarchy)
# ---------------------------------------------------------------------------


@mcp.tool
async def get_area_classes(ctx: Context) -> dict:
    """Get the full Rakuten Travel area-code hierarchy for Japan.

    Returns a tree: large (country) → middle (prefecture) → small (city/area)
    → detail (station/sub-area).  Use the codes from this tree as inputs to
    search_hotels, search_vacant_hotels, or search_hotels_by_keyword.

    Example path: japan → hokkaido → furano → (detail code)

    No input parameters required.
    """
    return await _call_api(ctx, "GetAreaClass/20140210", {})


# ---------------------------------------------------------------------------
# Tool 5 – Keyword Hotel Search
# ---------------------------------------------------------------------------


@mcp.tool
async def search_hotels_by_keyword(
    ctx: Context,
    keyword: str,
    middle_class_code: str | None = None,
    hotel_chain_code: str | None = None,
    search_field: int = 0,
    sort: str | None = None,
    page: int = 1,
    hits: int = 30,
    response_type: str = "large",
) -> dict:
    """Search Rakuten Travel hotels by keyword (Japanese or English).

    Best for natural-language queries like "ski", "onsen", "Disney",
    "キャンプ" (camping), "ペット" (pet-friendly), etc.
    Keywords are AND-matched when separated by spaces.

    Args:
        keyword: Search text (min 2 characters). Space-separated = AND search.
            Examples: "ski onsen", "東京 ビジネス", "camping Hokkaido".
        middle_class_code: Optional prefecture filter (e.g. "nagano", "hokkaido").
            Use get_area_classes to discover valid codes.
        hotel_chain_code: Optional hotel chain filter, comma-separated up to 5.
            Use get_hotel_chain_list to discover valid codes.
        search_field: 0 = search hotel name + plan name + room name (default),
            1 = search hotel name only.
        sort: "standard" (relevance, default), "+roomCharge" (cheapest), "-roomCharge" (priciest).
        page: Page number (1–100).
        hits: Results per page (1–30).
        response_type: "small", "middle", or "large" (default).
    """
    params: dict = {
        "datumType": 1,
        "keyword": keyword,
        "middleClassCode": middle_class_code,
        "hotelChainCode": hotel_chain_code,
        "searchField": search_field,
        "sort": sort,
        "page": page,
        "hits": hits,
        "responseType": response_type,
    }
    return await _call_api(ctx, "KeywordHotelSearch/20170426", params)


# ---------------------------------------------------------------------------
# Tool 6 – Get Hotel Chain List
# ---------------------------------------------------------------------------


@mcp.tool
async def get_hotel_chain_list(ctx: Context) -> dict:
    """Get the list of all hotel chain codes on Rakuten Travel.

    Returns chain codes (e.g. "JL", "NK"), names, kana names, and descriptions.
    Use the codes to filter search_hotels_by_keyword via the hotel_chain_code param.

    No input parameters required.
    """
    return await _call_api(ctx, "GetHotelChainList/20131024", {})


# ---------------------------------------------------------------------------
# Tool 7 – Hotel Ranking
# ---------------------------------------------------------------------------


@mcp.tool
async def get_hotel_ranking(
    ctx: Context,
    genre: str = "all",
) -> dict:
    """Get the Rakuten Travel hotel ranking (top 10).

    Returns the top-rated hotels with review scores, review counts, and URLs.

    Args:
        genre: Ranking genre — one or more comma-separated values:
            "all"     – overall ranking (default)
            "onsen"   – hot-spring / onsen hotel ranking
            "premium" – luxury hotel / ryokan ranking
            Example: "all,onsen" returns both rankings.
    """
    params: dict = {
        "genre": genre,
    }
    return await _call_api(ctx, "HotelRanking/20170426", params)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000)
