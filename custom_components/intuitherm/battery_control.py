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
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

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
        self.battery_mode_select = config.get("battery_mode_select")
        self.battery_charge_power = config.get("battery_charge_power")
        self.battery_discharge_power = config.get("battery_discharge_power")
        
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
        
        # Schedule periodic execution every 15 minutes
        self._cancel_timer = async_track_time_interval(
            self.hass,
            self._execute_control_callback,
            CONTROL_INTERVAL,
        )
        
        # Also execute immediately if we're close to an aligned time
        now = dt_util.now()
        time_until_next = (self._next_execution - now).total_seconds()
        
        if time_until_next < 60:  # Within 1 minute of aligned time
            _LOGGER.info("Close to aligned time, executing immediately")
            self.hass.async_create_task(self._execute_control())

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

    @callback
    def _execute_control_callback(self, now: datetime) -> None:
        """Callback for periodic control execution."""
        self.hass.async_create_task(self._execute_control())

    async def _execute_control(self) -> None:
        """Execute battery control for current time window."""
        if not self._enabled:
            return
        
        now = dt_util.now()
        self._last_execution = now
        self._next_execution = self._get_next_aligned_time()
        
        try:
            # Check if automatic control is enabled
            control_data = self.coordinator.data.get("control", {}) if self.coordinator.data else {}
            
            if not control_data.get("automatic_control_enabled", False):
                _LOGGER.debug("Automatic control disabled, skipping execution")
                return
            
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
            # Match controls within +/- 5 minutes of now
            target_control = None
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
                
                # Check if this control is for current time window (within 5 minutes)
                time_diff = abs((control_time - now).total_seconds())
                
                if time_diff < 300:  # 5 minutes tolerance
                    target_control = control
                    break
            
            if not target_control:
                _LOGGER.debug(f"No control found for current time {now}")
                return
            
            # Execute the control
            mode = target_control.get("control_action")
            power = target_control.get("power_setpoint", 0.0)
            
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
        
        Args:
            mode: Control mode (force_charge, self_use, backup)
            power_kw: Power setpoint in kW
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if mode == "force_charge":
                # Set to Force Charge mode
                await self.hass.services.async_call(
                    "select",
                    "select_option",
                    {
                        "entity_id": self.battery_mode_select,
                        "option": "Force Charge",
                    },
                    blocking=True,
                )
                
                # Set charge power
                if self.battery_charge_power:
                    # Convert kW to W for FoxESS
                    power_w = int(power_kw * 1000)
                    
                    await self.hass.services.async_call(
                        "number",
                        "set_value",
                        {
                            "entity_id": self.battery_charge_power,
                            "value": power_w,
                        },
                        blocking=True,
                    )
                
                _LOGGER.info(f"Applied Force Charge mode with {power_kw}kW")
                
            elif mode == "self_use":
                # Set to Self Use mode
                await self.hass.services.async_call(
                    "select",
                    "select_option",
                    {
                        "entity_id": self.battery_mode_select,
                        "option": "Self Use",
                    },
                    blocking=True,
                )
                
                _LOGGER.info("Applied Self Use mode")
                
            elif mode == "backup":
                # Set to Backup mode (preserves battery)
                await self.hass.services.async_call(
                    "select",
                    "select_option",
                    {
                        "entity_id": self.battery_mode_select,
                        "option": "Backup",
                    },
                    blocking=True,
                )
                
                _LOGGER.info("Applied Backup mode")
            
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
