"""Original 0FD9:0060 only. Owns the native IDF USB host exclusively."""
import struct

from esphome import automation
import esphome.codegen as cg
from esphome.components import binary_sensor as binary_sensor_component, esp32, sensor
import esphome.config_validation as cv
from esphome.const import CONF_ID, CONF_FILE
from esphome.core import CORE, HexInt
from esphome.coroutine import CoroPriority, coroutine_with_priority
import esphome.final_validate as fv

DEPENDENCIES = ["esp32"]
CONFLICTS_WITH = ["usb_host", "tinyusb"]
AUTO_LOAD = ["binary_sensor", "number", "sensor"]
MULTI_CONF = False

deck_ns = cg.esphome_ns.namespace("stream_deck")
StreamDeck = deck_ns.class_("StreamDeck", cg.Component)
NativeImage = deck_ns.namespace("protocol").class_("NativeImage")
SetImageAction = deck_ns.class_("SetImageAction", automation.Action)
RedrawAction = deck_ns.class_("RedrawAction", automation.Action)
CONF_DECK_ID = "stream_deck_id"
KEY = cv.int_range(min=0, max=14)


def native_bmp(value):
    path = cv.file_(value)
    data = path.read_bytes()
    if len(data) != 15606 or data[:2] != b"BM":
        raise cv.Invalid("Expected a 15,606-byte native 72x72 BMP; use tools/convert_assets.py")
    checks = ((2, "I", 15606), (6, "I", 0), (10, "I", 54), (14, "I", 40),
              (18, "I", 72), (22, "I", 72), (26, "H", 1), (28, "H", 24),
              (30, "I", 0), (34, "I", 15552), (46, "I", 0), (50, "I", 0))
    if any(struct.unpack_from("<" + fmt, data, offset)[0] != expected for offset, fmt, expected in checks):
        raise cv.Invalid("Unsupported native BMP layout; use tools/convert_assets.py")
    return path


IMAGE_SCHEMA = cv.Schema({
    cv.Required(CONF_ID): cv.declare_id(NativeImage),
    cv.GenerateID("raw_data_id"): cv.declare_id(cg.uint8),
    cv.Required(CONF_FILE): native_bmp,
})

DIAGNOSTICS = {"errors": "set_error_sensor", "input_overflows": "set_overflow_sensor",
               "input_queue_high_water": "set_high_water_sensor", "internal_free_heap": "set_heap_sensor",
               "internal_minimum_free_heap": "set_min_heap_sensor"}

CONFIG_SCHEMA = cv.All(
    cv.Schema({
        cv.GenerateID(): cv.declare_id(StreamDeck),
        cv.Optional("initial_brightness", default=30): cv.int_range(min=0, max=100),
        cv.Optional("input_report_id"): cv.hex_uint8_t,
        cv.Optional("images", default=[]): cv.ensure_list(IMAGE_SCHEMA),
        cv.Optional("connected"): binary_sensor_component.binary_sensor_schema(
            device_class="connectivity", entity_category="diagnostic"),
        cv.Optional("on_key_press"): automation.validate_automation(single=True),
        cv.Optional("on_key_release"): automation.validate_automation(single=True),
        **{cv.Optional(name): sensor.sensor_schema(accuracy_decimals=0, entity_category="diagnostic")
           for name in DIAGNOSTICS},
    }).extend(cv.COMPONENT_SCHEMA),
    esp32.only_on_variant(supported=[esp32.VARIANT_ESP32S3]),
)


def final_validate(config):
    full = fv.full_config.get()
    if full["esp32"]["framework"]["type"] != "esp-idf":
        raise cv.Invalid("stream_deck requires ESP-IDF")
    if full.get("logger", {}).get("hardware_uart") != "UART0":
        raise cv.Invalid("stream_deck requires logger.hardware_uart: UART0; native USB belongs to the host")
    for platform, field in (("binary_sensor", "key"), ("number", None)):
        seen = set()
        for entity in full.get(platform, []):
            if entity.get("platform") != "stream_deck":
                continue
            identity = (str(entity[CONF_DECK_ID]), entity.get(field) if field else "brightness")
            if identity in seen:
                raise cv.Invalid(f"Duplicate stream_deck {field or 'brightness'} binding")
            seen.add(identity)
    return config


FINAL_VALIDATE_SCHEMA = final_validate


@coroutine_with_priority(CoroPriority.FINAL - 10)
async def usb_sdkconfig():
    # The pinned logger enables the USB secondary console even for UART0.
    # Apply exclusive host ownership after core/logger SDK defaults.
    esp32.add_idf_sdkconfig_option("CONFIG_ESP_CONSOLE_SECONDARY_USB_SERIAL_JTAG", False)
    esp32.add_idf_sdkconfig_option("CONFIG_ESP_CONSOLE_SECONDARY_NONE", True)
    esp32.add_idf_sdkconfig_option("CONFIG_USB_HOST_CONTROL_TRANSFER_MAX_SIZE", 8192)
    esp32.add_idf_sdkconfig_option("CONFIG_USB_HOST_HUBS_SUPPORTED", False)


async def to_code(config):
    esp32.include_builtin_idf_component("usb")
    # IDF's cap sizes enumeration/configuration data stages. The dedicated client
    # buffer separately includes the 8-byte setup header (8199 bytes minimum).
    CORE.add_job(usb_sdkconfig)
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    cg.add(var.set_brightness(config["initial_brightness"]))
    if "input_report_id" in config:
        cg.add(var.set_input_report_id(config["input_report_id"]))
    if "connected" in config:
        connected = await binary_sensor_component.new_binary_sensor(config["connected"])
        cg.add(var.set_connected_sensor(connected))
    for name, setter in DIAGNOSTICS.items():
        if name in config:
            entity = await sensor.new_sensor(config[name])
            cg.add(getattr(var, setter)(entity))
    for name, getter in (("on_key_press", "get_press_trigger"), ("on_key_release", "get_release_trigger")):
        if name in config:
            await automation.build_automation(getattr(var, getter)(), [(cg.uint8, "key")], config[name])
    for asset in config["images"]:
        data = asset[CONF_FILE].read_bytes()
        raw = cg.progmem_array(asset["raw_data_id"], [HexInt(byte) for byte in data])
        cg.new_Pvariable(asset[CONF_ID], raw, len(data))


@automation.register_action("stream_deck.set_image", SetImageAction, cv.Schema({
    cv.Required(CONF_ID): cv.use_id(StreamDeck),
    cv.Required("key"): cv.templatable(KEY),
    cv.Required("image"): cv.use_id(NativeImage),
}), synchronous=True)
async def set_image_to_code(config, action_id, template_arg, args):
    parent = await cg.get_variable(config[CONF_ID])
    image = await cg.get_variable(config["image"])
    var = cg.new_Pvariable(action_id, template_arg, parent, image)
    key = await cg.templatable(config["key"], args, cg.int_)
    cg.add(var.set_key(key))
    return var


@automation.register_action("stream_deck.redraw", RedrawAction,
                            cv.maybe_simple_value({cv.Required(CONF_ID): cv.use_id(StreamDeck)}, key=CONF_ID),
                            synchronous=True)
async def redraw_to_code(config, action_id, template_arg, args):
    parent = await cg.get_variable(config[CONF_ID])
    return cg.new_Pvariable(action_id, template_arg, parent)
