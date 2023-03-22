"""
example_peer:
This demonstrates an example implementation of a peer that \
pings a hard-coded list of peers.

This hard-coded list is in `example_peer_list.txt`. It is stored \
as a dictionary, and the peer will send a `STATUS_REQUEST` to every \
peer in the dictionary every second.

When sent a `STATUS_REQUEST`, the peer will respond with a single \
`STATUS_RESPONSE`.

# Usage
`python example_peer.py [index]`
- `index`: The index of the line to use as peer ID and port for this peer. \
See the `example_peer_list.txt` for the data.
"""

import traceback
from time import sleep
from typing import Type, Tuple, List, Dict

### DEEP DARK MAGIC TO ALLOW FOR ABSOLUTE IMPORT
from pathlib import Path
import sys
path = str(Path(Path(__file__).parent.absolute()).parent.absolute())
sys.path.insert(0, path)
### END OF DEEP DARK MAGIC

from ctp import CTPPeer, RequestHandler, CTPMessage, CTPMessageType, CTPConnectionError

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
        #TODO: how to indicate no block?
        """
        # Parse request

        # Check if we have the block

        # Conjure data
        data = b'No data'
        self.send_response(
            CTPMessageType.BLOCK_RESPONSE,
            data
        )

    def handle_unknown_request(self, request: CTPMessage):
        """
        Handle unknown request by returning the status.
        """
        data = b"status: 1"
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
        super().__init__(peer_info.cluster_id, peer_info.peer_id, PeerRequestHandler)
        self.peermap:Dict[str, PeerInfo] = dict()

# Example cluster ID. Not needed for this example, it's just needed since CTPMessage expects a Cluster ID.
example_cluster_id = "3f80e91dc65311ed93abeddb088b3faa"

if __name__ == "__main__":
    # Get the line index
    import sys
    if len(sys.argv) != 2:
        print("Please input the line index of the address to use. Do note that this line index shouldn't already be used.")
        sys.exit(1)
    
    peer_list:List[PeerInfo] = []
    my_info:PeerInfo = None

    line_index = int(sys.argv[1])
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
            if str(i) == sys.argv[1]:
                my_info = peer_info
            else:
                peer_list.append(peer_info)
                
    peer = Peer(my_info)
    # map each peer ID to the peerinfo
    for peerinfo in peer_list:
        peer.peermap[peerinfo.peer_id] = peerinfo

    # setup listen
    print(my_info.address)
    peer.listen(my_info.address[0], my_info.address[1])

    print("Listener set up. Press ENTER to begin sending.")
    input()

    # message send loop
    try:
        short_id = my_info.peer_id[:6]
        messages_sent = 0
        while True:
            peermap_iter = 0

            # This simply loops through the peer list, sending a STATUS_REQUEST to every peer.
            while len(peer.peermap.keys()) > 0:
                if peermap_iter > len(peer.peermap):
                    peermap_iter = 0
                dest_peer_id = list(peer.peermap.keys())[peermap_iter]
                dest_peer_info = peer.peermap.get(dest_peer_id)
                try:
                    message = f"{short_id}-{messages_sent}"
                    # Send the STATUS_REQUEST
                    peer.send_request(
                        CTPMessageType.STATUS_REQUEST,
                        message.encode('ascii'),
                        dest_peer_info.address[0],
                        dest_peer_info.address[1]
                    )
                except CTPConnectionError:
                    # Error in the connection, probably because the peer has closed connection.
                    # So we end it, and remove the peer from the peermap.
                    print(f"Peer {dest_peer_info.peer_id} has closed connection.")
                    peer.peermap.pop(dest_peer_id)
                messages_sent += 1
                sleep(1)
    except KeyboardInterrupt:
        peer.end()
    except Exception as e:
        # End connection SAFELY.
        peer.peermap.clear()
        print("Ending connection due to Exception: " + str(e))
        peer.end()
        print("\nError Traceback: \n\n---\n")
        traceback.print_exc()
