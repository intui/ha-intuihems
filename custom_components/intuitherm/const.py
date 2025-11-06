"""Constants for the IntuiTherm integration."""
from typing import Final

# Integration domain
DOMAIN: Final = "intuitherm"

# Version
VERSION: Final = "2025.11.4.2"

# Platforms
PLATFORMS: Final = ["sensor", "switch"]

# Configuration keys
CONF_SERVICE_URL: Final = "service_url"
CONF_API_KEY: Final = "api_key"
CONF_UPDATE_INTERVAL: Final = "update_interval"

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
CONF_BATTERY_MODE_SELECT: Final = "battery_mode_select"  # Battery work mode select entity
CONF_BATTERY_CHARGE_POWER: Final = "battery_charge_power"  # Battery charge power number entity  
CONF_BATTERY_DISCHARGE_POWER: Final = "battery_discharge_power"  # Battery discharge power number entity

# House load configuration
CONF_HOUSE_LOAD_CALC_MODE: Final = "house_load_calc_mode"  # "auto" or "manual"

# Default values
DEFAULT_SERVICE_URL: Final = "http://128.140.44.143:80"
DEFAULT_UPDATE_INTERVAL: Final = 60  # seconds

# Service endpoints
ENDPOINT_HEALTH: Final = "/api/v1/health"
ENDPOINT_INFO: Final = "/api/v1/info"
ENDPOINT_CONTROL_STATUS: Final = "/api/v1/control/status"
ENDPOINT_CONTROL_OVERRIDE: Final = "/api/v1/control/override"
ENDPOINT_CONTROL_ENABLE: Final = "/api/v1/control/enable"
ENDPOINT_CONTROL_DISABLE: Final = "/api/v1/control/disable"
ENDPOINT_METRICS: Final = "/api/v1/metrics"

# Service names
SERVICE_MANUAL_OVERRIDE: Final = "manual_override"
SERVICE_ENABLE_AUTO: Final = "enable_automatic_control"
SERVICE_DISABLE_AUTO: Final = "disable_automatic_control"

# Coordinator data keys
DATA_COORDINATOR: Final = "coordinator"
DATA_UNSUB: Final = "unsub"

# Sensor types
SENSOR_TYPE_SERVICE_HEALTH: Final = "service_health"
SENSOR_TYPE_OPTIMIZATION_STATUS: Final = "optimization_status"
SENSOR_TYPE_CONTROL_MODE: Final = "control_mode"
SENSOR_TYPE_MPC_SUCCESS_RATE: Final = "mpc_success_rate"
SENSOR_TYPE_MPC_SOLVE_TIME: Final = "mpc_solve_time"
SENSOR_TYPE_MPC_RUNS_24H: Final = "mpc_runs_24h"

# Switch types
SWITCH_TYPE_AUTO_CONTROL: Final = "automatic_control"

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
