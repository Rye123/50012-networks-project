import unittest
from ctp.ctp import CTPMessageType
from ctp.peers import CTPPeer

#TODO: fix tests

class TestCTPPeer(unittest.TestCase):
    def test_invalid_cluster_ids(self):
        invalid_cluster_id_type = b'should not be bytes'
        invalid_cluster_id_short = "this is < 32 bytes"
        invalid_cluster_id_long = "this is almost certainly one hundred and one percent longer than 32 bytes trust me man i even len()ned this to check"
        self.assertRaises(TypeError, CTPPeer, cluster_id=invalid_cluster_id_type)
        self.assertRaises(ValueError, CTPPeer, cluster_id=invalid_cluster_id_short)
        self.assertRaises(ValueError, CTPPeer, cluster_id=invalid_cluster_id_long)

    def test_invalid_peer_ids(self):
        invalid_peer_id_type = b'should not be bytes'
        invalid_peer_id_short = "this is < 32 bytes"
        invalid_peer_id_long = "this is almost certainly one hundred and one percent longer than 32 bytes trust me man i even len()ned this to check"
        self.assertRaises(TypeError, CTPPeer, peer_id=invalid_peer_id_type)
        self.assertRaises(ValueError, CTPPeer, peer_id=invalid_peer_id_short)
        self.assertRaises(ValueError, CTPPeer, peer_id=invalid_peer_id_long)

    def test_send_request_invalidtype(self):
        testPeer = CTPPeer()
        self.assertRaises(ValueError, testPeer.send_request, 'boo', b'', '')
        self.assertRaises(ValueError, testPeer.send_request, CTPMessageType.STATUS_RESPONSE, b'', '')
        self.assertRaises(ValueError, testPeer.send_request, CTPMessageType.NOTIFICATION_ACK, b'', '')
        self.assertRaises(ValueError, testPeer.send_request, CTPMessageType.BLOCK_RESPONSE, b'', '')