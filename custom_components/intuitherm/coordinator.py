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

        _LOGGER.info(
            "IntuiTherm coordinator initialized (service: %s, interval: %s)",
            self.service_url,
            update_interval,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from IntuiTherm service."""
        _LOGGER.debug("Fetching data from IntuiTherm service")

        try:
            async with asyncio.timeout(10):
                # Fetch all endpoints in parallel for efficiency
                health_task = self._fetch_json(ENDPOINT_HEALTH)
                status_task = self._fetch_json(ENDPOINT_CONTROL_STATUS)
                metrics_task = self._fetch_json(ENDPOINT_METRICS, params={"period_hours": 1})

                health, status, metrics = await asyncio.gather(
                    health_task,
                    status_task,
                    metrics_task,
                    return_exceptions=True,
                )

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

            _LOGGER.debug("Data fetch complete")
            return data

        except asyncio.TimeoutError as err:
            raise UpdateFailed(f"Timeout fetching data from service: {err}") from err
        except Exception as err:
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
