import struct
from enum import IntEnum
from typing import List

class CTPMessageType(IntEnum):
    STATUS_REQUEST = 0
    STATUS_RESPONSE = 1
    MANIFEST_UPDATED = 2
    BLOCK_REQUEST = 3
    BLOCK_RESPONSE = 4

class CTPMessage:
    """
    A message in the Cluster Transfer Protocol.
    - msg_type
    - body_size
    - body
    """
    def __init__(self, 
        msg_type: CTPMessageType,
        data: bytes
    ):
        self.msg_type = msg_type
        self.body_size = len(data)
        self.body = data
    
    def pack(self) -> bytes:
        """
        Returns the message as a packet of assembled bytes.
        """
        # Assemble packet contents
        packet:bytes = b''
        packet += struct.pack('!H', self.msg_type.value)  # unsigned short, 2 bytes
        packet += struct.pack('!I', self.body_size) # unsigned int, 4 bytes
        packet += self.body

        return packet
    
    @staticmethod
    def unpack(packet: bytes) -> 'CTPMessage':
        """
        Unpacks a **full packet**.
        """
        headers = struct.unpack('!HI', packet[0:6])
        return CTPMessage(
            CTPMessageType(headers[0]),
            packet[6:]
        )
    
    def __repr__(self):
        return f"{self.msg_type.name}\n\tLength: {self.body_size}\n\tData: {self.body}"

    def __eq__(self, message: 'CTPMessage') -> bool:
        return (self.msg_type == message.msg_type) and \
            (self.body_size == message.body_size) and \
            (self.body == message.body)