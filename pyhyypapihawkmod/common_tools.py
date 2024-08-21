import logging
import requests

_LOGGER = logging.getLogger(__name__)


class ClientTools:
    """Initialize api client object."""

    def __init__(
        self,
    ) -> None:
        """Initialize the client object."""
        
    def internet_connectivity(self):
        _LOGGER.debug("Checking for connectivity")
        try:
            reply = requests.get('http://www.msftconnecttest.com/connecttest.txt')
        except requests.exceptions.RequestException:
            return False
        if reply.status_code != 200:
            return False
        if reply.text != "Microsoft Connect Test":
            return False
        return True