"""Constants for the IntuiTherm integration."""
from typing import Final
import json
from pathlib import Path

# Integration domain
DOMAIN: Final = "intuitherm"

# Version - read from manifest.json
def _get_version() -> str:
    """Read version from manifest.json."""
    try:
        manifest_path = Path(__file__).parent / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)
            return manifest.get("version", "unknown")
    except Exception:
        return "unknown"

VERSION = _get_version()

# Platforms
PLATFORMS: Final = ["sensor", "switch"]

# Configuration keys
CONF_SERVICE_URL: Final = "service_url"
CONF_API_KEY: Final = "api_key"
CONF_UPDATE_INTERVAL: Final = "update_interval"
CONF_INSTANCE_ID: Final = "instance_id"
CONF_USER_ID: Final = "user_id"
CONF_REGISTERED_AT: Final = "registered_at"
CONF_USER_EMAIL: Final = "user_email"  # Optional user email for communications
CONF_MARKETING_CONSENT: Final = "marketing_consent"  # User consent for product updates
CONF_SAVINGS_REPORT_CONSENT: Final = "savings_report_consent"  # User consent for monthly savings reports

# Auto-detected entity configuration keys
CONF_DETECTED_ENTITIES: Final = "detected_entities"
CONF_BATTERY_SOC_ENTITY: Final = "battery_soc_entity"
CONF_SOLAR_POWER_ENTITY: Final = "solar_power_entity"
CONF_HOUSE_LOAD_ENTITY: Final = "house_load_entity"

# Multi-sensor configuration (lists)
CONF_SOLAR_SENSORS: Final = "solar_sensors"  # List of solar production sensors
CONF_BATTERY_DISCHARGE_SENSORS: Final = "battery_discharge_sensors"  # List of battery discharge sensors
CONF_BATTERY_CHARGE_SENSORS: Final = "battery_charge_sensors"  # List of battery charge sensors
CONF_GRID_IMPORT_SENSORS: Final = "grid_import_sensors"  # List of grid import sensors
CONF_GRID_EXPORT_SENSORS: Final = "grid_export_sensors"  # List of grid export sensors

# Battery control entities
# Battery control configuration
CONF_BATTERY_MODE_SELECT: Final = "battery_mode_select"  # Battery work mode select entity
CONF_BATTERY_CHARGE_POWER: Final = "battery_charge_power"  # Battery charge power number entity  
CONF_BATTERY_DISCHARGE_POWER: Final = "battery_discharge_power"  # Battery discharge power number entity
CONF_SOLAREDGE_COMMAND_MODE: Final = "solaredge_command_mode"  # SolarEdge command mode select

# Battery control modes (standardized across inverters)
BATTERY_MODE_SELF_USE: Final = "self_use"
BATTERY_MODE_BACKUP: Final = "backup"
BATTERY_MODE_FORCE_CHARGE: Final = "force_charge"

# Battery mode display names
BATTERY_MODE_NAMES: Final = {
    BATTERY_MODE_SELF_USE: "Self Use",
    BATTERY_MODE_BACKUP: "Backup",
    BATTERY_MODE_FORCE_CHARGE: "Force Charge",
}

# Battery mode mapping configuration keys (map our standard modes to device-specific values)
CONF_MODE_SELF_USE: Final = "mode_self_use"  # Device's "self use" mode value
CONF_MODE_BACKUP: Final = "mode_backup"  # Device's "backup" mode value
CONF_MODE_FORCE_CHARGE: Final = "mode_force_charge"  # Device's "force charge" mode value

# Battery specifications
CONF_BATTERY_CAPACITY: Final = "battery_capacity_kwh"  # Battery capacity in kWh
CONF_BATTERY_MAX_POWER: Final = "battery_max_power_kw"  # Battery max charge/discharge power in kW
CONF_BATTERY_CHARGE_MAX_POWER: Final = "battery_charge_max_power_kw"  # Max charging power in kW

# House load configuration
CONF_HOUSE_LOAD_CALC_MODE: Final = "house_load_calc_mode"  # "auto" or "manual"

# Pricing configuration
CONF_EPEX_MARKUP: Final = "epex_markup"  # Additional cost on top of EPEX day-ahead price (€/kWh)
CONF_GRID_EXPORT_PRICE: Final = "grid_export_price"  # Feed-in tariff (€/kWh)

# Control mode configuration
CONF_DRY_RUN_MODE: Final = "dry_run_mode"  # Test mode - MPC runs but doesn't send battery commands

# Default values
DEFAULT_SERVICE_URL: Final = "https://api.intuihems.de"
DEFAULT_UPDATE_INTERVAL: Final = 900  # seconds (15 minutes)
# Battery executor triggers on-demand refresh before each control execution
DEFAULT_BATTERY_CAPACITY: Final = 10.0  # kWh
DEFAULT_BATTERY_MAX_POWER: Final = 3.0  # kW
DEFAULT_BATTERY_CHARGE_MAX_POWER: Final = 3.0  # kW
DEFAULT_EPEX_MARKUP: Final = 0.10  # €0.10/kWh markup
DEFAULT_GRID_EXPORT_PRICE: Final = 0.08  # €0.08/kWh feed-in tariff

# Service endpoints
ENDPOINT_AUTH_STATUS: Final = "/api/v1/auth/status"
ENDPOINT_AUTH_REGISTER: Final = "/api/v1/auth/register"
ENDPOINT_HEALTH: Final = "/api/v1/health"
ENDPOINT_INFO: Final = "/api/v1/info"
ENDPOINT_CONTROL_STATUS: Final = "/api/v1/control/status"
ENDPOINT_CONTROL_OVERRIDE: Final = "/api/v1/control/override"
ENDPOINT_CONTROL_ENABLE: Final = "/api/v1/control/enable"
ENDPOINT_CONTROL_DISABLE: Final = "/api/v1/control/disable"
ENDPOINT_METRICS: Final = "/api/v1/metrics"
ENDPOINT_SENSORS: Final = "/api/v1/sensors"
ENDPOINT_SENSOR_READINGS: Final = "/api/v1/sensors/{sensor_id}/readings"
ENDPOINT_UPDATE_CONFIG: Final = "/api/v1/config"

# Service names
SERVICE_MANUAL_OVERRIDE: Final = "manual_override"
SERVICE_ENABLE_AUTO: Final = "enable_automatic_control"
SERVICE_DISABLE_AUTO: Final = "disable_automatic_control"

# Coordinator data keys
DATA_COORDINATOR: Final = "coordinator"
DATA_BATTERY_CONTROL: Final = "battery_control"
DATA_UNSUB: Final = "unsub"

# Sensor types
SENSOR_TYPE_SERVICE_HEALTH: Final = "service_health"
SENSOR_TYPE_OPTIMIZATION_STATUS: Final = "optimization_status"
SENSOR_TYPE_CONTROL_MODE: Final = "control_mode"
SENSOR_TYPE_MPC_SUCCESS_RATE: Final = "mpc_success_rate"
SENSOR_TYPE_MPC_SOLVE_TIME: Final = "mpc_solve_time"
SENSOR_TYPE_DRY_RUN_MODE: Final = "dry_run_mode"

# Switch types
SWITCH_TYPE_AUTO_CONTROL: Final = "automatic_control"
SWITCH_TYPE_DEMO_MODE: Final = "demo_mode"

# SolarEdge Command Mode
SOLAREDGE_COMMAND_MODE_MAXIMIZE_SELF_CONSUMPTION: Final = "Maximize Self Consumption"
SOLAREDGE_COMMAND_MODE_CHARGE_FROM_SOLAR_POWER_AND_GRID: Final = "Charge from Solar Power and Grid"

# Device-based control entity mappings
# Maps (platform, manufacturer, model_pattern) -> control entity patterns
DEVICE_CONTROL_MAPPINGS: Final = {
    # FoxESS inverters
    ("foxess", "FoxESS", None): {
        "mode_select_patterns": ["work_mode", "battery_mode"],
        "charge_power_patterns": ["force_charge_power", "charge_power"],
        "discharge_power_patterns": ["force_discharge_power", "discharge_power"],
        "mode_options": ["Force Charge", "Self Use", "Back-up"],
    },
    # Solis inverters (similar to FoxESS)
    ("solis", "Solis", None): {
        "mode_select_patterns": ["work_mode", "battery_mode", "operating_mode"],
        "charge_power_patterns": ["charge_power", "battery_charge_limit"],
        "discharge_power_patterns": ["discharge_power", "battery_discharge_limit"],
    },
    # SolarEdge StorEdge systems
    ("solaredge", "SolarEdge", "StorEdge"): {
        "mode_select_patterns": ["storage_control_mode", "battery_mode"],
        "charge_power_patterns": ["storage_charge_limit"],
        "discharge_power_patterns": ["storage_discharge_limit"],
        "command_mode_patterns": ["storage_command_mode"],
    },
    # Huawei FusionSolar
    ("huawei_solar", "Huawei", None): {
        "mode_select_patterns": ["storage_working_mode", "battery_working_mode", "betriebsmodus"],
        "charge_power_patterns": ["storage_maximum_charging_power", "ladeleistung"],
        "discharge_power_patterns": ["storage_maximum_discharging_power", "entladeleistung"],
        "grid_charge_switch_patterns": ["laden_aus_dem_netz", "charge_from_grid"],
        "device_id_patterns": [""],  # Huawei device ID for service calls
    },
    # Growatt systems
    ("growatt_server", "Growatt", None): {
        "mode_select_patterns": ["work_mode", "battery_mode"],
        "charge_power_patterns": ["battery_charge_rate"],
        "discharge_power_patterns": ["battery_discharge_rate"],
    },
}

# Attributes
ATTR_ACTION: Final = "action"
ATTR_POWER_KW: Final = "power_kw"
ATTR_DURATION_MINUTES: Final = "duration_minutes"
ATTR_MODE: Final = "mode"
ATTR_REASON: Final = "reason"
ATTR_NEXT_REVIEW: Final = "next_review_at"
ATTR_LAST_MPC_RUN: Final = "last_mpc_run"
ATTR_MPC_STATUS: Final = "mpc_status"
ATTR_DATABASE_STATUS: Final = "database_status"
