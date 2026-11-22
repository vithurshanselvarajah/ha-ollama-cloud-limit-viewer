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

Legacy plans are limited by request count rather than by spend. Ollama does not report cost or token usage for them, so the **spend**, **token** and **cache** sensors are not created and the **remaining** sensors are the ones to watch.

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

Sensors that do not apply to your plan are simply never created — you will not see empty placeholders for them. The **spend**, **token** and **cache** sensors are only created when Ollama actually reports those values, which on legacy plans it does not.

The sensor set follows your plan, so a plan change is picked up on the next poll with no reconfiguration needed. If a legacy account is upgraded to a credit plan, the balance and token sensors appear and the legacy-only sensors are removed. If you downgrade the other way, the reverse happens. Sensors that exist in both plans keep their entity IDs, so dashboards and automations survive the change.

## Sensors

### Usage windows

| Sensor | Entity ID suffix | Unit | Description |
|---|---|---|---|
| Session Requests | `session_requests` | — | Requests in the current session window |
| Session Spend | `session_spend` | `USD` | Cost in the current session window |
| Session Remaining | `session_remaining` | `%` | Session quota remaining |
| Session Top Model | `session_top_model` | — | Model with the most requests in the session |
| Session Models | `session_model_breakdown` | — | Every model and its request count in the session |
| Session Model Spend | `session_model_spend_breakdown` | — | Spend per model, e.g. `gpt-oss:120b (0.01234)` |
| Session Other Model Requests | `session_other_model_requests` | — | Requests from models outside the reported group list |
| Session Input Tokens | `session_input_tokens` | — | Input tokens, cached ones included |
| Session Cached Input Tokens | `session_cached_input_tokens` | — | Input tokens served from the prompt cache |
| Session Output Tokens | `session_output_tokens` | — | Output tokens |
| Session Cache Hit Ratio | `session_cache_hit_ratio` | `%` | Share of input tokens served from cache |
| Session Period Start | `session_period_start` | — | Session window start (timestamp) |
| Session Period End | `session_period_end` | — | When the session resets (timestamp) |
| Session Time Remaining | `session_period_remaining` | `s` | Seconds until the session resets |
| Weekly Requests | `weekly_requests` | — | Requests in the current weekly window |
| Weekly Spend | `weekly_spend` | `USD` | Cost in the current weekly window |
| Weekly Remaining | `weekly_remaining` | `%` | Weekly quota remaining |
| Weekly Top Model | `weekly_top_model` | — | Model with the most requests in the week |
| Weekly Models | `weekly_model_breakdown` | — | Every model and its request count in the week |
| Weekly Model Spend | `weekly_model_spend_breakdown` | — | Spend per model |
| Weekly Other Model Requests | `weekly_other_model_requests` | — | Requests from models outside the reported group list |
| Weekly Input Tokens | `weekly_input_tokens` | — | Input tokens, cached ones included |
| Weekly Cached Input Tokens | `weekly_cached_input_tokens` | — | Input tokens served from the prompt cache |
| Weekly Output Tokens | `weekly_output_tokens` | — | Output tokens |
| Weekly Cache Hit Ratio | `weekly_cache_hit_ratio` | `%` | Share of input tokens served from cache |
| Weekly Period Start | `weekly_period_start` | — | Weekly window start (timestamp) |
| Weekly Period End | `weekly_period_end` | — | When the weekly quota resets (timestamp) |
| Weekly Time Remaining | `weekly_period_remaining` | `s` | Seconds until the weekly quota resets |
| Last 4 Weeks Requests | `last_4_weeks_requests` | — | Requests in the last 4 weeks |
| Last 4 Weeks Spend | `last_4_weeks_spend` | `USD` | Cost in the last 4 weeks |
| Last 4 Weeks Top Model | `last_4_weeks_top_model` | — | Model with the most requests in the last 4 weeks |
| Last 4 Weeks Models | `last_4_weeks_model_breakdown` | — | Every model and its request count in the last 4 weeks |
| Last 4 Weeks Model Spend | `last_4_weeks_model_spend_breakdown` | — | Spend per model |
| Last 4 Weeks Other Model Requests | `last_4_weeks_other_model_requests` | — | Requests from models outside the reported group list |
| Last 4 Weeks Input Tokens | `last_4_weeks_input_tokens` | — | Input tokens, cached ones included |
| Last 4 Weeks Cached Input Tokens | `last_4_weeks_cached_input_tokens` | — | Input tokens served from the prompt cache |
| Last 4 Weeks Output Tokens | `last_4_weeks_output_tokens` | — | Output tokens |
| Last 4 Weeks Cache Hit Ratio | `last_4_weeks_cache_hit_ratio` | `%` | Share of input tokens served from cache |
| Last 4 Weeks Period Start | `last_4_weeks_period_start` | — | Start of the 4 week window (timestamp) |
| Last 4 Weeks Period End | `last_4_weeks_period_end` | — | End of the 4 week window (timestamp) |

The `last_4_weeks_*` window is always available. The `session_*` and `weekly_*` windows depend on your plan.

Ollama caps the per-model breakdown at ten models and folds the rest into a remainder, so `*_other_model_requests` reports those additional requests rather than dropping them.

### Team scope

Team admins can report usage for the whole team instead of just their own API key. Set **Usage Scope** to `team` in the integration options. If the key belongs to a non-admin, ollama.com returns `403` and the integration falls back to personal scope with a warning in the log.

### Balance

| Sensor | Entity ID suffix | Unit | Description |
|---|---|---|---|
| Included Balance | `included_balance` | `USD` | Included credit left this period |
| Included Allowance | `included_allowance` | `USD` | Total included credit for the period |
| Purchased Balance | `purchased_balance` | `USD` | Remaining purchased credits |
| Included Period Start | `included_period_start` | — | Start of the included period (timestamp) |
| Included Period End | `included_period_end` | — | End of the included period (timestamp) |
| Included Time Remaining | `included_period_remaining` | `s` | Seconds until the included period ends |

`purchased_balance` is available on every plan. The other balance sensors need a credit plan.

Entity IDs are prefixed with the device name, for example `sensor.ollama_main_session_requests` for an account named "Main".

### How the windows are derived

The usage API returns buckets, not named windows, so the integration derives each window from the reset times the balance API reports:

- **Session** — the 7 hours ending at `included.session.resets_at`.
- **Weekly** — the 7 days ending at `included.weekly.resets_at`.
- **Last 4 weeks** — the 28 days ending at the current time.

Because the reset times come straight from Ollama, no local reset prediction is needed and there is nothing to re-anchor.

## Data updates

The integration polls ollama.com every 120 seconds by default. Each poll makes three requests: one to the balance endpoint and two to the usage endpoint, for the 30 day and 24 hour ranges. Ollama allows 10 requests per minute per user, shared across API keys and devices, so the default interval leaves plenty of headroom.

The update interval can be changed in the integration options. Lowering it below 60 seconds risks hitting the rate limit, in which case the integration honours the `Retry-After` header and retries later.

When ollama.com cannot be reached, the sensors become unavailable and a warning is logged. When the connection comes back, that is logged too, so the log shows exactly one message per outage rather than one per poll.

## Troubleshooting

### The sensors are unavailable

Check the Home Assistant log for the reason. The usual causes are:

- **The API key was rejected.** ollama.com answered with 401. The integration starts a re-authentication flow asking for a new key.
- **The account is suspended.** ollama.com answered with 403.
- **The rate limit was hit.** ollama.com allows 10 requests per minute per user. If other tools use the same API key, or the update interval is very short, the limit can be reached. The integration waits as long as the `Retry-After` header asks.

### Usage looks stale

The ollama.com usage API is not always immediate. Requests can take a while to appear in the reported totals.

### A window is missing

The sensor set follows your plan. On a legacy plan there is no `included_balance`, because legacy plans have no monthly credit allowance. On a credit plan there is no `session_remaining` or `weekly_remaining`, because credit plans have no session or weekly limit. See [Plan types](#plan-types).

### Diagnostics

For a bug report, download the diagnostics from **Settings → Devices & Services → Ollama Cloud Usage → ⋮ → Download diagnostics**. The API key is redacted, and the file contains the configuration and the last usage data.

## Known limitations

- Legacy plans report request counts only. Ollama does not provide cost or token usage for them, so the spend, token and cache sensors do not exist on legacy plans.
- Ollama caps the per-model breakdown at ten models and folds the rest into a remainder. The `*_other_model_requests` sensor reports those additional requests.
- The session window is seven hours. Ollama does not document the length of the session limit, so it was derived from the reported usage.
- Team scope needs a team admin API key. Other keys fall back to personal scope, and a repair issue appears under **Settings → System → Repairs**.
- The reported usage is what ollama.com records, which can lag behind the actual requests.

## Use cases

- **Watch your remaining quota.** The `session_remaining` and `weekly_remaining` sensors show how much of the limit is left, so a dashboard can show a warning when it runs low.
- **Track what you spend.** On a credit plan, `included_balance` and `included_allowance` show how much of the monthly allowance is used.
- **Find your most used model.** The `*_top_model` and `*_model_breakdown` sensors show which models you use and how much of the spend each accounts for.
- **Improve prompt caching.** `*_cache_hit_ratio` shows how much of your input was served from the prompt cache. A low ratio usually means prompts are not shared between requests.
- **Automate a warning.** Notify yourself when the session quota drops below a threshold, or when the included balance runs low.

## Automation examples

Warn when the weekly quota runs low:

```yaml
automation:
  - alias: "Ollama weekly quota low"
    triggers:
      - trigger: numeric_state
        entity_id: sensor.ollama_main_weekly_remaining
        below: 20
    actions:
      - action: notify.persistent_notification
        data:
          message: "Ollama weekly quota is down to {{ states('sensor.ollama_main_weekly_remaining') }}%."
```

Notify when the included credit is nearly used up:

```yaml
automation:
  - alias: "Ollama credit running out"
    triggers:
      - trigger: numeric_state
        entity_id: sensor.ollama_main_included_balance
        below: 10
    actions:
      - action: notify.persistent_notification
        data:
          message: "Only ${{ states('sensor.ollama_main_included_balance') }} of included credit left."
```

Log when a session window resets:

```yaml
automation:
  - alias: "Ollama session reset"
    triggers:
      - trigger: state
        entity_id: sensor.ollama_main_session_time_remaining
        to: 0
    actions:
      - action: notify.persistent_notification
        data:
          message: "The Ollama session window reset."
```

## Removing the integration

Go to **Settings → Devices & Services**, find the Ollama Cloud Usage entry, open the **⋮** menu and choose **Delete**. This removes the config entry and all of its entities from Home Assistant.

The API key itself is not revoked by this. To remove it, open **Settings → API Keys** on ollama.com and delete the key.

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
   - **Usage Scope**: `self` for your own usage, `team` for the whole team (team admins only)

The update interval and scope can also be changed later through the integration's **Configure** button, without removing and re-adding the entry.

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

## Migration from v3.0

Version 3.1 adds the token, cache and per-model cost sensors, plus the team scope option.

- All new sensors only appear when Ollama actually reports the underlying values, so legacy accounts see no change.
- Existing sensors are untouched.

## Migration from v3.1

Version 3.2 reorganises the integration and adds diagnostics.

- The diagnostic entities are now disabled by default. Enable the ones you want under the entity settings of the device.
- The entity IDs of the entities that were already enabled do not change.
- The integration now provides diagnostics, downloadable from the device page.

## License

GPL-v3.0
