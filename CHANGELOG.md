# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
