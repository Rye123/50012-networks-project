### DEEP DARK MAGIC TO ALLOW FOR ABSOLUTE IMPORT
from pathlib import Path
import sys
path = str(Path(Path(__file__).parent.absolute()).parent.absolute())
sys.path.insert(0, path)
### END OF DEEP DARK MAGIC

from ctp import *
from util import standardHandler
from traceback import format_exc
from time import sleep

# Logging Settings
APP_LOGGING_LEVEL = logging.DEBUG
CTP_LOGGING_LEVEL = logging.WARNING # Recieve only warnings.

logger = logging.getLogger()
logger.setLevel(APP_LOGGING_LEVEL)
ctp_logger = logging.getLogger('ctp')
ctp_logger.setLevel(CTP_LOGGING_LEVEL)
logger.addHandler(standardHandler)


example_cluster_id = "3f80e91dc65311ed93abeddb088b3faa"
dest_addr = ('127.0.0.1', 6969)
src_addr = ('127.0.0.1', 7070)

peer = CTPPeer(
    peer_addr=src_addr,
    cluster_id=example_cluster_id
)
try:
    peer.listen()
    logger.info(f"Send STATUS_REQUEST to {dest_addr}")
    peer.send_request(CTPMessageType.STATUS_REQUEST, b'This is a status request', dest_addr, retries=1)
    logger.info(f"Received response. Waiting for 0.5s...")
    sleep(0.5)
    logger.info(f"Send BLOCK_REQUEST to {dest_addr}")
    peer.send_request(CTPMessageType.BLOCK_REQUEST, b'This is a block request', dest_addr)
    logger.info(f"Received response. Waiting for 0.5s...")
    sleep(0.5)
    logger.info(f"Send NOTIFICATION to {dest_addr}")
    peer.send_request(CTPMessageType.NOTIFICATION, b'This is a notification.', dest_addr)
    logger.info(f"Received response.")
except CTPConnectionError as e:
    logger.info(f"Could not send request due to a connection error: {str(e)}")
    logger.info("Stopping peer...")
except Exception:
    logger.critical(format_exc())
    logger.info("Exception encountered, stopping peer...")
except KeyboardInterrupt:
    logger.info("Keyboard Interrupt, stopping peer...")
finally:
    peer.end()
    logger.info("Peer ended.")