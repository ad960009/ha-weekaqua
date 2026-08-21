"""Automatic Lovelace Frontend & Static Card Registration for WeekAqua."""

from __future__ import annotations
import logging
import os
import shutil

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

URL_BASE = "/weekaqua_static"
CARD_FILENAME = "weekaqua-card.js"
VERSION = "1.2.5"


def _prepare_card_files(current_dir: str, www_dir: str) -> str | None:
    """Synchronous file copy and validation executed in a background thread."""
    source_js = os.path.join(current_dir, "frontend", CARD_FILENAME)
    if not os.path.exists(source_js):
        source_js = os.path.join(current_dir, "..", "..", "dist", CARD_FILENAME)

    if not os.path.exists(source_js):
        return None

    try:
        if not os.path.exists(www_dir):
            os.makedirs(www_dir, exist_ok=True)
        dest_js = os.path.join(www_dir, CARD_FILENAME)
        shutil.copy2(source_js, dest_js)
    except Exception as err:
        _LOGGER.debug("Could not copy card to www folder: %s", err)

    return source_js


async def async_setup_frontend(hass: HomeAssistant) -> None:
    """Automatically host, copy, and register the WeekAqua card with Lovelace asynchronously."""
    current_dir = os.path.dirname(__file__)
    www_dir = hass.config.path("www")

    # Run blocking disk I/O in an executor thread to prevent event loop blocking
    source_js = await hass.async_add_executor_job(_prepare_card_files, current_dir, www_dir)

    if not source_js:
        _LOGGER.warning("WeekAqua Lovelace Card JS not found")
        return

    # 1. Host JS statically via HA HTTP server (/weekaqua_static/weekaqua-card.js)
    card_url = f"{URL_BASE}/{CARD_FILENAME}"
    try:
        if hasattr(hass.http, "async_register_static_paths"):
            await hass.http.async_register_static_paths([
                StaticPathConfig(card_url, source_js, cache_headers=False)
            ])
        else:
            hass.http.register_static_path(card_url, source_js, cache_headers=False)
    except Exception as err:
        _LOGGER.debug("Static path registration: %s", err)

    # 2. Add to extra_js_url (loads card globally across Lovelace without manual resource registration)
    try:
        add_extra_js_url(hass, f"{card_url}?v={VERSION}")
    except Exception as err:
        _LOGGER.debug("add_extra_js_url error: %s", err)

    # 3. Auto-register / update in Lovelace Resources Storage
    try:
        if "lovelace" in hass.data:
            lovelace = hass.data["lovelace"]
            if hasattr(lovelace, "resources"):
                resources = lovelace.resources
                if hasattr(resources, "loaded") and not resources.loaded:
                    await resources.async_load()
                if hasattr(resources, "async_items") and hasattr(resources, "async_create_item"):
                    existing = [
                        item for item in resources.async_items()
                        if item.get("url", "").startswith(URL_BASE) or item.get("url", "").startswith("/local/weekaqua-card")
                    ]
                    target_url = f"{card_url}?v={VERSION}"
                    if not existing:
                        await resources.async_create_item({
                            "res_type": "module",
                            "url": target_url,
                        })
                        _LOGGER.info("WeekAqua Card automatically registered into Lovelace Resources: %s", target_url)
                    else:
                        for item in existing:
                            if item.get("url") != target_url and hasattr(resources, "async_update_item"):
                                await resources.async_update_item(item["id"], {
                                    "res_type": "module",
                                    "url": target_url,
                                })
                                _LOGGER.info("WeekAqua Card resource automatically updated in Lovelace Resources: %s", target_url)
    except Exception as err:
        _LOGGER.debug("Lovelace resource storage auto-registration note: %s", err)
