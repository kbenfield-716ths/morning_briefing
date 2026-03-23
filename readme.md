# Morning Briefing for Clinicians

A zero-maintenance daily briefing that arrives as a push notification on your phone at 6:00 AM. No server required — runs entirely on GitHub Actions (free).

**What you get every morning:**
- ☀️ Weather forecast
- 📋 Your QGenda clinical schedule  
- 📅 Outlook meetings  
- 🏠 Personal/family calendar events  
- 📰 A medical news headline  

## Quick Start (15 minutes)

### 1. Fork this repo
Click **Fork** in the top right of this page.

### 2. Choose your notification app

**Option A: Pushover** ($5 one-time, very polished)
1. Install [Pushover](https://pushover.net/) on your iPhone
2. Create an account → note your **User Key**
3. [Create an Application](https://pushover.net/apps/build) → note the **API Token**

**Option B: Ntfy** (free, open source)
1. Install [Ntfy](https://ntfy.sh/) on your iPhone
2. Subscribe to a unique topic (e.g., `drsmith-briefing-2026`)
3. That's your topic name — no account needed

### 3. Get your calendar ICS feeds

**Outlook (UVA/M365):**
1. Go to [Outlook Web](https://outlook.office.com/calendar)
2. Settings → Calendar → Shared calendars
3. Under "Publish a calendar," select your calendar → Publish
4. Copy the **ICS link**

**QGenda:**
1. Log into QGenda → My Schedule
2. Look for "Subscribe" or "Export" → copy the ICS/webcal URL
3. Change `webcal://` to `https://` if needed

**Personal calendar (Apple/Google):**
- **Apple iCloud:** Settings → Calendar → Public calendar sharing → copy link
- **Google Calendar:** Settings → Calendar settings → Secret address in iCal format

### 4. Add secrets to your forked repo

Go to your fork → **Settings** → **Secrets and variables** → **Actions**

Add these **Secrets** (sensitive, hidden):
| Secret | Value |
|--------|-------|
| `OUTLOOK_ICS_URL` | Your Outlook ICS link |
| `QGENDA_ICS_URL` | Your QGenda ICS link |
| `PERSONAL_ICS_URL` | Your personal calendar ICS link |
| `PUSHOVER_USER_KEY` | *(if using Pushover)* |
| `PUSHOVER_APP_TOKEN` | *(if using Pushover)* |

Add these **Variables** (non-sensitive, visible):
| Variable | Default | Description |
|----------|---------|-------------|
| `WEATHER_LAT` | `38.03` | Your latitude (Cville default) |
| `WEATHER_LON` | `-78.48` | Your longitude |
| `WEATHER_UNIT` | `fahrenheit` | `fahrenheit` or `celsius` |
| `NOTIFY_METHOD` | `pushover` | `pushover`, `ntfy`, or `both` |
| `NTFY_TOPIC` | | Your ntfy topic name |
| `RSS_FEEDS` | NEJM feed | Comma-separated RSS URLs |
| `TIMEZONE_OFFSET_HOURS` | `-4` | UTC offset (-4 EDT, -5 EST) |

### 5. Test it

Go to **Actions** tab → **Morning Briefing** → **Run workflow** → click **Run workflow**.

You should get a notification within a minute.

### 6. You're done

The briefing will run automatically every day at 6:00 AM Eastern.

## Customization

### Add more RSS feeds
Set the `RSS_FEEDS` variable to a comma-separated list:
```
https://www.nejm.org/action/showFeed?jc=nejm&type=etoc&feed=rss,https://jamanetwork.com/rss/site_3/67.xml
```

### Popular medical RSS feeds
| Source | URL |
|--------|-----|
| NEJM | `https://www.nejm.org/action/showFeed?jc=nejm&type=etoc&feed=rss` |
| JAMA | `https://jamanetwork.com/rss/site_3/67.xml` |
| Lancet | `https://www.thelancet.com/rssfeed/lancet_current.xml` |
| CHEST | `https://journal.chestnet.org/rss/current` |
| AJRCCM | `https://www.atsjournals.org/action/showFeed?type=etoc&feed=rss&jc=ajrccm` |
| Critical Care Medicine | `https://journals.lww.com/ccmjournal/pages/currenttoc.aspx.rss` |

### Change the delivery time
Edit `.github/workflows/morning-briefing.yml` and change the cron schedule:
```yaml
- cron: '0 10 * * *'  # 10:00 UTC = 6:00 AM EDT
```

Common times (EDT):
- 5:00 AM → `'0 9 * * *'`
- 5:30 AM → `'30 9 * * *'`
- 6:30 AM → `'30 10 * * *'`
- 7:00 AM → `'0 11 * * *'`

### Skip weekends
```yaml
- cron: '0 10 * * 1-5'  # Weekdays only
```

## How it works

```
┌──────────────┐     ┌──────────┐     ┌──────────────┐
│ GitHub Actions│────▶│  Python  │────▶│  Pushover /  │────▶ 📱
│  (cron, free) │     │  script  │     │  Ntfy        │
└──────────────┘     └────┬─────┘     └──────────────┘
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
         ICS feeds    Open-Meteo   RSS feeds
        (calendars)   (weather)    (news)
```

No server. No hosting costs. No maintenance. Just a GitHub repo and a cron job.

## Troubleshooting

**No notification received:**
1. Check Actions tab → look for failed runs → read the logs
2. Verify secrets are set (Settings → Secrets → check they exist)
3. Run manually with `workflow_dispatch` to test

**Wrong times on events:**
- Adjust `TIMEZONE_OFFSET_HOURS` (EDT = -4, EST = -5)
- Some ICS feeds use UTC; the script adjusts automatically for `Z` timestamps

**GitHub Actions not running on schedule:**
- GitHub may delay cron jobs by up to 15 minutes
- If your repo has no activity for 60 days, Actions are auto-disabled — just re-enable

## Privacy note
Your calendar ICS URLs contain unique tokens. Treat them like passwords — that's why they're stored as GitHub Secrets (encrypted, never visible in logs).
