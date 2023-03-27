
### DEEP DARK MAGIC TO ALLOW FOR ABSOLUTE IMPORT
from pathlib import Path
import sys
path = str(Path(Path(__file__).parent.absolute()).parent.absolute())
sys.path.insert(0, path)
### END OF DEEP DARK MAGIC

from ctp import RequestHandler, CTPMessage, CTPMessageType, CTPPeer

class EchoRequestHandler(RequestHandler):
    """
    Example request handler which echos the given request, along with data from the 'server'.
    """
    def handle_status_request(self, request: CTPMessage):
        # Format the response data to contain the server ID
        data:bytes = self.peer.cluster_id.encode("ascii") + b": " + request.data
        self.send_response(CTPMessageType.STATUS_RESPONSE, data)

    def handle_notification(self, request: CTPMessage):
        data:bytes = self.peer.cluster_id.encode("ascii") + b": " + request.data
        self.send_response(CTPMessageType.NOTIFICATION_ACK, data)
    
    def handle_block_request(self, request: CTPMessage):
        data:bytes = self.peer.cluster_id.encode("ascii") + b": " + request.data
        self.send_response(CTPMessageType.BLOCK_RESPONSE, data)
    
    def handle_no_op(self, request: CTPMessage):
        pass
    
    def handle_unknown_request(self, request: CTPMessage):
        data:bytes = self.peer.cluster_id.encode("ascii") + b": " + request.data
        self.send_response(CTPMessageType.STATUS_RESPONSE, data)
    
    def cleanup(self):
        self.close()

example_cluster_id = "3f80e91dc65311ed93abeddb088b3faa"
src_addr = ('127.0.0.1', 6969)
dest_addr = ('127.0.0.1', 7070)

peer = CTPPeer(
    peer_addr=src_addr,
    cluster_id=example_cluster_id, 
    requestHandlerClass=EchoRequestHandler
)
try:
    peer.listen()
    while(True): 
        # Main Loop
        command = input().lower()
        if command == "exit":
            print("Exit command, stopping peer...")
            break
except KeyboardInterrupt:
    print("Keyboard Interrupt, stopping peer...")
finally:
    peer.end()
    print("Peer ended.")