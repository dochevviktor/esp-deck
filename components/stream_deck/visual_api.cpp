#include "visual_api.h"

namespace esphome::stream_deck::visual {
Response Api::snapshot_(int32_t key, int32_t revision) const {
  Response result;
  result.session = session_;
  result.key = key;
  result.request_revision = revision;
  if (store_) {
    const auto *status = store_->status(key);
    if (status) result.status = *status;
    if (status) {
      result.applied_revision = store_->applied_revision(key);
      result.usb_generation = store_->generation();
      result.context.assign(store_->context(key));
    }
  }
  return result;
}

Response Api::set(const Command &command) {
  if (!pipeline_) return snapshot_(command.key, command.revision);
  const auto submission = pipeline_->submit(command);
  auto result = snapshot_(command.key, command.revision);
  result.accepted = submission.accepted;
  result.error = submission.error;
  return result;
}

Response Api::get(std::string_view session, int32_t key) const {
  auto result = snapshot_(key, 0);
  if (!store_) return result;
  if (!store_->status(key)) result.error = Error::INVALID_KEY;
  else if (!store_->matches_session(session)) result.error = Error::WRONG_SESSION;
  else {
    result.accepted = true;
    result.error = result.status.error;
  }
  return result;
}

Response Api::clear(std::string_view session, int32_t key, int32_t revision) {
  Command command;
  command.session = session; command.key = key; command.revision = revision;
  command.fields = IMAGE | TEXT;
  return set(command);
}

Response Api::refresh(std::string_view session, int32_t key, int32_t revision, std::string_view image_revision) {
  auto check = get(session, key);
  check.request_revision = revision;
  if (!check.accepted) return check;
  const auto *desired = store_->desired(key);
  if (desired->image_url.empty() || image_revision.empty()) {
    check.accepted = false;
    check.error = desired->image_url.empty() ? Error::INVALID_URL : Error::INVALID_IMAGE_REVISION;
    return check;
  }
  Command command;
  command.session = session; command.key = key; command.revision = revision;
  command.fields = IMAGE;
  command.image_url = desired->image_url.view(); command.image_revision = image_revision;
  return set(command);
}
}  // namespace esphome::stream_deck::visual
