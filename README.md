# Ollama Cloud Usage

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

A Home Assistant custom integration that shows your [ollama.com](https://ollama.com) cloud usage as sensors — **session, weekly, and monthly (included usage)** limits, how much is remaining, and when they reset.

Ollama doesn't expose an API for this data, so the integration signs in with your browser cookie, fetches the server-rendered settings page, and parses the usage meters out of the HTML.

> **Note:** Ollama is rolling out a new fixed monthly usage model. The integration detects which model your account uses on every refresh and exposes the appropriate sensors automatically. Both models are supported simultaneously — nothing for you to do.

## Sensors

Each configured account exposes the sensors for **one** of the two usage models below. Ollama's transition from the legacy model to the new monthly model is **one-way**, so once your account moves to the new model the six legacy sensors are **removed from Home Assistant** (not hidden). Make a note of any automations that reference them before the flip.

### Legacy model (session + weekly)

| Sensor | Example Value | Unit | Description |
|---|---|---|---|
| Session Usage | `45.8` | `%` | Current session usage percentage |
| Session Remaining | `54.2` | `%` | How much session allowance is left |
| Session Resets In | `4 hours` | — | Time until session usage resets |
| Weekly Usage | `80.9` | `%` | Current weekly usage percentage |
| Weekly Remaining | `19.1` | `%` | How much weekly allowance is left |
| Weekly Resets In | `3 days` | — | Time until weekly usage resets |

### New model (monthly, included usage)

| Sensor | Example Value | Unit | Description |
|---|---|---|---|
| Monthly Usage | `44.3` | `%` | Current monthly (included) usage percentage |
| Monthly Remaining | `55.7` | `%` | How much monthly allowance is left |
| Monthly Resets In | `3 weeks` | — | Time until monthly usage resets |
| Monthly Resets At | `2026-10-01T21:51:07+00:00` | — | Exact reset datetime (ISO 8601, UTC) |
| Plan Tier | `free` | — | Your plan tier (e.g. `free`, `pro`, `plus`) |

### Shared

| Sensor | Example Value | Unit | Description |
|---|---|---|---|
| Model Info | `gemma4:31b, 331 requests` | — | Models used and request counts |

### Which model is my account on?

- **Legacy (session + weekly):** if you have two separate `data-usage-meter` blocks labelled "Session usage" and "Weekly usage".
- **New (monthly):** if you have a single "Included usage" section with one meter labelled e.g. "Free usage" / "Pro usage" / "Plus usage".

The integration decides automatically. There's nothing to configure.

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
   - **Cookie String**: Your ollama.com browser cookie (see below)
   - **Update Interval**: How often to check (default: 120 seconds / 2 minutes)

### Getting your cookie

1. Log in to [ollama.com](https://ollama.com) in your browser
2. Open **DevTools** (F12) → **Network** tab
3. Reload the page
4. Click the first document request (`settings` or `ollama.com`)
5. Under **Request Headers**, find the `Cookie:` line
6. Copy the **entire value** and paste it into the setup form

> **Tip**: Cookies usually last weeks to months. When one expires, the sensors will become unavailable. Use the integration's **Reconfigure** option to paste a fresh cookie — no need to delete and re-add the account.

## Cookie Expired?

When a cookie expires, the sensors will show as **unavailable** in Home Assistant.

To fix:
1. Go to **Settings → Devices & Services**
2. Find your Ollama Cloud Usage entry
3. Click the three dots menu → **Reconfigure**
4. Paste your fresh cookie string

## Multi-Account

You can add multiple ollama.com accounts. Each creates its own device with its own set of sensors. Just run the "Add Integration" flow again with a different account name and cookie.

## Migration from older versions

If you're upgrading from a version that only supported the legacy session/weekly model, your existing entities keep their IDs and history until Ollama transitions your account. The integration detects the new model on every refresh:

- **Legacy account → still legacy:** no change. Legacy sensors continue to work.
- **Legacy account → transitioned to monthly:** the six legacy sensors (`session_*`, `weekly_*`) are removed from your entity registry on the next refresh. New `monthly_*` and `tier` sensors are added automatically.

> ⚠️ The transition is **one-way**. If you have automations or dashboards that reference `sensor.session_usage` etc., update them to use `sensor.monthly_usage` once your account moves over — the legacy entity IDs will be deleted and HA will not recreate them.

## License

GPL-v3.0