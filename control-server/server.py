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
from util import standardHandler, SharedDirectory

# Logging Settings
APP_LOGGING_LEVEL = logging.DEBUG
CTP_LOGGING_LEVEL = logging.WARNING # Recieve only warnings from CTP.
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
        req_seqnum = self.request.seqnum
        resp_seqnum = req_seqnum + 1
        
        response = CTPMessage(
            msg_type,
            resp_seqnum,
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
            case CTPMessageType.NEW_CRINFO_NOTIF:
                self.handle_new_crinfo_notif(request)
            case CTPMessageType.NO_OP:
                self.handle_no_op(request)
            case _:
                self.handle_unknown_request(request)
    
    def handle_status_request(self, request: CTPMessage):
        self.send_response(CTPMessageType.STATUS_RESPONSE, b'status: 1')

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

    def handle_new_crinfo_notif(self, request: CTPMessage):
        # Request contains the new CRINFO file in bytes.
        try:
            filename_b, crinfo_b = request.data.split(b'\r\n\r\n', 1)
            filename = filename_b.decode('ascii')
            fileinfo = FileInfo._from_bytes(self.peer.shareddir, filename, crinfo_b)
            response_data_b = b''
            if fileinfo not in self.peer.fileinfo_map.values():
                self.peer.add_fileinfo(fileinfo)
                logger.info(f"Added new CRINFO of {filename}")
                response_data_b = b'success'
            else:
                logger.info(f"CRINFO already exists.")
                response_data_b = b'error: exists'
                
            self.send_response(
                CTPMessageType.NEW_CRINFO_NOTIF_ACK,
                response_data_b
            )
        except ValueError:
            # return an error message
            self.send_response(
                CTPMessageType.INVALID_REQ,
                b"error: corrupted CRINFO file or filename"
            )

    def handle_manifest_request(self, request: CTPMessage):
        """
        Return the manifest CRINFO file.
        """
        manifest_crinfo_b = b''
        with self.peer.get_manifest_crinfo().filepath.open('rb') as f:
            manifest_crinfo_b = f.read()

        self.send_response(
            CTPMessageType.MANIFEST_RESPONSE,
            manifest_crinfo_b
        )

    def handle_crinfo_request(self, request: CTPMessage):
        pass

    def handle_no_op(self, request: CTPMessage):
        pass

    def handle_unknown_request(self, request: CTPMessage):
        self.send_response(CTPMessageType.UNEXPECTED_REQ, b'unknown request')

class ServerError(Exception):
    """
    Generic server error.
    """

    def __init__(self, *args: object) -> None:
        super().__init__(*args)

class Server(CTPPeer):
    """
    CTP Server.

    Since it doesn't have its own `cluster_id`, several methods have been \
    overwritten.
    - `clusters`: A dictionary linking a `cluster_id` to the `Cluster` object.
    """
    FILE_MANIFEST_FILENAME = ".crmanifest"

    def __init__(self, address: AddressType, shared_dir_path: Path):
        if not isinstance(address, Tuple):
            if not isinstance(address[0], str) or not isinstance(address[1], int):
                raise TypeError("Invalid address: address should be a tuple of an IP address and a port.")
        self.peer_id = SERVER_PEER_ID
        self.short_peer_id = SERVER_PEER_ID[:6]
        self.clusters:Dict[str, Cluster] = {}
        self.cluster_id = None

        self.fileinfo_map:Dict[str, FileInfo] = {} # maps filename to FileInfo object
        self.shareddir = SharedDirectory(shared_dir_path)
        manifest_path = shared_dir_path.joinpath("manifest")
        self.manifestdir = SharedDirectory(manifest_path)
        self.shareddir.refresh()
        self.manifestdir.refresh()
        self._parse_manifest()

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
    
    def add_fileinfo(self, fileinfo: FileInfo):
        self.fileinfo_map[fileinfo.filename] = fileinfo
        fileinfo.write()
        logger.info(f"Saved {fileinfo.filename} fileinfo.")
        self._update_manifest()

    def get_manifest_crinfo(self) -> FileInfo:
        """
        Returns the CRINFO of the manifest file on the server.
        """
        self._update_manifest()
        return self.manifestdir.filemap.get(self.FILE_MANIFEST_FILENAME).fileinfo

    def _update_manifest(self):
        """
        Updates the server's local file manifest based on the current list of FileInfos.
        """
        filenames = sorted(self.fileinfo_map.keys())
        print(filenames)
        manifest_bytes = ('\r\n'.join(filenames)).encode('ascii')
        self.manifestdir.add_file(self.FILE_MANIFEST_FILENAME, manifest_bytes)

        logger.info(f"Updated stored manifest.")

    def _parse_manifest(self):
        """
        Overwrites in-memory `fileinfo_map` with the local manifest.
        """
        logger.info("Parsing stored manifest...")
        # If file already exists, set it.
        manifest_file = self.manifestdir.filemap.get(self.FILE_MANIFEST_FILENAME, None)

        # Otherwise, create it
        if manifest_file is None:
            logger.debug("No existing manifest, creating one.")
            self.manifestdir.add_file(self.FILE_MANIFEST_FILENAME, b'')
            manifest_file = self.manifestdir.filemap.get(self.FILE_MANIFEST_FILENAME, None)

            # if it's still None let's just quit while we're still ahead
            if manifest_file is None:
                raise ServerError("Manifest File could not be created.")

        # Now, overwrite.
        data = manifest_file.data.decode('ascii')
        filenames:List[str] = data.split('\r\n')
        for filename in filenames:
            filename = filename.strip()
            if len(filename) == 0:
                continue
            path = self.shareddir.crinfo_dirpath.joinpath(filename)
            self.fileinfo_map[filename] = FileInfo.from_crinfo(path.with_suffix(path.suffix + f".{FileInfo.CRINFO_EXT}"))
        logger.info(f"Loaded {len(self.fileinfo_map)} FileInfo objects.")

        manifest_file.write_file()

if __name__ == "__main__":
    server = Server(DEFAULT_SERVER_ADDRESS, Path('./control-server/data'))
    try:
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