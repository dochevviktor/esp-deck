"""Deliberately omit credentials, addresses, layout text, images and action data."""


async def async_get_config_entry_diagnostics(hass, entry):
    controller = getattr(entry, "runtime_data", None)
    status = controller.status() if controller else {"state": "not_loaded"}
    # Capabilities contain configured LAN addresses and a boot identity. Neither
    # belongs in an exported diagnostic or an HA status entity's public attributes.
    status["capabilities"] = {k: v for k, v in status.get("capabilities", {}).items() if k not in ("origins", "session")}
    return {"integration_version": "0.8.0", "runtime_contract": status["capabilities"].get("protocol_version", 1),
            "status": status}
