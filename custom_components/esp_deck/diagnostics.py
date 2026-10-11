"""Deliberately omit credentials, addresses, layout text, images and action data."""


async def async_get_config_entry_diagnostics(hass, entry):
    controller = getattr(entry, "runtime_data", None)
    return {"integration_version": "0.6.0", "runtime_contract": 1,
            "status": controller.status() if controller else {"state": "not_loaded"}}
