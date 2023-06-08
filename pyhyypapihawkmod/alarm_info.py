"""Alarm info for hass integration."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any
from datetime import datetime
from .constants import EventNumber

if TYPE_CHECKING:
    from .client import HyypClient

_last_notification_check_timestamp = 0

class HyypAlarmInfos:
    """Initialize Hyyp alarm objects."""

    def __init__(self, client: HyypClient) -> None:
        """init."""
        self._client = client
        self._sync_info: dict = {}
        self._state_info: dict = {}

    def _fetch_data(self) -> None:
        """Fetch data via client api."""
        self._sync_info = self._client.get_sync_info()
        self._state_info = self._client.get_state_info()

    def _last_notice(self, site_id: int) -> dict[Any, Any]:
        """Get last notification."""
        _response: dict[Any, Any] = {"lastNoticeTime": None, "lastNoticeName": None}

        _last_notification = self._client.site_notifications(
            site_id=site_id, json_key=0
        )

        if _last_notification:

            _last_event = _last_notification["eventNumber"]
            _last_event_datetime = str(
                datetime.fromtimestamp(_last_notification["timestamp"] / 1000)
            )  # Epoch in ms

            _response = {
                "lastNoticeTime": _last_event_datetime,
                "lastNoticeName": EventNumber[str(_last_event)],
            }

        return _response



    def _new_notifications(self, site_id: int) -> Any:

        global _last_notification_check_timestamp   
        _response = []

        _notifications = self._client.site_notifications(
            site_id=site_id)
                
        _current_timestamp = round(datetime.now().timestamp())
            
        for x in _notifications:
            
            _notification_timestamp = round(x['timestamp']/1000)
            if _current_timestamp - _notification_timestamp > 120:
                continue
            if _notification_timestamp <= (_last_notification_check_timestamp-30):
                continue
            _response.append(x)
        
        _last_notification_check_timestamp = _current_timestamp
 
        return _response


    def _triggered_zones(self, site_id: int) -> Any:
           
        triggeredZoneIds = []
        _new_notifications = self._new_notifications(site_id=site_id)
        
        for _notification in _new_notifications:
            if _notification['eventNumber'] != 5:
                continue
            triggeredZoneIds.append(_notification['zoneId'])  
                 
        _response = triggeredZoneIds
        
        return _response
     

     
    def _format_data(self) -> dict[Any, Any]:
        """Format data for Hass."""

        # The API returns data from site level.
        # Partitions are used as entity that actions are performed on.

        site_ids = {site["id"]: site for site in self._sync_info["sites"]}
        zone_ids = {zone["id"]: zone for zone in self._sync_info["zones"]}
        stay_ids = {
            stay_profile["id"]: stay_profile
            for stay_profile in self._sync_info["stayProfiles"]
        }
        partition_ids = {
            partition["id"]: partition for partition in self._sync_info["partitions"]
        }
        
        trigger_ids = {
            trigger["id"]: trigger for trigger in self._sync_info["triggers"]
        }
        
        for site in site_ids:
            
            triggered_zones = self._triggered_zones(site_id=site)

            # Add last site notification.
            _last_notice = self._last_notice(site_id=site)
            site_ids[site]["lastNoticeTime"] = _last_notice["lastNoticeTime"]
            site_ids[site]["lastNoticeName"] = _last_notice["lastNoticeName"]

            # Add triggers (PGM / Automations in APP)
            for trigger_id in trigger_ids:
                if trigger_id not in site_ids[site]["triggerIds"]:
                    continue
                else:
                    site_ids[site]["triggers"] = {
                        key: value
                        for (key, value) in trigger_ids.items()            
                    }
                
            
            # Add partition info.
            site_ids[site]["partitions"] = {
                partition_id: partition_ids[partition_id]
                for partition_id in site_ids[site]["partitionIds"]
            }

            for partition in partition_ids:
                # Add zone info to partition.
                if partition not in site_ids[site]["partitions"]:
                    continue
                else:  
                    site_ids[site]["partitions"][partition]["zones"] = {
                        key: value
                        for (key, value) in zone_ids.items()
                        if key in site_ids[site]["partitions"][partition]["zoneIds"]
                    }

                # Add zone bypass info to zone.
                for zone in site_ids[site]["partitions"][partition]["zones"]:
                    site_ids[site]["partitions"][partition]["zones"][zone][
                        "bypassed"
                    ] = bool(zone in self._state_info["bypassedZoneIds"])

                # Add zone trigger info to zone (Zone triggered alarm).
                for zone in site_ids[site]["partitions"][partition]["zones"]:
                    site_ids[site]["partitions"][partition]["zones"][zone][
                        "triggered"
                    ] = bool(zone in triggered_zones)


                # Add stay profile info.
                site_ids[site]["partitions"][partition]["stayProfiles"] = {
                    key: value
                    for (key, value) in stay_ids.items()
                    if key in site_ids[site]["partitions"][partition]["stayProfileIds"]
                }

                # Add partition armed status.
                site_ids[site]["partitions"][partition]["armed"] = bool(
                    partition in self._state_info["armedPartitionIds"]
                )

                # Add partition stay_armed status.
                site_ids[site]["partitions"][partition]["stayArmed"] = False
                
                for stay_profile in site_ids[site]["partitions"][partition][
                    "stayProfiles"
                ]:
                    if stay_profile not in self._state_info["armedStayProfileIds"]:
                        continue
                    
                    site_ids[site]["partitions"][partition]["stayArmed"] = bool(
                        stay_profile in self._state_info["armedStayProfileIds"]
                    )
                    site_ids[site]["partitions"][partition]["stayArmedProfileName"] = (
                        site_ids[site]["partitions"][partition]["stayProfiles"][
                            stay_profile
                        ]["name"]
                        if stay_profile in self._state_info["armedStayProfileIds"]
                        else None
                    )

        return site_ids

    def status(self) -> dict[Any, Any]:
        """Return the status of Hyyp connected alarms."""

        self._fetch_data()
        formatted_data: dict[Any, Any] = self._format_data()

        return formatted_data
