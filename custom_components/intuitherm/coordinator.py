"""Data coordinator for IntuiTherm integration."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
import logging
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    ENDPOINT_HEALTH,
    ENDPOINT_CONTROL_STATUS,
    ENDPOINT_METRICS,
    ENDPOINT_CONTROL_OVERRIDE,
    ENDPOINT_CONTROL_ENABLE,
    ENDPOINT_CONTROL_DISABLE,
    ENDPOINT_SENSORS,
    ENDPOINT_SENSOR_READINGS,
    CONF_SOLAR_SENSORS,
    CONF_BATTERY_DISCHARGE_SENSORS,
    CONF_BATTERY_CHARGE_SENSORS,
    CONF_GRID_IMPORT_SENSORS,
    CONF_GRID_EXPORT_SENSORS,
    CONF_BATTERY_SOC_ENTITY,
    CONF_HOUSE_LOAD_ENTITY,
    CONF_SOLAR_POWER_ENTITY,
    CONF_DETECTED_ENTITIES,
)

_LOGGER = logging.getLogger(__name__)


class IntuiThermCoordinator(DataUpdateCoordinator):
    """Coordinator to fetch data from IntuiTherm service."""

    def __init__(
        self,
        hass: HomeAssistant,
        session: aiohttp.ClientSession,
        service_url: str,
        api_key: str,
        update_interval: timedelta,
        entry: Any = None,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )
        self.service_url = service_url.rstrip("/")
        self.api_key = api_key
        self.session = session
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self.entry = entry
        self._sensors_registered = False
        self._historic_data_sent = False  # Track if historic backfill completed

        _LOGGER.info(
            "IntuiTherm coordinator initialized (service: %s, interval: %s)",
            self.service_url,
            update_interval,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from IntuiTherm service."""
        _LOGGER.info("🔄 Coordinator update cycle started")

        try:
            # Register sensors on first run
            if not self._sensors_registered and self.entry:
                _LOGGER.info("📝 Registering sensors...")
                await self._register_sensors()
                self._sensors_registered = True
                _LOGGER.info("✅ Sensors registered")
            
            # Backfill historic data on first run
            if not self._historic_data_sent and self.entry:
                _LOGGER.info("⏳ Starting historic backfill...")
                success = await self._backfill_historic_data()
                if success:
                    self._historic_data_sent = True
                    _LOGGER.info("✅ Historic backfill complete")

            # Send sensor readings
            if self.entry:
                _LOGGER.info("📊 Sending current sensor readings...")
                await self._send_sensor_readings()
                _LOGGER.info("✅ Sensor readings sent")

            async with asyncio.timeout(15):
                _LOGGER.info("🌐 Fetching backend data...")
                # Fetch all endpoints in parallel for efficiency
                health_task = self._fetch_json(ENDPOINT_HEALTH)
                status_task = self._fetch_json(ENDPOINT_CONTROL_STATUS)
                metrics_task = self._fetch_json(ENDPOINT_METRICS, params={"period_hours": 1})
                
                # Fetch forecast data
                consumption_forecast_task = self._fetch_json("/api/v1/forecasts/consumption")
                solar_forecast_task = self._fetch_json("/api/v1/forecasts/solar")
                battery_soc_plan_task = self._fetch_json("/api/v1/forecasts/battery_soc")
                control_plan_task = self._fetch_json("/api/v1/control/plan")  # Pull-based control plan
                price_forecast_task = self._fetch_json("/api/v1/forecasts/prices")

                health, status, metrics, consumption_forecast, solar_forecast, \
                battery_soc_plan, control_plan, price_forecast = await asyncio.gather(
                    health_task,
                    status_task,
                    metrics_task,
                    consumption_forecast_task,
                    solar_forecast_task,
                    battery_soc_plan_task,
                    control_plan_task,
                    price_forecast_task,
                    return_exceptions=True,
                )
                _LOGGER.info("✅ Backend data fetched successfully")

            # Build response, handling individual failures gracefully
            data = {
                "last_update": datetime.now(timezone.utc).isoformat(),
            }

            if isinstance(health, Exception):
                _LOGGER.warning("Failed to fetch health: %s", health)
                data["health"] = None
            else:
                data["health"] = health

            if isinstance(status, Exception):
                _LOGGER.warning("Failed to fetch control status: %s", status)
                data["control"] = None
            else:
                data["control"] = status

            if isinstance(metrics, Exception):
                _LOGGER.warning("Failed to fetch metrics: %s", metrics)
                data["metrics"] = None
            else:
                data["metrics"] = metrics
                
            # Add forecast data
            data["consumption_forecast"] = consumption_forecast if not isinstance(consumption_forecast, Exception) else None
            data["solar_forecast"] = solar_forecast if not isinstance(solar_forecast, Exception) else None
            data["battery_soc_plan"] = battery_soc_plan if not isinstance(battery_soc_plan, Exception) else None
            data["battery_soc_forecast"] = battery_soc_plan if not isinstance(battery_soc_plan, Exception) else None
            data["control_plan"] = control_plan if not isinstance(control_plan, Exception) else None
            data["price_forecast"] = price_forecast if not isinstance(price_forecast, Exception) else None
            
            if isinstance(consumption_forecast, Exception):
                _LOGGER.debug("No consumption forecast available yet: %s", consumption_forecast)
            if isinstance(solar_forecast, Exception):
                _LOGGER.debug("No solar forecast available yet: %s", solar_forecast)

            _LOGGER.info("🎉 Coordinator update cycle complete")
            return data

        except asyncio.TimeoutError as err:
            _LOGGER.error("⏱️ Timeout fetching data from service: %s", err)
            raise UpdateFailed(f"Timeout fetching data from service: {err}") from err
        except Exception as err:
            _LOGGER.error("❌ Error communicating with service: %s", err)
            raise UpdateFailed(f"Error communicating with service: {err}") from err

    async def _fetch_json(
        self, endpoint: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Fetch JSON data from an endpoint."""
        url = f"{self.service_url}{endpoint}"

        try:
            async with self.session.get(
                url, headers=self.headers, params=params
            ) as response:
                response.raise_for_status()
                return await response.json()

        except aiohttp.ClientResponseError as err:
            if err.status == 401:
                _LOGGER.error(
                    "Authentication failed for %s - check API key", endpoint
                )
            raise
        except aiohttp.ClientError as err:
            _LOGGER.error("HTTP error fetching %s: %s", endpoint, err)
            raise
        except Exception as err:
            _LOGGER.error("Unexpected error fetching %s: %s", endpoint, err)
            raise

    async def _post_json(
        self,
        endpoint: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Post JSON data to an endpoint."""
        url = f"{self.service_url}{endpoint}"

        try:
            async with self.session.post(
                url, headers=self.headers, json=data
            ) as response:
                response.raise_for_status()
                return await response.json()

        except aiohttp.ClientResponseError as err:
            if err.status == 401:
                _LOGGER.error(
                    "Authentication failed for %s - check API key", endpoint
                )
            elif err.status == 400:
                _LOGGER.error("Bad request to %s: %s", endpoint, await response.text())
            raise
        except aiohttp.ClientError as err:
            _LOGGER.error("HTTP error posting to %s: %s", endpoint, err)
            raise
        except Exception as err:
            _LOGGER.error("Unexpected error posting to %s: %s", endpoint, err)
            raise

    async def async_manual_override(
        self,
        action: str,
        power_kw: float | None = None,
        duration_minutes: int | None = None,
    ) -> dict[str, Any]:
        """Send manual control override command."""
        _LOGGER.info(
            "Sending manual override: action=%s, power=%s, duration=%s",
            action,
            power_kw,
            duration_minutes,
        )

        payload = {"action": action}
        if power_kw is not None:
            payload["power_kw"] = power_kw
        if duration_minutes is not None:
            payload["duration_minutes"] = duration_minutes

        try:
            result = await self._post_json(ENDPOINT_CONTROL_OVERRIDE, data=payload)
            _LOGGER.info("Manual override successful: %s", result.get("message"))
            return result
        except Exception as err:
            _LOGGER.error("Manual override failed: %s", err)
            return {"status": "failed", "detail": str(err)}

    async def async_enable_auto_control(self) -> dict[str, Any]:
        """Enable automatic battery control."""
        _LOGGER.info("Enabling automatic control")

        try:
            result = await self._post_json(ENDPOINT_CONTROL_ENABLE)
            _LOGGER.info("Automatic control enabled: %s", result.get("message"))
            return result
        except Exception as err:
            _LOGGER.error("Failed to enable automatic control: %s", err)
            return {"status": "failed", "detail": str(err)}

    async def async_disable_auto_control(self) -> dict[str, Any]:
        """Disable automatic battery control."""
        _LOGGER.info("Disabling automatic control")

        try:
            result = await self._post_json(ENDPOINT_CONTROL_DISABLE)
            _LOGGER.info("Automatic control disabled: %s", result.get("message"))
            return result
        except Exception as err:
            _LOGGER.error("Failed to disable automatic control: %s", err)
            return {"status": "failed", "detail": str(err)}

    async def _register_sensors(self) -> None:
        """Register sensors with the backend."""
        if not self.entry:
            return

        config = {**self.entry.data, **self.entry.options}
        
        # Note: Backend uses /sensors/data endpoint, so we don't need explicit registration
        # Sensors are auto-created when first data is sent
        _LOGGER.info("Sensors will be auto-registered on first data send")
        
    async def _send_sensor_readings(self) -> None:
        """Send current sensor readings to the backend."""
        if not self.entry:
            return

        config = {**self.entry.data, **self.entry.options}
        
        # Get detected entities (sensors are stored under this key)
        detected = config.get(CONF_DETECTED_ENTITIES, {})
        
        # Debug: Log what sensors are configured
        _LOGGER.info("📋 Configured sensors:")
        _LOGGER.info("  Solar: %s", detected.get(CONF_SOLAR_SENSORS, []))
        _LOGGER.info("  Battery Charge: %s", detected.get(CONF_BATTERY_CHARGE_SENSORS, []))
        _LOGGER.info("  Battery Discharge: %s", detected.get(CONF_BATTERY_DISCHARGE_SENSORS, []))
        _LOGGER.info("  Grid Import: %s", detected.get(CONF_GRID_IMPORT_SENSORS, []))
        _LOGGER.info("  Grid Export: %s", detected.get(CONF_GRID_EXPORT_SENSORS, []))
        _LOGGER.info("  Battery SOC: %s", detected.get(CONF_BATTERY_SOC_ENTITY))
        
        # Map our sensor categories to backend sensor types
        sensor_mappings = [
            (detected.get(CONF_SOLAR_SENSORS, []), "solar"),
            (detected.get(CONF_BATTERY_DISCHARGE_SENSORS, []), "soc"),  # Battery discharge correlates with SOC
            (detected.get(CONF_BATTERY_CHARGE_SENSORS, []), "soc"),
            (detected.get(CONF_GRID_IMPORT_SENSORS, []), "load"),  # Grid import indicates load
            (detected.get(CONF_GRID_EXPORT_SENSORS, []), "load"),
        ]
        
        # Add battery SOC if configured
        if battery_soc := detected.get(CONF_BATTERY_SOC_ENTITY):
            sensor_mappings.append(([battery_soc], "soc"))
        
        # Add house load if configured (CRITICAL for MPC)
        if house_load := detected.get(CONF_HOUSE_LOAD_ENTITY):
            sensor_mappings.append(([house_load], "load"))

        # Send data for each sensor type
        sensors_sent = 0
        for entity_ids, sensor_type in sensor_mappings:
            for entity_id in entity_ids:
                state = self.hass.states.get(entity_id)
                if state and state.state not in ("unknown", "unavailable"):
                    try:
                        value = float(state.state)
                        timestamp = datetime.now(timezone.utc)
                        
                        # Send to backend using /sensors/data endpoint
                        await self._post_json(
                            "/api/v1/sensors/data",
                            data={
                                "sensor_type": sensor_type,
                                "entity_id": entity_id,
                                "readings": [
                                    {
                                        "timestamp": timestamp.isoformat(),
                                        "value": value,
                                    }
                                ],
                            }
                        )
                        sensors_sent += 1
                        _LOGGER.debug("✓ Sent %s reading for %s: %s", sensor_type, entity_id, value)
                    except (ValueError, TypeError) as err:
                        _LOGGER.warning("⚠️ Could not parse value for %s: %s (state=%s)", entity_id, err, state.state)
                    except Exception as err:
                        _LOGGER.warning("⚠️ Failed to send reading for %s: %s", entity_id, err)
                else:
                    if state:
                        _LOGGER.debug("⏭️ Skipping %s: state=%s", entity_id, state.state)
                    else:
                        _LOGGER.warning("❌ Sensor not found: %s", entity_id)
        
        _LOGGER.info("📤 Sent %d sensor readings", sensors_sent)
    async def _backfill_historic_data(self) -> bool:
        """Backfill up to 7 days of historic sensor data on first run.
        
        Returns:
            True if backfill succeeded, False otherwise
        """
        from homeassistant.components.recorder import get_instance
        from homeassistant.components.recorder.history import state_changes_during_period
        
        _LOGGER.info("Starting historic data backfill (up to 7 days)")
        
        try:
            # Get recorder instance
            recorder = get_instance(self.hass)
            if not recorder:
                _LOGGER.warning("Recorder not available, skipping historic backfill")
                return False
            
            config = {**self.entry.data, **self.entry.options}
            
            # Get detected entities (sensors are stored under this key)
            detected = config.get(CONF_DETECTED_ENTITIES, {})
            
            # Calculate time range (7 days back)
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(days=7)
            
            # Collect all entity IDs to backfill (using the same logic as _send_sensor_readings)
            entities_to_backfill = []
            
            # Solar sensors (take first from list, or use all if needed)
            solar_sensors = detected.get(CONF_SOLAR_SENSORS, [])
            if solar_sensors:
                # Just backfill the first solar sensor (usually solar_energy_total)
                entities_to_backfill.append((solar_sensors[0], "solar"))
                _LOGGER.debug("Backfill: Solar sensor: %s", solar_sensors[0])
            
            # Battery charge sensors
            battery_charge_sensors = detected.get(CONF_BATTERY_CHARGE_SENSORS, [])
            if battery_charge_sensors:
                entities_to_backfill.append((battery_charge_sensors[0], "soc"))
                _LOGGER.debug("Backfill: Battery charge sensor: %s", battery_charge_sensors[0])
            
            # Battery discharge sensors
            battery_discharge_sensors = detected.get(CONF_BATTERY_DISCHARGE_SENSORS, [])
            if battery_discharge_sensors:
                entities_to_backfill.append((battery_discharge_sensors[0], "soc"))
                _LOGGER.debug("Backfill: Battery discharge sensor: %s", battery_discharge_sensors[0])
            
            # Grid import sensors
            grid_import_sensors = detected.get(CONF_GRID_IMPORT_SENSORS, [])
            if grid_import_sensors:
                entities_to_backfill.append((grid_import_sensors[0], "load"))
                _LOGGER.debug("Backfill: Grid import sensor: %s", grid_import_sensors[0])
            
            # Grid export sensors
            grid_export_sensors = detected.get(CONF_GRID_EXPORT_SENSORS, [])
            if grid_export_sensors:
                entities_to_backfill.append((grid_export_sensors[0], "load"))
                _LOGGER.debug("Backfill: Grid export sensor: %s", grid_export_sensors[0])
            
            # Battery SoC
            battery_soc = detected.get(CONF_BATTERY_SOC_ENTITY)
            if battery_soc:
                entities_to_backfill.append((battery_soc, "soc"))
                _LOGGER.debug("Backfill: Battery SOC sensor: %s", battery_soc)
            
            if not entities_to_backfill:
                _LOGGER.info("No entities configured for historic backfill")
                return False
            
            _LOGGER.info(
                "Backfilling %d sensors from %s to %s",
                len(entities_to_backfill),
                start_time.isoformat(),
                end_time.isoformat()
            )
            
            # Query historic data for all entities
            entity_ids = [entity_id for entity_id, _ in entities_to_backfill]
            
            _LOGGER.debug("Querying historic data for entities: %s", entity_ids)
            
            # Query each entity separately (state_changes_during_period doesn't accept list)
            history_data = {}
            for entity_id in entity_ids:
                entity_history = await recorder.async_add_executor_job(
                    state_changes_during_period,
                    self.hass,
                    start_time,
                    end_time,
                    entity_id,  # Single entity_id as string
                )
                if entity_history and entity_id in entity_history:
                    history_data[entity_id] = entity_history[entity_id]
            
            if not history_data:
                _LOGGER.warning("No historic data found for sensors")
                return False
            
            # Create entity_id to sensor_type mapping
            sensor_type_map = {entity_id: sensor_type for entity_id, sensor_type in entities_to_backfill}
            
            # Send historic data to backend
            total_readings = 0
            for entity_id, states in history_data.items():
                sensor_type = sensor_type_map.get(entity_id)
                if not sensor_type:
                    continue
                
                # Convert states to readings
                readings = []
                for state in states:
                    try:
                        if state.state in ("unknown", "unavailable", None):
                            continue
                        value = float(state.state)
                        timestamp = state.last_changed or state.last_updated
                        readings.append({
                            "timestamp": timestamp.isoformat(),
                            "value": value,
                        })
                    except (ValueError, TypeError, AttributeError):
                        continue
                
                if not readings:
                    continue
                
                # Send in batches of 100 (API max_items limit)
                batch_size = 100
                for i in range(0, len(readings), batch_size):
                    batch = readings[i:i + batch_size]
                    try:
                        await self._post_json(
                            "/api/v1/sensors/data",
                            data={
                                "sensor_type": sensor_type,
                                "entity_id": entity_id,
                                "readings": batch,
                            }
                        )
                        total_readings += len(batch)
                        _LOGGER.debug(
                            "Sent %d historic readings for %s (%s)",
                            len(batch),
                            entity_id,
                            sensor_type
                        )
                    except Exception as err:
                        _LOGGER.warning(
                            "Failed to send historic batch for %s: %s",
                            entity_id,
                            err
                        )
            
            _LOGGER.info(
                "Historic backfill complete: sent %d readings across %d sensors",
                total_readings,
                len(history_data)
            )
            return True
            
        except Exception as err:
            _LOGGER.error("Historic backfill failed: %s", err, exc_info=True)
            # Don't raise - backfill failure shouldn't prevent integration from working
            return False
