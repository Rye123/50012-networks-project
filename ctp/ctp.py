import struct
import logging
from enum import IntEnum
from typing import Dict, Any
from uuid import uuid4

logging.basicConfig(level = logging.DEBUG)
PLACEHOLDER_CLUSTER_ID:str = uuid4().hex
PLACEHOLDER_SENDER_ID:str = uuid4().hex

class InvalidCTPMessageError(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)

class CTPMessageType(IntEnum):
    STATUS_REQUEST   = 0b0000
    STATUS_RESPONSE  = 0b0001
    NOTIFICATION     = 0b0010
    NOTIFICATION_ACK = 0b0011
    BLOCK_REQUEST    = 0b0100
    BLOCK_RESPONSE   = 0b0101

    def is_request(self) -> bool:
        """
        Helper method that returns True if this message type is a request.
        """
        # if value is even (i.e. last bit is 0, then it's a request)
        return (self.value % 2) == 0

class CTPMessage:
    """
    A message in the Cluster Transfer Protocol.
    - msg_type
    - data_length
    - cluster_id
    - sender_id
    - data
    """
    HEADER_LENGTH = 70
    MAX_PACKET_SIZE = 1400
    ENCODING = 'ascii'

    def __init__(self, 
        msg_type: CTPMessageType,
        data: bytes = b'',
        src_port: int = 6969,
        cluster_id: str = PLACEHOLDER_CLUSTER_ID,
        sender_id: str = PLACEHOLDER_SENDER_ID
    ):
        """
        Initialise a `CTPMessage`.

        # Inputs
        - `msg_type`: A `CTPMessageType` representing the type of the message.
        - `data`: The actual data to be encapsulated in the message.
        - `cluster_id`: ID of the cluster this message is sent under.
        - `sender_id`: ID of the sender of this message.
        """
        if not isinstance(msg_type, CTPMessageType):
            raise TypeError("Invalid type for msg_type: msg_type is not a CTPMessageType.")
        if not isinstance(data, bytes):
            raise TypeError("Invalid type for data: data is not a bytes object.")
        if not isinstance(cluster_id, str):
            raise TypeError("Invalid type for cluster_id: cluster_id is not a str.")
        if not isinstance(sender_id, str):
            raise TypeError("Invalid type for sender_id: sender_id is not a str.")
        if len(cluster_id.encode(self.ENCODING)) != 32:
            raise ValueError(f"cluster_id of invalid length: {len(cluster_id)} != 32")
        if len(sender_id.encode(self.ENCODING)) != 32:
            raise ValueError(f"sender_id of invalid length: {len(sender_id)} != 32")

        self.msg_type = msg_type
        self.src_port = src_port
        self.data = data
        self.cluster_id = cluster_id
        self.sender_id = sender_id
    
    def pack(self) -> bytes:
        """
        Returns the message as a packet of assembled bytes.
        """
        # Assemble packet contents
        packet:bytes = b''
        packet += struct.pack('!H', self.msg_type.value)                      # unsigned short, 2 bytes
        packet += struct.pack('!I', self.src_port)                         # unsigned int, 4 bytes
        packet += struct.pack('!32s', self.cluster_id.encode(self.ENCODING))
        packet += struct.pack('!32s', self.sender_id.encode(self.ENCODING))
        
        packet += self.data

        return packet
    
    @classmethod
    def unpack_header(cls, packet_header: bytes) -> Dict[str, Any]:
        """
        Unpacks the given bytes as a packet header.
        Returns a Dictionary mapping each packet header to the actual value.
        - Raises an `InvalidCTPMessageError` if the header is invalid.
        """
        if len(packet_header) != cls.HEADER_LENGTH:
            raise InvalidCTPMessageError("Packet header does not have exactly 6 bytes.")
        
        headers = struct.unpack('!HI32s32s', packet_header)
        # Validate values
        msg_type = None
        src_port = headers[1]
        cluster_id = None
        sender_id = None
        try:
            msg_type = CTPMessageType(headers[0])
        except (TypeError, ValueError) as e:
            raise InvalidCTPMessageError(f"Unknown message type: {str(e)}")
        try:
            cluster_id = bytes(headers[2]).decode(cls.ENCODING)
            sender_id  = bytes(headers[3]).decode(cls.ENCODING)
        except UnicodeDecodeError:
            raise InvalidCTPMessageError("Non-ASCII encoding in header")

        return {
            "msg_type": msg_type,
            "src_port": src_port,
            "cluster_id": cluster_id,
            "sender_id": sender_id
        }

    @classmethod
    def unpack(cls, packet: bytes) -> 'CTPMessage':
        """
        Unpacks the given `packet`.
        Returns a `CTPMessage` constructed from the packet.
        - Raises an `InvalidCTPMessageError` if the packet is invalid.
        """
        if len(packet) < cls.HEADER_LENGTH:
            raise InvalidCTPMessageError("Invalid packet")
        
        headers = CTPMessage.unpack_header(packet[0:cls.HEADER_LENGTH])
        data = packet[cls.HEADER_LENGTH:]

        return CTPMessage(
            headers['msg_type'],
            data,
            src_port=headers["src_port"],
            cluster_id=headers['cluster_id'],
            sender_id=headers['sender_id']
        )
    
    def is_request(self) -> bool:
        """
        Helper method that returns True if this is a request.
        """
        return self.msg_type.is_request()

    def __repr__(self):
        return f"{self.msg_type.name}\n\tSource Port: {self.src_port}\n\tCluster/Sender ID: {self.cluster_id}/{self.sender_id}\n\tData: {self.data}"

    def __eq__(self, message: 'CTPMessage') -> bool:
        return (self.msg_type == message.msg_type) and \
            (self.cluster_id == message.cluster_id) and \
            (self.sender_id == message.sender_id) and \
            (self.src_port == message.src_port) and \
            (self.data == message.data)
