# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.1.0] - 2026-11-07

### Added
- Camera entity for the `videoCapture` capability (Samsung ovens with a cooking camera). It shows the thumbnail of the latest clip from the SmartThings cloud and exposes `thumbnail_url`, `clip_url`, `clip_status`, `clip_time` and `clip_keys` attributes. It is created only when the device has reported a clip.
- Option "Fridge camera (View Inside): client id" (`viewinside_cid`). The fridge photo endpoint is undocumented; community projects call it with the Samsung app client id, so the integration adds it to the download request only when you set it.

### Fixed
- Camera images (imageCapture, generic image URL, new videoCapture) are downloaded with the integration's OAuth token. SmartThings media hosts refuse anonymous requests, so these cameras returned no image (HTTP 500 in the camera proxy). A plain request is still tried for pre-signed URLs.
- A refused media download no longer risks sending the config entry into re-authentication.
- Fridge camera (`samsungce.viewInside`): the photo is downloaded with the OAuth token from `file_links` with the device id; a photo link expires about 10 minutes after the fridge publishes it, so an expired or refused link now sends `viewInside.refreshAll` (at most once a minute) and the camera keeps the last photo meanwhile. New attributes: `captured_at`, `link_expires_at`, `focus_area`.
- imageCapture cameras send `take` at most once a minute instead of on every frontend refresh (~10 s), and keep the last image when a download fails.

## [2.1.5] - 2026-01-19

### Fixed
- Fixed `parent_attribute` handling in sensor platform
- Fixed `remainingTime` parsing (HH:MM string → minutes conversion)
- Resolved template filter warnings for `machineState` attribute matching

## [2.1.3] - 2026-01-15

### Fixed
- Added `parent_attribute` to sensor entities for proper template filtering
- Added `isinstance` checks for attribute value types

## [2.1.1] - 2026-01-14

### Added
- Initial versioned release
- Dynamic entity creation for all SmartThings capabilities
- OAuth2 authentication with Basic Auth
- Support for multi-component devices
- Specialized vacuum platform for Samsung JetBot robots
- Polish translations
- Three discovery modes: standard, expose_command_buttons, aggressive_mode
- Custom `send_command` service
- Capability definition caching

## [1.0.0] - 2025-06-20

### Added
- Initial development version
- SmartThings API client with OAuth2
- Basic entity discovery and creation
