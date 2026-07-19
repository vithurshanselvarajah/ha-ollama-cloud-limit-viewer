# Ollama Cloud Usage

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

A Home Assistant custom integration that shows your [ollama.com](https://ollama.com) cloud usage as sensors — **session and weekly limits**, how much is remaining, and when they reset.

Ollama doesn't expose an API for this data, so the integration signs in with your browser cookie, fetches the server-rendered settings page, and parses the usage meters out of the HTML.

## Sensors

Each configured account creates the following sensors:

| Sensor | Example Value | Unit | Description |
|---|---|---|---|
| Session Usage | `45.8` | `%` | Current session usage percentage |
| Session Remaining | `54.2` | `%` | How much session allowance is left |
| Session Resets In | `4 hours` | — | Time until session usage resets |
| Weekly Usage | `80.9` | `%` | Current weekly usage percentage |
| Weekly Remaining | `19.1` | `%` | How much weekly allowance is left |
| Weekly Resets In | `3 days` | — | Time until weekly usage resets |
| Model Info | `gemma3:27b, 369 requests` | — | Models used and request counts |

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
   - **Update Interval**: How often to check (default: 300 seconds / 5 minutes)

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

## License

GPL-v3.0
