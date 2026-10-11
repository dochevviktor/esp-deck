"""Real physical edges only; state/initial synchronization stays in binary_sensor."""
import esphome.codegen as cg
from esphome.components import event
import esphome.config_validation as cv

from . import CONF_DECK_ID, KEY, StreamDeck

CONFIG_SCHEMA = event.event_schema(device_class="button").extend({
    cv.GenerateID(CONF_DECK_ID): cv.use_id(StreamDeck),
    cv.Required("key"): KEY,
})


async def to_code(config):
    cg.add_define("USE_STREAM_DECK_KEY_EVENTS")
    var = await event.new_event(config, event_types=["press", "release"])
    parent = await cg.get_variable(config[CONF_DECK_ID])
    cg.add(parent.set_key_event(config["key"], var))
