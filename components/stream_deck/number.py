import esphome.codegen as cg
from esphome.components import number
import esphome.config_validation as cv

from . import CONF_DECK_ID, StreamDeck, deck_ns

DeckBrightness = deck_ns.class_("DeckBrightness", number.Number, cg.Component)

CONFIG_SCHEMA = number.number_schema(DeckBrightness, unit_of_measurement="%", icon="mdi:brightness-6").extend({
    cv.GenerateID(CONF_DECK_ID): cv.use_id(StreamDeck),
}).extend(cv.COMPONENT_SCHEMA)


async def to_code(config):
    var = await number.new_number(config, min_value=0, max_value=100, step=1)
    await cg.register_component(var, config)
    parent = await cg.get_variable(config[CONF_DECK_ID])
    cg.add(var.set_parent(parent))
