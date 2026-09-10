DOMAIN = "ollama_cloud_usage"

CONF_COOKIE = "cookie"
CONF_ACCOUNT_NAME = "account_name"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_USAGE_MODE = "usage_mode"

DEFAULT_SCAN_INTERVAL = 120

# Persisted usage mode on the config entry. "legacy" = session + weekly
# meters; "monthly" = the new single fixed-monthly limit. Once we observe
# "monthly" for an entry, we never revert — Ollama's transition is one-way.
USAGE_MODE_LEGACY = "legacy"
USAGE_MODE_MONTHLY = "monthly"

# Sensor unique-id keys (suffixed onto the config entry id) for the legacy
# model. These are removed from the entity registry once the entry transitions
# to the new model. Keep in sync with SENSOR_DESCRIPTIONS in sensor.py.
LEGACY_SENSOR_KEYS: tuple[str, ...] = (
    "session_usage",
    "session_remaining",
    "session_resets_in",
    "weekly_usage",
    "weekly_remaining",
    "weekly_resets_in",
)

SETTINGS_URL = "https://ollama.com/settings"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
