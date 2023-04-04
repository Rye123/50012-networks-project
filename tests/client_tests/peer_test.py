from pathlib import Path
from typing import List, Tuple

### DEEP DARK MAGIC TO ALLOW FOR ABSOLUTE IMPORT
from pathlib import Path
import sys
path = str(Path(Path(Path(__file__).parent.absolute()).parent.absolute()).parent.absolute())
sys.path.insert(0, path)
### END OF DEEP DARK MAGIC

from ctp import *
from client import *

peerlist_path = Path("./tests/client_tests/bootstrapped_peer_list.txt")
example_cluster_id = "3f80e91dc65311ed93abeddb088b3faa"

def setup_peer(this_peer_id: str) -> Peer:
    peerlist:List[PeerInfo] = []
    this_peerinfo:PeerInfo = None
    this_peer_shareddir = None
    this_peer:Peer = None
    with peerlist_path.open('r') as f:
        lines = f.readlines()
        for line in lines:
            ip, port, peer_id, dirname = line.strip().split(" ")
            addr = (ip, int(port))
            peer_info = PeerInfo(
                cluster_id=example_cluster_id,
                peer_id=peer_id,
                address=addr
            )

            if peer_id == this_peer_id:
                this_peerinfo = peer_info
                this_peer_shareddir = dirname
            else:
                peerlist.append(peer_info)
    
    # Set peerlist

    this_peer = Peer(
        peer_info=this_peerinfo,
        shared_dir=Path(f"./tests/client_tests/data/{this_peer_shareddir}"),
        initial_peerlist=peerlist
    )
    return this_peer

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Please input the line index of the address to use. Do note that this line index shouldn't already be used.")
        sys.exit(1)

    line_index = int(sys.argv[1])
    this_peer_id = None
    with peerlist_path.open('r') as f:
        lines = f.readlines()
        this_peer_id = lines[line_index].split(" ")[2]

    peer = setup_peer(this_peer_id)

    peer.listen()
    print("\n\nPeer has been set up.\nCommands:\n\tSCAN: Scan local directory for new files\n\tSYNC PEERS: Sync peers with the bootstrapped peerlist\n\tSYNC FILES: Syncs files with peers\n\tEXIT: Exit. Duh.")



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
                    peer.scan_local_dir()
                case "EXIT":
                    print("-- Exiting... --")
                    break
    except KeyboardInterrupt:
        print("-- Exiting... --")
    finally:
        peer.end()
        print("-- Peer ended. --")