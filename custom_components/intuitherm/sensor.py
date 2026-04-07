"""Sensor platform for IntuiTherm integration."""
from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    DATA_COORDINATOR,
    SENSOR_TYPE_SERVICE_HEALTH,
    SENSOR_TYPE_OPTIMIZATION_STATUS,
    SENSOR_TYPE_CONTROL_MODE,
    SENSOR_TYPE_MPC_SUCCESS_RATE,
    SENSOR_TYPE_MPC_SOLVE_TIME,
    SENSOR_TYPE_DRY_RUN_MODE,
    SENSOR_TYPE_SAVINGS_TODAY,
    SENSOR_TYPE_PV_SAVINGS_TODAY,
    SENSOR_TYPE_ARBITRAGE_SAVINGS_TODAY,
    CONF_DETECTED_ENTITIES,
    CONF_DRY_RUN_MODE,
    ATTR_MODE,
    ATTR_REASON,
    ATTR_NEXT_REVIEW,
    ATTR_LAST_MPC_RUN,
    ATTR_MPC_STATUS,
    ATTR_DATABASE_STATUS,
)
from .coordinator import IntuiThermCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up IntuiTherm sensors based on a config entry."""
    coordinator: IntuiThermCoordinator = hass.data[DOMAIN][entry.entry_id][
        DATA_COORDINATOR
    ]

    sensors = [
        # Status sensors
        IntuiThermServiceHealthSensor(coordinator, entry),
        IntuiThermOptimizationStatusSensor(coordinator, entry),
        IntuiThermControlModeSensor(coordinator, entry),
        IntuiThermMPCSuccessRateSensor(coordinator, entry),
        IntuiThermMPCSolveTimeSensor(coordinator, entry),
        IntuiThermDryRunModeSensor(coordinator, entry),
        # Forecast sensors
        IntuiThermConsumptionForecastSensor(coordinator, entry),
        IntuiThermSolarForecastSensor(coordinator, entry),
        IntuiThermNextControlSensor(coordinator, entry),
        IntuiThermPredictedCostSensor(coordinator, entry),
        # Savings sensors
        IntuiThermSavingsTodaySensor(coordinator, entry),
        IntuiThermPVSavingsTodaySensor(coordinator, entry),
        IntuiThermArbitrageSavingsTodaySensor(coordinator, entry),
    ]

    async_add_entities(sensors)
    _LOGGER.info("sensors added")


class IntuiThermSensorBase(CoordinatorEntity, SensorEntity):
    """Base class for IntuiTherm sensors."""

    def __init__(
        self,
        coordinator: IntuiThermCoordinator,
        entry: ConfigEntry,
        sensor_type: str,
        name: str,
        icon: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._sensor_type = sensor_type
        self._attr_name = name
        self._attr_icon = icon
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{sensor_type}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Battery Optimizer",
            "manufacturer": "IntuiHEMS",
            "model": "Battery Optimization Service",
            "sw_version": "1.0",
        }


class IntuiThermServiceHealthSensor(IntuiThermSensorBase):
    """Sensor for service health status."""

    def __init__(self, coordinator: IntuiThermCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            SENSOR_TYPE_SERVICE_HEALTH,
            "Service Health",
            "mdi:heart-pulse",
        )

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None

        health_data = self.coordinator.data.get("health") or {}

        if isinstance(health_data, Exception):
            return "unhealthy"

        status = health_data.get("status", "unknown")

        # Map service status to health level
        if status == "healthy":
            return "healthy"
        elif status in ["degraded", "warning"]:
            return "degraded"
        else:
            return "unhealthy"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        if not self.coordinator.data:
            return {}

        health_data = self.coordinator.data.get("health") or {}

        if isinstance(health_data, Exception):
            return {"error": str(health_data)}

        attrs = {
            ATTR_DATABASE_STATUS: health_data.get("database", "unknown"),
            ATTR_MPC_STATUS: health_data.get("mpc_solver", "unknown"),
        }

        # Add timestamp if available
        if "timestamp" in health_data:
            attrs["last_check"] = health_data["timestamp"]

        return attrs


class IntuiThermOptimizationStatusSensor(IntuiThermSensorBase):
    """Sensor for optimization enabled/disabled status."""

    def __init__(self, coordinator: IntuiThermCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            SENSOR_TYPE_OPTIMIZATION_STATUS,
            "Optimization Status",
            "mdi:robot",
        )

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None

        control_data = self.coordinator.data.get("control") if isinstance(self.coordinator.data, dict) else None

        if not control_data or isinstance(control_data, Exception):
            return "unknown"

        return "enabled" if control_data.get("automatic_control_enabled") else "disabled"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        if not self.coordinator.data:
            return {}

        control_data = self.coordinator.data.get("control") if isinstance(self.coordinator.data, dict) else None

        if not control_data or isinstance(control_data, Exception):
            return {"error": str(control_data)}

        attrs = {}

        # Add next review time
        if "next_review_at" in control_data:
            attrs[ATTR_NEXT_REVIEW] = control_data["next_review_at"]

        # Add last MPC run
        if "last_mpc_run_at" in control_data:
            attrs[ATTR_LAST_MPC_RUN] = control_data["last_mpc_run_at"]

        return attrs


class IntuiThermControlModeSensor(IntuiThermSensorBase):
    """Sensor for current battery control mode."""

    def __init__(self, coordinator: IntuiThermCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            SENSOR_TYPE_CONTROL_MODE,
            "Control Mode",
            "mdi:battery-charging",
        )

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None

        control_data = self.coordinator.data.get("control") if isinstance(self.coordinator.data, dict) else None

        if not control_data or isinstance(control_data, Exception):
            return "unknown"

        mode = control_data.get("current_mode", "unknown")

        # Map internal mode names to friendly names
        mode_mapping = {
            "force_charge": "Force Charge",
            "self_use": "Self Use",
            "backup": "Back-up",
            "feedin_priority": "Feed-in Priority",
            "unknown": "Unknown",
        }

        return mode_mapping.get(mode, mode)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        if not self.coordinator.data:
            return {}

        control_data = self.coordinator.data.get("control") if isinstance(self.coordinator.data, dict) else None

        if not control_data or isinstance(control_data, Exception):
            return {"error": str(control_data)}

        attrs = {}

        # Add mode details
        if "current_mode" in control_data:
            attrs[ATTR_MODE] = control_data["current_mode"]

        # Add reason for current mode
        if "mode_reason" in control_data:
            attrs[ATTR_REASON] = control_data["mode_reason"]

        # Add override info if present
        if control_data.get("override_active"):
            attrs["override_active"] = True
            if "override_until" in control_data:
                attrs["override_until"] = control_data["override_until"]

        # Add power setpoint if available
        if "power_setpoint_kw" in control_data:
            attrs["power_setpoint_kw"] = control_data["power_setpoint_kw"]

        return attrs


class IntuiThermMPCSuccessRateSensor(IntuiThermSensorBase):
    """Sensor for MPC success rate percentage."""

    def __init__(self, coordinator: IntuiThermCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            SENSOR_TYPE_MPC_SUCCESS_RATE,
            "MPC Success Rate",
            "mdi:percent-circle",
        )
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None

        metrics_data = self.coordinator.data.get("metrics") if isinstance(self.coordinator.data, dict) else None

        if not metrics_data or isinstance(metrics_data, Exception):
            return None

        # Access nested mpc_metrics structure
        mpc_metrics = metrics_data.get("mpc_metrics", {})
        total_runs = mpc_metrics.get("total_runs", 0)
        successful_runs = mpc_metrics.get("successful_runs", 0)

        if total_runs == 0:
            return 0.0  # Return 0% instead of None for new users

        return round((successful_runs / total_runs) * 100, 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        if not self.coordinator.data:
            return {}

        metrics_data = self.coordinator.data.get("metrics") if isinstance(self.coordinator.data, dict) else None

        if not metrics_data or isinstance(metrics_data, Exception):
            return {"error": str(metrics_data)}

        # Access nested mpc_metrics structure
        mpc_metrics = metrics_data.get("mpc_metrics", {})
        
        attrs = {
            "total_runs": mpc_metrics.get("total_runs", 0),
            "successful_runs": mpc_metrics.get("successful_runs", 0),
            "failed_runs": mpc_metrics.get("total_runs", 0) - mpc_metrics.get("successful_runs", 0),
            "period": f"{metrics_data.get('period_hours', 1)} hour(s)",
        }

        return attrs


class IntuiThermMPCSolveTimeSensor(IntuiThermSensorBase):
    """Sensor for MPC average solve time."""

    def __init__(self, coordinator: IntuiThermCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            SENSOR_TYPE_MPC_SOLVE_TIME,
            "MPC Solve Time",
            "mdi:timer-sand",
        )
        self._attr_native_unit_of_measurement = UnitOfTime.MILLISECONDS
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None

        metrics_data = self.coordinator.data.get("metrics") if isinstance(self.coordinator.data, dict) else None

        if not metrics_data or isinstance(metrics_data, Exception):
            return None

        # Access nested mpc_metrics structure
        mpc_metrics = metrics_data.get("mpc_metrics", {})
        avg_solve_time_ms = mpc_metrics.get("avg_solve_time_ms", 0.0)

        return round(avg_solve_time_ms, 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        if not self.coordinator.data:
            return {}

        metrics_data = self.coordinator.data.get("metrics") if isinstance(self.coordinator.data, dict) else None

        if not metrics_data or isinstance(metrics_data, Exception):
            return {"error": str(metrics_data)}

        # Access nested mpc_metrics structure
        mpc_metrics = metrics_data.get("mpc_metrics", {})
        
        attrs = {
            "period": f"{metrics_data.get('period_hours', 1)} hour(s)",
        }
        
        # Add min/max if available (these may not be in current API response)
        if "min_solve_time_ms" in mpc_metrics:
            attrs["min_solve_time_ms"] = mpc_metrics["min_solve_time_ms"]
        if "max_solve_time_ms" in mpc_metrics:
            attrs["max_solve_time_ms"] = mpc_metrics["max_solve_time_ms"]

        return attrs


class IntuiThermDryRunModeSensor(IntuiThermSensorBase):
    """Sensor showing if test/dry-run mode is active."""

    def __init__(self, coordinator: IntuiThermCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            SENSOR_TYPE_DRY_RUN_MODE,
            "Demo Mode Status",
            "mdi:information",
        )
        self._entry = entry

    @property
    def native_value(self) -> str:
        """Return test mode status."""
        # Get dry_run_mode from config
        config = {**self._entry.data, **self._entry.options}
        detected_entities = config.get(CONF_DETECTED_ENTITIES, {})
        dry_run_mode = detected_entities.get(CONF_DRY_RUN_MODE, False)
        
        return "Active" if dry_run_mode else "Disabled"

    @property
    def icon(self) -> str:
        """Return icon based on state."""
        config = {**self._entry.data, **self._entry.options}
        detected_entities = config.get(CONF_DETECTED_ENTITIES, {})
        dry_run_mode = detected_entities.get(CONF_DRY_RUN_MODE, False)
        
        return "mdi:flask" if dry_run_mode else "mdi:flask-empty-off"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        config = {**self._entry.data, **self._entry.options}
        detected_entities = config.get(CONF_DETECTED_ENTITIES, {})
        dry_run_mode = detected_entities.get(CONF_DRY_RUN_MODE, False)
        
        attrs = {
            "description": "Demo mode - MPC runs but doesn't control battery" if dry_run_mode else "Normal mode - battery control enabled",
            "commands_executed": not dry_run_mode,
            "note": "Use the Demo Mode switch in controls to toggle this setting"
        }
        
        if dry_run_mode:
            attrs["warning"] = "Battery is NOT being controlled - for testing only"
        
        return attrs


# Forecast Sensors

class IntuiThermConsumptionForecastSensor(IntuiThermSensorBase):
    """Sensor showing consumption forecast with historical data."""

    def __init__(self, coordinator: IntuiThermCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            "consumption_forecast",
            "Consumption Forecast",
            "mdi:home-lightning-bolt",
        )
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_native_unit_of_measurement = "kW"
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        """Return mean forecast value."""
        if not self.coordinator.data:
            return None

        forecast_data = self.coordinator.data.get("consumption_forecast")
        if not forecast_data or isinstance(forecast_data, Exception):
            return None

        return forecast_data.get("mean_forecast")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return forecast points as attributes for ApexCharts."""
        if not self.coordinator.data:
            return {}

        forecast_data = self.coordinator.data.get("consumption_forecast")
        if not forecast_data or isinstance(forecast_data, Exception):
            return {"error": str(forecast_data) if isinstance(forecast_data, Exception) else "No data"}

        return {
            "forecast": forecast_data.get("forecast", []),
            "generated_at": forecast_data.get("generated_at"),
            "forecast_method": forecast_data.get("forecast_method"),
            "unit": "kW",
        }


class IntuiThermSolarForecastSensor(IntuiThermSensorBase):
    """Sensor showing solar generation forecast."""

    def __init__(self, coordinator: IntuiThermCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            "solar_forecast",
            "Solar Forecast",
            "mdi:solar-power",
        )
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_native_unit_of_measurement = "kW"
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        """Return mean forecast value."""
        if not self.coordinator.data:
            return None

        forecast_data = self.coordinator.data.get("solar_forecast")
        if not forecast_data or isinstance(forecast_data, Exception):
            return None

        return forecast_data.get("mean_forecast")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return forecast points as attributes."""
        if not self.coordinator.data:
            return {}

        forecast_data = self.coordinator.data.get("solar_forecast")
        if not forecast_data or isinstance(forecast_data, Exception):
            return {"error": str(forecast_data) if isinstance(forecast_data, Exception) else "No data"}

        return {
            "forecast": forecast_data.get("forecast", []),
            "generated_at": forecast_data.get("generated_at"),
            "forecast_method": forecast_data.get("forecast_method"),
            "unit": "kW",
        }


class IntuiThermBatterySOCForecastSensor(IntuiThermSensorBase):
    """Sensor showing battery SOC forecast."""

    def __init__(self, coordinator: IntuiThermCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            "battery_soc_forecast",
            "Battery SOC Forecast",
            "mdi:battery-charging-80",
        )
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_native_unit_of_measurement = "%"
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        """Return mean forecast value."""
        if not self.coordinator.data:
            return None

        forecast_data = self.coordinator.data.get("battery_soc_forecast")
        if not forecast_data or isinstance(forecast_data, Exception):
            return None

        return forecast_data.get("mean_forecast")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return forecast points as attributes."""
        if not self.coordinator.data:
            return {}

        forecast_data = self.coordinator.data.get("battery_soc_forecast")
        if not forecast_data or isinstance(forecast_data, Exception):
            return {"error": str(forecast_data) if isinstance(forecast_data, Exception) else "No data"}

        return {
            "forecast": forecast_data.get("forecast", []),
            "generated_at": forecast_data.get("generated_at"),
            "unit": "%",
        }


class IntuiThermBatterySOCPlanSensor(IntuiThermSensorBase):
    """Sensor showing planned battery SOC trajectory."""

    def __init__(self, coordinator: IntuiThermCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            "battery_soc_plan",
            "Battery SOC Plan",
            "mdi:battery-charging",
        )
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        """Return current SOC."""
        if not self.coordinator.data:
            return None

        soc_data = self.coordinator.data.get("battery_soc_plan")
        if not soc_data or isinstance(soc_data, Exception):
            return None

        return soc_data.get("current_soc")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return planned SOC trajectory."""
        if not self.coordinator.data:
            return {}

        soc_data = self.coordinator.data.get("battery_soc_plan")
        if not soc_data or isinstance(soc_data, Exception):
            return {"error": str(soc_data) if isinstance(soc_data, Exception) else "No data"}

        return {
            "planned_soc": soc_data.get("planned_soc", []),
            "generated_at": soc_data.get("generated_at"),
            "unit": "%",
        }


class IntuiThermNextControlSensor(IntuiThermSensorBase):
    """Sensor showing next control decision."""

    def __init__(self, coordinator: IntuiThermCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            "next_control",
            "Next Control",
            "mdi:chart-timeline-variant",
        )

    @property
    def native_value(self) -> str | None:
        """Return immediate next control decision matching battery state format."""
        if not self.coordinator.data:
            return None

        control_data = self.coordinator.data.get("control_plan")
        if not control_data or isinstance(control_data, Exception):
            return "No plan available"

        controls = control_data.get("controls", [])
        if not controls:
            return "No upcoming control"

        # Find the next control (first one with timestamp >= now)
        from homeassistant.util import dt as dt_util
        now = dt_util.now()
        
        next_control = None
        for control in controls:
            try:
                timestamp_str = control.get("target_timestamp")
                if timestamp_str:
                    control_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    if control_time >= now:
                        next_control = control
                        break
            except:
                continue
        
        if not next_control:
            return "No upcoming control"

        # Format mode name to match battery state
        mode = next_control.get("control_action", "unknown")
        mode_mapping = {
            "force_charge": "Force Charge",
            "self_use": "Self Use",
            "backup": "Back-up"
        }
        
        return mode_mapping.get(mode, mode)

    @property
    def icon(self) -> str:
        """Return dynamic icon based on mode."""
        if not self.coordinator.data:
            return "mdi:battery-unknown"

        control_data = self.coordinator.data.get("control_plan")
        if not control_data or isinstance(control_data, Exception):
            return "mdi:battery-unknown"

        controls = control_data.get("controls", [])
        if not controls:
            return "mdi:battery"

        # Find next control
        from homeassistant.util import dt as dt_util
        now = dt_util.now()
        
        for control in controls:
            try:
                timestamp_str = control.get("target_timestamp")
                if timestamp_str:
                    control_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    if control_time >= now:
                        mode = control.get("control_action", "")
                        icons = {
                            "force_charge": "mdi:battery-charging",
                            "self_use": "mdi:battery-sync",
                            "backup": "mdi:battery-lock"
                        }
                        return icons.get(mode, "mdi:battery")
            except:
                continue
        
        return "mdi:battery"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return control plan details with next 4 upcoming controls in schedule."""
        if not self.coordinator.data:
            return {}

        control_data = self.coordinator.data.get("control_plan")
        if not control_data or isinstance(control_data, Exception):
            return {"error": str(control_data) if isinstance(control_data, Exception) else "No data"}

        controls = control_data.get("controls", [])
        
        # Get next 4 upcoming controls with unique times for schedule attribute
        from homeassistant.util import dt as dt_util
        now = dt_util.now()
        
        upcoming = []
        seen_times = set()
        
        for control in controls:
            try:
                timestamp_str = control.get("target_timestamp")
                if timestamp_str:
                    control_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    # Convert to local timezone for display
                    control_time_local = dt_util.as_local(control_time)
                    if control_time >= now:
                        time_key = control_time_local.strftime("%H:%M")
                        
                        # Only add if we haven't seen this time yet (avoid duplicates)
                        if time_key not in seen_times:
                            seen_times.add(time_key)
                            upcoming.append({
                                "time": time_key,
                                "action": control.get("control_action"),
                                "power_kw": round(control.get("power_setpoint", 0), 1),
                                "expected_soc": round(control.get("expected_soc", 0) * 100)
                            })
                            if len(upcoming) >= 4:
                                break
            except:
                continue
        
        # Build schedule string
        schedule_parts = []
        for item in upcoming:
            mode_short = {
                "force_charge": "Charge",
                "self_use": "Self-Use",
                "backup": "Preserve"
            }.get(item["action"], item["action"])
            schedule_parts.append(f"{item['time']} {mode_short}")
        
        attrs = {
            "schedule": " → ".join(schedule_parts) if schedule_parts else "No upcoming changes",
            "next_execution_time": upcoming[0]["time"] if upcoming else None,
            "next_action": upcoming[0]["action"] if upcoming else None,
            "upcoming_controls": upcoming,
            "total_controls": len(controls),
            "plan_generated_at": control_data.get("plan_generated_at"),
        }

        return attrs


class IntuiThermPredictedCostSensor(IntuiThermSensorBase):
    """Sensor showing predicted electricity cost for next 24h."""

    def __init__(self, coordinator: IntuiThermCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            "predicted_cost",
            "Predicted Cost (24h)",
            "mdi:currency-eur",
        )
        self._attr_native_unit_of_measurement = "EUR"
        self._attr_state_class = SensorStateClass.TOTAL

    @property
    def native_value(self) -> float | None:
        """Return predicted cost from latest MPC run."""
        if not self.coordinator.data:
            return None

        control_data = self.coordinator.data.get("control_plan")
        if not control_data or isinstance(control_data, Exception):
            return None

        return control_data.get("optimization_cost_eur")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return price forecast data."""
        if not self.coordinator.data:
            return {}

        price_data = self.coordinator.data.get("price_forecast")
        if not price_data or isinstance(price_data, Exception):
            return {}

        return {
            "prices": price_data.get("prices", []),
            "current_price": price_data.get("current_price"),
            "mean_price": price_data.get("mean_price"),
            "min_price": price_data.get("min_price"),
            "max_price": price_data.get("max_price"),
            "unit": "EUR/kWh",
        }


class IntuiThermSavingsTodaySensor(IntuiThermSensorBase):
    """Sensor showing total estimated savings today (PV + arbitrage)."""

    def __init__(self, coordinator: IntuiThermCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            SENSOR_TYPE_SAVINGS_TODAY,
            "Savings Today",
            "mdi:piggy-bank-outline",
        )
        self._attr_native_unit_of_measurement = "EUR"
        self._attr_state_class = SensorStateClass.TOTAL

    @property
    def native_value(self) -> float | None:
        """Return total savings today."""
        if not self.coordinator.data:
            return None

        savings = self.coordinator.data.get("savings")
        if not savings or isinstance(savings, Exception):
            return None

        return savings.get("total_savings_eur")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return savings breakdown."""
        if not self.coordinator.data:
            return {}

        savings = self.coordinator.data.get("savings")
        if not savings or isinstance(savings, Exception):
            return {}

        pv_eur = savings.get("pv_savings_eur", 0) or 0
        arb_eur = savings.get("arbitrage_savings_eur", 0) or 0
        solar_kwh = savings.get("solar_kwh_in_battery", 0) or 0
        grid_kwh = savings.get("grid_kwh_in_battery", 0) or 0
        avg_grid_cost = savings.get("avg_grid_cost_eur_kwh")
        pool_total = solar_kwh + grid_kwh
        solar_pct = round(100 * solar_kwh / pool_total) if pool_total > 0.01 else 0
        grid_pct = 100 - solar_pct if pool_total > 0.01 else 0

        return {
            "description": (
                "Estimated total battery savings today: solar energy buffered in the battery "
                "(PV savings) plus grid energy bought cheap and used at higher prices "
                "(arbitrage savings). Only covers energy flowing through the battery — "
                "direct solar-to-load is not included."
            ),
            "pv_savings_eur": round(pv_eur, 4),
            "arbitrage_savings_eur": round(arb_eur, 4),
            "pv_savings_note": (
                f"Solar pool: {round(solar_kwh, 3)} kWh ({solar_pct}% of battery). "
                "Savings = solar_fraction × discharge_kWh × (spot_price − feed_in_price)."
            ),
            "arbitrage_savings_note": (
                f"Grid pool: {round(grid_kwh, 3)} kWh ({grid_pct}% of battery)"
                + (f" charged at avg {round(avg_grid_cost, 3)} €/kWh. " if avg_grid_cost else ". ")
                + "Savings = grid_fraction × discharge_kWh × (spot_price − avg_charge_cost)."
            ),
            "battery_solar_kwh": round(solar_kwh, 3),
            "battery_grid_kwh": round(grid_kwh, 3),
            "battery_solar_pct": solar_pct,
            "battery_grid_pct": grid_pct,
            "avg_grid_cost_eur_kwh": round(avg_grid_cost, 4) if avg_grid_cost else None,
            "savings_date": savings.get("savings_date"),
            "updated_at": savings.get("updated_at"),
        }


class IntuiThermPVSavingsTodaySensor(IntuiThermSensorBase):
    """Sensor showing savings from using stored solar energy."""

    def __init__(self, coordinator: IntuiThermCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            SENSOR_TYPE_PV_SAVINGS_TODAY,
            "PV Savings Today",
            "mdi:solar-power-variant",
        )
        self._attr_native_unit_of_measurement = "EUR"
        self._attr_state_class = SensorStateClass.TOTAL

    @property
    def native_value(self) -> float | None:
        """Return PV savings today."""
        if not self.coordinator.data:
            return None

        savings = self.coordinator.data.get("savings")
        if not savings or isinstance(savings, Exception):
            return None

        return savings.get("pv_savings_eur")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return PV savings explanation and pool state."""
        if not self.coordinator.data:
            return {}

        savings = self.coordinator.data.get("savings")
        if not savings or isinstance(savings, Exception):
            return {}

        solar_kwh = savings.get("solar_kwh_in_battery", 0) or 0
        grid_kwh = savings.get("grid_kwh_in_battery", 0) or 0
        pool_total = solar_kwh + grid_kwh
        solar_pct = round(100 * solar_kwh / pool_total) if pool_total > 0.01 else 0

        return {
            "description": (
                "Savings from solar energy that was stored in the battery and later "
                "discharged to the house. Calculated as: solar_fraction × discharge_kWh × "
                "(spot_price − feed_in_price). The feed-in price is subtracted because "
                "exporting that solar would have earned revenue — using it avoids import "
                "but forgoes export. Does not include direct solar-to-load (no battery)."
            ),
            "solar_kwh_in_battery": round(solar_kwh, 3),
            "solar_pct_of_battery": solar_pct,
            "savings_date": savings.get("savings_date"),
            "updated_at": savings.get("updated_at"),
        }


class IntuiThermArbitrageSavingsTodaySensor(IntuiThermSensorBase):
    """Sensor showing savings from smart charging timing (buy cheap, use at peak)."""

    def __init__(self, coordinator: IntuiThermCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            SENSOR_TYPE_ARBITRAGE_SAVINGS_TODAY,
            "Arbitrage Savings Today",
            "mdi:chart-timeline-variant-shimmer",
        )
        self._attr_native_unit_of_measurement = "EUR"
        self._attr_state_class = SensorStateClass.TOTAL

    @property
    def native_value(self) -> float | None:
        """Return arbitrage savings today."""
        if not self.coordinator.data:
            return None

        savings = self.coordinator.data.get("savings")
        if not savings or isinstance(savings, Exception):
            return None

        return savings.get("arbitrage_savings_eur")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return arbitrage savings explanation and pool state."""
        if not self.coordinator.data:
            return {}

        savings = self.coordinator.data.get("savings")
        if not savings or isinstance(savings, Exception):
            return {}

        solar_kwh = savings.get("solar_kwh_in_battery", 0) or 0
        grid_kwh = savings.get("grid_kwh_in_battery", 0) or 0
        avg_grid_cost = savings.get("avg_grid_cost_eur_kwh")
        pool_total = solar_kwh + grid_kwh
        grid_pct = round(100 * grid_kwh / pool_total) if pool_total > 0.01 else 0

        return {
            "description": (
                "Savings from grid energy that was force-charged into the battery at a "
                "lower spot price and later discharged when prices are higher. "
                "Calculated as: grid_fraction × discharge_kWh × (current_spot_price − avg_charge_cost). "
                "Negative spreads (charged expensive, using cheap) are clamped to zero."
            ),
            "grid_kwh_in_battery": round(grid_kwh, 3),
            "grid_pct_of_battery": grid_pct,
            "avg_grid_charge_cost_eur_kwh": round(avg_grid_cost, 4) if avg_grid_cost else None,
            "savings_date": savings.get("savings_date"),
            "updated_at": savings.get("updated_at"),
        }
