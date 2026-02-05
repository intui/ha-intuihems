"""
Battery control executor for Home Assistant.

Implements pull-based control: HA fetches control plans from the cloud service
and executes them locally using battery control entities.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Dict, List, Optional
import logging

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.util import dt as dt_util

from .const import (
    CONF_DRY_RUN_MODE,
    CONF_DETECTED_ENTITIES,
    CONF_MODE_SELF_USE,
    CONF_MODE_BACKUP,
    CONF_MODE_FORCE_CHARGE,
    CONF_SOLAREDGE_COMMAND_MODE,
    CONF_BATTERY_MAX_POWER,
    SOLAREDGE_COMMAND_MODE_MAXIMIZE_SELF_CONSUMPTION,
    SOLAREDGE_COMMAND_MODE_CHARGE_FROM_SOLAR_POWER_AND_GRID,
)

if TYPE_CHECKING:
    from .coordinator import IntuiThermDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# Control interval - execute every 15 minutes aligned to :00, :15, :30, :45
CONTROL_INTERVAL = timedelta(minutes=15)


class BatteryControlExecutor:
    """
    Executes MPC battery control decisions locally in Home Assistant.
    
    Architecture:
    1. Coordinator fetches 24h control plan from backend
    2. Executor waits for aligned time (:00, :15, :30, :45)
    3. Executor finds matching control for current time
    4. Executor applies control to battery entities
    5. Executor sends execution feedback to backend
    """

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: IntuiThermDataUpdateCoordinator,
        config: Dict,
    ) -> None:
        """Initialize the battery control executor."""
        self.hass = hass
        self.coordinator = coordinator
        self.config = config
        
        # Battery control entity IDs from config
        detected_entities = config.get(CONF_DETECTED_ENTITIES, {})
        self.battery_mode_select = detected_entities.get("battery_mode_select")
        self.battery_charge_power = detected_entities.get("battery_charge_power")
        self.battery_discharge_power = detected_entities.get("battery_discharge_power")
        self.solaredge_command_mode = detected_entities.get(CONF_SOLAREDGE_COMMAND_MODE)
        
        # Max battery power in kW (for SolarEdge backup/peak shaving)
        self.battery_max_power = config.get(CONF_BATTERY_MAX_POWER, 3.0)
        
        # Mode mappings from config (device-specific mode names)
        self.mode_self_use = detected_entities.get(CONF_MODE_SELF_USE, "Self Use")
        self.mode_backup = detected_entities.get(CONF_MODE_BACKUP, "Backup")
        self.mode_force_charge = detected_entities.get(CONF_MODE_FORCE_CHARGE, "Force Charge")
        
        # State
        self._enabled = False
        self._last_execution = None
        self._next_execution = None
        self._cancel_timer = None
        
        _LOGGER.info(
            "BatteryControlExecutor initialized with entities: "
            f"mode={self.battery_mode_select}, "
            f"charge={self.battery_charge_power}, "
            f"discharge={self.battery_discharge_power}"
        )

    def start(self) -> None:
        """Start the battery control executor."""
        if self._enabled:
            _LOGGER.warning("Battery control executor already running")
            return
        
        self._enabled = True
        
        # Calculate next aligned execution time
        self._next_execution = self._get_next_aligned_time()
        
        _LOGGER.info(
            f"Starting battery control executor. Next execution: {self._next_execution}"
        )
        
        # Schedule execution at the next aligned time
        self._schedule_next_execution()

    def stop(self) -> None:
        """Stop the battery control executor."""
        if self._cancel_timer:
            self._cancel_timer()
            self._cancel_timer = None
        
        self._enabled = False
        _LOGGER.info("Battery control executor stopped")

    def _get_next_aligned_time(self) -> datetime:
        """Get next aligned execution time (:00, :15, :30, :45)."""
        now = dt_util.now()
        
        # Round to next 15-minute mark
        minute = now.minute
        aligned_minute = ((minute // 15) + 1) * 15
        
        if aligned_minute >= 60:
            # Next hour
            next_time = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        else:
            next_time = now.replace(minute=aligned_minute, second=0, microsecond=0)
        
        return next_time

    def _schedule_next_execution(self) -> None:
        """Schedule execution at the next aligned time."""
        if self._cancel_timer:
            self._cancel_timer()
        
        self._next_execution = self._get_next_aligned_time()
        
        _LOGGER.debug(f"Scheduling next execution at {self._next_execution}")
        
        self._cancel_timer = async_track_point_in_time(
            self.hass,
            self._execute_control_callback,
            self._next_execution,
        )

    @callback
    def _execute_control_callback(self, now: datetime) -> None:
        """Callback for control execution at aligned time."""
        # Schedule next execution before running current one
        self._schedule_next_execution()
        
        # Execute control
        self.hass.async_create_task(self._execute_control())

    async def _execute_control(self) -> None:
        """Execute battery control for current time window."""
        if not self._enabled:
            return
        
        now = dt_util.now()
        self._last_execution = now
        self._next_execution = self._get_next_aligned_time()
        
        try:
            # Refresh coordinator data to get latest control plan from backend
            # This ensures we have the freshest plan that was generated 3 minutes ago by MPC
            _LOGGER.info("Refreshing coordinator data before execution")
            await self.coordinator.async_request_refresh()
            
            # Check if automatic control is enabled
            control_data = self.coordinator.data.get("control", {}) if self.coordinator.data else {}
            
            if not control_data.get("automatic_control_enabled", False):
                _LOGGER.debug("Automatic control disabled, skipping execution")
                return
            
            # Check if demo mode is enabled (dry_run)
            detected_entities = self.config.get(CONF_DETECTED_ENTITIES, {})
            demo_mode = detected_entities.get(CONF_DRY_RUN_MODE, False)
            
            if demo_mode:
                _LOGGER.info("🎮 Demo mode active - MPC control would execute: mode=%s, power=%.2fkW (NOT executing)", 
                           "TBD", 0.0)  # Will be updated with actual values later
                # Continue to fetch and log the plan, but don't execute
            
            # Get control plan from coordinator
            control_plan = self.coordinator.data.get("control_plan", {}) if self.coordinator.data else {}
            
            if not control_plan:
                _LOGGER.warning("No control plan available, skipping execution")
                return
            
            controls = control_plan.get("controls", [])
            
            if not controls:
                _LOGGER.warning("Control plan is empty, skipping execution")
                return
            
            # Find control for current time window
            # Match control at the current aligned quarter-hour mark
            target_control = None
            
            # Calculate current aligned time (round down to last quarter hour)
            current_minute = now.minute
            aligned_minute = (current_minute // 15) * 15
            current_aligned = now.replace(minute=aligned_minute, second=0, microsecond=0)
            
            _LOGGER.info(f"Looking for control at aligned time: {current_aligned}")
            
            for control in controls:
                control_time_str = control.get("target_timestamp")
                if not control_time_str:
                    continue
                
                # Parse timestamp
                try:
                    control_time = datetime.fromisoformat(control_time_str.replace("Z", "+00:00"))
                    control_time = dt_util.as_local(control_time)
                except (ValueError, TypeError) as e:
                    _LOGGER.error(f"Failed to parse control timestamp {control_time_str}: {e}")
                    continue
                
                # Match exact quarter-hour (allow up to 30 seconds before/after for timing jitter)
                time_diff = abs((control_time - current_aligned).total_seconds())
                
                if time_diff < 30:  # 30 seconds tolerance for exact match
                    target_control = control
                    _LOGGER.info(f"Found matching control for {current_aligned}: {control.get('control_action')}")
                    break
            
            if not target_control:
                _LOGGER.info(f"No control found for current time {now}")
                return
            
            # Execute the control
            mode = target_control.get("control_action")
            power = target_control.get("power_setpoint", 0.0)
            
            # Check demo mode again before execution
            detected_entities = self.config.get(CONF_DETECTED_ENTITIES, {})
            demo_mode = detected_entities.get(CONF_DRY_RUN_MODE, False)
            
            if demo_mode:
                _LOGGER.info(
                    f"🎮 Demo mode: Would execute mode={mode}, power={power}kW at {now} (NOT executing)"
                )
                return  # Don't execute in demo mode
            
            _LOGGER.info(
                f"Executing control: mode={mode}, power={power}kW at {now}"
            )
            
            success = await self._apply_control(mode, power)
            
            if success:
                _LOGGER.info(f"Successfully executed control: {mode}")
                
                # Send feedback to backend
                await self._send_execution_feedback(
                    target_timestamp=target_control.get("target_timestamp"),
                    executed_at=now,
                    mode=mode,
                    power=power,
                )
            else:
                _LOGGER.error(f"Failed to execute control: {mode}")
        
        except Exception as e:
            _LOGGER.error(f"Error executing battery control: {e}", exc_info=True)

    async def _apply_control(self, mode: str, power_kw: float) -> bool:
        """
        Apply battery control to HA entities.
        
        Detects inverter type and uses appropriate control method:
        - Huawei: Uses forcible_charge service (required for physical charging)
        - Other brands: Uses direct mode/power entity control
        
        Args:
            mode: Control mode (force_charge, self_use, backup)
            power_kw: Power setpoint in kW
            
        Returns:
            True if successful, False otherwise
        """
        try:
            detected_entities = self.config.get(CONF_DETECTED_ENTITIES, {})
            
            # Detect if this is a Huawei system by checking for grid_charge_switch
            # This entity is only present on Huawei Solar integration
            is_huawei = detected_entities.get("grid_charge_switch") is not None
            
            # Detect if this is a SolarEdge system with multi-modbus entities
            is_solaredge = self.solaredge_command_mode is not None
            
            if mode == "force_charge":
                if is_huawei:
                    # Huawei-specific procedure using forcible_charge service
                    # Based on: https://community.simon42.com/t/stromspeicher-vom-netz-laden-bei-guenstigen-preisen-tibber/16194/50
                    _LOGGER.info(f"Using Huawei forcible charge procedure for {power_kw}kW")
                    
                    # Step 1: Start forcible charge with power and duration
                    # Use MPC-calculated power (power_kw is the optimal value between 0 and configured max)
                    # The max power configured during setup is stored but MPC calculates optimal value per period
                    power_watts = int(round(abs(power_kw), 2) * 1000)  # Convert kW to Watts from MPC, limit to 2 decimals
                    
                    ha_device_id = detected_entities.get("ha_device_id")
                    if not ha_device_id:
                        _LOGGER.error("No Huawei battery device ID found - cannot call forcible_charge service")
                        return
                    
                    service_data = {
                        "device_id": ha_device_id,  # HA device registry ID
                        "duration": 16,  # 16 minutes (slightly longer than 15min control interval)
                        "power": str(power_watts),  # Huawei requires power as string, MPC respects configured limits
                    }
                    
                    try:
                        await self.hass.services.async_call(
                            "huawei_solar",
                            "forcible_charge",
                            service_data,
                            blocking=True,
                        )
                        _LOGGER.info(f"✓ Called huawei_solar.forcible_charge with {power_watts}W for 16 minutes (device_id={ha_device_id})")
                    except Exception as e:
                        _LOGGER.error(f"✗ Failed to call huawei_solar.forcible_charge: {e}", exc_info=True)
                        return False
                    
                    await asyncio.sleep(5)
                    
                    # Step 2: Set battery mode to fixed_charge_discharge
                    try:
                        await self.hass.services.async_call(
                            "select",
                            "select_option",
                            {
                                "entity_id": self.battery_mode_select,
                                "option": "fixed_charge_discharge",
                            },
                            blocking=True,
                        )
                        _LOGGER.info(f"✓ Set battery mode to fixed_charge_discharge")
                    except Exception as e:
                        _LOGGER.error(f"✗ Failed to set battery mode: {e}", exc_info=True)
                        return False
                    await asyncio.sleep(5)
                    
                    # Step 3: Enable grid charging switch
                    grid_charge_switch = detected_entities.get("grid_charge_switch")
                    if grid_charge_switch:
                        await self.hass.services.async_call(
                            "switch",
                            "turn_on",
                            {
                                "entity_id": grid_charge_switch,
                            },
                            blocking=True,
                        )
                        _LOGGER.info(f"Enabled grid charging switch: {grid_charge_switch}")
                    
                    _LOGGER.info(f"Applied Huawei forcible charge: {power_kw}kW ({power_watts}W)")
                
                elif is_solaredge:
                    # SolarEdge Multi Modbus: Force Charge
                    _LOGGER.info(f"Using SolarEdge multi-modbus force charge for {power_kw}kW")
                    
                    # 1. Set Charge Limit to target power (in Watts)
                    if self.battery_charge_power:
                        power_watts = int(round(abs(power_kw), 2) * 1000)
                        await self.hass.services.async_call(
                            "number", "set_value",
                            {"entity_id": self.battery_charge_power, "value": power_watts},
                            blocking=True,
                        )
                    
                    # 2. Set Command Mode to "Charge from Solar Power and Grid"
                    await self.hass.services.async_call(
                        "select", "select_option",
                        {
                            "entity_id": self.solaredge_command_mode,
                            "option": SOLAREDGE_COMMAND_MODE_CHARGE_FROM_SOLAR_POWER_AND_GRID,
                        },
                        blocking=True,
                    )
                    _LOGGER.info(f"Applied SolarEdge Force Charge: {power_kw}kW")

                else:
                    # Generic procedure for non-Huawei systems (FoxESS, Solis, etc.)
                    _LOGGER.info(f"Using generic force charge for {power_kw}kW")
                    
                    # Set to Force Charge mode
                    await self.hass.services.async_call(
                        "select",
                        "select_option",
                        {
                            "entity_id": self.battery_mode_select,
                            "option": self.mode_force_charge,
                        },
                        blocking=True,
                    )
                    
                    # Set charge power if entity exists
                    if self.battery_charge_power:
                        power_value = max(0, min(50, power_kw))  # Clamp to 0-50kW
                        
                        await self.hass.services.async_call(
                            "number",
                            "set_value",
                            {
                                "entity_id": self.battery_charge_power,
                                "value": round(power_value, 2),
                            },
                            blocking=True,
                        )
                        _LOGGER.debug(f"Set charge power to {power_value}kW")
                    
                    _LOGGER.info(f"Applied Force Charge mode ({self.mode_force_charge}) with {power_kw}kW")
                
            elif mode == "self_use":
                if is_huawei:
                    # Huawei-specific procedure to stop forcible charge
                    _LOGGER.info("Using Huawei stop forcible charge procedure")
                    
                    # Step 1: Disable grid charging switch
                    grid_charge_switch = detected_entities.get("grid_charge_switch")
                    if grid_charge_switch:
                        await self.hass.services.async_call(
                            "switch",
                            "turn_off",
                            {
                                "entity_id": grid_charge_switch,
                            },
                            blocking=True,
                        )
                        _LOGGER.debug(f"Disabled grid charging switch: {grid_charge_switch}")
                    
                    await asyncio.sleep(5)
                    
                    # Step 2: Set battery mode to maximise_self_consumption
                    await self.hass.services.async_call(
                        "select",
                        "select_option",
                        {
                            "entity_id": self.battery_mode_select,
                            "option": "maximise_self_consumption",
                        },
                        blocking=True,
                    )
                    
                    _LOGGER.debug("Set battery mode to maximise_self_consumption")
                    await asyncio.sleep(5)
                    
                    # Step 3: Stop forcible charge
                    ha_device_id = detected_entities.get("ha_device_id")
                    service_data = {}
                    if ha_device_id:
                        service_data["device_id"] = ha_device_id
                    
                    await self.hass.services.async_call(
                        "huawei_solar",
                        "stop_forcible_charge",
                        service_data,
                        blocking=True,
                    )
                    
                    _LOGGER.info("Applied Self Use mode (stopped Huawei forcible charge)")
                
                elif is_solaredge:
                    # SolarEdge Multi Modbus: Peak Shaving (Laden blockieren)
                    _LOGGER.info("Using SolarEdge multi-modbus peak shaving (block charge)")
                    
                    # 1. Set Charge Limit to Max Power (in Watts)
                    if self.battery_charge_power:
                        await self.hass.services.async_call(
                            "number", "set_value",
                            {"entity_id": self.battery_charge_power, "value": int(self.battery_max_power * 1000)},
                            blocking=True,
                        )
                    
                    # 2. Set Discharge Limit to Max Power (in Watts)
                    if self.battery_discharge_power:
                        max_power_watts = int(self.battery_max_power * 1000)
                        await self.hass.services.async_call(
                            "number", "set_value",
                            {"entity_id": self.battery_discharge_power, "value": max_power_watts},
                            blocking=True,
                        )
                    
                    # 3. Set Command Mode to "Maximize Self Consumption"
                    await self.hass.services.async_call(
                        "select", "select_option",
                        {
                            "entity_id": self.solaredge_command_mode,
                            "option": SOLAREDGE_COMMAND_MODE_MAXIMIZE_SELF_CONSUMPTION,
                        },
                        blocking=True,
                    )
                    _LOGGER.info("Applied SolarEdge maximize self consumption (Charge and Discharge allowed)")

                else:
                    # Generic procedure for non-Huawei systems
                    await self.hass.services.async_call(
                        "select",
                        "select_option",
                        {
                            "entity_id": self.battery_mode_select,
                            "option": self.mode_self_use,
                        },
                        blocking=True,
                    )
                    
                    _LOGGER.info(f"Applied Self Use mode ({self.mode_self_use})")
                
            elif mode == "backup":
                if is_huawei:
                    # Huawei-specific procedure
                    _LOGGER.info("Using Huawei backup mode procedure")
                    
                    # Stop forcible charge first
                    grid_charge_switch = detected_entities.get("grid_charge_switch")
                    if grid_charge_switch:
                        await self.hass.services.async_call(
                            "switch",
                            "turn_off",
                            {
                                "entity_id": grid_charge_switch,
                            },
                            blocking=True,
                        )
                    
                    await asyncio.sleep(5)
                    
                    # Set to backup mode (maximise self consumption, battery stays reserved)
                    await self.hass.services.async_call(
                        "select",
                        "select_option",
                        {
                            "entity_id": self.battery_mode_select,
                            "option": "maximise_self_consumption",
                        },
                        blocking=True,
                    )
                    
                    await asyncio.sleep(5)
                    
                    ha_device_id = detected_entities.get("ha_device_id")
                    service_data = {}
                    if ha_device_id:
                        service_data["device_id"] = ha_device_id
                    
                    await self.hass.services.async_call(
                        "huawei_solar",
                        "stop_forcible_charge",
                        service_data,
                        blocking=True,
                    )
                    
                    _LOGGER.info("Applied Backup mode (stopped Huawei forcible charge)")
                
                elif is_solaredge:
                    # SolarEdge Multi Modbus: Backup (Entladen blockieren)
                    _LOGGER.info("Using SolarEdge multi-modbus backup (block discharge)")
                    
                    # 1. Set Charge Limit to Max Power (in Watts)
                    if self.battery_charge_power:
                        max_power_watts = int(self.battery_max_power * 1000)
                        await self.hass.services.async_call(
                            "number", "set_value",
                            {"entity_id": self.battery_charge_power, "value": max_power_watts},
                            blocking=True,
                        )
                    
                    # 2. Set Discharge Limit to 0
                    if self.battery_discharge_power:
                        await self.hass.services.async_call(
                            "number", "set_value",
                            {"entity_id": self.battery_discharge_power, "value": 0},
                            blocking=True,
                        )
                    
                    # 3. Set Command Mode to "Maximize Self Consumption"
                    await self.hass.services.async_call(
                        "select", "select_option",
                        {
                            "entity_id": self.solaredge_command_mode,
                            "option": SOLAREDGE_COMMAND_MODE_MAXIMIZE_SELF_CONSUMPTION,
                        },
                        blocking=True,
                    )
                    _LOGGER.info("Applied SolarEdge Backup (Discharge Blocked / Charge Allowed)")

                else:
                    # Generic procedure for non-Huawei systems
                    await self.hass.services.async_call(
                        "select",
                        "select_option",
                        {
                            "entity_id": self.battery_mode_select,
                            "option": self.mode_backup,
                        },
                        blocking=True,
                    )
                    
                    _LOGGER.info(f"Applied Backup mode ({self.mode_backup})")
            
            else:
                _LOGGER.error(f"Unknown control mode: {mode}")
                return False
            
            return True
        
        except Exception as e:
            _LOGGER.error(f"Error applying control {mode}: {e}", exc_info=True)
            return False

    async def _send_execution_feedback(
        self,
        target_timestamp: str,
        executed_at: datetime,
        mode: str,
        power: float,
    ) -> None:
        """
        Send execution feedback to backend.
        
        Args:
            target_timestamp: Target timestamp from control plan
            executed_at: Actual execution time
            mode: Executed control mode
            power: Power setpoint
        """
        try:
            # Get current battery state
            actual_soc = None
            actual_power = None
            
            # Try to read battery SOC sensor
            soc_sensor = self.hass.states.get("sensor.battery_soc_2")
            if soc_sensor and soc_sensor.state not in ["unknown", "unavailable"]:
                try:
                    actual_soc = float(soc_sensor.state) / 100.0  # Convert % to 0-1
                except ValueError:
                    pass
            
            # Try to read battery power sensor
            power_sensor = self.hass.states.get("sensor.battery_power")
            if power_sensor and power_sensor.state not in ["unknown", "unavailable"]:
                try:
                    actual_power = float(power_sensor.state) / 1000.0  # Convert W to kW
                except ValueError:
                    pass
            
            # Send feedback to backend
            feedback_data = {
                "target_timestamp": target_timestamp,
                "executed_at": executed_at.isoformat(),
                "actual_power": actual_power,
                "actual_soc": actual_soc,
            }
            
            response = await self.coordinator._post_json(
                "/api/v1/control/execution_feedback",
                data=feedback_data,
            )
            
            if response:
                _LOGGER.debug(f"Sent execution feedback: {feedback_data}")
            else:
                _LOGGER.warning("Failed to send execution feedback to backend")
        
        except Exception as e:
            _LOGGER.error(f"Error sending execution feedback: {e}", exc_info=True)

    @property
    def is_enabled(self) -> bool:
        """Return True if executor is enabled."""
        return self._enabled

    @property
    def last_execution(self) -> Optional[datetime]:
        """Return timestamp of last execution."""
        return self._last_execution

    @property
    def next_execution(self) -> Optional[datetime]:
        """Return timestamp of next scheduled execution."""
        return self._next_execution
