import unittest
import struct
from uuid import uuid4
from ctp.ctp import CTPMessage, CTPMessageType, InvalidCTPMessageError

class TestCTPMessage(unittest.TestCase):
    def test_invalid_types_give_error(self):
        invalid_msg_type = 1
        valid_msg_type = CTPMessageType.BLOCK_REQUEST
        invalid_data = "invalid string arg"
        valid_data = b''
        invalid_id_type = b"id should be a string"
        valid_cluster_id = uuid4().hex
        valid_sender_id = uuid4().hex
        self.assertRaises(TypeError, CTPMessage, invalid_msg_type)
        self.assertRaises(TypeError, CTPMessage, valid_msg_type, invalid_data)
        self.assertRaises(TypeError, CTPMessage, valid_msg_type, valid_data, invalid_id_type)
        self.assertRaises(TypeError, CTPMessage, valid_msg_type, valid_data, valid_cluster_id, invalid_id_type)
        self.assertRaises(TypeError, CTPMessage, valid_msg_type, valid_data, invalid_id_type, valid_sender_id)
    
    def test_invalid_ids_give_error(self):
        valid_msg_type = CTPMessageType.BLOCK_REQUEST
        valid_data = b''
        valid_cluster_id = uuid4().hex
        valid_sender_id = uuid4().hex
        invalid_id_short = "this is less than 32 bytes"
        invalid_id_long = "this is almost certainly one hundred and one percent longer than 32 bytes trust me man i even len()ned this to check"
        self.assertRaises(ValueError, CTPMessage, valid_msg_type, valid_data, invalid_id_short, valid_sender_id)
        self.assertRaises(ValueError, CTPMessage, valid_msg_type, valid_data, invalid_id_long, valid_sender_id)
        self.assertRaises(ValueError, CTPMessage, valid_msg_type, valid_data, valid_cluster_id, invalid_id_short)
        self.assertRaises(ValueError, CTPMessage, valid_msg_type, valid_data, valid_cluster_id, invalid_id_long)

    def test_pack_and_unpack(self):
        data = b'Hello world'
        test_cluster_id = uuid4().hex
        test_sender_id = uuid4().hex
        msg_type = CTPMessageType.STATUS_REQUEST
        message = CTPMessage(msg_type, data, test_cluster_id, test_sender_id)
        packet = message.pack()
        expected_packet_b = struct.pack('!HI32s32s',
                                        msg_type,
                                        len(data),
                                        test_cluster_id.encode('ascii'),
                                        test_sender_id.encode('ascii')
                                        ) + data
        self.assertEqual(packet, expected_packet_b)
        resolved_message = CTPMessage.unpack(expected_packet_b)
        self.assertEqual(message, resolved_message)

    def test_unpack_invalid_packet(self):
        invalid_packets = [
            b'',
            b'potato',
            b"According to all known laws of aviation, there is no way a bee should be able to fly. Its wings are too small to get its fat little body off the ground. The bee, of course, flies anyway because bees don't care what humans think is impossible."
        ]
        for invalid_packet in invalid_packets:
            self.assertRaises(InvalidCTPMessageError, CTPMessage.unpack_header, invalid_packet)
            self.assertRaises(InvalidCTPMessageError, CTPMessage.unpack, invalid_packet)

