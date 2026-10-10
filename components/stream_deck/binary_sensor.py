import esphome.codegen as cg
from esphome.components import binary_sensor
import esphome.config_validation as cv

from . import CONF_DECK_ID, KEY, StreamDeck


def validate(config):
    if config.get("filters") or config.get("trigger_on_initial_state") or config.get("publish_initial_state"):
        raise cv.Invalid("Key filters and initial-state triggers conflict with reconnect edge synchronization")
    return config


CONFIG_SCHEMA = cv.All(binary_sensor.binary_sensor_schema().extend({
    cv.GenerateID(CONF_DECK_ID): cv.use_id(StreamDeck),
    cv.Required("key"): KEY,
}), validate)


async def to_code(config):
    var = await binary_sensor.new_binary_sensor(config)
    parent = await cg.get_variable(config[CONF_DECK_ID])
    cg.add(var.set_trigger_on_initial_state(False))
    cg.add(parent.set_key_sensor(config["key"], var))
