"""Lab-only glue: never loaded by production configurations."""
import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import binary_sensor, event, text_sensor
from esphome.const import CONF_ID

AUTO_LOAD = ["binary_sensor", "event", "text_sensor", "json"]
DEPENDENCIES = ["host", "api"]
VirtualDeck = cg.esphome_ns.namespace("virtual_deck").class_("VirtualDeck", cg.Component)

CONFIG_SCHEMA = cv.Schema({
    cv.GenerateID(): cv.declare_id(VirtualDeck),
    cv.Required("session"): text_sensor.text_sensor_schema(),
    cv.Required("keys"): cv.All(cv.ensure_list(cv.Schema({
        cv.Required("key"): cv.int_range(min=0, max=14),
        cv.Required("state"): binary_sensor.binary_sensor_schema(),
        cv.Required("edge"): event.event_schema(device_class="button"),
    })), cv.Length(min=15, max=15)),
}).extend(cv.COMPONENT_SCHEMA)


async def to_code(config):
    cg.add_build_flag("-I/lab/components/virtual_deck")
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    session = await text_sensor.new_text_sensor(config["session"])
    cg.add(var.set_session_sensor(session))
    for key in config["keys"]:
        state = await binary_sensor.new_binary_sensor(key["state"])
        edge = await event.new_event(key["edge"], event_types=["press", "release"])
        cg.add(var.set_key(key["key"], state, edge))
