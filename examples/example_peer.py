"""
example_peer:
This demonstrates an example implementation of a peer that \
pings a hard-coded list of peers 
"""

import traceback
from time import sleep
from typing import Type, Tuple, List

### DEEP DARK MAGIC TO ALLOW FOR ABSOLUTE IMPORT
from pathlib import Path
import sys
path = str(Path(Path(__file__).parent.absolute()).parent.absolute())
sys.path.insert(0, path)
### END OF DEEP DARK MAGIC

from ctp import CTPPeer, RequestHandler, CTPMessage, CTPMessageType

class PeerInfo:
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
    def __init__(self, peer_info: PeerInfo):
        super().__init__(peer_info.cluster_id, peer_info.peer_id, PeerRequestHandler)
        self.peer_list:List[PeerInfo] = []

example_cluster_id = "3f80e91dc65311ed93abeddb088b3faa"

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Please input the line index of the address to use")
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
    peer.peer_list = peer_list #TODO: shift this into Peer fn as bootstrapped peerlist?

    # setup listen
    print(my_info.address)
    peer.listen(my_info.address[0], my_info.address[1])

    print("Listener set up. Press ENTER to begin sending.")
    input()

    # message send loop
    #TODO for sender: address connectionrefusederror
    try:
        while True:
            for dest_peer_info in peer.peer_list:
                print(dest_peer_info.address)
                peer.send_request(
                    CTPMessageType.STATUS_REQUEST,
                    b'',
                    dest_peer_info.address[0],
                    dest_peer_info.address[1]
                )
            sleep(1)
    except KeyboardInterrupt:
        peer.end()
    except Exception as e:
        # End connection SAFELY.
        print("Ending connection due to Exception: " + str(e))
        peer.end()
        print("\nError Traceback: \n\n---\n")
        traceback.print_exc()
