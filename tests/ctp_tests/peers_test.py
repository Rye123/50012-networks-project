import unittest
from ctp.ctp import CTPMessageType
from ctp.peers import CTPPeer
import socket

def get_unused_port() -> int:
    sock = socket.socket()
    sock.bind(('', 0))
    empty_port = sock.getsockname()[1]
    sock.close()
    return empty_port

class TestCTPPeer(unittest.TestCase):
    def setUp(self):
        valid_addr = ('127.0.0.1', get_unused_port())
        valid_cluster_id = "000___ctp_test_cluster_num___000"
        valid_peer_id    = "000___ctp_test_peer_number___000"
        self.valid_peer = CTPPeer(
            peer_addr=valid_addr,
            cluster_id=valid_cluster_id,
            peer_id=valid_peer_id
        )

    def test_invalid_cluster_ids(self):
        valid_addr = ('127.0.0.1', get_unused_port())
        invalid_cluster_id_type = b'should not be bytes'
        invalid_cluster_id_short = "this is < 32 bytes"
        invalid_cluster_id_long = "this is almost certainly one hundred and one percent longer than 32 bytes trust me man i even len()ned this to check"
        self.assertRaises(TypeError, CTPPeer, peer_addr=valid_addr, cluster_id=invalid_cluster_id_type)
        self.assertRaises(ValueError, CTPPeer, peer_addr=valid_addr, cluster_id=invalid_cluster_id_short)
        self.assertRaises(ValueError, CTPPeer, peer_addr=valid_addr, cluster_id=invalid_cluster_id_long)

    def test_invalid_peer_ids(self):
        valid_addr = ('127.0.0.1', get_unused_port())
        invalid_peer_id_type = b'should not be bytes'
        invalid_peer_id_short = "this is < 32 bytes"
        invalid_peer_id_long = "this is almost certainly one hundred and one percent longer than 32 bytes trust me man i even len()ned this to check"
        self.assertRaises(TypeError, CTPPeer, peer_addr=valid_addr, peer_id=invalid_peer_id_type)
        self.assertRaises(ValueError, CTPPeer, peer_addr=valid_addr, peer_id=invalid_peer_id_short)
        self.assertRaises(ValueError, CTPPeer, peer_addr=valid_addr, peer_id=invalid_peer_id_long)

    def test_invalid_peer_addr(self):
        invalid_addr_1 = '127.0.0.1'
        invalid_addr_2 = ('127.0.0.1', '6969')
        invalid_addr_3 = (1, '6969')
        self.assertRaises(TypeError, CTPPeer, peer_addr=invalid_addr_1)
        self.assertRaises(TypeError, CTPPeer, peer_addr=invalid_addr_2)
        self.assertRaises(TypeError, CTPPeer, peer_addr=invalid_addr_3)

    def test_send_request_invalidtype(self):
        self.assertRaises(ValueError, self.valid_peer.send_request, 'boo', b'', '')
        self.assertRaises(ValueError, self.valid_peer.send_request, CTPMessageType.STATUS_RESPONSE, b'', '')
        self.assertRaises(ValueError, self.valid_peer.send_request, CTPMessageType.NOTIFICATION_ACK, b'', '')
        self.assertRaises(ValueError, self.valid_peer.send_request, CTPMessageType.BLOCK_RESPONSE, b'', '')
    
    def tearDown(self):
        self.valid_peer.end()