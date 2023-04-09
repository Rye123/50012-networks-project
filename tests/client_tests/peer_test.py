from pathlib import Path
from typing import List, Tuple
import traceback

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
        shared_dir_path=Path(f"./tests/client_tests/data/{this_peer_shareddir}"),
        initial_peerlist=peerlist,
        server_addr=DEFAULT_SERVER_ADDRESS
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

    peer:Peer = None
    try:
        peer = setup_peer(this_peer_id)
    except PeerError:
        print("Could not setup peer.")
        sys.exit(1)
    
    if peer is None:
        print("Uncaught error caused invalid peer return.")
        sys.exit(1)

    commands = {
        "SCAN": "Scan local directory for new files",
        "JOIN": "Joins the hardcoded cluster",
        "SYNC PEERS": "Sync peerlist from server",
        "SYNC MANIFEST": "Sync manifest from server",
        "SYNC FILES": "Sync files with known peers", 
        "SYNC": "Calls sync functions in this order: SYNC PEERS, SYNC MANIFEST, SYNC FILES.",
        "SHARE": "Syncs local files that aren't in the server manifest with the cluster.",
        "EXIT": "Exit the program."
    }

    print("\n\nPeer has been set up.\nCommands:\n\t" + "\n\t".join([f"{command}: {desc}" for command, desc in commands.items()]))

    # Main Loop
    try:
        while True:
            command = input().upper()
            match command:
                case "SCAN":
                    print("SCAN: Updating files from local directory...")
                    peer.scan_local_dir()
                    print("SCAN: Files updated.")
                case "JOIN":
                    print(f"JOIN: Joining cluster {peer.cluster_id}...")
                    peer.join_cluster()
                    print("JOIN: Cluster joined.")
                case "SYNC PEERS":
                    print("SYNC PEERS: Syncing peers...")
                    peer.sync_peermap()
                    print("SYNC PEERS: Peers synced.")
                case "SYNC MANIFEST":
                    print("SYNC MANIFEST: Syncing manifest...")
                    peer.sync_manifest()
                    print("SYNC MANIFEST: Manifest synced.")
                case "SYNC FILES":
                    print("SYNC FILES: Syncing files...")
                    peer.sync_files()
                    print("SYNC FILES: Files synced.")
                case "SHARE":
                    print("SHARE: Sharing files with cluster.")
                    peer.share()
                    print("SHARE: Files shared.")
                case "SYNC":
                    print("SYNC: Syncing all...")
                    # print("SYNC PEERS: Syncing peers...")
                    # peer.sync_peermap()
                    # print("SYNC PEERS: Peers synced.")
                    print("SYNC MANIFEST: Syncing manifest...")
                    peer.sync_manifest()
                    print("SYNC MANIFEST: Manifest synced.")
                    print("SYNC FILES: Syncing files...")
                    peer.sync_files()
                    print("SYNC FILES: Files synced.")
                    print("SYNC: Sync completed.")
                case "EXIT":
                    print("-- Exiting... --")
                    break
    except KeyboardInterrupt:
        print("-- Exiting... --")
    except Exception:
        print("-- Exiting due to exception... --")
    finally:
        peer.end()
        print("-- Peer ended. --")