import struct
import logging
from socket import socket, AF_INET, SOCK_STREAM
from enum import IntEnum
from typing import List, Tuple, Dict, Any

logging.basicConfig(level = logging.DEBUG)


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
        data: bytes,
        cluster_id: str = "placeholder cluster",
        sender_id: str = "placeholder sender"
    ):
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
        Unpacks only the packet headers.
        """
        if len(packet_header) != cls.HEADER_LENGTH:
            raise InvalidCTPMessageError("Packet header does not have exactly 6 bytes.")
        
        headers = struct.unpack('!HI32s32s', packet_header)
        return {
            "msg_type": CTPMessageType(headers[0]),
            "data_length": headers[1],
            "cluster_id": bytes(headers[2]).decode(cls.ENCODING),
            "sender_id": bytes(headers[3]).decode(cls.ENCODING)
        }

    @classmethod
    def unpack(cls, packet: bytes) -> 'CTPMessage':
        """
        Unpacks a **full packet**.
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
    
    def __repr__(self):
        return f"{self.msg_type.name}\n\tLength: {self.data_length}\n\tData: {self.data}"

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
        headers = CTPMessage.unpack_header(header_b)
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
    def __init__(self, id:int = None, max_connections: int = 5):
        self.connections:List[Connection] = []
        if id is None:
            id = 999 #TODO: use uuid or use their actual ID (how?)
        self.id = id

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
    
    def send_message(self, msg_type: CTPMessageType, data: bytes, dest_ip: str, dest_port: int = 6969):
        conn = self._connect(dest_ip, dest_port)
        message = CTPMessage(
            msg_type,
            data
        )

        # if it's a request, expect a response
        #TODO: maybe change the CTP Message to be request or response, then put the actual type in the headers?
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
        conn.close() #TODO: this results in a socket connection broken break in server, maybe should check for that on server end
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
            client_msg = conn.recv_message()

            # Respond appropriately
            response:CTPMessage = None

            self._log("info", f"Received {client_msg.msg_type.name} with data {client_msg.data}.")
            match client_msg.msg_type:
                #TODO: create class for response? also need to follow data as stated in docs
                case CTPMessageType.STATUS_REQUEST:
                    response = CTPMessage(
                        CTPMessageType.STATUS_RESPONSE,
                        b"" 
                    )
                case CTPMessageType.BLOCK_REQUEST:
                    response = CTPMessage(
                        CTPMessageType.BLOCK_RESPONSE,
                        b""
                    )
                case CTPMessageType.NOTIFICATION: # for manifest update notifs
                    response = CTPMessage(
                        CTPMessageType.NOTIFICATION_ACK,
                        b""
                    )
                case _:
                    # Break
                    conn.close()
                    continue
            
            conn.send_message(response)
            self._log("info", f"Responded with {response.msg_type.name}.")


