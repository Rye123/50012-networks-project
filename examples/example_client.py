### DEEP DARK MAGIC TO ALLOW FOR ABSOLUTE IMPORT
from pathlib import Path
import sys
path = str(Path(Path(__file__).parent.absolute()).parent.absolute())
sys.path.insert(0, path)
### END OF DEEP DARK MAGIC

from ctp import *
example_cluster_id = "3f80e91dc65311ed93abeddb088b3faa"
dest_host = 'localhost'

peer = CTPPeer(example_cluster_id)
peer.send_request(CTPMessageType.STATUS_REQUEST, b'This is a status request', dest_host)
peer.send_request(CTPMessageType.BLOCK_REQUEST, b'This is a block request', dest_host)
peer.send_request(CTPMessageType.NOTIFICATION, b'This is a notification.', dest_host)