import traceback
from time import sleep
from typing import Type, Tuple, List, Dict, Any
import logging

### DEEP DARK MAGIC TO ALLOW FOR ABSOLUTE IMPORT
from pathlib import Path
import sys
path = str(Path(Path(__file__).parent.absolute()).parent.absolute())
sys.path.insert(0, path)
### END OF DEEP DARK MAGIC

from ctp import CTPPeer, RequestHandler, CTPMessage, CTPMessageType, CTPConnectionError, AddressType
from util import FileInfo, File, FileError, Block
from util import ensure_shared_folder, standardHandler

# Logging Settings
APP_LOGGING_LEVEL = logging.DEBUG
CTP_LOGGING_LEVEL = logging.WARNING # Recieve only warnings.

logger = logging.getLogger()
logger.setLevel(APP_LOGGING_LEVEL)
ctp_logger = logging.getLogger('ctp')
ctp_logger.setLevel(CTP_LOGGING_LEVEL)
logger.addHandler(standardHandler)
BOOTSTRAPPED_PEERLIST:List['PeerInfo'] = []

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
        self.send_response(
            CTPMessageType.NOTIFICATION_ACK,
            b''
        )

    def handle_block_request(self, request: CTPMessage):
        """
        Handle BLOCK_REQUEST with a BLOCK_RESPONSE
        - Block data will come in the form of a `Block.pack()`ed packet with no data.
        #TODO: how to indicate no block?
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
            resp_packet = packet

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
    """
    def __init__(self, peer_info: PeerInfo):
        super().__init__(
            peer_addr=peer_info.address,
            cluster_id=peer_info.cluster_id,
            peer_id=peer_info.peer_id,
            requestHandlerClass=PeerRequestHandler
        )
        self.peer = self
        self.peermap:Dict[str, PeerInfo] = dict()
        self.shared_dir = Path(f"./examples/shared_{peer_info.peer_id}")

        ensure_shared_folder(self.shared_dir)
        self.filelist:List[File] = self.load_from_dir()
        self.sync_peermap()

    def sync_peermap(self):
        """
        Sync the current peerlist.
        """
        for peerinfo in BOOTSTRAPPED_PEERLIST:
            self.peermap[peerinfo.peer_id] = peerinfo

    def sync_files(self):
        """
        Based on the file manifest, send out block requests to peers.
        """
        for file in self.filelist:
            if not file.downloaded:
                # Loop through blocks and send a request for each missing block
                for block in file.blocks:
                    if block.downloaded:
                        continue
                    # Clone peer_ids so we can iterate through it this time.
                    peer_id_list = list(self.peermap.keys())
                    for peer_id in peer_id_list:
                        request_packet = block.pack()
                        response = self.send_request(
                            msg_type=CTPMessageType.BLOCK_REQUEST,
                            data=request_packet,
                            dest_peer_id=peer_id,
                            retries=1
                        )
                        
                        if response is None:
                            # Couldn't connect, continue to next peer
                            continue

                        # Parse the response
                        response_packet = response.data
                        response_block = Block.unpack(response_packet)

                        if response_block.downloaded:
                            self._log("debug", f"{peer_id} had the block.")
                            block.downloaded = True
                            block.data = response_block.data
                            # We got the data, no need to ask the other peers
                            break
                        else:
                            self._log("debug", f"{peer_id} did not have the block.")
                
                
                # If file is fully downloaded, we can save it! Otherwise we save it temporarily.
                print(file) # Report file progress

                ## Delete file first
                file.delete_local_copy()

                ## Save relevant version of file.
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
            self.handle_down_peer(dest_peer_id)
        
        dest_peerinfo:PeerInfo = self.peermap.get(dest_peer_id)
        dest_addr = dest_peerinfo.address
        try:
            response = super().send_request(msg_type, data, dest_addr, timeout, retries)
            return response
        except CTPConnectionError:
            self.handle_down_peer(dest_peer_id)
            return None

    def handle_down_peer(self, dest_peer_id: str):
        """
        Handles what to do if the destination peer is down.

        For now, we just pop the peer from the list.
        #TODO: send request to the server, to check if WE are the ones that are disconnected.
        - This will also allow us to 'complain' to the server that the peer is down.
        """
        self._log("info", f"Could not connect to {dest_peer_id}")
        self.peermap.pop(dest_peer_id, None)

    def load_from_dir(self):
        """
        Scan through the shared directory for files.
        """
        file_objs:List[File] = []
        # Scan through directory for files
        fileinfo_dir_path:Path = None
        file_paths:List[Path] = []
        tempfile_paths:List[Path] = []
        fileinfo_paths:List[Path] = []
        for child in Path(self.shared_dir).iterdir():
            if child.is_dir():
                if child.name == FileInfo.CRINFO_DIR_NAME:
                    fileinfo_dir_path = child
                continue
            if child.suffix == f".{File.TEMP_FILE_EXT}":
                tempfile_paths.append(child)
            else:
                file_paths.append(child)

        # Scan through directory for fileInfos
        for child in Path(fileinfo_dir_path).iterdir():
            if child.is_dir():
                continue
            if child.suffix == f".{FileInfo.CRINFO_EXT}":
                fileinfo_paths.append(child)
        
        # Load files
        for file_path in file_paths:
            try:
                file = File.from_file(file_path)
                file_objs.append(file)
            except FileError as e:
                logging.warning(f"Could not load file {file_path} due to error: {e}")
                continue
            corr_fileinfo = self.shared_dir.joinpath(FileInfo.CRINFO_DIR_NAME).joinpath(f"{file.fileinfo.filename}.{FileInfo.CRINFO_EXT}")
            try:
                ## If corresponding fileinfo is loaded, delete
                print(f"Checking for fileinfo at: {corr_fileinfo}")
                fileinfo_paths.remove(corr_fileinfo)
                logging.debug(f"Detected file with FileInfo: {file_path}")
            except ValueError: # doesn't already exist
                logging.debug(f"Detected new file: {file_path}")
                file.fileinfo.save_crinfo(self.shared_dir)
        # Load temp files
        for tempfile_path in tempfile_paths:
            try:
                tempfile = File.from_temp_file(tempfile_path)
                file_objs.append(tempfile)
            except FileError as e:
                logging.warning(f"Could not load tempfile {tempfile_path} due to error: {e}")
                continue
            corr_fileinfo = self.shared_dir.joinpath(FileInfo.CRINFO_DIR_NAME).joinpath(f"{tempfile.fileinfo.filename}.{FileInfo.CRINFO_EXT}")
            try:
                ## If corresponding fileinfo is loaded, delete
                logging.debug(f"Detected tempfile with FileInfo: {tempfile_path}")
                fileinfo_paths.remove(corr_fileinfo)
            except ValueError: # doesn't already exist
                logging.error(f"Detected new tempfile: {tempfile_path}. This should not happen.")
                raise NotImplemented

        # Load files from remaining fileInfos (i.e. empty files)
        for fileinfo_path in fileinfo_paths:
            fileinfo = FileInfo.from_crinfo(fileinfo_path)
            file = File(fileinfo, self.shared_dir)
            file_objs.append(file)
            logging.debug(f"Detected empty tempfile from fileinfo: {fileinfo_path}")
        
        return file_objs


# Example cluster ID. Not needed for this example, it's just needed since CTPMessage expects a Cluster ID.
example_cluster_id = "3f80e91dc65311ed93abeddb088b3faa"

def setup(line_index: int) -> Peer:
    my_info:PeerInfo = None

    # Updated bootstrapped peerlist with file from storage
    with open("./examples/example_peer_list.txt", 'r') as f:
        lines = f.readlines()
        if line_index < 0 or line_index >= len(lines):
            print("invalid line_index")
            sys.exit(1)
        line = lines[line_index]
        for i in range(len(lines)):
            line_parts = lines[i].strip().split(" ")
            addr = (line_parts[0], int(line_parts[1]))
            peer_id = line_parts[2]
            peer_info = PeerInfo(
                cluster_id=example_cluster_id,
                peer_id=peer_id,
                address=addr
            )
            if i == line_index:
                my_info = peer_info
            else:
                BOOTSTRAPPED_PEERLIST.append(peer_info)
                
    peer = Peer(my_info)
    return peer


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Please input the line index of the address to use. Do note that this line index shouldn't already be used.")
        sys.exit(1)

    line_index = int(sys.argv[1])
    peer = setup(line_index)
    print("\n\nPeer has been set up.\nCommands:\n\tSCAN: Scan local directory for new files\n\tSYNC PEERS: Sync peers with the bootstrapped peerlist\n\tSYNC FILES: Syncs files with peers\n\tEXIT: Exit. Duh.")

    peer.listen()

    # Main Loop
    try:
        while True:
            command = input().upper()
            match command:
                case "SYNC":
                    print("-- Syncing peers... --")
                    peer.sync_peermap()
                    print("-- Syncing files... --")
                    peer.sync_files()
                case "SYNC PEERS":
                    print("-- Syncing peers... --")
                    peer.sync_peermap()
                case "SYNC FILES":
                    print("-- Syncing files... --")
                    peer.sync_files()
                case "SCAN":
                    print("-- Syncing files... --")
                    peer.load_from_dir()
                case "EXIT":
                    print("-- Exiting... --")
                    break
    except KeyboardInterrupt:
        print("-- Exiting... --")
    finally:
        peer.end()
        print("-- Peer ended. --")