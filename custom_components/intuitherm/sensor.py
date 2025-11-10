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
    SENSOR_TYPE_MPC_RUNS_24H,
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
        IntuiThermServiceHealthSensor(coordinator, entry),
        IntuiThermOptimizationStatusSensor(coordinator, entry),
        IntuiThermControlModeSensor(coordinator, entry),
        IntuiThermMPCSuccessRateSensor(coordinator, entry),
        IntuiThermMPCSolveTimeSensor(coordinator, entry),
        IntuiThermMPCRuns24hSensor(coordinator, entry),
    ]

    async_add_entities(sensors)
    _LOGGER.info("IntuiTherm sensors added")


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
        self._attr_unique_id = f"{entry.entry_id}_{sensor_type}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "IntuiTherm Battery Optimizer",
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
            "IntuiTherm Service Health",
            "mdi:heart-pulse",
        )

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None

        health_data = self.coordinator.data.get("health", {})

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

        health_data = self.coordinator.data.get("health", {})

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
            "IntuiTherm Optimization Status",
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
            "IntuiTherm Control Mode",
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
            "IntuiTherm MPC Success Rate",
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

        # Calculate success rate from metrics
        total_runs = metrics_data.get("mpc_total_runs", 0)
        successful_runs = metrics_data.get("mpc_successful_runs", 0)

        if total_runs == 0:
            return None

        return round((successful_runs / total_runs) * 100, 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        if not self.coordinator.data:
            return {}

        metrics_data = self.coordinator.data.get("metrics") if isinstance(self.coordinator.data, dict) else None

        if not metrics_data or isinstance(metrics_data, Exception):
            return {"error": str(metrics_data)}

        attrs = {}

        # Add raw counts
        if "mpc_total_runs" in metrics_data:
            attrs["total_runs"] = metrics_data["mpc_total_runs"]
        if "mpc_successful_runs" in metrics_data:
            attrs["successful_runs"] = metrics_data["mpc_successful_runs"]
        if "mpc_failed_runs" in metrics_data:
            attrs["failed_runs"] = metrics_data["mpc_failed_runs"]

        # Add period
        attrs["period"] = "1 hour"

        return attrs


class IntuiThermMPCSolveTimeSensor(IntuiThermSensorBase):
    """Sensor for MPC average solve time."""

    def __init__(self, coordinator: IntuiThermCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            SENSOR_TYPE_MPC_SOLVE_TIME,
            "IntuiTherm MPC Solve Time",
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

        # Get average solve time
        avg_solve_time_ms = metrics_data.get("mpc_avg_solve_time_ms")

        if avg_solve_time_ms is None:
            return None

        return round(avg_solve_time_ms, 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        if not self.coordinator.data:
            return {}

        metrics_data = self.coordinator.data.get("metrics") if isinstance(self.coordinator.data, dict) else None

        if not metrics_data or isinstance(metrics_data, Exception):
            return {"error": str(metrics_data)}

        attrs = {}

        # Add min/max if available
        if "mpc_min_solve_time_ms" in metrics_data:
            attrs["min_solve_time_ms"] = metrics_data["mpc_min_solve_time_ms"]
        if "mpc_max_solve_time_ms" in metrics_data:
            attrs["max_solve_time_ms"] = metrics_data["mpc_max_solve_time_ms"]

        # Add period
        attrs["period"] = "1 hour"

        return attrs


class IntuiThermMPCRuns24hSensor(IntuiThermSensorBase):
    """Sensor for MPC run count in last 24h."""

    def __init__(self, coordinator: IntuiThermCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            SENSOR_TYPE_MPC_RUNS_24H,
            "IntuiTherm MPC Runs (24h)",
            "mdi:counter",
        )
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING

    @property
    def native_value(self) -> int | None:
        """Return number of MPC runs in the last 24 hours."""
        if not self.coordinator.data or self.coordinator.data is None:
            return None

        # Note: This sensor will show the 1-hour count from the metrics endpoint
        # In a future enhancement, we could query /api/v1/metrics?period_hours=24
        # separately to get true 24h counts
        metrics_data = self.coordinator.data.get("metrics") if isinstance(self.coordinator.data, dict) else None

        if not metrics_data or isinstance(metrics_data, Exception):
            return None

        total_runs = metrics_data.get("mpc_total_runs")

        if total_runs is None:
            return None

        return total_runs

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        if not self.coordinator.data:
            return {}

        metrics_data = self.coordinator.data.get("metrics") if isinstance(self.coordinator.data, dict) else None

        if not metrics_data or isinstance(metrics_data, Exception):
            return {"error": str(metrics_data)}

        attrs = {}

        # Add successful/failed breakdown
        if "mpc_successful_runs" in metrics_data:
            attrs["successful"] = metrics_data["mpc_successful_runs"]
        if "mpc_failed_runs" in metrics_data:
            attrs["failed"] = metrics_data["mpc_failed_runs"]

        # Note: Currently showing 1h period due to coordinator implementation
        # TODO: Fetch 24h metrics separately for this sensor
        attrs["period"] = "1 hour (displaying)"
        attrs["note"] = "24h tracking not yet implemented"

        return attrs
