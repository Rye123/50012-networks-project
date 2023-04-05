import traceback
from time import sleep
from typing import Type, Tuple, List, Dict, Any
import logging
from socket import socket, AF_INET, SOCK_DGRAM

### DEEP DARK MAGIC TO ALLOW FOR ABSOLUTE IMPORT
from pathlib import Path
import sys
path = str(Path(Path(__file__).parent.absolute()).parent.absolute())
sys.path.insert(0, path)
### END OF DEEP DARK MAGIC

from ctp import CTPPeer, RequestHandler, Listener
from ctp import CTPMessage, CTPMessageType, CTPConnectionError, AddressType
from util import FileInfo, File, FileError, Block
from util import ensure_shared_folder, standardHandler

# Logging Settings
APP_LOGGING_LEVEL = logging.DEBUG
CTP_LOGGING_LEVEL = logging.DEBUG # Recieve only warnings from CTP.
UTIL_LOGGING_LEVEL = logging.WARNING # Receive only warnings from util

logger = logging.getLogger()
logger.setLevel(APP_LOGGING_LEVEL)
ctp_logger = logging.getLogger('ctp')
ctp_logger.setLevel(CTP_LOGGING_LEVEL)
util_logger = logging.getLogger('util')
util_logger.setLevel(UTIL_LOGGING_LEVEL)
logger.addHandler(standardHandler)

BOOTSTRAPPED_PEERLIST:List['PeerInfo'] = []
SERVER_PEER_ID = '000____ctp_server_peer_id____000'
DEFAULT_SERVER_ADDRESS = ('127.0.0.1', 6969)

class Cluster:
    def __init__(self, cluster_id: str):
        self.cluster_id = cluster_id
        self.peermap:Dict[str, PeerInfo] = {}

    def add_peer(self, peer: 'PeerInfo'):
        self.peermap[peer.peer_id] = peer
        logger.info(f"Cluster {self.cluster_id}: Added new peer {peer.peer_id}")

    def remove_peer(self, peer_id: str):
        self.peermap.pop(peer_id, None)
        logger.info(f"Cluster {self.cluster_id}: Removed peer {peer_id}")
    
    def generate_peerlist(self) -> str:
        """
        Returns the peerlist as a string.
        - Peer IDs are in alphabetical order.
        """
        peer_ids = sorted(list(self.peermap.keys()))
        peer_lines = []
        for peer_id in peer_ids:
            addr = self.peermap.get(peer_id).address
            peer_lines.append(f"{peer_id} {addr[0]} {addr[1]}")
        return "\r\n".join(peer_lines)

class PeerInfo:
    """
    Class that encapsulates data for each peer.

    This is used to define the other peers for this peer to connect to.
    """
    def __init__(self, cluster_id: str, peer_id: str, address: Tuple[str, int]):
        self.cluster_id = cluster_id
        self.peer_id = peer_id
        self.address = address

class ServerRequestHandler(RequestHandler):
    """
    - `peer`: The `Server` object.
    - `cluster_id`: The cluster in which the request was sent in.
    - `request_addr`: The request sender's address.
    - `peer_id`: The server peer ID.
    """

    def __init__(self, peer: 'Server', request: CTPMessage, client_addr: AddressType):
        self.peer = peer # just to overwrite the unofficial class
        self.cluster_id = request.cluster_id
        self.request_addr = client_addr
        self.peer_id = SERVER_PEER_ID
        super().__init__(peer, request, client_addr)

    def cleanup(self):
        self.close()

    def send_response(self, msg_type: CTPMessageType, data: bytes):
        """
        Sends a response. This overwrites `RequestHandler.send_response()`, using \
        the request's cluster ID.
        """
        if not isinstance(msg_type, CTPMessageType) or msg_type.is_request():
            raise ValueError("Invalid msg_type: msg_type should be a CTPMessageType and a response.")
        
        response = CTPMessage(
            msg_type,
            data,
            self.cluster_id,
            self.peer_id
        )
        self.peer._send_message(response, self.client_addr)
        self.peer._log("debug", f"Responded with {response.msg_type.name}.")
    
    def handle(self, request: CTPMessage):
        match request.msg_type:
            case CTPMessageType.STATUS_REQUEST:
                self.handle_status_request(request)
            case CTPMessageType.BLOCK_REQUEST:
                self.handle_block_request(request)
            case CTPMessageType.CLUSTER_JOIN_REQUEST:
                self.handle_cluster_join_request(request)
            case CTPMessageType.MANIFEST_REQUEST:
                self.handle_manifest_request(request)
            case CTPMessageType.CRINFO_RESPONSE:
                self.handle_crinfo_request(request)
            case CTPMessageType.NO_OP:
                self.handle_no_op(request)
            case _:
                self.handle_unknown_request(request)
    
    def handle_status_request(self, request: CTPMessage):
        return super().handle_status_request(request)

    def handle_block_request(self, request: CTPMessage):
        return super().handle_block_request(request)

    def handle_cluster_join_request(self, request: CTPMessage):
        # Create new PeerInfo object from the requestor
        cluster_id = self.cluster_id
        peer_id = request.sender_id
        peer_addr = self.request_addr
        
        new_peer = PeerInfo(cluster_id, peer_id, peer_addr)
        
        # Validation
        if cluster_id not in self.peer.clusters.keys():
            self.send_response(CTPMessageType.INVALID_REQ, "No such cluster.".encode('ascii'))
            return
        
        self.peer.clusters[cluster_id].add_peer(new_peer)
        data_str:str = self.peer.clusters[cluster_id].generate_peerlist()
        self.send_response(
            CTPMessageType.CLUSTER_JOIN_RESPONSE,
            data_str.encode('ascii')
        )


    def handle_manifest_request(self, request: CTPMessage):
        pass

    def handle_crinfo_request(self, request: CTPMessage):
        pass

    def handle_no_op(self, request: CTPMessage):
        pass

    def handle_status_request(self, request: CTPMessage):
        pass

    def handle_unknown_request(self, request: CTPMessage):
        self.send_response(CTPMessageType.UNEXPECTED_REQ, b'unknown request')

class Server(CTPPeer):
    """
    CTP Server.

    Since it doesn't have its own `cluster_id`, several methods have been \
    overwritten.
    - `clusters`: A dictionary linking a `cluster_id` to the `Cluster` object.
    """
    def __init__(self, address: AddressType):
        if not isinstance(address, Tuple):
            if not isinstance(address[0], str) or not isinstance(address[1], int):
                raise TypeError("Invalid address: address should be a tuple of an IP address and a port.")
        self.peer_id = SERVER_PEER_ID
        self.short_peer_id = SERVER_PEER_ID[:6]
        self.clusters:Dict[str, Cluster] = {}

        self.cluster_id = None
        self.requestHandlerClass = ServerRequestHandler
        self.peer_addr = address
        self.sock = socket(AF_INET, SOCK_DGRAM)
        self.sock.bind(address)
        self.listener = Listener(self)

    def send_request(self, cluster_id: str, msg_type: CTPMessageType, data: bytes, dest_addr: AddressType, timeout: float = 1, retries: int = 0) -> CTPMessage:
        if cluster_id not in self.clusters.keys():
            raise ValueError("No such cluster.")
        
        self.cluster_id = cluster_id # Set cluster ID to send to first
        response = super().send_request(msg_type, data, dest_addr, timeout, retries)
        self.cluster_id = None # reset cluster ID so we get an error if this is used elsewhere.
        
        return response

    def add_cluster(self, cluster_id: str):
        new_cluster = Cluster(cluster_id)
        self.clusters[cluster_id] = new_cluster

if __name__ == "__main__":
    server = None
    try:
        server = Server(DEFAULT_SERVER_ADDRESS)
        server.add_cluster("3f80e91dc65311ed93abeddb088b3faa")

        server.listen()
        while True:
            pass
    except KeyboardInterrupt:
        print("Interrupt")
    except Exception:
        print(traceback.format_exc())
    finally:
        server.end()