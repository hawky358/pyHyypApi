This is a fork from https://github.com/RenierM26. This fork has reversed engineered the protobuf pb2 files and recompiled with version 4.21. This fixes the issues on newer versions of home assistant and incorporated several new features. See the main integration: https://github.com/hawky358/hass_ids_hyyp for more information.







# pyHyypApi

**Note** this Api is built to work with the IDS Hyyp integration for home assistant and while the commands will work via a python console, this is not the recommended usage method.

API for ADT Secure Home and IDS Hyyp. There could be more variants but it's easy to add package names to the constants.py file.


Changelog 


1.3.2
- Fixed high cpu usage infinite loop
- Added full restart callback for notification system
- Added connectivity check and better reconnect system when internet is lost.

1.3.1
- Released 1.3.1 with push receiver system
- Further heartbeat optimization
- Added exception for ping

1.3.0b8
- Changed debug level

1.3.0b7
- Fixed HeartbeatPing and HeartbeatPingAck packets. Should now provide hearbeat and ack correctly.

1.3.0b6
- Added 30 min ping (Ping is from initial implementation, to investigate). Currently reconnects

1.3.0b5
- Added reconnect for timeouts

1.3.0b4
- Minor Refactoring

1.3.0b3
- Hotfix, notifications appear to go to random people. Implemented random IMEI

1.3.0b2
- Implementation of push receiver.

1.3.0b1
- API supports both push and poll mode.
- API will can now send to Home Assistant when data is ready instead of Home assistant Polling
- Relevant new methods:
  - `request_alarm_info_push_to_hass()` - Hass can call this to request an earlier push instead of the 30 seconds
  - `initialize_alarm_info_push_timer()` - Hass must call this when ready as it initializes the timer in the API
  - `register_alarm_info_callback()` - Hass muss register a callback method using this method


1.2.1
- Added additional debug checks
- Added additional checks for openviolated and tampered information when not received

1.1.7
- Zones now show openviolated and tampered information from IDS server
- Added delays between server requests to prevent blocking

1.1.6
- Zones now show openviolated and tampered information from IDS server
- Will now show zones as bypassed when a stay arm bypassing zones is activated.

1.1.5
- Added functions to supply notifications for debugging when specifically called.

1.1.4
- Bugfix: When no "triggers" exist a blank key is now returned instead of nothing. This caused a KeyError in home assistant.

1.1.3
- Bugfix: Fixes a bug when calling notifications

1.1.2
- Changed the way notifications are cached
- Changed the last notification timestamp from a global variable to a class variable

1.1.1
- Bugfix: Missing variable to timeout

1.1.0
- Added feature to detect which zones triggered an alarm.


1.0.3
- Fixed a bug where stay profiles would mostly go to false even though stay profiles were armed.

1.0.2
- Fixed a bug where the parameters for certain items were swapped

1.0.1

- Added fix where setups with multiple sites would crash
- Added the ability to find "automations" and also trigger the automations

1.0.0

Bumped main release to 1.0.0