### DEEP DARK MAGIC TO ALLOW FOR ABSOLUTE IMPORT
from pathlib import Path
import sys
path = str(Path(Path(__file__).parent.absolute()).parent.absolute())
sys.path.insert(0, path)
### END OF DEEP DARK MAGIC

from ctp import *
example_cluster_id = "3f80e91dc65311ed93abeddb088b3faa"
dest_addr = ('localhost', 6969)
src_addr = ('localhost', 7070)

peer = CTPPeer(
    peer_addr=src_addr,
    cluster_id=example_cluster_id
)
peer.send_request(CTPMessageType.STATUS_REQUEST, b'This is a status request', dest_addr, retries=1)
peer.send_request(CTPMessageType.BLOCK_REQUEST, b'This is a block request', dest_addr)
peer.send_request(CTPMessageType.NOTIFICATION, b'This is a notification.', dest_addr)