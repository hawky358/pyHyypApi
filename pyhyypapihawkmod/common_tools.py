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
        reply = requests.get('http://www.msftconnecttest.com/connecttest.txt')
        if reply.status_code != 200:
            return False
        if reply.text != "Microsoft Connect Test":
            return False
        return True