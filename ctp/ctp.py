import struct
import logging
from socket import socket, AF_INET, SOCK_STREAM
from enum import IntEnum
from typing import List, Tuple, Dict, Any
from uuid import uuid1, uuid4, UUID

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
    ENCODING = 'ascii'

    def __init__(self, 
        msg_type: CTPMessageType,
        data: bytes = b'',
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
        self.data_length = len(data)
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
        packet += struct.pack('!I', self.data_length)                         # unsigned int, 4 bytes
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
        data_length = headers[1]
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
            "data_length": data_length,
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
            cluster_id=headers['cluster_id'],
            sender_id=headers['sender_id']
        )
    
    def is_request(self) -> bool:
        """
        Helper method that returns True if this is a request.
        """
        return self.msg_type.is_request()

    def __repr__(self):
        return f"{self.msg_type.name}\n\tLength: {self.data_length}\n\tCluster/Sender ID: {self.cluster_id}/{self.sender_id}\n\tData: {self.data}"

    def __eq__(self, message: 'CTPMessage') -> bool:
        return (self.msg_type == message.msg_type) and \
            (self.cluster_id == message.cluster_id) and \
            (self.sender_id == message.sender_id) and \
            (self.data_length == message.data_length) and \
            (self.data == message.data)
    
class Connection:
    """
    Defines a CTP connection.
    """
    class ConnectionError(Exception):
        def __init__(self, *args: object) -> None:
            super().__init__(*args)

    def __init__(self, sock: socket, default_timeout: float = 5.0):
        self.sock = sock
        self.timeout = default_timeout

    def send_message(self, message: CTPMessage):
        """
        Sends `packet` over the current socket.
        - Raises a `ConnectionError` if there was an error in the connection.
        """
        packet = message.pack()

        total_bytes_sent = 0
        while total_bytes_sent < len(packet):
            bytes_sent = self.sock.send(packet)
            if bytes_sent == 0:
                raise ConnectionError("Socket connection broken")
            total_bytes_sent += bytes_sent

    def recv_message(self) -> CTPMessage:
        """
        Receives a full message from the current socket.
        """

        # Receive len(headers) bytes from the socket.
        header_b = self._recv(CTPMessage.HEADER_LENGTH)

        # Parse, get the length of the data
        try:
            headers = CTPMessage.unpack_header(header_b)
        except InvalidCTPMessageError:
            raise ConnectionError("Invalid message header.")
        expected_data_len = headers['data_length']

        # Get the rest of the data.
        data = self._recv(expected_data_len)

        return CTPMessage.unpack(header_b + data)

    def _recv(self, byte_len: int) -> bytes:
        """
        Receives `byte_len` from the current socket.
        """
        recvd_bytes = b''
        while len(recvd_bytes) < byte_len:
            chunk = self.sock.recv(byte_len - len(recvd_bytes))
            if not chunk or len(chunk) == 0:
                raise ConnectionError("Socket connection broken in _recv()")
            recvd_bytes += chunk
        return recvd_bytes

    def close(self):
        """
        Closes the socket
        """
        self.sock.close()
    
class CTPPeer:
    def __init__(self, cluster_id:str = PLACEHOLDER_CLUSTER_ID, max_connections: int = 5):
        if not isinstance(cluster_id, str):
            raise TypeError("Invalid type for cluster_id: cluster_id is not a str.")
        if len(cluster_id.encode('ascii')) != 32:
            raise ValueError(f"cluster_id of invalid length: {len(cluster_id)} != 32")
        self.connections:List[Connection] = []
        self.id = uuid1().hex
        self.cluster_id = cluster_id

    def _log(self, level: str, message: str):
        """
        Helper function to log messages regarding this peer.
        """
        level = level.lower()
        message = f"{self.id}: {message}"
        #TODO: probably another better way to do this

        match level:
            case "debug":
                logging.debug(message)
            case "info":
                logging.info(message)
            case "warning":
                logging.warning(message)
            case "error":
                logging.error(message)
            case "critical":
                logging.critical(message)
            case _:
                logging.warning(f"{self.id}: Unknown log level used for the following message:")
                logging.info(message)
    
    def _connect(self, dest_ip: str, dest_port: int, default_timeout: float = 5.0) -> Connection:
        client_sock = socket(AF_INET, SOCK_STREAM)
        client_sock.settimeout(default_timeout) #TODO: determine where to put timeout
        try:
            client_sock.connect((dest_ip, dest_port))
        except TimeoutError:
            raise ConnectionError("Could not connect due to timeout.")
        
        #TODO: Should connection be in another thread?
        return Connection(client_sock)
    
    def send_request(self, msg_type: CTPMessageType, data: bytes, dest_ip: str, dest_port: int = 6969):
        """
        Sends a request of type `msg_type` containing data `data` to `(dest_ip, dest_port)`.
        - Raises a `ValueError` if the given `msg_type` is not a request.
        """
        if not isinstance(msg_type, CTPMessageType) or not msg_type.is_request():
            raise ValueError("Invalid msg_type: msg_type should be a CTPMessageType and a request.")
        
        conn = self._connect(dest_ip, dest_port)
        message = CTPMessage(
            msg_type,
            data,
            self.cluster_id,
            self.id
        )

        # if it's a request, expect a response
        self._log("info", f"Sending {msg_type.name} with data {data}.")
        response:CTPMessage = None
        match msg_type:
            #TODO: need to follow data as stated in docs
            case CTPMessageType.STATUS_REQUEST:
                conn.send_message(message)
                response = conn.recv_message()
            case CTPMessageType.BLOCK_REQUEST:
                print("Sending BLOCK_REQUEST")
                conn.send_message(message)
                response = conn.recv_message()
            case CTPMessageType.NOTIFICATION: # for manifest update notifs
                print("Sending NOTIFICATION")
                conn.send_message(message)
                response = conn.recv_message()
            case _:
                print("Cannot send non-request")
        if response is not None:
            self._log("info", f"Received response {response.msg_type.name} with data: {response.data}")
        else:
            self._log("warning", f"Non-request detected, cancelling send operation.")
        
        # Close connection
        conn.close()
        self._log("info", f"Connection closed.")
    
    def listen(self, src_ip: str = '', src_port: int = 6969, max_requests:int = 1):
        """
        Blocking function that listens on `(src_ip, src_port)`.
        """
        welcome_sock = socket(AF_INET, SOCK_STREAM)
        welcome_sock.bind((src_ip, src_port))
        welcome_sock.listen(max_requests)
        self._log("info", f"Listening on ({src_ip}, {src_port}).")

        while True:
            conn_sock, conn_addr = welcome_sock.accept()
            self._log("info", f"Received connection from ({conn_addr})")
            conn = Connection(conn_sock)
            #TODO: threading

            # Receive message on conn_sock
            try:
                client_msg = conn.recv_message()
            except ConnectionError:
                self._log("info", f"Client disconnected.")
                continue

            # Respond appropriately
            response:CTPMessage = None

            self._log("info", f"Received {client_msg.msg_type.name} with data {client_msg.data}.")
            #TODO: encapsulate this part in a separate function
            match client_msg.msg_type:
                #TODO: create class for response? also need to follow data as stated in docs
                case CTPMessageType.STATUS_REQUEST:
                    response = CTPMessage(
                        CTPMessageType.STATUS_RESPONSE,
                        b"",
                        self.cluster_id,
                        self.id
                    )
                case CTPMessageType.BLOCK_REQUEST:
                    response = CTPMessage(
                        CTPMessageType.BLOCK_RESPONSE,
                        b"",
                        self.cluster_id,
                        self.id
                    )
                case CTPMessageType.NOTIFICATION: # for manifest update notifs
                    response = CTPMessage(
                        CTPMessageType.NOTIFICATION_ACK,
                        b"",
                        self.cluster_id,
                        self.id
                    )
                case _:
                    # Break
                    conn.close()
                    continue
            
            conn.send_message(response)
            self._log("info", f"Responded with {response.msg_type.name}.")


