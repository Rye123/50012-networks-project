import unittest
from ctp.ctp import CTPMessageType
from ctp.peers import CTPPeer

class TestCTPPeer(unittest.TestCase):
    def test_send_request_invalidtype(self):
        testPeer = CTPPeer()
        self.assertRaises(ValueError, testPeer.send_request, 'boo', b'', '')
        self.assertRaises(ValueError, testPeer.send_request, CTPMessageType.STATUS_RESPONSE, b'', '')
        self.assertRaises(ValueError, testPeer.send_request, CTPMessageType.NOTIFICATION_ACK, b'', '')
        self.assertRaises(ValueError, testPeer.send_request, CTPMessageType.BLOCK_RESPONSE, b'', '')