# Ollama Cloud Usage

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

A Home Assistant custom integration that shows your [ollama.com](https://ollama.com) cloud usage as sensors — money spent per window, request counts, the model that used the most, and when each window resets.

The integration talks to Ollama's API (`GET /api/usage`) using an API key — no browser cookie scraping.

## Sensors

Each configured account exposes the sensors for every usage window that the API returns. The API exposes up to three windows:

- **`session`** — the current in-flight session window
- **`weekly`** — the rolling weekly window
- **`activity` (last 4 weeks)** — the activity window reported under `activity` in the response

A window that is absent from the API response simply produces no sensors.

### Per-window sensors

For each window that exists (e.g. `session_*`, `weekly_*`, `last_4_weeks_*`):

| Sensor | Example Value | Unit | Description |
|---|---|---|---|
| Spend | `0.02500` | `USD` | Money spent in this window (cumulative) |
| Requests | `180` | — | Total requests in this window |
| Top Model | `minimax-m3` | — | The model with the most requests in this window |
| Models | `minimax-m3 (176), gemma4:31b (4)` | — | Every model and its request count |
| Period Start | `2026-09-14T00:00:00+00:00` | — | Window start (ISO 8601, UTC) |
| Period End | `2026-09-14T21:52:52+00:00` | — | Window end (ISO 8601, UTC) |
| Time Remaining | `0` | `s` | Seconds until the window ends |

### When does `Period Start` / `Period End` show up?

The Ollama API only reports reset boundaries for the `last_4_weeks` (activity) window. For `session` and `weekly`, the integration **predicts** the resets locally and shows them in those sensors:

- **Session** resets on fixed 5-hour UTC buckets: `00:00`, `05:00`, `10:00`, `15:00`, `20:00`.
- **Weekly** resets every **Monday at 00:00 UTC**.

The integration doesn't start predicting until it has actually observed a real reset for that window — the first time the API reports `usage` dropping by more than 50% from the previous sample, it snaps to the current bucket as the anchor. Until that happens, the four `session_*_period_*` / `weekly_*_period_*` sensors stay **unknown**. This avoids showing a fake "next reset at 5 PM" that has nothing to do with when Ollama actually resets your session.

Once anchored, the watchdog keeps verifying on every refresh — if Ollama moves the bucket (say they shift session buckets from 5h to 6h), the next observed reset just re-anchors to the new boundary and the predictions update automatically.

### Example API response

```json
{
  "activity": {
    "cost": "0.00000",
    "period": {
      "type": "last_4_weeks",
      "starting_at": "2026-08-24T00:00:00Z",
      "ending_at": "2026-09-14T21:52:52.558286586Z"
    },
    "models": []
  },
  "limits": {
    "session": {
      "usage": 0.001,
      "models": [
        {"name": "minimax-m3", "request_count": 1},
        {"name": "gemma4:31b", "request_count": 2}
      ]
    },
    "weekly": {
      "usage": 0.025,
      "models": [
        {"name": "minimax-m3", "request_count": 176},
        {"name": "gemma4:31b", "request_count": 4}
      ]
    }
  }
}
```

→ produces `session_spend = 0.001 USD`, `weekly_spend = 0.025 USD`, `last_4_weeks_spend = 0.0 USD`, and per-window model breakdowns.

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

### Getting an API key

1. Log in to [ollama.com](https://ollama.com)
2. Open **Settings → API Keys**
3. Click **Create API Key** (or equivalent), give it a name, copy the value
4. Paste it into the setup form

> **Tip:** API keys don't expire the way browser cookies do, but you can revoke them from the same page at any time. If you revoke a key, the sensors will become **unavailable** — delete the existing entry and re-add the integration with a new key.

## API key revoked?

When an API key is rejected (HTTP 401/403), the sensors will show as **unavailable** in Home Assistant and the entry will be marked for re-auth.

To fix:

1. Generate a fresh API key on ollama.com
2. Delete the existing Ollama Cloud Usage entry from **Settings → Devices & Services**
3. Re-add the integration with the new key

## Multi-Account

You can add multiple ollama.com accounts. Each creates its own device with its own set of sensors. Just run the "Add Integration" flow again with a different account name and API key.

## Migration from v1 (cookie auth)

Version 2.0 is a clean break from v1.x. The old integration scraped the settings page using your browser cookie; v2 uses Ollama's official API.

- v1 entries are **not** auto-migrated. Delete any v1 entries and add a fresh integration with your API key.
- v1 sensor entity IDs (`sensor.session_usage`, etc.) no longer exist — rewrite any automations or dashboards to use the new sensor IDs.

## License

GPL-v3.0