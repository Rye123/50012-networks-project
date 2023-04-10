from typing import List, Tuple, Dict, Any, Union
from pathlib import Path
from copy import deepcopy, copy
from time import sleep
from traceback import format_exc
import logging
from ctp import CTPPeer, RequestHandler, CTPMessage, CTPMessageType, CTPConnectionError, AddressType
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
DEFAULT_SERVER_ADDRESS = ('127.0.0.1', 6969)

class Cluster:
    """
    Class that encapsulates data for a cluster.
    - `cluster_id`: ID of the cluster
    - `server_uri`: URI of the server
    """
    def __init__(self, cluster_id: str, server_uri: str):
        self.cluster_id = cluster_id
        self.server_uri = server_uri

class PeerInfo:
    """
    Class that encapsulates data for each peer.

    This is used to define the other peers for this peer to connect to.
    """
    def __init__(self, cluster_id: str, peer_id: str, address: Tuple[str, int]):
        self.cluster_id = cluster_id
        self.peer_id = peer_id
        self.address = address

class PeerError(Exception):
    """
    Generic error in peer.
    """
    def __init__(self, *args: object) -> None:
        super().__init__(*args)

class ServerConnectionError(Exception):
    """
    Error with the connection with the server.
    """
    def __init__(self, *args: object) -> None:
        super().__init__(*args)

class PeerRequestHandler(RequestHandler):
    def __init__(self, peer: 'Peer', request: CTPMessage, client_addr: AddressType):
        self.peer = peer # just to overwrite the unofficial class
        self.request_addr = client_addr
        super().__init__(peer, request, client_addr)

    def cleanup(self):
        self.close()
    
    def handle(self, request: CTPMessage):
        logger.debug(f"Received {request.msg_type.name} from {self.request_addr}")
        try:
            match request.msg_type:
                case CTPMessageType.STATUS_REQUEST:
                    self.handle_status_request(request)
                case CTPMessageType.NOTIFICATION:
                    self.handle_notification(request)
                case CTPMessageType.BLOCK_REQUEST:
                    self.handle_block_request(request)
                case CTPMessageType.PEERLIST_PUSH:
                    self.handle_peerlist_push(request)
                case CTPMessageType.NO_OP:
                    self.handle_no_op(request)
                case _:
                    self.handle_unknown_request(request)
        except Exception as e:
            logger.error(str(e))
            if request.msg_type != CTPMessageType.NO_OP:
                self.send_response(CTPMessageType.SERVER_ERROR, b'')
    
    def handle_status_request(self, request: CTPMessage):
        """
        Handle STATUS_REQUEST by returning the status.
        """
        data = b"status: 1"
        self.send_response(
            CTPMessageType.STATUS_RESPONSE,
            data
        )

    def handle_notification(self, request: CTPMessage):
        """
        Handle NOTIFICATION with a NOTIFICATION_ACK.
        """
        notification_msg = request.data
        # TODO: Do something with the notification message.

        self.send_response(
            CTPMessageType.NOTIFICATION_ACK,
            b''
        )

    def handle_block_request(self, request: CTPMessage):
        """
        Handle BLOCK_REQUEST with a BLOCK_RESPONSE
        - Block data will come in the form of a `Block.pack()`ed packet with no data.
        """
        # Parse request
        packet = request.data
        requested_block = Block.unpack(packet)

        # Check if we have the block
        resp_packet = None
        filelist = [f for f in self.peer.shareddir.filemap.values()]
        for f in filelist:
            if f.fileinfo.filehash != requested_block.filehash:
                continue
            for block in f.blocks:
                if block.block_id != requested_block.block_id:
                    continue
                # Found, return the response if it's downloaded
                if block.downloaded:
                    resp_packet = block.pack()
                    break
                else:
                    # it's not downloaded, but we DID find it
                    break
            # block cannot be found in this file, but we DID find the file
            break

        if resp_packet is None:
            # Indicate not found with an echoed packet.
            resp_packet = b''

        # Return the response
        self.send_response(
            CTPMessageType.BLOCK_RESPONSE,
            resp_packet
        )

    def handle_peerlist_push(self, request: CTPMessage):
        peerlist = request.data
        self.peer._parse_peerlist(peerlist)

    def handle_no_op(self, request: CTPMessage):
        pass

    def handle_unknown_request(self, request: CTPMessage):
        """
        Handle unknown request by returning the status.
        """
        data = b"status: 1"
        logger.debug("Unknown response")
        self.send_response(
            CTPMessageType.STATUS_RESPONSE,
            data
        )

class Peer(CTPPeer):
    """
    A simple subclass of `CTPPeer`, that adds context in the form of the peermap. \
    This isn't strictly necessary (we can just work with a global peermap variable), \
    but we might want to expand this class to involve other context variables.
    - `peermap`: Maps the peer ID to the corresponding `PeerInfo` object.
    - `server_addr`
    - `shared_dir`: Encapsulates file management.
        - Files are accessed through `shared_dir.filemap`.
    - `manifest_path`: Allows us to effectively treat the manifest file as another file to be shared.
    - `manifest_filelist`: The list of filenames in the manifest. 

    The local filemap is represented by `shared_dir.filemap`, while `manifest_filelist` represents the fileinfos known by the server.
    """
    FILE_MANIFEST_FILENAME = ".crmanifest"

    def __init__(self, peer_info: PeerInfo, shared_dir_path: Path, server_addr: AddressType, initial_peerlist:List[PeerInfo]=[]):
        """
        Initialise the peer, with a given `peer_info` object.
        """
        super().__init__(
            peer_addr=peer_info.address,
            cluster_id=peer_info.cluster_id,
            peer_id=peer_info.peer_id,
            requestHandlerClass=PeerRequestHandler
        )
        self.shareddir = SharedDirectory(shared_dir_path)

        self.peermap:Dict[str, PeerInfo] = dict()
        self.server_addr = server_addr

        manifest_path = shared_dir_path.joinpath("manifest")
        self.manifestdir = SharedDirectory(manifest_path)
        self.manifest_filelist:List[str] = {} # a list of filenames, extracted from manifestdir

        # Initialisation
        self.scan_local_dir()
        # self._bootstrap_peermap(initial_peerlist)
        # self.sync_peermap()
        #TODO: determine if this is necessary, since we have the server push new peers anyway

        self.listen()
        try:
            self.join_cluster()
            self.sync_manifest()
        except Exception as e:
            logger.critical("Fatal error encountered. " + format_exc())
            self.end()
            raise PeerError("Could not start Peer.")

    def _parse_peerlist(self, peerlist: bytes):
        """
        Parses a peerlist and updates the local peermap.
        """
        # Process the response (list of peers in ASCII)
        data = peerlist.decode('ascii')
        lines = data.split("\r\n")
        peerlist:List[PeerInfo] = []
        for line in lines:
            try:
                peer_id, ip_addr, port = line.split(' ')
                peer_info = PeerInfo(self.cluster_id, peer_id, (ip_addr, int(port)))
                peerlist.append(peer_info)
            except ValueError:
                raise ValueError("Invalid response from server.")
        logger.info("New peerlist received: " + str([peer.peer_id for peer in peerlist]))
        # Overwrite peermap
        self.peermap = {}
        for peerinfo in peerlist:
            if peerinfo.peer_id != self.peer_id and peerinfo.address != self.peer_addr:
                self.peermap[peerinfo.peer_id] = peerinfo

    def join_cluster(self):
        response = self.send_request_to_server(
            CTPMessageType.CLUSTER_JOIN_REQUEST,
            b'',
            retries=2
        )
        if response is None:
            raise ValueError(f"Could not connect.")
        if response.msg_type == CTPMessageType.INVALID_REQ:
            raise ValueError(response.data.decode('ascii'))
        if response.msg_type != CTPMessageType.CLUSTER_JOIN_RESPONSE:
            raise ValueError(f"Unexpected response {response.msg_type}")
        self._parse_peerlist(response.data)
        #TODO: auto send no_ops for liveness.

    def listen(self):
        """
        Listens for incoming messages -- these could be requests, or \
        responses to this peer's requests.

        This should call the lower level CTP functions.
        """
        logger.info(f"{self.short_peer_id}: Listener initiated on {self.peer_addr}.")
        super().listen()
    
    def sync_peermap(self):
        """
        Syncs the current peerlist.
        """
        pass
    
    def _bootstrap_peermap(self, peerlist: List[PeerInfo]):
        """
        Sets up `peermap` with a bootstrapped list of peers.
        """
        for peerinfo in peerlist:
            self.peermap[peerinfo.peer_id] = peerinfo

    def get_peer(self, context=Dict[str, Any]) -> PeerInfo:
        """
        Gets a (known) peer to interact with.

        The decisionmaking process is done based on the context, this should be \
        using a `context` dictionary determined by `sync_files`.

        TODO: Add additional details to context for smarter decisionmaking.
        """
        if len(self.peermap) == 0:
            return None
        peer_index = context.get("counter", 0) % len(self.peermap)
        peer_id = list(self.peermap.keys())[peer_index]
        return self.peermap.get(peer_id)
    
    def _update_manifest_file(self):
        """
        Updates the manifest file, based on the manifest file CRINFO.
        """
        retries = 1 # number of retries to send for EVERY request

        manifest_file = self.manifestdir.filemap.get(self.FILE_MANIFEST_FILENAME)
        if manifest_file is not None:
            manifest_file.delete_local_copy()  # clear the existing manifest
        logger.debug("Updating manifest file...")
        for block in manifest_file.blocks:
            if not block.downloaded:
                request_pkt = block.pack()
                response = self.send_request_to_server(
                    CTPMessageType.BLOCK_REQUEST,
                    data=request_pkt,
                    timeout=2,
                    retries=retries
                )

                if response is None:
                    # Store what we have first, then exit
                    manifest_file.write_temp_file()
                    raise ServerConnectionError()

                response_pkt = response.data
                response_block = Block.unpack(response_pkt)

                if response_block is not None and response_block.downloaded:
                    block.downloaded = True
                    block.data = response_block.data
                    self._log("debug", f"Request: block {block.block_id}, Manifest File: HIT")
                    break
                else:
                    self._log("debug", f"Request: block {block.block_id}, Manifest File: MISS")
                    pass
        
        if manifest_file.downloaded: 
            # ONLY write if it's downloaded.
            # This allows us to continue requesting from other peers if the server goes down.
            manifest_file.write_file()

        logger.debug("Manifest file updated.")

    def _parse_manifest_file(self):
        """
        Parses the manifest file
        """
        logger.debug("Parsing manifest...")
        manifest_file = self.manifestdir.filemap.get(self.FILE_MANIFEST_FILENAME)
        if not manifest_file.downloaded:
            raise RuntimeError("Cannot parse manifest file, manifest file not fully downloaded.")
        
        # Use the currently stored version.
        with manifest_file.filepath.open('rb') as f:
            header, data = f.read().decode('ascii').split('\r\n\r\n', 1)
            filenames_raw = data.split('\r\n')
            # Ensure no empty filenames
            filenames = []
            for filename in filenames_raw:
                if len(filename.strip()) != 0:
                    filenames.append(filename)
            self.manifest_filelist = filenames
        logger.debug("Manifest parsed.")

    def _req_missing_fileinfos_from_manifest(self) -> int:
        """
        Based on the file manifest, download fileinfos from the server \
        and update local `shareddir.filemap`.

        Returns the total number of fileinfos downloaded.
        """
        # Identify missing fileinfos
        missing_count = 0
        for filename in self.manifest_filelist:
            if filename not in self.shareddir.filemap.keys():
                # Request file
                request_data = f"filename: {filename}"

                response:CTPMessage = self.send_request_to_server(
                    CTPMessageType.CRINFO_REQUEST,
                    request_data.encode('ascii'),
                    timeout=1,
                    retries=3
                )

                if response is None:
                    raise ServerConnectionError("Could not connect to server.")

                if response.msg_type == CTPMessageType.SERVER_ERROR:
                    logger.debug(response)
                    raise ServerConnectionError("Failed to sync manifest due to server error")
                
                if response.msg_type == CTPMessageType.INVALID_REQ:
                    logger.debug("Server didn't have the fileinfo.")
                    return

                if response.msg_type != CTPMessageType.CRINFO_RESPONSE:
                    raise ServerConnectionError("Unknown response from server.")

                # Response data is the file's CRINFO
                self.shareddir.add_fileinfo(filename, response.data)
                missing_count += 1
        return missing_count

    def sync_manifest(self):
        """
        Get the latest file manifest from the server, and update \
        the `manifest_filemap`.

        Then, update the local filemap (`shareddir.filemap`) by requesting \
        all necessary fileinfos from the server.
        """
        response:CTPMessage = self.send_request_to_server(
            CTPMessageType.MANIFEST_REQUEST, 
            b'',
            timeout=1,
            retries=3
        )

        if response is None:
            raise ServerConnectionError("Could not connect to server.")

        if response.msg_type == CTPMessageType.SERVER_ERROR:
            logger.debug(response)
            raise ServerConnectionError("Failed to sync manifest due to server error")

        if response.msg_type != CTPMessageType.MANIFEST_RESPONSE:
            raise ServerConnectionError("Unknown response from server.")
        
        # Overwrite existing manifest
        self.manifestdir.add_fileinfo(self.FILE_MANIFEST_FILENAME, response.data)
        self._update_manifest_file()
        self._parse_manifest_file()

        logger.debug("Manifest updated: " + str(self.manifest_filelist))

        # Request missing fileinfos from the server
        fileinfos_updated = self._req_missing_fileinfos_from_manifest()
        logger.debug(f"Fileinfos updated: {fileinfos_updated}")

    def share(self):
        """
        Share files with cluster.
        1. Scans the server manifest (`./manifest`).
        2. Scans local files (filelist)
        3. For each local file that is not in the manifest, share the file with the server
        """
        filelist = [f for f in self.shareddir.filemap.values() if (f.downloaded)]
        for file in filelist:
            if file.fileinfo.filename not in self.manifest_filelist: # i.e. server doesn't know this file
                self._share_file(file)

    def scan_local_dir(self):
        """
        Updates the in-memory shared directory with the local directory.
        """
        self.shareddir.refresh()
    
    def _share_file(self, file: File):
        """
        Shares `file`. 
        This should share the given file's `FileInfo` object with the entire \
        cluster
        """
        if not file.downloaded:
            raise ValueError("Given file is not fully downloaded.")
        
        fileinfo_b = b''
        with file.fileinfo.filepath.open('rb') as f:
            fileinfo_b = f.read()
        formatted_data = file.fileinfo.filename.encode('ascii') + b'\r\n\r\n' + fileinfo_b

        response = self.send_request_to_server(
            CTPMessageType.NEW_CRINFO_NOTIF,
            formatted_data,
            1
        )

        if response is None:
            return
        
        if response.data == b"success":
            # Send a follow-up asking for the updated manifest.
            self.sync_manifest()
        elif response.data == b"error: exists":
            logger.debug("File already exists.")

    def sync_files(self):
        """
        Based on the current local filemap, request file blocks from known peers.
        """
        counter = 0 # counter for requests sent, used for naive peer usage
        retries = 1 # number of retries to send for EVERY request

        # Get all non-downloaded files
        filelist = [f for f in self.shareddir.filemap.values() if (not f.downloaded)]
        for file in filelist:
            blocks = [b for b in file.blocks if (not b.downloaded)]
            for block in blocks:
                # Sequentially get blocks
                while not block.downloaded:
                    request_pkt = block.pack()
                    dest_peer = self.get_peer({"counter": counter})
                    if dest_peer is None:
                        logger.debug("Could not sync files, no peers available.")
                        break

                    # Send the request
                    response = self.send_request(
                        msg_type=CTPMessageType.BLOCK_REQUEST,
                        data=request_pkt,
                        dest_peer_id=dest_peer.peer_id,
                        retries=retries
                    )
                    counter += 1

                    # Handle the response
                    if response is None:
                        # Could not connect, assume it's down for now
                        self.handle_down_peer(dest_peer.peer_id)
                        continue

                    response_pkt = response.data
                    response_block = Block.unpack(response_pkt)

                    if response_block is not None and response_block.downloaded:
                        block.downloaded = True
                        block.data = response_block.data
                        self._log("debug", f"Request: block {block.block_id}, file {file.fileinfo.filename} from {dest_peer.peer_id}: HIT")
                        break
                    else:
                        self._log("debug", f"Request: block {block.block_id}, file {file.fileinfo.filename} from {dest_peer.peer_id}: MISS")
                        pass
            logger.debug(f"Progress: {file}")
            self.store_file(file)

    def store_file(self, file: File):
        """
        Save the current version of the file locally.
        """
        ## Delete file first
        file.delete_local_copy()

        ## Save relevant version
        if file.downloaded:
            file.write_file()
        else:
            file.write_temp_file()

    def _report(self, peer):
        """
        Report the given peer for inactivity to the server.
        """
        pass

    def handle_down_peer(self, dest_peer_id: str):
        """
        Handles what to do if the destination peer is down.

        For now, we just pop the peer from the list.
        #TODO: send request to the server, to check if WE are the ones that are disconnected.
        - This will also allow us to 'complain' to the server that the peer is down.
        """
        logger.info(f"Could not connect to {dest_peer_id}.")
        self.peermap.pop(dest_peer_id, None)
    
    def end(self):
        logger.info("Ending peer...")
        super().end()

        logger.info("Saving files...")
        # Save all current in-memory versions of each file.
        for file in self.shareddir.filemap.values():
            self.store_file(file)
        logger.info("Files saved.")

    def send_request(self, msg_type: CTPMessageType, data: bytes, dest_peer_id: str, timeout: float = 1, retries: int = 0) -> Union[CTPMessage, None]:
        """
        Sends a request to another peer. Returns the request, or returns `None` if the send failed.
        - Calls `handle_down_peer()` if there was a connection error.
        """
        # sleep(0.5) #TODO: REMOVE FOR PRODUCTION, this is for testing

        if dest_peer_id not in self.peermap.keys():
            return None
        
        dest_peerinfo:PeerInfo = self.peermap.get(dest_peer_id)
        dest_addr = dest_peerinfo.address
        try:
            response = super().send_request(msg_type, data, dest_addr, timeout, retries)
            return response
        except CTPConnectionError:
            return None

    def send_request_to_server(self, msg_type: CTPMessageType, data: bytes, timeout: float = 1, retries: int = 0) -> Union[CTPMessage, None]:
        """
        Sends a request to the server. Returns the response, or `None`.
        """
        dest_addr = self.server_addr
        try:
            response = super().send_request(msg_type, data, dest_addr, timeout, retries)
            return response
        except CTPConnectionError:
            return None