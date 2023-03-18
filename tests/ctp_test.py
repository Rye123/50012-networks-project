import unittest
from client.ctp import CTPMessage, CTPMessageType

class TestPackingAndUnpacking(unittest.TestCase):
    def test_pack_and_unpack(self):
        data = b'Hello world'
        message = CTPMessage(CTPMessageType.STATUS_REQUEST, data)
        packet = message.pack()
        expected_packet_b = b'\x00\x00\x00\x00\x00\x0b' + data
        self.assertEqual(packet, expected_packet_b)
        resolved_message = CTPMessage.unpack(expected_packet_b)
        self.assertEqual(message, resolved_message)