"""Original 0FD9:0060 only. Owns the native IDF USB host exclusively."""
import struct
import re
from pathlib import Path

from esphome import automation
import esphome.codegen as cg
from esphome.components import binary_sensor as binary_sensor_component, esp32, sensor, text_sensor
import esphome.config_validation as cv
from esphome.const import CONF_ID, CONF_FILE
from esphome.core import CORE, HexInt
from esphome.coroutine import CoroPriority, coroutine_with_priority
import esphome.final_validate as fv

DEPENDENCIES = ["esp32"]
CONFLICTS_WITH = ["usb_host", "tinyusb"]
MULTI_CONF = False


def AUTO_LOAD(config):
    base = ["binary_sensor", "number", "sensor"]
    return base + ["text_sensor", "sha256"] if not config or "runtime_visuals" in config else base

deck_ns = cg.esphome_ns.namespace("stream_deck")
StreamDeck = deck_ns.class_("StreamDeck", cg.Component)
NativeImage = deck_ns.namespace("protocol").class_("NativeImage")
SetImageAction = deck_ns.class_("SetImageAction", automation.Action)
RedrawAction = deck_ns.class_("RedrawAction", automation.Action)
CONF_DECK_ID = "stream_deck_id"
KEY = cv.int_range(min=0, max=14)


def asset_origin(value):
    value = cv.string_strict(value)
    match = re.fullmatch(r"(https?)://([A-Za-z0-9.-]+)(?::([0-9]{1,5}))?", value)
    if not match or len(value) > 280:
        raise cv.Invalid("Expected an HTTP/HTTPS origin only, without credentials, path, query or fragment")
    scheme, host, port = match.groups()
    if len(host) > 253 or any(not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
                              for label in host.split(".")) or (port and not 1 <= int(port) <= 65535):
        raise cv.Invalid("Invalid asset origin host or port")
    return value


def asset_certificate(value):
    path = cv.file_(value)
    data = path.read_text()
    if len(data.encode()) > 16384 or "-----BEGIN CERTIFICATE-----" not in data or "PRIVATE KEY" in data:
        raise cv.Invalid("Expected a public CA certificate PEM, at most 16 KiB, without private keys")
    return path


ASSET_SCHEMA = cv.Schema({
    cv.Required("allowed_origins"): cv.All(cv.ensure_list(asset_origin), cv.Length(min=1, max=4)),
    cv.Optional("ca_certificate"): asset_certificate,
})


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
        cv.Optional("input_report_id", default=0x01): cv.hex_uint8_t,
        cv.Optional("usb_diagnostics", default=False): cv.boolean,
        cv.Optional("asset_loading"): ASSET_SCHEMA,
        cv.Optional("runtime_visuals"): cv.Schema({
            cv.Required("session"): text_sensor.text_sensor_schema(entity_category="diagnostic"),
        }),
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
    if "runtime_visuals" in config:
        if "asset_loading" not in config or "psram" not in full:
            raise cv.Invalid("runtime_visuals requires asset_loading and psram")
        if "encryption" not in full.get("api", {}):
            raise cv.Invalid("runtime_visuals requires encrypted native api")
        if config["images"] or "on_key_press" in config or "on_key_release" in config:
            raise cv.Invalid("runtime_visuals owns artwork; use HA key events instead of local images/key automations")
    for platform, field in (("binary_sensor", "key"), ("event", "key"), ("number", None)):
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
    esp32.add_idf_sdkconfig_option("CONFIG_USB_HOST_HW_BUFFER_BIAS_BALANCED", False)
    esp32.add_idf_sdkconfig_option("CONFIG_USB_HOST_HW_BUFFER_BIAS_IN", False)
    esp32.add_idf_sdkconfig_option("CONFIG_USB_HOST_HW_BUFFER_BIAS_PERIODIC_OUT", True)


@coroutine_with_priority(CoroPriority.FINAL - 10)
async def asset_sdkconfig():
    for name in ("CONFIG_ESP_HTTP_CLIENT_ENABLE_HTTPS", "CONFIG_ESP_HTTP_CLIENT_ENABLE_CUSTOM_TRANSPORT",
                 "CONFIG_MBEDTLS_CERTIFICATE_BUNDLE", "CONFIG_MBEDTLS_CERTIFICATE_BUNDLE_DEFAULT_FULL",
                 "CONFIG_MBEDTLS_HAVE_TIME", "CONFIG_MBEDTLS_HAVE_TIME_DATE"):
        esp32.add_idf_sdkconfig_option(name, True)
    for name in ("CONFIG_ESP_TLS_INSECURE", "CONFIG_ESP_TLS_SKIP_SERVER_CERT_VERIFY"):
        esp32.add_idf_sdkconfig_option(name, False)


async def to_code(config):
    esp32.include_builtin_idf_component("usb")
    esp32.add_extra_build_file("src/esphome/components/stream_deck/third_party/miniz.inc",
                              Path(__file__).parent / "third_party/miniz.inc")
    # A project component named usb overrides the built-in component. Copy only
    # our build recipe/helper; its CMake reads the pinned SDK without editing it.
    for name in ("CMakeLists.txt", "Kconfig", "prepare.py", "stream_deck_quirk.h", "link_application.cmake"):
        esp32.add_extra_build_file(f"components/usb/{name}", Path(__file__).parent / "idf_usb" / name)
    # IDF's cap sizes enumeration/configuration data stages. The dedicated client
    # buffer separately includes the 8-byte setup header (8199 bytes minimum).
    CORE.add_job(usb_sdkconfig)
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    if "asset_loading" in config:
        cg.add_define("USE_STREAM_DECK_ASSETS")
        # The shared IDF HTTP parser also sees chunked trailers. Bound it as
        # well as the transport's initial-header/wire counters.
        cg.add_build_flag("-DHTTP_MAX_HEADER_SIZE=8192")
        for component in ("esp_http_client", "esp-tls", "tcp_transport"):
            esp32.include_builtin_idf_component(component)
        CORE.add_job(asset_sdkconfig)
        for origin in config["asset_loading"]["allowed_origins"]:
            cg.add(var.add_asset_origin(origin))
        if "ca_certificate" in config["asset_loading"]:
            cg.add(var.set_asset_ca(config["asset_loading"]["ca_certificate"].read_text()))
    if "runtime_visuals" in config:
        cg.add_define("USE_STREAM_DECK_RUNTIME_API")
        entity = await text_sensor.new_text_sensor(config["runtime_visuals"]["session"])
        cg.add(var.set_visual_session_sensor(entity))
    cg.add(var.set_brightness(config["initial_brightness"]))
    cg.add(var.set_usb_diagnostics(config["usb_diagnostics"]))
    if "input_report_id" in config:
        cg.add(var.set_input_report_id(config["input_report_id"]))
    if "connected" in config:
        connected = await binary_sensor_component.new_binary_sensor(config["connected"])
        cg.add(var.set_connected_sensor(connected))
    for name, setter in DIAGNOSTICS.items():
        if name in config:
            entity = await sensor.new_sensor(config[name])
            cg.add(getattr(var, setter)(entity))
    # Key automations can reference this hub's own images. Declare the assets
    # before awaiting action generation, or get_variable(image) deadlocks here.
    for asset in config["images"]:
        data = asset[CONF_FILE].read_bytes()
        raw = cg.progmem_array(asset["raw_data_id"], [HexInt(byte) for byte in data])
        cg.new_Pvariable(asset[CONF_ID], raw, len(data))
    for name, getter in (("on_key_press", "get_press_trigger"), ("on_key_release", "get_release_trigger")):
        if name in config:
            await automation.build_automation(getattr(var, getter)(), [(cg.uint8, "key")], config[name])


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
