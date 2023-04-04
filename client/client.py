from typing import List, Tuple, Dict, Any
from pathlib import Path
from copy import deepcopy, copy
from time import sleep
import logging
from ctp import CTPPeer, RequestHandler, CTPMessage, CTPMessageType, CTPConnectionError, AddressType
from util import FileInfo, File, FileError, Block
from util import ensure_shared_folder, standardHandler

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

class PeerRequestHandler(RequestHandler):
    def __init__(self, peer: 'Peer', request: CTPMessage, client_addr: AddressType):
        super().__init__(peer, request, client_addr)
        self.peer = peer # just to overwrite the unofficial class

    def cleanup(self):
        self.close()
    
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
        for f in self.peer.filelist:
            if f.fileinfo.filehash != requested_block.filehash:
                continue
            for block in f.blocks:
                if block.block_id != requested_block.block_id:
                    continue
                # Found, return the response if it's downloaded
                if block.downloaded:
                    block_data = block.data
                    resp_packet = block.pack()
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
    
    def handle_no_op(self, request: CTPMessage):
        pass

    def handle_unknown_request(self, request: CTPMessage):
        """
        Handle unknown request by returning the status.
        """
        data = b"status: 1"
        self.peer._log("debug", "unknown request")
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
    
    """
    def __init__(self, peer_info: PeerInfo, shared_dir: Path, initial_peerlist:List[PeerInfo]=[]):
        """
        Initialise the peer, with a given `peer_info` object.
        """
        super().__init__(
            peer_addr=peer_info.address,
            cluster_id=peer_info.cluster_id,
            peer_id=peer_info.peer_id,
            requestHandlerClass=PeerRequestHandler
        )
        self.shared_dir = shared_dir
        ensure_shared_folder(self.shared_dir)

        self.filelist:List[File] = []
        self.peermap:Dict[str, PeerInfo] = dict()

        # Initialisation
        self.filelist = self.scan_local_dir()
        self._bootstrap_peermap(initial_peerlist)
        self.sync_peermap()
    
    def share(self, file: File):
        """
        Shares `file`. 
        This should share the given file's `FileInfo` object with the entire \
        cluster
        """
        pass

    def listen(self):
        """
        Listens for incoming messages -- these could be requests, or \
        responses to this peer's requests.

        This should call the lower level CTP functions.
        """
        logger.info(f"{self.short_peer_id}: Listener initiated.")
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
        Gets a peer to interact with.

        The decisionmaking process is done based on the context, this should be \
        using a `context` dictionary determined by `sync_files`.

        TODO: Add additional details to context for smarter decisionmaking.
        """
        if len(self.peermap) == 0:
            return None
        peer_index = context.get("counter", 0) % len(self.peermap)
        peer_id = list(self.peermap.keys())[peer_index]
        return self.peermap.get(peer_id)

    def sync_files(self):
        """
        Based on the CURRENT file manifest (i.e. the current directory of \
        `.crinfo` files), send out block requests to missing files.

        This will not automatically sync the file manifest.
        """
        counter = 0 # counter for requests sent, used for naive peer usage
        retries = 1 # number of retries to send for EVERY request

        # Get all non-downloaded files
        filelist = [f for f in self.filelist if (not f.downloaded)]
        for file in filelist:
            blocks = [b for b in file.blocks if (not b.downloaded)]
            for block in blocks:
                # Sequentially get blocks
                while not block.downloaded:
                    request_pkt = block.pack()
                    dest_peer = self.get_peer({"counter": counter})
                    if dest_peer is None:
                        logger.debug("Could not sync files, no peers available.")

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
                        logger.debug(f"Request: block {block.block_id}, file {file.fileinfo.filehash} from {dest_peer.peer_id}: HIT")
                        break
                    else:
                        logger.debug(f"Request: block {block.block_id}, file {file.fileinfo.filehash} from {dest_peer.peer_id}: MISS")
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
            file.save_file()
        else:
            file.save_temp_file()
    
    def send_request(self, msg_type: CTPMessageType, data: bytes, dest_peer_id: str, timeout: float = 1, retries: int = 0) -> CTPMessage:
        """
        Sends a request to another peer. Returns the request, or returns `None` if the send failed.
        - Calls `handle_down_peer()` if there was a connection error.
        """
        sleep(0.5) #TODO: REMOVE FOR PRODUCTION, this is for testing

        if dest_peer_id not in self.peermap.keys():
            return None
        
        dest_peerinfo:PeerInfo = self.peermap.get(dest_peer_id)
        dest_addr = dest_peerinfo.address
        try:
            response = super().send_request(msg_type, data, dest_addr, timeout, retries)
            return response
        except CTPConnectionError:
            return None
    
    def handle_down_peer(self, dest_peer_id: str):
        """
        Handles what to do if the destination peer is down.

        For now, we just pop the peer from the list.
        #TODO: send request to the server, to check if WE are the ones that are disconnected.
        - This will also allow us to 'complain' to the server that the peer is down.
        """
        logger.info(f"Could not connect to {dest_peer_id}.")
        self.peermap.pop(dest_peer_id, None)
    
    def scan_local_dir(self):
        """
        Scan through the local shared directory for files.
        """
        filelist:List[File] = []

        # Scan through directory to identify relevant files
        crinfo_dir_path:Path = None
        file_paths:List[Path] = []
        tempfile_paths:List[Path] = []
        crinfo_paths:List[Path] = []
        for child in self.shared_dir.iterdir():
            if child.is_dir():
                if child.name == FileInfo.CRINFO_DIR_NAME:
                    crinfo_dir_path = child
                continue #TODO: should we handle other directories?

            if child.suffix == f".{File.TEMP_FILE_EXT}":
                tempfile_paths.append(child)
            else:
                file_paths.append(child)
        
        # Scan through identified crinfo directory for CRINFO files
        for child in crinfo_dir_path.iterdir():
            if child.is_dir():
                continue # ignore directories in here
            if child.suffix == f".{FileInfo.CRINFO_EXT}":
                crinfo_paths.append(child)
        
        # Now we load the files based on the paths
        ## Load fully-downloaded files
        for file_path in file_paths:
            file = None
            try:
                file = File.from_file(file_path)
                filelist.append(file)
            except FileError as e:
                logger.warning(f"Could not load file from {file_path}, error was: {str(e)}")
                continue

            fileinfo_path = crinfo_dir_path.joinpath(f"{file.fileinfo.filename}.{FileInfo.CRINFO_EXT}")

            if fileinfo_path in crinfo_paths:
                logger.debug(f"Loading existing file from {file_path} with CRINFO from {fileinfo_path}.")
                crinfo_paths.remove(fileinfo_path)
            else:
                logger.debug(f"Loading new file from {file_path}")
                file.fileinfo.save_crinfo(self.shared_dir)
        ## Load tempfiles
        for tempfile_path in tempfile_paths:
            tempfile = None
            try:
                tempfile = File.from_temp_file(tempfile_path)
                filelist.append(tempfile)
            except FileError as e:
                logger.warning(f"Could not load file from {tempfile_path}, error was: {str(e)}")
                continue

            fileinfo_path = crinfo_dir_path.joinpath(f"{tempfile.fileinfo.filename}.{FileInfo.CRINFO_EXT}")

            if fileinfo_path in crinfo_paths:
                logger.debug(f"Loading existing tempfile from {tempfile_path} with CRINFO {fileinfo_path}.")
                crinfo_paths.remove(fileinfo_path)
            else:
                logger.error(f"Error: Tempfile {tempfile.fileinfo.filename} does not have a corresponding fileinfo object.")
                raise NotImplemented

        # Load files from remaining fileInfos (i.e. empty files)
        for fileinfo_path in crinfo_paths:
            fileinfo = FileInfo.from_crinfo(fileinfo_path)
            file = File(fileinfo, self.shared_dir)
            filelist.append(file)
            logger.debug(f"Loading empty tempfile with CRINFO {fileinfo_path}.")

        return filelist

    def end(self):
        logger.info("Ending peer...")
        super().end()

        logger.info("Saving files...")
        # Save all current in-memory versions of each file.
        for file in self.filelist:
            self.store_file(file)

    def _report(self, peer):
        """
        Report the given peer for inactivity to the server.
        """
        pass