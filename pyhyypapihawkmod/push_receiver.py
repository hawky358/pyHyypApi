"""Receive GCM/FCM messages from google."""

from base64 import b64encode, urlsafe_b64decode, urlsafe_b64encode
from binascii import hexlify
import json
import logging
import os
import os.path
import select
import socket
import ssl
import struct
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import threading as thread
import requests
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from google.protobuf.json_format import MessageToDict
import http_ece
from oscrypto.asymmetric import generate_pair



from .common_tools import ClientTools
from .android_checkin_pb2 import AndroidCheckinProto, ChromeBuildProto
from .checkin_pb2 import AndroidCheckinRequest, AndroidCheckinResponse
from .constants import GCF_SENDER_ID
from .mcs_pb2 import (
    Close,
    DataMessageStanza,
    HeartbeatAck,
    HeartbeatPing,
    IqStanza,
    LoginRequest,
    LoginResponse,
    StreamErrorStanza,
)

_LOGGER = logging.getLogger(__name__)

SERVER_KEY = (
    b"\x04\x33\x94\xf7\xdf\xa1\xeb\xb1\xdc\x03\xa2\x5e\x15\x71\xdb\x48\xd3"
    + b"\x2e\xed\xed\xb2\x34\xdb\xb7\x47\x3a\x0c\x8f\xc4\xcc\xe1\x6f\x3c"
    + b"\x8c\x84\xdf\xab\xb6\x66\x3e\xf2\x0c\xd4\x8b\xfe\xe3\xf9\x76\x2f"
    + b"\x14\x1c\x63\x08\x6a\x6f\x2d\xb1\x1a\x95\xb0\xce\x37\xc0\x9c\x6e"
)

REGISTER_URL = "https://android.clients.google.com/c2dm/register3"
CHECKIN_URL = "https://android.clients.google.com/checkin"
FCM_SUBSCRIBE = "https://fcm.googleapis.com/fcm/connect/subscribe"
FCM_ENDPOINT = "https://fcm.googleapis.com/fcm/send"

FCM_AUTH_URL = "https://firebaseinstallations.googleapis.com/v1/projects/hyyp-49b11/installations/"
FCM_REGISTRATION_URL = "https://fcmtoken.googleapis.com/register"
FCM_V1_REGISTRATION_URL = "https://fcmregistrations.googleapis.com/v1/"

GOOGLE_MTALK_ENDPOINT = "mtalk.google.com"
READ_TIMEOUT_SECS = 60 * 60
MIN_RESET_INTERVAL_SECS = 60 * 5
MAX_SILENT_INTERVAL_SECS = 60 * 15

GOOGLE_FCM_PUBLIC_APIKEY = "AIzaSyDH5H6kfGQEWm7FQSYfWYy8OAHPq__5Y6s"

MCS_VERSION = 41
PACKET_BY_TAG = [
    HeartbeatPing,
    HeartbeatAck,
    LoginRequest,
    LoginResponse,
    Close,
    "MessageStanza",
    "PresenceStanza",
    IqStanza,
    DataMessageStanza,
    "BatchPresenceStanza",
    StreamErrorStanza,
    "HttpRequest",
    "HttpResponse",
    "BindAccountRequest",
    "BindAccountResponse",
    "TalkMetadata",
]




class FCMRegistration:
    
    
    def __init__(
        self,
    ) -> None:

        self.blank = '123'

    def __do_request(self, req, retries=5):
        for _ in range(retries):
            try:
                resp = urlopen(req)
                resp_data = resp.read()
                resp.close()
                _LOGGER.debug(resp_data)                
                return resp_data
            except Exception as err:
                _LOGGER.debug("error during request", exc_info=err)
                time.sleep(1)
        return None


    def gcm_check_in(self, androidId=None, securityToken=None, **kwargs):
        """
        perform check-in request

        androidId, securityToken can be provided if we already did the initial
        check-in

        returns dict with androidId, securityToken and more
        """
        chrome = ChromeBuildProto()
        chrome.platform = 3
        chrome.chrome_version = "63.0.3234.0"
        chrome.channel = 1

        checkin = AndroidCheckinProto()
        checkin.type = 3
        checkin.chrome_build.CopyFrom(chrome)  # pylint: disable=maybe-no-member

        payload = AndroidCheckinRequest()
        payload.user_serial_number = 0
        payload.checkin.CopyFrom(checkin)  # pylint: disable=maybe-no-member
        payload.version = 3
        if androidId:
            payload.id = int(androidId)
        if securityToken:
            payload.security_token = int(securityToken)

        _LOGGER.debug(payload)
        req = Request(
            url=CHECKIN_URL,
            headers={"Content-Type": "application/x-protobuf"},
            data=payload.SerializeToString(),
        )
        resp_data = self.__do_request(req)
        resp = AndroidCheckinResponse()
        resp.ParseFromString(resp_data)
        _LOGGER.debug(resp)
        resp = MessageToDict(resp)        
        return resp


    def urlsafe_base64(self, data):
        """
        base64-encodes data with -_ instead of +/ and removes all = padding.
        also strips newlines

        returns a string
        """
        res = urlsafe_b64encode(data).replace(b"=", b"")
        return res.replace(b"\n", b"").decode("ascii")



# start of new FCM functions


    def fcm_get_initial_auth_data(self, app_id, credentials = None, retries = 5):
        """
        get the google firebase auth key for the app. app_id is provided, second half being random (see def register())    

        returns the firebase auth key and the supplied (generated) app_id
        """
       
        data =  {
                "appId":app_id,
                "sdkVersion":"i:8.10.0"
            }
        
        headers = {
                "x-goog-api-key" : GOOGLE_FCM_PUBLIC_APIKEY,        
        }
       
        _LOGGER.debug(data)
        #error checks need to be added
        req = requests.post(url=FCM_AUTH_URL, json=data, headers=headers)
        fcm_auth_data = req.json()
        fcm_auth_data["appid"] = app_id
        return fcm_auth_data



    def fcm_get_token(self, fcm_auth_data):

        
        check_in = self.gcm_check_in() 
        firebase_installation_auth = fcm_auth_data["authToken"]["token"]
        appid = fcm_auth_data["fid"]
        gmp_app_id = fcm_auth_data["appid"]
        androidid = check_in["androidId"]
        security_token = check_in["securityToken"]
        versioninfo = check_in["versionInfo"]
      
        public, private = generate_pair("ec", curve=str("secp256r1"))
        keys = {
            "public": self.urlsafe_base64(public.asn1.dump()[26:]),
            "private": self.urlsafe_base64(private.asn1.dump()),
            "secret": self.urlsafe_base64(os.urandom(16)),
        }
                
        headers = {
                "x-goog-firebase-installations-auth":firebase_installation_auth,
                "authorization":"AidLogin " + androidid + ":" + security_token,
                "info":versioninfo
        }
         
        data = {
            "device":androidid,
            "app":"com.hyyp247.home",
            "app_ver":"4.2.2",
            "X-cliv":"fiid-8.10.0",
            "sender":GCF_SENDER_ID,
            "X-subtype":GCF_SENDER_ID,
            "appid":appid,
            "gmp_app_id":gmp_app_id,
            
            }       
          
        data = urlencode(data)
        req = requests.post(url=FCM_REGISTRATION_URL + "?" + data, headers=headers)
        fcm_token = req.text
        res = {"fcm": fcm_token}
        res.update(check_in)
        res.update(fcm_auth_data)
        res.update(keys)
        return res

    def fcm_subscribe(self, credentials):

        firebase_installation_auth = credentials["auth_info"]["googleAuthToken"]
        androidid = credentials["gcm"]["androidId"]
        fid = credentials["auth_info"]["fid"]
        gmp_app_id = credentials["gcm"]["appId"]
        security_token = credentials["gcm"]["securityToken"]
        fcm_token = credentials["fcm"]["token"]

                 
        headers = {
                "x-goog-firebase-installations-auth":firebase_installation_auth,
                "authorization":"AidLogin " + androidid + ":" + security_token,
        }
      
        data = {
            "device":androidid,
            "app":"com.hyyp247.home",
            "app_ver":"4.2.2",
            "X-cliv":"fiid-8.10.0",
            "sender":GCF_SENDER_ID,
            "X-subtype":GCF_SENDER_ID,
            "appid":fid,
            "gmp_app_id":gmp_app_id,
            "endpoint": "{}/{}".format(FCM_ENDPOINT, fcm_token),
            "p256dh": credentials["keys"]["public"],
            "auth": credentials["keys"]["secret"],           
            }       
      
       
        data = urlencode(data)
        req = requests.post(url=FCM_REGISTRATION_URL + "?" + data, headers=headers)
        return req




#this isn't being used. I tested this but it doesn't seem to be working correctly
# I am keeping the code to not lose the work I put in

    def fcm_register_with_v1_api(self, credentials, retries = 5):  
        print("using v1 api")
        firebase_installation_auth = credentials["auth_info"]["googleAuthToken"]
        androidid = credentials["gcm"]["androidId"]
        security_token = credentials["gcm"]["securityToken"]
        fcm_token = credentials["fcm"]["token"]
 
 
        headers = {
                "x-goog-api-key" : GOOGLE_FCM_PUBLIC_APIKEY, 
                "x-goog-firebase-installations-auth":firebase_installation_auth,
                "authorization":"AidLogin " + androidid + ":" + security_token,
        }
 
         
        data = {"web":{
                "endpoint": "{}/{}".format(FCM_ENDPOINT, fcm_token),
                "p256dh": credentials["keys"]["public"],
                "auth": credentials["keys"]["secret"],
                }
        }    
           
        
        url_full = FCM_V1_REGISTRATION_URL + "projects/" + str(GCF_SENDER_ID) + "/registrations"
        _LOGGER.debug(data)
        print("---")
        resp_data = requests.post(url=url_full, json=data, headers=headers)
        return resp_data

        
    
    


    def build_credetials_json(self, all_info):
        
        
        appid = all_info["appid"]
        android_id = all_info["androidId"]
        security_token = all_info["securityToken"]
        google_auth_token = all_info["authToken"]["token"]
        refresh_token = all_info["refreshToken"]
        version_info = all_info["versionInfo"]
        name = all_info["name"]
        fid = all_info["fid"]
        fcmtoken = all_info["fcm"].replace("token=","")
        publickey = all_info["public"]
        privatekey = all_info["private"]
        secretkey = all_info["secret"]
        
        
        
        processed_credentials = {
                                    "gcm":{
                                        "appId":appid,
                                        "androidId":android_id,
                                        "securityToken":security_token,
                                        "versionInfo":version_info,            
                                    },
                                    "fcm":{
                                        "token":fcmtoken,
                                        "refreshToken":refresh_token,                                      
                                    },
                                    "auth_info":{
                                        "versionInfo":version_info,
                                        "googleAuthToken":google_auth_token,
                                        "name":name,
                                        "fid":fid,                                     
                                    },
                                    "keys":{
                                        "public":publickey,
                                        "private":privatekey,
                                        "secret":secretkey, 
                                    }
            
        }
      

        return processed_credentials
        
        
        


    def register(self):
        """register gcm and fcm tokens for sender_id"""
        app_id = "1:87969245803:ios:" + os.urandom(8).hex()
        subscription = self.fcm_get_initial_auth_data(app_id=app_id)
        credentials_unprocessed = self.fcm_get_token(fcm_auth_data=subscription)
        credentials = self.build_credetials_json(credentials_unprocessed)
        self.fcm_subscribe(credentials=credentials)
        return credentials







#end of new fcm functions





# -------------------------------------------------------------------------


class FCMListener:

    
    def __init__(
        self,
    ) -> None:
        self.fcm_registration = FCMRegistration()
        self.received_persistent_ids = []
        self.time_of_last_reset = 0
        self.time_of_last_receive = time.time()
        self.current_ping_thread = 0
        self.listen_for_data_thread = 0
        self.awaiting_ack = False
        self.ids_callback = None


    def __read(self, sock, size):
        _LOGGER.debug("Started reading")
        _LOGGER.debug("Size: " + str(size))
        _count = 0
        buf = b""
        while len(buf) < size:
            _count += 1
            buf += sock.recv(size - len(buf))
            if _count > 10:
                _LOGGER.debug("Escaped infite loop")
                sock.close()
                return buf
        _LOGGER.debug("Finished reading")
        return buf
        

    # protobuf variable length integers are encoded in base 128
    # each byte contains 7 bits of the integer and the msb is set if there's
    # more. pretty simple to implement


    def __read_varint32(self, value):
        res = 0
        shift = 0
        while True:
            (b,) = struct.unpack("B", self.__read(value, 1))
            res |= (b & 0x7F) << shift
            if (b & 0x80) == 0:
                break
            shift += 7
        return res


    def __encode_varint32(self, value):
        res = bytearray([])
        while value != 0:
            b = value & 0x7F
            value >>= 7
            if value != 0:
                b |= 0x80
            res.append(b)
        return bytes(res)


    def __send(self, google_socket, data):
        header = bytearray([MCS_VERSION, PACKET_BY_TAG.index(type(data))])
        _LOGGER.debug(data)
        payload = data.SerializeToString()
        buf = bytes(header) + self.__encode_varint32(len(payload)) + payload
        _LOGGER.debug(hexlify(buf))
        total = 0
        while total < len(buf):
            sent = google_socket.send(buf[total:])
            if sent == 0:
                raise RuntimeError("socket connection broken")
            total += sent


    def __recv(self, data, first=False):

        try:
            readable, _, _ = select.select(
                [
                    data,
                ],
                [],
                [],
                READ_TIMEOUT_SECS,
            )
            if len(readable) == 0:
                _LOGGER.debug("Select read timeout")
                return None

        except select.error:
            _LOGGER.debug("Select error")
            return None

        _LOGGER.debug("Data available to read")

        if first:
            version, tag = struct.unpack("BB", self.__read(data, 2))
            _LOGGER.debug("version %s", version)
            if version < MCS_VERSION and version != 38:
                raise RuntimeError("protocol version {} unsupported".format(version))
        else:
            (tag,) = struct.unpack("B", self.__read(data, 1))
        _LOGGER.debug("tag %s (%s)", tag, PACKET_BY_TAG[tag])
        size = self.__read_varint32(data)
        _LOGGER.debug("size %s", size)
        self.time_of_last_receive = time.time()
        if size >= 0:
            buf = self.__read(data, size)
            _LOGGER.debug(hexlify(buf))
            packet = PACKET_BY_TAG[tag]
            payload = packet()
            payload.ParseFromString(buf)
            _LOGGER.debug(payload)
            return payload
        return None


    def __app_data_by_key(self, data, key, blow_shit_up=True):
        for item in data.app_data:
            if item.key == key:
                return item.value
        if blow_shit_up:
            raise RuntimeError("couldn't find in app_data {}".format(key))
        return None


    def __open(self):

        context = ssl.create_default_context()
        google_socket = socket.create_connection((GOOGLE_MTALK_ENDPOINT, 5228))
        google_socket = context.wrap_socket(
            google_socket, server_hostname=GOOGLE_MTALK_ENDPOINT
        )
        _LOGGER.debug("connected to ssl socket")
        return google_socket


    def __login(self, credentials, persistent_ids):
        google_socket = self.__open()
        self.fcm_registration.gcm_check_in(**credentials["gcm"])
        req = LoginRequest()
        req.adaptive_heartbeat = False
        req.auth_service = 2
        req.auth_token = credentials["gcm"]["securityToken"]
        req.id = "chrome-63.0.3234.0"
        req.domain = "mcs.android.com"
        req.device_id = "android-%x" % int(credentials["gcm"]["androidId"])
        req.network_type = 1
        req.resource = credentials["gcm"]["androidId"]
        req.user = credentials["gcm"]["androidId"]
        req.use_rmq2 = True
        req.setting.add(name="new_vc", value="1")  # pylint: disable=maybe-no-member
        req.received_persistent_id.extend(persistent_ids)  # pylint: disable=maybe-no-member
        self.__send(google_socket, req)
        login_response = self.__recv(google_socket, first=True)
        _LOGGER.debug("Received login response: %s", login_response)
        self.time_of_last_receive = time.time() + 60
        thread.Thread(target=self.__ping_scheduler, args=(google_socket,
                                                          credentials,
                                                          persistent_ids)).start()

        return google_socket


    def __reset(self, google_socket, credentials, persistent_ids):
        now = time.time()
        if now - self.time_of_last_reset < MIN_RESET_INTERVAL_SECS:
            raise Exception("Too many connection reset attempts.")
        self.time_of_last_reset = now
        _LOGGER.debug("Reestablishing connection")
        try:
            google_socket.shutdown(2)
            google_socket.close()
        except OSError as err:
            _LOGGER.debug("Unable to close connection %f", err)
        return self.__login(credentials, persistent_ids)


    def _close_socket(self, google_socket):
        try:
            google_socket.shutdown(2)
            google_socket.close()
        except OSError as err:
            _LOGGER.debug("Unable to close connection %f", err)
            
    def _restart_push_receiver(self, google_socket):
        self.current_ping_thread += 1
        self.awaiting_ack = False
        self.time_of_last_receive = time.time() + 60
        self.listen_for_data_thread += 1
        self._close_socket(google_socket)
        _LOGGER.debug("RESTARTING PUSH RECEIVER")
        self.ids_callback("restart_push_receiver")
        


    def __ping_scheduler(self, google_socket, credentials, persistent_ids):
        self.current_ping_thread += 1
        if self.current_ping_thread > 1000:
            self.current_ping_thread = 1
        mythread = self.current_ping_thread
        while mythread == self.current_ping_thread:
            if self.awaiting_ack:
                _LOGGER.debug(str(mythread) + ": Ping Timeout resetting")
                self._restart_push_receiver(google_socket=google_socket)
                break
            if time.time() - self.time_of_last_receive > MAX_SILENT_INTERVAL_SECS:
                _LOGGER.debug(str(mythread) + ": Sending PING now==========================")
                self.awaiting_ack = True
                try:
                    self.__send_ping(google_socket=google_socket)
                except:
                    _LOGGER.debug("Error with ping send %f")
                    self._restart_push_receiver(google_socket=google_socket)
                    break
            if not self._internet_connectivity():
                self.awaiting_ack = True
            time.sleep(60)
        _LOGGER.debug("Closing PING thread : " + str(mythread))

                
                    
    def __send_ping(self, google_socket):
        header = bytearray([0, 0])
        buf = bytes(header)
        total = 0
        while total < len(buf):
            sent = google_socket.send(buf[total:])
            if sent == 0:
                raise RuntimeError("socket connection broken")
            total += sent
     
     
    def __handle_ping(self, google_socket):
        header = bytearray([0, 2])
        buf = bytes(header)
        total = 0
        while total < len(buf):
            sent = google_socket.send(buf[total:])
            if sent == 0:
                raise RuntimeError("socket connection broken")
            total += sent
  
     
    def __listen(self, credentials, on_notify_callback, ids_callback, received_persistent_ids=None, obj=None):
        received_persistent_ids = []
        if received_persistent_ids is None:
            received_persistent_ids = []   
        persistent_ids = received_persistent_ids
        self.fcm_registration.fcm_subscribe(credentials=credentials)
        google_socket = self.__login(credentials, persistent_ids)
        self.listen_for_data_thread += 1
        mythread = self.listen_for_data_thread
        while mythread == self.listen_for_data_thread:
            try:
                data = self.__recv(google_socket)
                if isinstance(data, DataMessageStanza):
                    msg_id = self.__handle_data_message(data, credentials, on_notify_callback, obj)
                    persistent_ids.append(msg_id)
                elif isinstance(data, HeartbeatPing):
                    self.__handle_ping(google_socket)
                elif isinstance(data, HeartbeatAck):
                    self.awaiting_ack = False
                elif data is None or isinstance(data, Close):
                    self.listen_for_data_thread += 1
                else:
                    _LOGGER.debug("Unexpected message type %s", type(data))
            except ConnectionResetError:
                _LOGGER.debug("Connection Reset: Reconnecting")
                self.listen_for_data_thread += 1
            except:
                _LOGGER.debug("Other Listener Error")
                self.listen_for_data_thread += 1
        _LOGGER.debug("Closing main thread" + str(mythread))
        self._close_socket(google_socket=google_socket)    
                


    def __handle_data_message(self, data, credentials, callback, obj):
        load_der_private_key = serialization.load_der_private_key

        crypto_key = self.__app_data_by_key(
            data, "crypto-key", blow_shit_up=False
        )  # Can be None
        if crypto_key:
            crypto_key = crypto_key[3:]  # strip dh=

        salt = self.__app_data_by_key(data, "encryption", blow_shit_up=False)  # Can be None
        if salt:
            salt = salt[5:]  # strip salt=

        crypto_key = urlsafe_b64decode(crypto_key.encode("ascii"))
        salt = urlsafe_b64decode(salt.encode("ascii"))
        der_data = credentials["keys"]["private"]
        der_data = urlsafe_b64decode(der_data.encode("ascii") + b"========")
        secret = credentials["keys"]["secret"]
        secret = urlsafe_b64decode(secret.encode("ascii") + b"========")
        privkey = load_der_private_key(der_data, password=None, backend=default_backend())
        decrypted = http_ece.decrypt(
            data.raw_data,
            salt=salt,
            private_key=privkey,
            dh=crypto_key,
            version="aesgcm",
            auth_secret=secret,
        )
        _LOGGER.debug("Received data message %s: %s", data.persistent_id, decrypted)
        callback(obj, json.loads(decrypted.decode("utf-8")), data)
        return data.persistent_id
   

    def runner(self, callback, credentials = None, persistent_ids = None):
        """Registers a token and waits for notifications"""
        #_LOGGER.setLevel(logging.DEBUG)
        ids_callback = callback
        
        if persistent_ids is None:
            persistent_ids = []
        if credentials is None:
            credentials = self.fcm_registration.register()
            _credentials = {"credentials" : credentials}
            callback(_credentials) #doesn't do anything for now. Using a different method currently

        def on_notification(obj, notification, data_message):
            idstr = data_message.persistent_id
            if idstr in persistent_ids:
                return
            persistent_ids.append(idstr)
            self.received_persistent_ids = persistent_ids
            _new_persistend_ids = {"new_persistent_id" : idstr}
            callback(_new_persistend_ids)
            _notification = {"notification" : notification}
            callback(_notification)
            _LOGGER.debug(_notification)   
         
        self.__listen(credentials=credentials, on_notify_callback=on_notification, ids_callback=ids_callback, received_persistent_ids=self.received_persistent_ids)
        
    def _internet_connectivity(self):
        return ClientTools().internet_connectivity()