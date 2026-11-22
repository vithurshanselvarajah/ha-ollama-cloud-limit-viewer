# Ollama Cloud Usage

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

A Home Assistant custom integration that shows your [ollama.com](https://ollama.com) cloud usage as sensors — remaining quota per window, request counts, the model that used the most, when each window resets, and how much credit you have left.

The integration talks to Ollama's official cloud API using an API key — no browser cookie scraping.

## API endpoints

| Endpoint | Purpose |
|---|---|
| `GET https://ollama.com/api/usage?range=30d&group_by=model` | Request counts, cost and token usage, bucketed by hour or day |
| `GET https://ollama.com/api/balance` | Remaining included quota, purchased credits and reset times |

Both endpoints allow **10 requests per minute per user**, shared across API keys and devices. The integration polls every 120 seconds by default and issues one request per endpoint per poll, which stays comfortably inside the limit. A `429` response is honoured via the `Retry-After` header.

## Plan types

Ollama serves two different plan shapes, and the integration supports both.

### Legacy plans (session + weekly limits)

```json
{
  "included": {
    "session": {"remaining_percent": 78.5, "resets_at": "2026-11-23T00:00:00Z"},
    "weekly": {"remaining_percent": 71.2, "resets_at": "2026-11-23T00:00:00Z"}
  },
  "purchased": {"balance_usd": 0}
}
```

Legacy plans are limited by request count rather than by spend. Ollama does not report cost or token usage for them, so the **spend** sensors are not created and the **remaining** sensors are the ones to watch.

### Credit plans (monthly USD allowance)

```json
{
  "included": {
    "balance_usd": 72.5,
    "allowance_usd": 100,
    "period": {"from": "2026-09-15T09:30:00Z", "until": "2026-10-15T09:30:00Z"}
  },
  "purchased": {"balance_usd": 25}
}
```

Credit plans report a monthly allowance. The **session** and **weekly** windows do not exist, so those sensors are not created and the **balance** sensors are the ones to watch.

Sensors that do not apply to your plan are simply never created — you will not see empty placeholders for them. The **spend** sensors are only created when Ollama actually reports cost, which on legacy plans it does not.

## Sensors

### Usage windows

| Sensor | Unit | Description |
|---|---|---|
| `session_requests` | — | Requests in the current session window |
| `session_spend` | `USD` | Cost in the current session window |
| `session_remaining` | `%` | Session quota remaining |
| `session_top_model` | — | Model with the most requests in the session |
| `session_models` | — | Every model and its request count in the session |
| `session_period_start` | — | Session window start (timestamp) |
| `session_period_end` | — | When the session resets (timestamp) |
| `session_time_remaining` | `s` | Seconds until the session resets |
| `weekly_requests` | — | Requests in the current weekly window |
| `weekly_spend` | `USD` | Cost in the current weekly window |
| `weekly_remaining` | `%` | Weekly quota remaining |
| `weekly_top_model` | — | Model with the most requests in the week |
| `weekly_models` | — | Every model and its request count in the week |
| `weekly_period_start` | — | Weekly window start (timestamp) |
| `weekly_period_end` | — | When the weekly quota resets (timestamp) |
| `weekly_time_remaining` | `s` | Seconds until the weekly quota resets |
| `last_4_weeks_requests` | — | Requests in the last 4 weeks |
| `last_4_weeks_spend` | `USD` | Cost in the last 4 weeks |
| `last_4_weeks_top_model` | — | Model with the most requests in the last 4 weeks |
| `last_4_weeks_models` | — | Every model and its request count in the last 4 weeks |
| `last_4_weeks_period_start` | — | Start of the 4 week window (timestamp) |
| `last_4_weeks_period_end` | — | End of the 4 week window (timestamp) |

The `last_4_weeks_*` window is always available. The `session_*` and `weekly_*` windows depend on your plan.

### Balance

| Sensor | Unit | Description |
|---|---|---|
| `included_balance` | `USD` | Included credit left this period |
| `included_allowance` | `USD` | Total included credit for the period |
| `purchased_balance` | `USD` | Remaining purchased credits |
| `included_period_start` | — | Start of the included period (timestamp) |
| `included_period_end` | — | End of the included period (timestamp) |
| `included_time_remaining` | `s` | Seconds until the included period ends |

`purchased_balance` is available on every plan. The other balance sensors need a credit plan.

### How the windows are derived

The usage API returns buckets, not named windows, so the integration derives each window from the reset times the balance API reports:

- **Session** — the window ending at `included.session.resets_at`.
- **Weekly** — the window ending at `included.weekly.resets_at`.
- **Last 4 weeks** — the 28 days ending at the current time.

Because the reset times come straight from Ollama, no local reset prediction is needed and there is nothing to re-anchor.

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots menu → **Custom repositories**
3. Add `https://github.com/vithurshanselvarajah/ha-ollama-cloud-limit-viewer` as an **Integration**
4. Search for "Ollama Cloud Usage" and install
5. Restart Home Assistant

### Manual

1. Copy the `custom_components/ollama_cloud_usage` folder into your Home Assistant `custom_components` directory
2. Restart Home Assistant

## Setup

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **Ollama Cloud Usage**
3. Enter:
   - **Account Name**: A friendly label (e.g. "Main", "Work")
   - **API Key**: An ollama.com API key (see below)
   - **Update Interval**: How often to check (default: 120 seconds / 2 minutes)

The update interval can also be changed later through the integration's **Configure** button, without removing and re-adding the entry.

### Getting an API key

1. Log in to [ollama.com](https://ollama.com)
2. Open **Settings → API Keys**
3. Click **Create API Key** (or equivalent), give it a name, copy the value
4. Paste it into the setup form

## API key revoked?

When an API key is rejected (HTTP 401/403), the sensors become **unavailable** and Home Assistant starts a re-authentication flow asking for a new key. Enter the new key and the entry reloads itself — you do not need to delete and re-add the integration.

## Multi-Account

You can add multiple ollama.com accounts. Each creates its own device with its own set of sensors. Just run the "Add Integration" flow again with a different account name and API key.

## Migration from v2

Version 3.0 replaces the retired `/api/usage` response shape with Ollama's current `/api/usage` and `/api/balance` endpoints.

- The `session_spend`, `weekly_spend` and `last_4_weeks_spend` sensors keep their names, but on legacy plans Ollama no longer reports cost, so they are not created there.
- The `session_period_*` and `weekly_period_*` sensors now report the real reset times from the balance API instead of locally predicted ones.
- New sensors for the remaining quota, credit balances and purchased credits have been added.

## License

GPL-v3.0
