"""Hyyp Client API."""
from __future__ import annotations

import logging
from typing import Any

import requests
import threading as thread
import time

from .alarm_info import HyypAlarmInfos
from .push_receiver import FCMListener, FCMRegistration
from .constants import DEFAULT_TIMEOUT, REQUEST_HEADER, STD_PARAMS, DEBUG_CLIENT_STRING, PUSH_DELAY, IMEI_SEED, HyypPkg
from .exceptions import HTTPError, HyypApiError, InvalidURL
from .imei import ImeiGenerator
from .common_tools import ClientTools

_LOGGER = logging.getLogger(__name__)

BASE_URL = "ids.trintel.co.za/Inhep-Impl-1.0-SNAPSHOT/"
API_ENDPOINT_LOGIN = "/auth/login"
API_ENDPOINT_CHECK_APP_VERSION = "/auth/checkAppVersion"
API_ENDPOINT_GET_SITE_NOTIFICATIONS = "/device/getSiteNotifications"
API_ENDPOINT_SYNC_INFO = "/device/getSyncInfo"
API_ENDPOINT_STATE_INFO = "/device/getStateInfo"
API_ENDPOINT_NOTIFICATION_SUBSCRIPTIONS = "/device/getNotificationSubscriptions"
API_ENDPOINT_GET_USER_PREFERANCES = "/user/getUserPreferences"
API_ENDPOINT_SET_USER_PREFERANCE = "/user/setUserPreference"
API_ENDPOINT_SECURITY_COMPANIES = "/security-companies/list"
API_ENDPOINT_STORE_GCM_REGISTRATION_ID = "/user/storeGcmRegistrationId"
API_ENDPOINT_ARM_SITE = "/device/armSite"
API_ENDPOINT_TRIGGER_ALARM = "/device/triggerAlarm"
API_ENDPOINT_SET_ZONE_BYPASS = "/device/bypass"
API_ENDPOINT_GET_CAMERA_BY_PARTITION = "/device/getCameraByPartition"
API_ENDPOINT_UPDATE_SUB_USER = "/user/updateSubUser"
API_ENDPOINT_SET_NOTIFICATION_SUBSCRIPTIONS = "/user/setNotificationSubscriptionsNew"
API_ENDPOINT_TRIGGER_AUTOMATION = "/device/trigger"
API_ENDPOINT_GET_ZONE_STATE_INFO = "/device/getZoneStateInfo"
REQUEST_PUSH_TIMEOUT = 1.5
FAILURE_CAUSE_STRING = "failure_cause"
class HyypClient:
    """Initialize api client object."""

    def __init__(
        self,
        email: str | None = None,
        password: str | None = None,
        pkg: str = HyypPkg.ADT_SECURE_HOME.value,
        timeout: int = DEFAULT_TIMEOUT,
        token: str | None = None,
        userid: int | None = None,
    ) -> None:
        """Initialize the client object."""
        self._email = email
        self._password = password
        self._session = requests.session()
        self._session.headers.update(REQUEST_HEADER)
        STD_PARAMS["pkg"] = pkg
        STD_PARAMS["token"] = token
        STD_PARAMS["userId"] = userid
        STD_PARAMS["imei"] = self.generate_imei()
        self._timeout = timeout
        self.time_to_push = PUSH_DELAY
        self.forced_refresh = False
        self.alarminfos = HyypAlarmInfos(self)
        self.fcm_listener = FCMListener()
        self.fcm_register = FCMRegistration()
        self.fcm_credentials = None
        self.current_status = None
        self.tools = ClientTools()
        self.generic_callback_to_hass = None
    
        
    def login(self) -> Any:
        """Login to ADT Secure Home API."""

            
        _params = STD_PARAMS.copy()
        _params["email"] = self._email
        _params["password"] = self._password
        try:
            req = self._session.get(
                "https://" + BASE_URL + API_ENDPOINT_LOGIN,
                allow_redirects=False,
                params=_params,
                timeout=self._timeout,
            )

            req.raise_for_status()

        except requests.ConnectionError as err:
            raise InvalidURL("A Invalid URL or Proxy error occured") from err

        except requests.HTTPError as err:
            raise HTTPError from err

        try:
            _json_result: dict[Any, Any] = req.json()

        except ValueError as err:
            raise HyypApiError(
                "Impossible to decode response: "
                + str(err)
                + "\nResponse was: "
                + str(req.text)
            ) from err

        if _json_result["status"] != "SUCCESS" and _json_result["error"] is not None:
            raise HyypApiError(f"Login error: {_json_result['error']}")

        STD_PARAMS["token"] = _json_result["token"]
        STD_PARAMS["userId"] = _json_result["user"]["id"]

        DEBUG_CLIENT_STRING["client_string"] = _json_result
        return _json_result

    def generate_imei(self):
        imei = ImeiGenerator().generate_imei(IMEI_SEED)
        return imei

    def check_app_version(self) -> Any:
        """Check App version via API."""

        _params = STD_PARAMS.copy()
        _params["clientImei"] = STD_PARAMS["imei"]

        try:
            req = self._session.get(
                "https://" + BASE_URL + API_ENDPOINT_CHECK_APP_VERSION,
                allow_redirects=False,
                params=_params,
                timeout=self._timeout,
            )

            req.raise_for_status()

        except requests.ConnectionError as err:
            raise InvalidURL("A Invalid URL or Proxy error occured") from err

        except requests.HTTPError as err:
            raise HTTPError from err

        try:
            _json_result: dict[Any, Any] = req.json()

        except ValueError as err:
            raise HyypApiError(
                "Impossible to decode response: "
                + str(err)
                + "\nResponse was: "
                + str(req.text)
            ) from err

        if _json_result["status"] != "SUCCESS" and _json_result["error"] is not None:
            raise HyypApiError(
                f"Error checking app version from api: {_json_result['error']}"
            )

        return _json_result

    def alarm_info_push_timer(self, callback, onetime = False):
        SLEEP_DELAY = 0.1
        if onetime:
            time.sleep(REQUEST_PUSH_TIMEOUT)
            alarminfo = self.load_alarm_infos()
            callback(alarminfo)
            return
        while 1:
            if self.forced_refresh and self.time_to_push > REQUEST_PUSH_TIMEOUT:
                self.time_to_push = REQUEST_PUSH_TIMEOUT
            while self.time_to_push > 0:
                time.sleep(SLEEP_DELAY)
                self.time_to_push -= SLEEP_DELAY
            alarminfo = self.load_alarm_infos()
            callback(alarminfo)
            self.forced_refresh = False
            self.time_to_push = PUSH_DELAY

    def request_alarm_info_push_to_hass(self):
        self.forced_refresh = True
        self.time_to_push = REQUEST_PUSH_TIMEOUT
        
    def initialize_alarm_info_push_timer(self, callback, onetime = False):
        thread.Thread(target=self.alarm_info_push_timer,
                      kwargs={"callback" : callback, "onetime" : onetime}).start()


    def load_alarm_infos(self) -> dict[Any, Any]:
        """Get alarm infos formatted for hass infos."""
        forced = self.forced_refresh
        self.current_status = self.alarminfos.status(forced=forced)
        return self.current_status

    def initialize_fcm_notification_listener(self, callback, restart = False, persistent_pids = None):
        thread.Thread(target=self.fcm_notification_thread,
                      kwargs={"persistent_ids" : persistent_pids,
                              "callback" : callback,
                              "restart" : restart,
                              }).start()
   
   
    def register_generic_callback_to_hass(self, callback):
       self.generic_callback_to_hass = callback

    def fcm_notification_thread(self, callback, restart, persistent_ids = None):
        #_LOGGER.setLevel(logging.DEBUG)
        if not restart:
            if not self.tools.internet_connectivity():
                return
        self.fcm_credentials = self.get_intial_fcm_credentials()
        if self.fcm_credentials is None:
            _LOGGER.warning("No FCM credentials available, disabling notifications")
            return
        if "fcm" not in self.fcm_credentials:
            _LOGGER.warning("No FCM credentials available, disabling notifications")
            return
        
        
        gcm_address = self.fcm_credentials["fcm"]["token"]  
        if restart:
            time.sleep(60)
        if not self.tools.internet_connectivity():
            while not self.tools.internet_connectivity():
                time.sleep(60) 
            callback("restart_push_receiver")
            return
        time.sleep(2)

        
        retry_count = 0
        while self.store_gcm_registrationid(gcm_id=gcm_address) == 0:
            time.sleep(30)
            retry_count += 1
            if retry_count >= 2:
                callback("restart_push_receiver")
                return
        time.sleep(60)
        self.fcm_listener.runner(callback=callback,
                                 credentials=self.fcm_credentials,
                                 persistent_ids=persistent_ids)


    def get_intial_fcm_credentials(self):
        if not self.tools.internet_connectivity():
            return False
        return self.fcm_register.register()
        ## add some sort of validation

    def get_debug_infos(self) -> dict[Any, Any]:
        """Get alarm infos formatted for hass infos."""
        return HyypAlarmInfos(self).get_debug_info()

    def site_notifications(
        self, site_id: int, timestamp: int | None = None, json_key: int | None = None
    ) -> Any:
        """Get site notifications from API."""

        _params: dict[str, Any] = STD_PARAMS.copy()
        _params["siteId"] = site_id
        _params["timestamp"] = timestamp

        try:
            req = self._session.get(
                "https://" + BASE_URL + API_ENDPOINT_GET_SITE_NOTIFICATIONS,
                allow_redirects=False,
                params=_params,
                timeout=self._timeout,
            )

            req.raise_for_status()

        except requests.ConnectionError as err:
            raise InvalidURL("A Invalid URL or Proxy error occured") from err

        except requests.HTTPError as err:
            raise HTTPError from err

        try:
            _json_result: dict[Any, Any] = req.json()

        except ValueError as err:
            raise HyypApiError(
                "Impossible to decode response: "
                + str(err)
                + "\nResponse was: "
                + str(req.text)
            ) from err

        if _json_result["status"] != "SUCCESS" and _json_result["error"] is not None:
            raise HyypApiError(
                f"Error getting site notifications from api: {_json_result['error']}"
            )

        if json_key is None or not _json_result["listSiteNotifications"][str(site_id)]:
            return _json_result["listSiteNotifications"][str(site_id)]

        return _json_result["listSiteNotifications"][str(site_id)][json_key]

    def set_notification_subscriptions(
        self,
        trouble_notifications: bool = True,
        emergency_notifications: bool = True,
        user_notifications: bool = True,
        information_notifications: bool = True,
        test_report_notifications: bool = False,
    ) -> Any:
        """Enable or disable app notifications."""

        _params: dict[str, Any] = STD_PARAMS.copy()
        del _params["imei"]
        _params["mobileImei"] = STD_PARAMS["imei"]
        _params["troubleNotifications"] = trouble_notifications
        _params["emergencyNotifications"] = emergency_notifications
        _params["userNotifications"] = user_notifications
        _params["informationNotifications"] = information_notifications
        _params["testReportNotifications"] = test_report_notifications

        try:
            req = self._session.post(
                "https://" + BASE_URL + API_ENDPOINT_SET_NOTIFICATION_SUBSCRIPTIONS,
                allow_redirects=False,
                params=_params,
                timeout=self._timeout,
            )

            req.raise_for_status()

        except requests.ConnectionError as err:
            raise InvalidURL("A Invalid URL or Proxy error occured") from err

        except requests.HTTPError as err:
            raise HTTPError from err

        try:
            _json_result: dict[Any, Any] = req.json()

        except ValueError as err:
            raise HyypApiError(
                "Impossible to decode response: "
                + str(err)
                + "\nResponse was: "
                + str(req.text)
            ) from err

        if _json_result["status"] != "SUCCESS" and _json_result["error"] is not None:
            raise HyypApiError(
                f"Error getting site notifications from api: {_json_result['error']}"
            )

        return _json_result

    def get_camera_by_partition(
        self, partition_id: int, json_key: str | None = None
    ) -> Any:
        """Get cameras, bypassed zones and zone ids by partition from API."""

        _params: dict[str, Any] = STD_PARAMS.copy()
        _params["partitionId"] = partition_id

        try:
            req = self._session.get(
                "https://" + BASE_URL + API_ENDPOINT_GET_CAMERA_BY_PARTITION,
                allow_redirects=False,
                params=_params,
                timeout=self._timeout,
            )

            req.raise_for_status()

        except requests.ConnectionError as err:
            raise InvalidURL("A Invalid URL or Proxy error occured") from err

        except requests.HTTPError as err:
            raise HTTPError from err

        try:
            _json_result: dict[Any, Any] = req.json()

        except ValueError as err:
            raise HyypApiError(
                "Impossible to decode response: "
                + str(err)
                + "\nResponse was: "
                + str(req.text)
            ) from err

        if _json_result["status"] != "SUCCESS" and _json_result["error"] is not None:
            raise HyypApiError(
                f"Error getting partition cameras from api: {_json_result['error']}"
            )
        if json_key is None:
            return _json_result

        return _json_result[json_key]



    def get_zone_state_info(self, site_id: int, json_key: str | None = None) -> Any:
        """Get state info from API. Returns armed, bypassed partition ids."""

        _params: dict[str, Any] = STD_PARAMS.copy()
        _params["siteId"] = site_id
        
        try:
            req = self._session.get(
                "https://" + BASE_URL + API_ENDPOINT_GET_ZONE_STATE_INFO,
                allow_redirects=False,
                params=_params,
                timeout=self._timeout,
            )
            req.raise_for_status()
        except requests.ConnectionError as err:
            raise InvalidURL("A Invalid URL or Proxy error occured") from err

        except requests.HTTPError as err:
            raise HTTPError from err    
        try:
            _json_result: dict[Any, Any] = req.json()

        except ValueError as err:
            raise HyypApiError(
                "Impossible to decode response: "
                + str(err)
                + "\nResponse was: "
                + str(req.text)
            ) from err

        if _json_result["status"] != "SUCCESS" and _json_result["error"] is not None:
            _LOGGER.warning(f"Error getting zone state info from api: {_json_result['error']}")
            #raise HyypApiError(
            #    f"Error getting zone state info from api: {_json_result['error']}"
            #)

        if json_key is None:
            return _json_result

        return _json_result[json_key]


    def get_sync_info(self, json_key: str | None = None) -> Any:
        """Get user, site, partition and users info from API."""

        _params = STD_PARAMS.copy()
        if self.fcm_credentials is not None:
            _params["gcmId"] = self.fcm_credentials["fcm"]["token"] 

        try:
            req = self._session.get(
                "https://" + BASE_URL + API_ENDPOINT_SYNC_INFO,
                allow_redirects=False,
                params=_params,
                timeout=self._timeout,
            )

            req.raise_for_status()

        except requests.ConnectionError as err:
            raise InvalidURL("A Invalid URL or Proxy error occured") from err

        except requests.HTTPError as err:
            raise HTTPError from err

        try:
            _json_result: dict[Any, Any] = req.json()

        except ValueError as err:
            raise HyypApiError(
                "Impossible to decode response: "
                + str(err)
                + "\nResponse was: "
                + str(req.text)
            ) from err

        if _json_result["status"] != "SUCCESS" and _json_result["error"] is not None:
            raise HyypApiError(
                f"Error getting sync info from api: {_json_result['error']}"
            )

        if json_key is None:
            return _json_result

        return _json_result[json_key]

    def get_state_info(self, json_key: str | None = None) -> Any:
        """Get state info from API. Returns armed, bypassed partition ids."""

        _params = STD_PARAMS

        try:
            req = self._session.get(
                "https://" + BASE_URL + API_ENDPOINT_STATE_INFO,
                allow_redirects=False,
                params=_params,
                timeout=self._timeout,
            )

            req.raise_for_status()

        except requests.ConnectionError as err:
            raise InvalidURL("A Invalid URL or Proxy error occured") from err

        except requests.HTTPError as err:
            raise HTTPError from err

        try:
            _json_result: dict[Any, Any] = req.json()

        except ValueError as err:
            raise HyypApiError(
                "Impossible to decode response: "
                + str(err)
                + "\nResponse was: "
                + str(req.text)
            ) from err

        if _json_result["status"] != "SUCCESS" and _json_result["error"] is not None:
            raise HyypApiError(
                f"Error getting state info from api: {_json_result['error']}"
            )

        if json_key is None:
            return _json_result

        return _json_result[json_key]

    def get_notification_subscriptions(self, json_key: str | None = None) -> Any:
        """Get notification subscriptions from API."""

        _params = STD_PARAMS

        try:
            req = self._session.get(
                "https://" + BASE_URL + API_ENDPOINT_NOTIFICATION_SUBSCRIPTIONS,
                allow_redirects=False,
                params=_params,
                timeout=self._timeout,
            )

            req.raise_for_status()

        except requests.ConnectionError as err:
            raise InvalidURL("A Invalid URL or Proxy error occured") from err

        except requests.HTTPError as err:
            raise HTTPError from err

        try:
            _json_result: dict[Any, Any] = req.json()

        except ValueError as err:
            raise HyypApiError(
                "Impossible to decode response: "
                + str(err)
                + "\nResponse was: "
                + str(req.text)
            ) from err

        if _json_result["status"] != "SUCCESS" and _json_result["error"] is not None:
            raise HyypApiError(
                f"Error getting notification subscriptions: {_json_result['error']}"
            )

        if json_key is None:
            return _json_result

        return _json_result[json_key]

    def get_user_preferences(
        self, user_id: int, site_id: int | None = None, json_key: str | None = None
    ) -> Any:
        """Get user preferences from API."""

        _params: dict[str, Any] = STD_PARAMS.copy()
        _params["userId"] = user_id
        _params["siteId"] = site_id

        try:
            req = self._session.get(
                "https://" + BASE_URL + API_ENDPOINT_GET_USER_PREFERANCES,
                allow_redirects=False,
                params=_params,
                timeout=self._timeout,
            )

            req.raise_for_status()

        except requests.ConnectionError as err:
            raise InvalidURL("A Invalid URL or Proxy error occured") from err

        except requests.HTTPError as err:
            raise HTTPError from err

        try:
            _json_result: dict[Any, Any] = req.json()

        except ValueError as err:
            raise HyypApiError(
                "Impossible to decode response: "
                + str(err)
                + "\nResponse was: "
                + str(req.text)
            ) from err

        if _json_result["status"] != "SUCCESS" and _json_result["error"] is not None:
            raise HyypApiError(
                f"Error getting user preferences: {_json_result['error']}"
            )

        if json_key is None:
            return _json_result

        return _json_result[json_key]

    def get_security_companies(self, json_key: str | None = None) -> Any:
        """Get security companies from API."""

        _params = STD_PARAMS

        try:
            req = self._session.get(
                "https://" + BASE_URL + API_ENDPOINT_SECURITY_COMPANIES,
                allow_redirects=False,
                params=_params,
                timeout=self._timeout,
            )

            req.raise_for_status()

        except requests.ConnectionError as err:
            raise InvalidURL("A Invalid URL or Proxy error occured") from err

        except requests.HTTPError as err:
            raise HTTPError from err

        try:
            _json_result: dict[Any, Any] = req.json()

        except ValueError as err:
            raise HyypApiError(
                "Impossible to decode response: "
                + str(err)
                + "\nResponse was: "
                + str(req.text)
            ) from err

        if _json_result["status"] != "SUCCESS" and _json_result["error"] is not None:
            raise HyypApiError(
                f"Failed to get security companies: {_json_result['error']}"
            )

        if json_key is None:
            return _json_result

        return _json_result[json_key]

    def store_gcm_registrationid(self, gcm_id = None) -> Any:
        """Store gcmid."""
        _params = STD_PARAMS.copy()
        _params["gcmId"] = gcm_id
        _params["clientImei"] = STD_PARAMS["imei"]
        _params["requestingUserId"] = STD_PARAMS["userId"]
        
        try:
            req = self._session.post(
                "https://" + BASE_URL + API_ENDPOINT_STORE_GCM_REGISTRATION_ID,
                allow_redirects=False,
                params=_params,
                timeout=self._timeout,
            )
        
            req.raise_for_status()
         
        except requests.ConnectionError as err:
            raise InvalidURL("A Invalid URL or Proxy error occured") from err

        except requests.HTTPError as err:
            raise HTTPError from err
        
        except:
            _LOGGER.debug("GCM Registration Error")
            return 0
        
        

        try:
            _json_result = req.json()

        except ValueError as err:
            raise HyypApiError(
                "Impossible to decode response: "
                + str(err)
                + "\nResponse was: "
                + str(req.text)
            ) from err

        if _json_result["status"] != "SUCCESS" and _json_result["error"] is not None:
            raise HyypApiError(f"Storing gcm id failed with: {_json_result['error']}")
        return _json_result

    def set_user_preference(
        self,
        store_for: str,
        new_code: int,
        site_id: str,
        partition_id: str,
    ) -> Any:
        """Set user code preferences."""

        if store_for not in ["Arm", "Bypass"]:
            raise HyypApiError("Invalid selection, choose between Arm or Bypass")

        _params: dict[Any, Any] = STD_PARAMS.copy()
        _params["siteId"] = site_id

        _params["name"] = (
            "site." + site_id + ".partition." + partition_id + ".storeFor" + store_for
        )

        _params["preference_value"] = new_code

        try:
            req = self._session.post(
                "https://" + BASE_URL + API_ENDPOINT_SET_USER_PREFERANCE,
                allow_redirects=False,
                params=_params,
                timeout=self._timeout,
            )

            req.raise_for_status()

        except requests.ConnectionError as err:
            raise InvalidURL("A Invalid URL or Proxy error occured") from err

        except requests.HTTPError as err:
            raise HTTPError from err

        try:
            _json_result: dict[Any, Any] = req.json()

        except ValueError as err:
            raise HyypApiError(
                "Impossible to decode response: "
                + str(err)
                + "\nResponse was: "
                + str(req.text)
            ) from err

        if _json_result["status"] != "SUCCESS" and _json_result["error"] is not None:
            raise HyypApiError(
                f"Set user preferance failed with: {_json_result['error']}"
            )

        return _json_result

    def set_subuser_preference(
        self,
        user_id: str,
        site_id: str | None = None,
        partition_id: str | None = None,
        partition_pin: str | None = None,
        stay_profile_id: int | None = None,
    ) -> Any:
        """Set sub user preferences."""

        _params: dict[Any, Any] = STD_PARAMS.copy()
        _params["siteId"] = site_id
        _params["userId"] = user_id

        _params["partitions"] = {}
        _params["partitions"][0] = {}
        _params["partitions"][0][".id"] = partition_id
        _params["partitions"][0][".pin"] = partition_pin
        _params["stayProfileIds"] = {}
        _params["stayProfileIds"][0] = stay_profile_id

        try:
            req = self._session.post(
                "https://" + BASE_URL + API_ENDPOINT_UPDATE_SUB_USER,
                allow_redirects=False,
                params=_params,
                timeout=self._timeout,
            )

            req.raise_for_status()

        except requests.ConnectionError as err:
            raise InvalidURL("A Invalid URL or Proxy error occured") from err

        except requests.HTTPError as err:
            raise HTTPError from err

        try:
            _json_result: dict[Any, Any] = req.json()

        except ValueError as err:
            raise HyypApiError(
                "Impossible to decode response: "
                + str(err)
                + "\nResponse was: "
                + str(req.text)
            ) from err

        if _json_result["status"] != "SUCCESS" and _json_result["error"] is not None:
            raise HyypApiError(
                f"Updating sub user failed with: {_json_result['error']}"
            )

        return _json_result

               
                        
    def arm_site(
        self,
        site_id: int,
        arm: bool = True,
        pin: int | None = None,
        partition_id: int | None = None,
        stay_profile_id: int | None = None,
    ) -> Any:
        """Arm alarm or stay profile via API."""

        _params: dict[Any, Any] = STD_PARAMS.copy()
        _params["arm"] = arm
        _params["pin"] = pin
        _params["partitionId"] = partition_id
        _params["siteId"] = site_id
        _params["stayProfileId"] = stay_profile_id
        _params["clientImei"] = STD_PARAMS["imei"]
        
            
        try:
            req = self._session.get(
                "https://" + BASE_URL + API_ENDPOINT_ARM_SITE,
                allow_redirects=False,
                params=_params,
                timeout=self._timeout,
            )

            req.raise_for_status()

        except requests.ConnectionError as err:
            raise InvalidURL("A Invalid URL or Proxy error occured") from err

        except requests.HTTPError as err:
            raise HTTPError from err
        
        try:
            _json_result: dict[Any, Any] = req.json()

        except ValueError as err:
            raise HyypApiError(
                "Impossible to decode response: "
                + str(err)
                + "\nResponse was: "
                + str(req.text)
            ) from err

        if _json_result["status"] != "SUCCESS":  
            raise HyypApiError(f"Arm site failed: {_json_result['error']}")

        return _json_result
        
        
        


    def trigger_alarm(
        self,
        site_id: int,
        pin: int | None = None,
        partition_id: int | None = None,
        trigger_id: int | None = None,
    ) -> Any:
        """Trigger Alarm via API."""

        _params: dict[Any, Any] = STD_PARAMS.copy()
        _params["pin"] = pin
        _params["partitionId"] = partition_id
        _params["siteId"] = site_id
        _params["triggerId"] = trigger_id
        _params["clientImei"] = STD_PARAMS["imei"]

        try:
            req = self._session.post(
                "https://" + BASE_URL + API_ENDPOINT_TRIGGER_ALARM,
                allow_redirects=False,
                params=_params,
                timeout=self._timeout,
            )

            req.raise_for_status()

        except requests.ConnectionError as err:
            raise InvalidURL("A Invalid URL or Proxy error occured") from err

        except requests.HTTPError as err:
            raise HTTPError from err

        try:
            _json_result: dict[Any, Any] = req.json()

        except ValueError as err:
            raise HyypApiError(
                "Impossible to decode response: "
                + str(err)
                + "\nResponse was: "
                + str(req.text)
            ) from err

        if _json_result["status"] != "SUCCESS" and _json_result["error"] is not None:
            raise HyypApiError(f"Trigger alarm failed: {_json_result['error']}")

        return _json_result


    def trigger_automation(
        self,
        site_id: int,
        trigger_id: int | None = None,
        pin: int | None = None,
    ) -> Any:
        """Trigger Automation via API."""

        _params: dict[Any, Any] = STD_PARAMS.copy()
        _params["pin"] = pin
        _params["siteId"] = site_id
        _params["triggerId"] = trigger_id
        del _params["imei"]
        _params["clientImei"] = STD_PARAMS["imei"]

        try:
            req = self._session.post(
                "https://" + BASE_URL + API_ENDPOINT_TRIGGER_AUTOMATION,
                allow_redirects=False,
                params=_params,
                timeout=self._timeout,
            )

            req.raise_for_status()

        except requests.ConnectionError as err:
            raise InvalidURL("A Invalid URL or Proxy error occured") from err

        except requests.HTTPError as err:
            raise HTTPError from err

        try:
            _json_result: dict[Any, Any] = req.json()

        except ValueError as err:
            raise HyypApiError(
                "Impossible to decode response: "
                + str(err)
                + "\nResponse was: "
                + str(req.text)
            ) from err

        if _json_result["status"] != "SUCCESS" and _json_result["error"] is not None:
            raise HyypApiError(f"Trigger automation failed: {_json_result['error']}")

        return _json_result


    def set_zone_bypass(
        self,
        zones: int,
        partition_id: int | None = None,
        stay_profile_id: int = 0,
        pin: int | None = None,
    ) -> Any:
        """Set/toggle zone bypass."""

        _params: dict[str, Any] = STD_PARAMS.copy()
        _params["partitionId"] = partition_id
        _params["zones"] = zones
        _params["stayProfileId"] = stay_profile_id
        _params["pin"] = pin
        _params["clientImei"] = STD_PARAMS["imei"]
        
        try:
            req = self._session.get(
                "https://" + BASE_URL + API_ENDPOINT_SET_ZONE_BYPASS,
                allow_redirects=False,
                params=_params,
                timeout=self._timeout,
            )
            req.raise_for_status()

        except requests.ConnectionError as err:
            raise InvalidURL("A Invalid URL or Proxy error occured") from err

        except requests.HTTPError as err:
            raise HTTPError from err

        try:
            _json_result: dict[Any, Any] = req.json()

        except ValueError as err:
            raise HyypApiError(
                "Impossible to decode response: "
                + str(err)
                + "\nResponse was: "
                + str(req.text)
            ) from err

        if _json_result["status"] != "SUCCESS" and _json_result["error"] is not None:
            raise HyypApiError(f"Failed to set zone bypass: {_json_result['error']}")

        return _json_result

    def logout(self) -> None:
        """Close ADT Secure Home session."""
        self.close_session()

    def close_session(self) -> None:
        """Clear current session."""
        if self._session:
            self._session.close()

        self._session = requests.session()
        self._session.headers.update(REQUEST_HEADER)  # Reset session.