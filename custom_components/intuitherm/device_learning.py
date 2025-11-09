"""Device learning system for IntuiTherm.

Collects user configurations for unknown devices and optionally shares
them with the community to improve auto-detection.
"""
from __future__ import annotations

import json
import logging
from typing import Any
from datetime import datetime

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.storage import Store

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_device_learning"

# Community learning service endpoint (optional)
COMMUNITY_SERVICE_URL = "https://api.intuihems.io/api/v1/device-learning"


class DeviceLearningStore:
    """Store and manage learned device configurations."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize device learning store."""
        self.hass = hass
        self._store = Store[dict[str, Any]](hass, STORAGE_VERSION, STORAGE_KEY)
        self._data: dict[str, Any] = {}

    async def async_load(self) -> None:
        """Load learned devices from storage."""
        stored = await self._store.async_load()
        if stored:
            self._data = stored
            _LOGGER.info(
                "Loaded %d learned device configurations",
                len(self._data.get("learned_devices", [])),
            )

    async def async_save_device_config(
        self,
        device_info: dict[str, Any],
        control_entities: dict[str, str],
        user_notes: str | None = None,
        share_with_community: bool = False,
    ) -> None:
        """Save a learned device configuration.

        Args:
            device_info: Device information (platform, manufacturer, model)
            control_entities: Selected control entities
            user_notes: Optional notes from the user
            share_with_community: Whether to submit to community database
        """
        # Create learned device entry
        learned_device = {
            "platform": device_info.get("platform"),
            "manufacturer": device_info.get("manufacturer"),
            "model": device_info.get("model"),
            "control_entities": control_entities,
            "user_notes": user_notes,
            "learned_at": datetime.now().isoformat(),
            "times_used": 1,
            "success_rate": 1.0,  # Track if auto-detection works
        }

        # Add to local storage
        if "learned_devices" not in self._data:
            self._data["learned_devices"] = []

        # Check if similar device already exists
        existing_idx = self._find_similar_device(device_info)
        if existing_idx is not None:
            # Update existing entry
            existing = self._data["learned_devices"][existing_idx]
            existing["times_used"] += 1
            existing["control_entities"] = control_entities  # Update with latest
            _LOGGER.info(
                "Updated existing learned device: %s %s (used %d times)",
                device_info.get("manufacturer"),
                device_info.get("model"),
                existing["times_used"],
            )
        else:
            # Add new entry
            self._data["learned_devices"].append(learned_device)
            _LOGGER.info(
                "Saved new learned device: %s %s",
                device_info.get("manufacturer"),
                device_info.get("model"),
            )

        # Save to storage
        await self._store.async_save(self._data)

        # Optionally share with community
        if share_with_community:
            await self._share_with_community(learned_device)

    def _find_similar_device(self, device_info: dict[str, Any]) -> int | None:
        """Find index of similar device in learned devices.

        Args:
            device_info: Device info to match

        Returns:
            Index of matching device, or None if not found
        """
        platform = device_info.get("platform", "").lower()
        manufacturer = device_info.get("manufacturer", "").lower()
        model = device_info.get("model", "").lower()

        for idx, learned in enumerate(self._data.get("learned_devices", [])):
            if (
                learned.get("platform", "").lower() == platform
                and learned.get("manufacturer", "").lower() == manufacturer
                and learned.get("model", "").lower() == model
            ):
                return idx

        return None

    def get_learned_patterns(
        self, device_info: dict[str, Any]
    ) -> dict[str, str] | None:
        """Get learned control entity patterns for a device.

        Args:
            device_info: Device info to look up

        Returns:
            Control entities dict if found, None otherwise
        """
        idx = self._find_similar_device(device_info)
        if idx is not None:
            learned = self._data["learned_devices"][idx]
            _LOGGER.info(
                "Found learned patterns for %s %s (used %d times, success rate: %.1f%%)",
                device_info.get("manufacturer"),
                device_info.get("model"),
                learned.get("times_used", 0),
                learned.get("success_rate", 0) * 100,
            )
            return learned.get("control_entities")

        return None

    async def _share_with_community(self, learned_device: dict[str, Any]) -> None:
        """Share learned device configuration with community database.

        Args:
            learned_device: Device configuration to share
        """
        try:
            # Prepare payload (remove personal info)
            payload = {
                "platform": learned_device["platform"],
                "manufacturer": learned_device["manufacturer"],
                "model": learned_device["model"],
                "control_entity_patterns": self._extract_patterns(
                    learned_device["control_entities"]
                ),
                "notes": learned_device.get("user_notes"),
                "source": "intuitherm_ha_integration",
                "version": "1.0",
            }

            # Submit to community service
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{COMMUNITY_SERVICE_URL}/submit",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        _LOGGER.info(
                            "Successfully shared device config with community: %s %s",
                            learned_device["manufacturer"],
                            learned_device["model"],
                        )
                    else:
                        _LOGGER.warning(
                            "Failed to share with community (status %d)",
                            response.status,
                        )

        except aiohttp.ClientError as err:
            _LOGGER.debug("Could not share with community: %s", err)
        except Exception as err:
            _LOGGER.error("Error sharing with community: %s", err, exc_info=True)

    def _extract_patterns(self, control_entities: dict[str, str]) -> dict[str, list[str]]:
        """Extract patterns from entity IDs.

        Args:
            control_entities: Dict of control entity IDs

        Returns:
            Dict of patterns extracted from entity IDs
        """
        patterns = {}

        for key, entity_id in control_entities.items():
            if not entity_id:
                continue

            # Extract the meaningful part (after domain and before unique ID)
            # e.g., "select.foxess_work_mode" -> "work_mode"
            parts = entity_id.split(".")
            if len(parts) >= 2:
                pattern = parts[1]  # Everything after the domain
                # Remove common prefixes (manufacturer names, etc.)
                pattern = self._clean_pattern(pattern)

                if key not in patterns:
                    patterns[key] = []
                patterns[key].append(pattern)

        return patterns

    def _clean_pattern(self, pattern: str) -> str:
        """Clean pattern by removing manufacturer-specific prefixes.

        Args:
            pattern: Raw pattern from entity ID

        Returns:
            Cleaned pattern
        """
        # Common prefixes to remove
        prefixes = [
            "foxess_",
            "solis_",
            "huawei_",
            "solaredge_",
            "growatt_",
            "inverter_",
            "battery_",
        ]

        pattern_lower = pattern.lower()
        for prefix in prefixes:
            if pattern_lower.startswith(prefix):
                pattern = pattern[len(prefix) :]
                break

        return pattern

    async def fetch_community_suggestions(
        self, device_info: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Fetch community-learned patterns for a device.

        Args:
            device_info: Device info to query

        Returns:
            List of community suggestions
        """
        try:
            params = {
                "platform": device_info.get("platform"),
                "manufacturer": device_info.get("manufacturer"),
                "model": device_info.get("model"),
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{COMMUNITY_SERVICE_URL}/suggest",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        suggestions = data.get("suggestions", [])
                        _LOGGER.info(
                            "Found %d community suggestions for %s %s",
                            len(suggestions),
                            device_info.get("manufacturer"),
                            device_info.get("model"),
                        )
                        return suggestions

        except aiohttp.ClientError as err:
            _LOGGER.debug("Could not fetch community suggestions: %s", err)
        except Exception as err:
            _LOGGER.error(
                "Error fetching community suggestions: %s", err, exc_info=True
            )

        return []

    def get_all_learned_devices(self) -> list[dict[str, Any]]:
        """Get all learned device configurations.

        Returns:
            List of learned devices
        """
        return self._data.get("learned_devices", [])

    async def delete_learned_device(self, device_index: int) -> bool:
        """Delete a learned device configuration.

        Args:
            device_index: Index of device to delete

        Returns:
            True if deleted, False if not found
        """
        learned_devices = self._data.get("learned_devices", [])
        if 0 <= device_index < len(learned_devices):
            deleted = learned_devices.pop(device_index)
            await self._store.async_save(self._data)
            _LOGGER.info(
                "Deleted learned device: %s %s",
                deleted.get("manufacturer"),
                deleted.get("model"),
            )
            return True

        return False

    async def update_success_rate(
        self, device_info: dict[str, Any], success: bool
    ) -> None:
        """Update success rate for a learned device.

        Args:
            device_info: Device info
            success: Whether auto-detection was successful
        """
        idx = self._find_similar_device(device_info)
        if idx is not None:
            learned = self._data["learned_devices"][idx]
            times_used = learned.get("times_used", 1)
            current_rate = learned.get("success_rate", 1.0)

            # Update running average
            new_rate = (current_rate * (times_used - 1) + (1.0 if success else 0.0)) / times_used
            learned["success_rate"] = new_rate

            await self._store.async_save(self._data)
            _LOGGER.debug(
                "Updated success rate for %s %s: %.1f%%",
                device_info.get("manufacturer"),
                device_info.get("model"),
                new_rate * 100,
            )


async def async_setup_device_learning(hass: HomeAssistant) -> DeviceLearningStore:
    """Set up device learning system.

    Args:
        hass: Home Assistant instance

    Returns:
        DeviceLearningStore instance
    """
    store = DeviceLearningStore(hass)
    await store.async_load()
    return store
