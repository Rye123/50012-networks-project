import traceback
from time import sleep
from typing import Type, Tuple, List, Dict, Any
from threading import Timer, Event, Thread
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
DEFAULT_SERVER_ADDRESS = ('', 6969)

class Cluster:
    TIMEOUT_INTERVAL = 30.0

    def __init__(self, cluster_id: str):
        self.cluster_id = cluster_id
        self.peermap:Dict[str, PeerInfo] = {}
        self.peertimers:Dict[str, Timer] = {}
        self.peer_left:Event = Event() # if set, a peer has left. This is to indicate a peerleft event to the server.
                                       #TODO: refactor so this works for a change to the peerlist

    def add_peer(self, peer: 'PeerInfo'):
        """
        Adds a peer to the cluster.
        - This overrides the existing peer in there if any.
        """
        self.peermap[peer.peer_id] = peer
        self.start_peertimer(peer.peer_id)
        logger.info(f"Cluster {self.cluster_id}: Added new peer {peer.peer_id}")

    def remove_peer(self, peer_id: str):
        self.peermap.pop(peer_id, None)
        self.peer_left.set()
        logger.info(f"Cluster {self.cluster_id}: Removed peer {peer_id}")
    
    def peer_left_ack(self):
        """
        Clears the `peer_left` Event.
        """
        self.peer_left.clear()
    
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

    def start_peertimer(self, peer_id: str):
        """
        Starts the timer associated with a peer.
        """
        self.peertimers[peer_id] = Timer(self.TIMEOUT_INTERVAL, self.peer_timeout, args=[peer_id])
        self.peertimers[peer_id].start()

    def reset_peertimer(self, peer_id: str):
        """
        Reset the timer associated with a peer.
        - `peer_id`: The peer associated with the timer.
        """
        self.peertimers[peer_id].cancel()
        self.start_peertimer(peer_id)
    
    def peer_timeout(self, peer_id: str):
        """
        Timeout for a peer. The peer will be kicked out.
        """
        if self.peertimers[peer_id].is_alive(): # kill the timer if it's still alive
            self.peertimers[peer_id].cancel()
            self.peertimers[peer_id] = None
        self.remove_peer(peer_id)
    
    def end(self):
        """
        Ends the cluster, and all corresponding timeouts for the peers.
        """
        for peertimer in self.peertimers.values():
            if peertimer is not None:
                peertimer.cancel()


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
        logger.debug(f"Responded with {response.msg_type.name}.")
    
    def handle(self, request: CTPMessage):
        logger.debug(f"Received {request.msg_type.name} from {request.sender_id}.")
        # Update timer for the peer
        cluster_id = request.cluster_id
        peer_id = request.sender_id
        if peer_id in self.peer.clusters[cluster_id].peermap.keys():
            self.peer.clusters[cluster_id].reset_peertimer(peer_id)

        # Match request
        try:
            match request.msg_type:
                case CTPMessageType.STATUS_REQUEST:
                    self.handle_status_request(request)
                case CTPMessageType.BLOCK_REQUEST:
                    self.handle_block_request(request)
                case CTPMessageType.CLUSTER_JOIN_REQUEST:
                    self.handle_cluster_join_request(request)
                case CTPMessageType.MANIFEST_REQUEST:
                    self.handle_manifest_request(request)
                case CTPMessageType.CRINFO_REQUEST:
                    self.handle_crinfo_request(request)
                case CTPMessageType.NEW_CRINFO_NOTIF:
                    self.handle_new_crinfo_notif(request)
                case CTPMessageType.NO_OP:
                    self.handle_no_op(request)
                case _:
                    self.handle_unknown_request(request)
        except Exception as e:
            logger.error(str(e))
            if request.msg_type != CTPMessageType.NO_OP:
                self.send_response(CTPMessageType.SERVER_ERROR, b'')
    
    def handle_status_request(self, request: CTPMessage):
        self.send_response(CTPMessageType.STATUS_RESPONSE, b'status: 1')

    def handle_block_request(self, request: CTPMessage):
        # Parse request
        packet = request.data
        requested_block = Block.unpack(packet)

        # Check if we have the block (in manifestdir)
        manifest_file = self.peer.manifestdir.filemap.get(self.peer.FILE_MANIFEST_FILENAME)
        if requested_block.filehash != manifest_file.fileinfo.filehash:
            self.send_response(CTPMessageType.INVALID_REQ, b'server does not serve files other than the manifest')
            return
        
        for block in manifest_file.blocks:
            if block.block_id != requested_block.block_id:
                continue
            # Found, return response
            if block.downloaded:
                self.send_response(
                    CTPMessageType.BLOCK_RESPONSE,
                    block.pack()
                )
            else:
                # we don't have it. why don't we have it why why why
                self.send_response(CTPMessageType.SERVER_ERROR, b'help')
                logger.critical(f"Server does not have {block.block_id}.")
                
            return
        
        self.send_response(CTPMessageType.INVALID_REQ, b'requested block does not exist')
        logger.debug(f"Client requested for {requested_block.block_id}, which does not exist.")
        
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

        # Update the other peers
        self.peer.push_peerlist(cluster_id, peer_id)
        logger.info(f"New peer: {peer_id}. All peers updated.")
        

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
        logger.info("Returned manifest.")

    def handle_crinfo_request(self, request: CTPMessage):
        # Request data is in the form filename: {filename}.
        data = request.data.decode('ascii').split(": ", 1)
        filename = data[1]

        # Return the appropriate file
        if filename in self.peer.fileinfo_map.keys():
            data = b''
            with self.peer.fileinfo_map.get(filename).filepath.open('rb') as f:
                data = f.read()

            if data != b'':
                self.send_response(
                    CTPMessageType.CRINFO_RESPONSE,
                    data
                )
                logger.info(f"Returned fileinfo for {filename}")
                return
            self.send_response(
                CTPMessageType.SERVER_ERROR,
                b''
            )
            logger.error(f"Could not read fileinfo {filename}")
        else:
            self.send_response(
                CTPMessageType.INVALID_REQ,
                b'unknown filename'
            )
            logger.info(f"Could not locate fileinfo for {filename}")

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
    - `shareddir`: `SharedDirectory` object associated with the known fileinfos
    - `manifestdir`: `SharedDirectory` object associated with the file manifest.
    - `fileinfo_map`: Dictionary associating a filename to a `FileInfo` object.
    """
    FILE_MANIFEST_FILENAME = ".crmanifest"

    def __init__(self, address: AddressType, shared_dir_path: Path):
        if not isinstance(address, Tuple):
            if not isinstance(address[0], str) or not isinstance(address[1], int):
                raise TypeError("Invalid address: address should be a tuple of an IP address and a port.")
        self.peer_id = SERVER_PEER_ID
        self.short_peer_id = SERVER_PEER_ID[:6]
        self.clusters:Dict[str, Cluster] = {}
        self.clusters_peerlist_watchers:Dict[str, Thread] = {}
        self.cluster_id = None
        self.clusters_stop_signal:Event = Event()

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
        self.listener = Listener(self)
    
    def send_request(self, cluster_id: str, msg_type: CTPMessageType, data: bytes, dest_addr: AddressType, timeout: float = 1, retries: int = 0) -> CTPMessage:
        if cluster_id not in self.clusters.keys():
            raise ValueError("No such cluster.")
        
        self.cluster_id = cluster_id # Set cluster ID to send to first
        response = super().send_request(msg_type, data, dest_addr, timeout, retries)
        self.cluster_id = None # reset cluster ID so we get an error if this is used elsewhere.
        
        return response

    def _watch_cluster(self, cluster: Cluster):
        """
        Watches for the `peer_left` Event on a given cluster.
        """
        cluster.peer_left_ack()

        while not self.clusters_stop_signal.is_set():
            while not cluster.peer_left.is_set():
                sleep(1)
                if self.clusters_stop_signal.is_set():
                    cluster.peer_left_ack()
                    return
            
            # push out the notification about peer leaving
            self.push_peerlist(cluster.cluster_id)
            logger.info("Peerlist pushed.")
            cluster.peer_left_ack()
        cluster.peer_left_ack()

    def add_cluster(self, cluster_id: str):
        new_cluster = Cluster(cluster_id)
        self.clusters[cluster_id] = new_cluster
        self.clusters_peerlist_watchers[cluster_id] = Thread(target=self._watch_cluster, args=[new_cluster])
        self.clusters_peerlist_watchers[cluster_id].start()
    
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
    
    def push_peerlist(self, cluster_id: str, peer_id: str=None):
        """
        Pushes an updated peerlist to all peers in a given cluster, excluding a given peer_id
        - This is to update all existing peers except a given peer.
        - If we want to update ALL (e.g. for peer_left events)
        """
        cluster = self.clusters[cluster_id]
        for peer in cluster.peermap.values():
            if peer_id is not None:
                if peer.peer_id == peer_id:
                    continue
            self.send_request(
                cluster_id,
                CTPMessageType.PEERLIST_PUSH,
                cluster.generate_peerlist().encode('ascii'),
                peer.address
            )

    def end(self):
        # Stop watching clusters
        self.clusters_stop_signal.set()
        logger.debug("Watchers on cluster peerlists stopped.")

        # End clusters
        for cluster in self.clusters.values():
            cluster.end()
        logger.debug("Clusters deinitialised.")

        super().end()


    def _update_manifest(self):
        """
        Updates the server's local file manifest based on the current list of FileInfos.
        """
        filenames = sorted(self.fileinfo_map.keys())
        manifest_bytes = ('CRMANIFEST\r\n\r\n' + '\r\n'.join(filenames)).encode('ascii')
        self.manifestdir.add_file(self.FILE_MANIFEST_FILENAME, manifest_bytes)

        logger.debug(f"Updated stored manifest.")

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
            self.manifestdir.add_file(self.FILE_MANIFEST_FILENAME, b'CRMANIFEST\r\n\r\n')
            manifest_file = self.manifestdir.filemap.get(self.FILE_MANIFEST_FILENAME, None)

            # if it's still None let's just quit while we're still ahead
            if manifest_file is None:
                raise ServerError("Manifest File could not be created.")

        # Now, overwrite.
        header, data = manifest_file.data.decode('ascii').split('\r\n\r\n', 1)
        filenames:List[str] = data.split('\r\n')
        for filename in filenames:
            filename = filename.strip()
            if len(filename) == 0:
                continue
            path = self.shareddir.crinfo_dirpath.joinpath(filename)
            self.fileinfo_map[filename] = FileInfo.from_crinfo(path.with_suffix(path.suffix + f".{FileInfo.CRINFO_EXT}"))
        logger.info(f"Loaded {len(self.fileinfo_map)} FileInfo objects.")

        manifest_file.write_file()