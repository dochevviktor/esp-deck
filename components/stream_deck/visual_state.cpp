#include "visual_state.h"

namespace esphome::stream_deck::visual {
namespace {
bool alnum(char c) {
  return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9');
}
int hex(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}
bool parse_hex(std::string_view value, uint64_t &out) {
  out = 0;
  for (char c : value) {
    const int digit = hex(c);
    if (digit < 0) return false;
    out = (out << 4) | unsigned(digit);
  }
  return true;
}
bool color(std::string_view value, uint32_t &out) {
  uint64_t parsed;
  if (value.size() != 7 || value[0] != '#' || !parse_hex(value.substr(1), parsed)) return false;
  out = uint32_t(parsed);
  return true;
}
}  // namespace

bool valid_url(std::string_view url) {
  if (url.empty() || url.size() > MAX_URL_BYTES) return false;
  // V1 deliberately has no URL credentials, signed queries, fragments, IPv6
  // literals or redirects. P3 additionally requires an exact allowed origin.
  size_t start;
  if (url.substr(0, 7) == "http://") start = 7;
  else if (url.substr(0, 8) == "https://") start = 8;
  else return false;
  for (size_t i = 0; i < url.size(); i++) {
    const auto c = uint8_t(url[i]);
    if (c <= 0x20 || c >= 0x7f || c == '@' || c == '?' || c == '#' || c == '\\') return false;
    if (c == '%') {
      if (i + 2 >= url.size() || hex(url[i + 1]) < 0 || hex(url[i + 2]) < 0) return false;
      i += 2;
    }
  }
  const auto slash = url.find('/', start);
  const auto authority = url.substr(start, slash == std::string_view::npos ? slash : slash - start);
  const auto colon = authority.find(':');
  auto host = authority.substr(0, colon);
  if (host.empty() || host.size() > 253) return false;
  if (colon != std::string_view::npos) {
    const auto port = authority.substr(colon + 1);
    if (port.empty() || port.size() > 5) return false;
    unsigned number = 0;
    for (char c : port) {
      if (c < '0' || c > '9') return false;
      number = number * 10 + unsigned(c - '0');
    }
    if (number == 0 || number > 65535) return false;
  }
  while (!host.empty()) {
    const auto dot = host.find('.');
    const auto label = host.substr(0, dot);
    if (label.empty() || label.size() > 63 || !alnum(label.front()) || !alnum(label.back())) return false;
    for (char c : label) if (!alnum(c) && c != '-') return false;
    if (dot == std::string_view::npos) break;
    host.remove_prefix(dot + 1);
    if (host.empty()) return false;
  }
  return true;
}
Error decode_label(std::string_view text, std::array<uint32_t, MAX_LABEL_CODEPOINTS> &points, size_t &count) {
  count = 0;
  if (text.size() > MAX_LABEL_BYTES) return Error::LIMIT_EXCEEDED;
  for (size_t offset = 0; offset < text.size();) {
    const auto first = uint8_t(text[offset++]);
    uint32_t point;
    size_t extra;
    uint32_t minimum;
    if (first < 0x80) { point = first; extra = 0; minimum = 0; }
    else if (first >= 0xc2 && first <= 0xdf) { point = first & 0x1f; extra = 1; minimum = 0x80; }
    else if (first >= 0xe0 && first <= 0xef) { point = first & 0x0f; extra = 2; minimum = 0x800; }
    else if (first >= 0xf0 && first <= 0xf4) { point = first & 0x07; extra = 3; minimum = 0x10000; }
    else return Error::INVALID_TEXT;
    if (extra > text.size() - offset) return Error::INVALID_TEXT;
    for (size_t n = 0; n < extra; n++) {
      const auto c = uint8_t(text[offset++]);
      if ((c & 0xc0) != 0x80) return Error::INVALID_TEXT;
      point = (point << 6) | (c & 0x3f);
    }
    if (point < minimum || point > 0x10ffff || (point >= 0xd800 && point <= 0xdfff) ||
        (point < 0x20 && point != '\n') || (point >= 0x7f && point <= 0x9f)) return Error::INVALID_TEXT;
    if (count == points.size()) return Error::LIMIT_EXCEEDED;
    points[count++] = point;
  }
  return Error::NONE;
}

bool State::operator==(const State &other) const {
  return image_url == other.image_url && image_revision == other.image_revision && text == other.text &&
         text_color == other.text_color && outline_color == other.outline_color &&
         background_color == other.background_color && font == other.font && fit == other.fit;
}

Error apply_patch(const Command &cmd, const State &base, State &result) {
  if (cmd.fields <= 0 || (cmd.fields & ~ALL_FIELDS) != 0) return Error::INVALID_FIELDS;
  // Even ignored placeholders have finite byte limits at the API boundary.
  if (cmd.image_url.size() > MAX_URL_BYTES || cmd.image_revision.size() > MAX_IMAGE_REVISION_BYTES ||
      cmd.text.size() > MAX_LABEL_BYTES || cmd.text_color.size() > 7 || cmd.outline_color.size() > 7 ||
      cmd.background_color.size() > 7 || cmd.fit.size() > 7) return Error::LIMIT_EXCEEDED;
  State candidate = base;
  if (cmd.fields & IMAGE) {
    if (cmd.image_url.empty()) {
      if (!cmd.image_revision.empty()) return Error::INVALID_IMAGE_REVISION;
    } else {
      if (!valid_url(cmd.image_url)) return Error::INVALID_URL;
      if (cmd.image_revision.empty()) return Error::INVALID_IMAGE_REVISION;
      for (char c : cmd.image_revision)
        if (!alnum(c) && c != '.' && c != '_' && c != '-' && c != ':') return Error::INVALID_IMAGE_REVISION;
    }
    candidate.image_url.assign(cmd.image_url);
    candidate.image_revision.assign(cmd.image_revision);
  }
  if (cmd.fields & TEXT) {
    std::array<uint32_t, MAX_LABEL_CODEPOINTS> points;
    size_t count;
    const auto error = decode_label(cmd.text, points, count);
    if (error != Error::NONE) return error;
    candidate.text.assign(cmd.text);
  }
  if (cmd.fields & FONT) {
    if (cmd.font != 12 && cmd.font != 16 && cmd.font != 20) return Error::INVALID_FONT;
    candidate.font = uint8_t(cmd.font);
  }
  if ((cmd.fields & TEXT_COLOR) && !color(cmd.text_color, candidate.text_color)) return Error::INVALID_COLOR;
  if ((cmd.fields & OUTLINE_COLOR) && !color(cmd.outline_color, candidate.outline_color)) return Error::INVALID_COLOR;
  if ((cmd.fields & BACKGROUND_COLOR) && !color(cmd.background_color, candidate.background_color)) return Error::INVALID_COLOR;
  if (cmd.fields & FIT) {
    if (cmd.fit == "contain") candidate.fit = Fit::CONTAIN;
    else if (cmd.fit == "crop") candidate.fit = Fit::CROP;
    else return Error::INVALID_FIT;
  }
  result = candidate;
  return Error::NONE;
}

Submission Store::submit(const Command &cmd) {
  if (protocol::wire_key(cmd.key) < 0) return {false, Error::INVALID_KEY};
  auto &slot = slots_[cmd.key];
  const auto reject = [&](Error error) { return Submission{false, error, slot.status.phase, slot.status.revision}; };
  uint64_t session;
  if (cmd.session.size() != 16 || !parse_hex(cmd.session, session) || session != session_)
    return reject(Error::WRONG_SESSION);
  if (cmd.revision <= 0) return reject(Error::INVALID_REVISION);
  if (uint32_t(cmd.revision) < slot.status.revision) return reject(Error::STALE_REVISION);
  State state;
  const auto error = apply_patch(cmd, slot.desired, state);
  if (error != Error::NONE) return reject(error);
  if (uint32_t(cmd.revision) == slot.status.revision) {
    if (cmd.fields != slot.fields || !(state == slot.desired)) return reject(Error::REVISION_CONFLICT);
    return {true, slot.status.error, slot.status.phase, slot.status.revision};
  }
  slot.desired = state;
  slot.fields = cmd.fields;
  slot.status.revision = uint32_t(cmd.revision);
  slot.status.error = Error::NONE;
  if (slot.status.rendered_revision != 0 && state == slot.rendered) {
    slot.status.rendered_revision = slot.status.revision;
    slot.status.phase = Phase::RENDERED;
  } else {
    slot.status.phase = Phase::QUEUED;
  }
  return {true, Error::NONE, slot.status.phase, slot.status.revision};
}
const Status *Store::status(int key) const {
  return protocol::wire_key(key) < 0 ? nullptr : &slots_[key].status;
}
const State *Store::desired(int key) const {
  return protocol::wire_key(key) < 0 ? nullptr : &slots_[key].desired;
}
bool Store::next(RenderJob &job) {
  if (active_) return false;
  for (size_t n = 0; n < protocol::KEY_COUNT; n++) {
    const auto key = uint8_t((cursor_ + n) % protocol::KEY_COUNT);
    auto &slot = slots_[key];
    if (slot.status.phase != Phase::QUEUED) continue;
    active_ = true;
    active_key_ = key;
    active_revision_ = slot.status.revision;
    slot.status.phase = Phase::RENDERING;
    job = {session_, ++token_, key, active_revision_, slot.desired};
    cursor_ = (key + 1) % protocol::KEY_COUNT;
    return true;
  }
  return false;
}
bool Store::matches_active_(const RenderJob &job) const {
  return active_ && job.session == session_ && job.token == token_ && job.key == active_key_ &&
         job.revision == active_revision_;
}
bool Store::finish(const RenderJob &job, const ImageRef &image) {
  if (!matches_active_(job)) return false;
  if (!image) {
    fail(job, Error::RENDER_FAILED);
    return false;
  }
  active_ = false;
  auto &slot = slots_[job.key];
  if (slot.status.revision != job.revision) return false;
  if (!scheduler_.set_image(job.key, image)) return false;
  slot.rendered = slot.desired;
  slot.status.rendered_revision = job.revision;
  slot.status.phase = Phase::RENDERED;
  slot.status.error = Error::NONE;
  return true;
}
bool Store::fail(const RenderJob &job, Error error) {
  if (!matches_active_(job)) return false;
  active_ = false;
  auto &status = slots_[job.key].status;
  if (status.revision != job.revision) return false;
  status.phase = Phase::FAILED;
  status.error = error == Error::NONE ? Error::RENDER_FAILED : error;
  return true;
}

const char *error_name(Error error) {
  switch (error) {
    case Error::NONE: return "none";
    case Error::INVALID_KEY: return "invalid_key";
    case Error::WRONG_SESSION: return "wrong_session";
    case Error::INVALID_REVISION: return "invalid_revision";
    case Error::STALE_REVISION: return "stale_revision";
    case Error::REVISION_CONFLICT: return "revision_conflict";
    case Error::INVALID_FIELDS: return "invalid_fields";
    case Error::LIMIT_EXCEEDED: return "limit_exceeded";
    case Error::INVALID_URL: return "invalid_url";
    case Error::INVALID_IMAGE_REVISION: return "invalid_image_revision";
    case Error::INVALID_TEXT: return "invalid_text";
    case Error::INVALID_FONT: return "invalid_font";
    case Error::INVALID_COLOR: return "invalid_color";
    case Error::INVALID_FIT: return "invalid_fit";
    case Error::FETCH_FAILED: return "fetch_failed";
    case Error::DECODE_FAILED: return "decode_failed";
    case Error::RENDER_FAILED: return "render_failed";
    case Error::OUT_OF_MEMORY: return "out_of_memory";
    case Error::ORIGIN_NOT_ALLOWED: return "origin_not_allowed";
    case Error::FETCH_TIMEOUT: return "fetch_timeout";
    case Error::HTTP_STATUS: return "http_status";
    case Error::UNSUPPORTED_ENCODING: return "unsupported_encoding";
    case Error::UNSUPPORTED_PNG: return "unsupported_png";
    case Error::CLOCK_NOT_READY: return "clock_not_ready";
  }
  return "unknown";
}
const char *phase_name(Phase phase) {
  switch (phase) {
    case Phase::IDLE: return "idle";
    case Phase::QUEUED: return "queued";
    case Phase::RENDERING: return "rendering";
    case Phase::RENDERED: return "rendered";
    case Phase::FAILED: return "failed";
  }
  return "unknown";
}
}  // namespace esphome::stream_deck::visual
