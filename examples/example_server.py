
### DEEP DARK MAGIC TO ALLOW FOR ABSOLUTE IMPORT
from pathlib import Path
import sys
path = str(Path(Path(__file__).parent.absolute()).parent.absolute())
sys.path.insert(0, path)
### END OF DEEP DARK MAGIC

from ctp import RequestHandler, CTPMessage, CTPMessageType, CTPPeer

class EchoRequestHandler(RequestHandler):
    """
    Example request handler which echos the given request.
    """
    def handle_status_request(self, request: CTPMessage):
        self.send_response(CTPMessageType.STATUS_RESPONSE, request.data)

    def handle_notification(self, request: CTPMessage):
        self.send_response(CTPMessageType.NOTIFICATION_ACK, request.data)
    
    def handle_block_request(self, request: CTPMessage):
        self.send_response(CTPMessageType.BLOCK_RESPONSE, request.data)
    
    def handle_unknown_request(self, request: CTPMessage):
        self.send_response(CTPMessageType.STATUS_RESPONSE, request.data)
    
    def cleanup(self):
        self.close()

example_cluster_id = "3f80e91dc65311ed93abeddb088b3faa"

peer = CTPPeer(example_cluster_id, EchoRequestHandler)
try:
    peer.listen('localhost')
    while(True): 
        # loop to keep main thread alive
        pass
except KeyboardInterrupt:
    peer.end()