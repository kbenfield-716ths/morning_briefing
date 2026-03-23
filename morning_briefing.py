#!/usr/bin/env python3
"""
Morning Briefing for Clinicians
================================
Assembles a daily briefing from multiple data sources and delivers
it as a push notification to your phone.

Data sources:
  - Outlook calendar (via ICS feed)
  - QGenda schedule (via ICS feed)
  - Personal/family calendar (via ICS feed)
  - Weather (Open-Meteo API, free, no key required)
  - Custom RSS feeds (medical news, etc.)

Delivery:
  - Pushover (rich push notifications, $5 one-time)
  - Ntfy (free, open-source push notifications)

Designed to run as a GitHub Actions cron job. No server required.
"""

import os
import json
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Optional

# ──────────────────────────────────────────────────────────────
# CONFIGURATION (set these as GitHub Actions secrets/variables)
# ──────────────────────────────────────────────────────────────

# ICS Calendar feeds (set as GitHub secrets)
OUTLOOK_ICS_URL = os.environ.get("OUTLOOK_ICS_URL", "")
QGENDA_ICS_URL = os.environ.get("QGENDA_ICS_URL", "")

# Personal/family calendars — supports multiple feeds
# Format: JSON object mapping label → ICS URL
# Example: {"My Calendar":"https://...","Liam School":"https://...","Annalise School":"https://..."}
# OR: a single URL string for backward compatibility
PERSONAL_CALENDARS_JSON = os.environ.get("PERSONAL_CALENDARS", "")
PERSONAL_ICS_URL = os.environ.get("PERSONAL_ICS_URL", "")  # legacy single-feed fallback

# Weather location (default: Charlottesville, VA)
WEATHER_LAT = float(os.environ.get("WEATHER_LAT", "38.03"))
WEATHER_LON = float(os.environ.get("WEATHER_LON", "-78.48"))
WEATHER_UNIT = os.environ.get("WEATHER_UNIT", "fahrenheit")

# RSS feeds (comma-separated URLs)
RSS_FEEDS = os.environ.get("RSS_FEEDS", "https://www.nejm.org/action/showFeed?jc=nejm&type=etoc&feed=rss")

# Notification delivery (choose one or both)
NOTIFY_METHOD = os.environ.get("NOTIFY_METHOD", "pushover")  # "pushover", "ntfy", or "both"

# Pushover credentials
PUSHOVER_USER_KEY = os.environ.get("PUSHOVER_USER_KEY", "")
PUSHOVER_APP_TOKEN = os.environ.get("PUSHOVER_APP_TOKEN", "")

# Ntfy topic (your unique topic name)
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")
NTFY_SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh")

# Timezone
TIMEZONE_OFFSET = int(os.environ.get("TIMEZONE_OFFSET_HOURS", "-4"))  # ET = -4 (EDT) or -5 (EST)

# ──────────────────────────────────────────────────────────────
# ICS PARSER (lightweight, no external dependencies)
# ──────────────────────────────────────────────────────────────

def fetch_url(url: str, timeout: int = 15) -> str:
    """Fetch URL content as string."""
    req = urllib.request.Request(url, headers={"User-Agent": "MorningBriefing/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_ics_events(ics_text: str, target_date: datetime) -> list[dict]:
    """
    Parse ICS text and return events occurring on target_date.
    Handles basic VEVENT parsing without external libraries.
    """
    events = []
    in_event = False
    current = {}
    
    # Unfold long lines per ICS spec
    lines = ics_text.replace("\r\n ", "").replace("\r\n\t", "").split("\r\n")
    if len(lines) <= 1:
        lines = ics_text.replace("\n ", "").replace("\n\t", "").split("\n")
    
    target_str = target_date.strftime("%Y%m%d")
    
    for line in lines:
        line = line.strip()
        if line == "BEGIN:VEVENT":
            in_event = True
            current = {}
        elif line == "END:VEVENT":
            in_event = False
            if current:
                event = process_event(current, target_str, target_date)
                if event:
                    events.append(event)
            current = {}
        elif in_event and ":" in line:
            # Handle properties with parameters (e.g., DTSTART;TZID=...)
            key_part, _, value = line.partition(":")
            key = key_part.split(";")[0]
            current[key] = value
    
    # Sort by start time
    events.sort(key=lambda e: e.get("sort_time", ""))
    return events


def process_event(props: dict, target_str: str, target_date: datetime) -> Optional[dict]:
    """Process a single VEVENT and return dict if it falls on target_date."""
    dtstart = props.get("DTSTART", "")
    dtend = props.get("DTEND", "")
    summary = props.get("SUMMARY", "No title")
    location = props.get("LOCATION", "")
    
    # Clean up escaped characters
    summary = summary.replace("\\,", ",").replace("\\;", ";").replace("\\n", " ")
    location = location.replace("\\,", ",").replace("\\;", ";").replace("\\n", " ")
    
    # Check if event falls on target date
    is_all_day = len(dtstart) == 8  # Just a date, no time
    
    if is_all_day:
        if dtstart == target_str:
            return {
                "summary": summary,
                "time": "All day",
                "location": location,
                "sort_time": "00:00",
                "all_day": True
            }
        return None
    
    # Parse datetime (handle various formats)
    dt_clean = dtstart.replace("Z", "")
    try:
        if "T" in dt_clean:
            dt = datetime.strptime(dt_clean[:15], "%Y%m%dT%H%M%S")
        else:
            dt = datetime.strptime(dt_clean[:8], "%Y%m%d")
    except ValueError:
        return None
    
    # Rough timezone adjustment (ICS times may be UTC)
    if dtstart.endswith("Z"):
        dt = dt + timedelta(hours=TIMEZONE_OFFSET)
    
    if dt.strftime("%Y%m%d") == target_str:
        time_str = dt.strftime("%-I:%M %p")
        
        # Parse end time if available
        end_str = ""
        if dtend:
            dt_end_clean = dtend.replace("Z", "")
            try:
                if "T" in dt_end_clean:
                    dt_end = datetime.strptime(dt_end_clean[:15], "%Y%m%dT%H%M%S")
                    if dtend.endswith("Z"):
                        dt_end = dt_end + timedelta(hours=TIMEZONE_OFFSET)
                    end_str = f" – {dt_end.strftime('%-I:%M %p')}"
            except ValueError:
                pass
        
        return {
            "summary": summary,
            "time": f"{time_str}{end_str}",
            "location": location,
            "sort_time": dt.strftime("%H:%M"),
            "all_day": False
        }
    
    return None


# ──────────────────────────────────────────────────────────────
# DATA FETCHERS
# ──────────────────────────────────────────────────────────────

def fetch_calendar_events(ics_url: str, label: str, target_date: datetime) -> list[dict]:
    """Fetch and parse events from an ICS feed."""
    if not ics_url:
        return []
    try:
        ics_text = fetch_url(ics_url)
        events = parse_ics_events(ics_text, target_date)
        for e in events:
            e["source"] = label
        return events
    except Exception as ex:
        print(f"⚠ Could not fetch {label} calendar: {ex}")
        return []


def fetch_personal_calendars(target_date: datetime) -> list[dict]:
    """
    Fetch events from all personal/family calendars.
    
    Supports two config styles:
      1. PERSONAL_CALENDARS secret as JSON: {"Label":"url", "Label2":"url2", ...}
      2. Legacy PERSONAL_ICS_URL secret as a single URL string
    """
    all_events = []
    
    # Try the multi-calendar JSON format first
    if PERSONAL_CALENDARS_JSON:
        try:
            calendars = json.loads(PERSONAL_CALENDARS_JSON)
            if isinstance(calendars, dict):
                for label, url in calendars.items():
                    events = fetch_calendar_events(url.strip(), label.strip(), target_date)
                    all_events.extend(events)
                return all_events
        except json.JSONDecodeError:
            print("⚠ PERSONAL_CALENDARS is not valid JSON, trying as comma-separated URLs")
            # Fallback: treat as comma-separated URLs
            urls = [u.strip() for u in PERSONAL_CALENDARS_JSON.split(",") if u.strip()]
            for i, url in enumerate(urls):
                label = f"Personal {i+1}" if len(urls) > 1 else "Personal"
                events = fetch_calendar_events(url, label, target_date)
                all_events.extend(events)
            return all_events
    
    # Legacy single-URL fallback
    if PERSONAL_ICS_URL:
        return fetch_calendar_events(PERSONAL_ICS_URL, "Personal", target_date)
    
    return []


def fetch_weather() -> dict:
    """Fetch today's weather from Open-Meteo (free, no API key)."""
    try:
        unit_param = "fahrenheit" if WEATHER_UNIT == "fahrenheit" else "celsius"
        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={WEATHER_LAT}&longitude={WEATHER_LON}"
            f"&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,"
            f"weathercode&temperature_unit={unit_param}&timezone=auto&forecast_days=1"
        )
        data = json.loads(fetch_url(url))
        daily = data.get("daily", {})
        
        # Weather code descriptions
        weather_codes = {
            0: "Clear sky ☀️", 1: "Mainly clear 🌤", 2: "Partly cloudy ⛅",
            3: "Overcast ☁️", 45: "Foggy 🌫", 48: "Rime fog 🌫",
            51: "Light drizzle 🌦", 53: "Drizzle 🌦", 55: "Heavy drizzle 🌧",
            61: "Light rain 🌧", 63: "Rain 🌧", 65: "Heavy rain 🌧",
            71: "Light snow 🌨", 73: "Snow 🌨", 75: "Heavy snow 🌨",
            77: "Snow grains 🌨", 80: "Light showers 🌦", 81: "Showers 🌧",
            82: "Heavy showers ⛈", 85: "Light snow showers 🌨",
            86: "Snow showers 🌨", 95: "Thunderstorm ⛈",
            96: "Thunderstorm w/ hail ⛈", 99: "Severe thunderstorm ⛈"
        }
        
        code = daily.get("weathercode", [0])[0]
        unit_symbol = "°F" if unit_param == "fahrenheit" else "°C"
        
        return {
            "high": round(daily.get("temperature_2m_max", [0])[0]),
            "low": round(daily.get("temperature_2m_min", [0])[0]),
            "unit": unit_symbol,
            "precip_chance": daily.get("precipitation_probability_max", [0])[0],
            "description": weather_codes.get(code, f"Code {code}"),
        }
    except Exception as ex:
        print(f"⚠ Could not fetch weather: {ex}")
        return {}


def fetch_rss_headlines(max_per_feed: int = 1) -> list[dict]:
    """Fetch latest headline from each RSS feed."""
    headlines = []
    feeds = [f.strip() for f in RSS_FEEDS.split(",") if f.strip()]
    
    for feed_url in feeds:
        try:
            xml_text = fetch_url(feed_url)
            root = ET.fromstring(xml_text)
            
            # Handle both RSS 2.0 and Atom feeds
            items = root.findall(".//item")  # RSS 2.0
            if not items:
                # Try Atom
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                items = root.findall(".//atom:entry", ns)
            
            for item in items[:max_per_feed]:
                title = ""
                link = ""
                
                # RSS 2.0
                title_el = item.find("title")
                link_el = item.find("link")
                
                if title_el is not None and title_el.text:
                    title = title_el.text.strip()
                if link_el is not None:
                    link = (link_el.text or "").strip()
                    if not link:
                        link = link_el.get("href", "")
                
                # Atom fallback
                if not title:
                    ns = {"atom": "http://www.w3.org/2005/Atom"}
                    t = item.find("atom:title", ns)
                    if t is not None:
                        title = (t.text or "").strip()
                if not link:
                    ns = {"atom": "http://www.w3.org/2005/Atom"}
                    l = item.find("atom:link", ns)
                    if l is not None:
                        link = l.get("href", "")
                
                if title:
                    headlines.append({"title": title, "link": link})
        except Exception as ex:
            print(f"⚠ Could not fetch RSS {feed_url}: {ex}")
    
    return headlines


# ──────────────────────────────────────────────────────────────
# BRIEFING FORMATTER
# ──────────────────────────────────────────────────────────────

def format_briefing(
    today: datetime,
    weather: dict,
    outlook_events: list,
    qgenda_events: list,
    personal_events: list,
    headlines: list
) -> tuple[str, str, str]:
    """
    Format the briefing as (title, html_body, plain_body).
    Returns HTML for Pushover and plain text for Ntfy/logging.
    """
    day_name = today.strftime("%A")
    date_str = today.strftime("%B %-d")
    
    title = f"☀️ {day_name}, {date_str}"
    
    html = []
    plain = []
    
    # ── Weather ──
    if weather:
        w = weather
        temp = f"{w['low']}{w['unit']} → {w['high']}{w['unit']}"
        rain = f"  ·  🌧 {w['precip_chance']}%" if w.get("precip_chance", 0) > 20 else ""
        html.append(f"<b>{w['description']}</b>  {temp}{rain}")
        plain.append(f"{w['description']}  {temp}{rain}")
    
    # ── WORK section ──
    if qgenda_events or outlook_events:
        html.append("\n<b>━━ WORK ━━</b>")
        plain.append("━━ WORK ━━")
        
        if qgenda_events:
            html.append("📋 <b>Clinical</b>")
            plain.append("📋 Clinical:")
            for e in qgenda_events:
                loc = f" ({e['location']})" if e.get("location") else ""
                html.append(f"  <b>{e['time']}</b>  {e['summary']}{loc}")
                plain.append(f"  {e['time']}  {e['summary']}{loc}")
        
        if outlook_events:
            if qgenda_events:
                html.append("")
            html.append("📅 <b>Meetings</b>")
            plain.append("📅 Meetings:")
            for e in outlook_events:
                loc = f" ({e['location']})" if e.get("location") else ""
                html.append(f"  <b>{e['time']}</b>  {e['summary']}{loc}")
                plain.append(f"  {e['time']}  {e['summary']}{loc}")
    
    # ── PERSONAL section ──
    if personal_events:
        html.append("\n<b>━━ PERSONAL ━━</b>")
        plain.append("━━ PERSONAL ━━")
        
        # Group events by source label (e.g., "My Calendar", "Liam School")
        sources: dict[str, list] = {}
        for e in personal_events:
            src = e.get("source", "Personal")
            if src not in sources:
                sources[src] = []
            sources[src].append(e)
        
        first = True
        for source_label, events in sources.items():
            if not first:
                html.append("")
            first = False
            
            # Show sub-header when multiple calendars
            if len(sources) > 1:
                html.append(f"🏠 <b>{source_label}</b>")
                plain.append(f"🏠 {source_label}:")
            else:
                html.append("🏠 <b>Personal</b>")
                plain.append("🏠 Personal:")
            
            for e in events:
                loc = f" ({e['location']})" if e.get("location") else ""
                html.append(f"  <b>{e['time']}</b>  {e['summary']}{loc}")
                plain.append(f"  {e['time']}  {e['summary']}{loc}")
    
    # No events
    if not qgenda_events and not outlook_events and not personal_events:
        html.append("📅 No events on calendar today.")
        plain.append("📅 No events on calendar today.")
    
    # ── Headlines ──
    if headlines:
        hl = headlines[0]
        hl_text = hl["title"][:120]
        if hl.get("link"):
            html.append(f"\n📰 <a href=\"{hl['link']}\">{hl_text}</a>")
        else:
            html.append(f"\n📰 {hl_text}")
        plain.append(f"📰 {hl_text}")
    
    html_body = "\n".join(html)
    plain_body = "\n\n".join(plain)
    return title, html_body, plain_body


# ──────────────────────────────────────────────────────────────
# NOTIFICATION DELIVERY
# ──────────────────────────────────────────────────────────────

def send_pushover(title: str, html_body: str):
    """Send HTML-formatted notification via Pushover."""
    if not PUSHOVER_USER_KEY or not PUSHOVER_APP_TOKEN:
        print("⚠ Pushover credentials not configured, skipping.")
        return
    
    data = urllib.parse.urlencode({
        "token": PUSHOVER_APP_TOKEN,
        "user": PUSHOVER_USER_KEY,
        "title": title,
        "message": html_body,
        "html": 1,          # Enable HTML rendering
        "priority": 0,
        "sound": "morning",
    }).encode("utf-8")
    
    req = urllib.request.Request("https://api.pushover.net/1/messages.json", data=data)
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
            if result.get("status") == 1:
                print("✓ Pushover notification sent.")
            else:
                print(f"⚠ Pushover error: {result}")
    except Exception as ex:
        print(f"⚠ Pushover send failed: {ex}")


def send_ntfy(title: str, body: str):
    """Send notification via ntfy.sh."""
    if not NTFY_TOPIC:
        print("⚠ Ntfy topic not configured, skipping.")
        return
    
    url = f"{NTFY_SERVER}/{NTFY_TOPIC}"
    req = urllib.request.Request(url, data=body.encode("utf-8"), method="POST")
    req.add_header("Title", title)
    req.add_header("Priority", "default")
    req.add_header("Tags", "sunrise,calendar")
    
    try:
        with urllib.request.urlopen(req) as resp:
            if resp.status == 200:
                print("✓ Ntfy notification sent.")
            else:
                print(f"⚠ Ntfy returned status {resp.status}")
    except Exception as ex:
        print(f"⚠ Ntfy send failed: {ex}")


# ──────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────

def main():
    # Determine "today" in local time
    utc_now = datetime.now(timezone.utc)
    local_now = utc_now + timedelta(hours=TIMEZONE_OFFSET)
    today = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    print(f"🌅 Morning Briefing for {today.strftime('%A, %B %-d, %Y')}")
    print("=" * 50)
    
    # Fetch all data
    weather = fetch_weather()
    
    outlook_events = fetch_calendar_events(OUTLOOK_ICS_URL, "Outlook", today)
    qgenda_events = fetch_calendar_events(QGENDA_ICS_URL, "QGenda", today)
    personal_events = fetch_personal_calendars(today)
    
    headlines = fetch_rss_headlines(max_per_feed=1)
    
    # Format
    title, html_body, plain_body = format_briefing(
        today, weather, outlook_events, qgenda_events, personal_events, headlines
    )
    
    print(f"\n{title}\n{plain_body}\n")
    
    # Deliver
    method = NOTIFY_METHOD.lower()
    if method in ("pushover", "both"):
        send_pushover(title, html_body)
    if method in ("ntfy", "both"):
        send_ntfy(title, plain_body)
    
    print("\n✓ Briefing complete.")


if __name__ == "__main__":
    main()
