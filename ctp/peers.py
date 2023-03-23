import logging
from abc import ABC, abstractmethod
from threading import Thread, Event
from socket import socket, AF_INET, SOCK_DGRAM # UDP
from uuid import uuid1, UUID
from typing import Any, Type, List, Callable, Tuple

from ctp.ctp import CTPMessage, CTPMessageType, InvalidCTPMessageError
from ctp.ctp import PLACEHOLDER_CLUSTER_ID, PLACEHOLDER_SENDER_ID

AddressType = Tuple[str, int]
ENCODING = 'ascii'
# logging.basicConfig(filename='example.log', encoding='utf-8', level=logging.DEBUG)

class RequestHandler(ABC):
    """
    An abstract base class that abstracts away socket control for \
        handling a given `CTPMessage` and sending a response.

    This class has several abstract methods that should be \
        implemented, these provide functionality to handle given requests. \
            We almost always want to respond to the request, since the \
                client's default state is to wait for a response. 
    - `cleanup()`
    - `handle_status_request(request)`
    - `handle_notification(request)`
    - `handle_block_request(request)`
    - `handle_unknown_request(request)`.

    An example implementation is the `DefaultRequestHandler`.
    """
    def __init__(self, peer: 'CTPPeer', connection: 'CTPConnection'):
        self.peer = peer
        self._conn = connection

    def handle(self, request: CTPMessage):
        """
        Handles a request. 
        If necessary, this can be overriden for different logic.

        When a `request` is received by a `CTPPeer`, a `HandlerThread` is \
        created which runs this method. This method then delegates the \
        responsibility of handling the request to the following abstract \
        methods:
        - `handle_status_request(request)`
        - `handle_notification(request)`
        - `handle_block_request(request)`
        - `handle_unknown_request(request)`.
        """
        self.peer._log("info", f"Received {request.msg_type.name} with data {request.data}.")
        match request.msg_type:
            case CTPMessageType.STATUS_REQUEST:
                self.handle_status_request(request)
            case CTPMessageType.NOTIFICATION:
                self.handle_notification(request)
            case CTPMessageType.BLOCK_REQUEST:
                self.handle_block_request(request)
            case _:
                self.handle_unknown_request(request)
        self.cleanup()
    
    def close(self):
        """
        Ends the connection.
        """
        self.peer._log("info", "Closing connection.")
        self._conn.close()
    
    def send_response(self, msg_type: CTPMessageType, data: bytes):
        """
        Sends a response.
        - `msg_type`: CTPMessageType of the message. Should be a response.
        - `data`: Data bytes to be sent in the response.
        """
        if not isinstance(msg_type, CTPMessageType) or msg_type.is_request():
            raise ValueError("Invalid msg_type: msg_type should be a CTPMessageType and a response.")
        
        response = CTPMessage(
            msg_type,
            data,
            self.peer.cluster_id,
            self.peer.peer_id
        )
        self.peer._log("info", f"Responded with {response.msg_type.name}.")
        self._conn.send_message(response)
    
    @abstractmethod
    def cleanup(self):
        """
        Handles the cleanup after a request.
        Most of the time, we want to end the interaction, which can be done with the `.close()` method.
        """
    
    @abstractmethod
    def handle_status_request(self, request: CTPMessage):
        """
        Handles a `STATUS_REQUEST`.
        This should send an appropriate `STATUS_RESPONSE`, with the `send_response` method.
        """
    
    @abstractmethod
    def handle_notification(self, request: CTPMessage):
        """
        Handles a `NOTIFICATION`.
        This should send an appropriate `NOTIFICATION_ACK`, with the `send_response` method.
        """

    @abstractmethod
    def handle_block_request(self, request: CTPMessage):
        """
        Handles a `BLOCK_REQUEST`.
        This should send an appropriate `BLOCK_RESPONSE`, with the `send_response` method.
        """
    
    @abstractmethod
    def handle_unknown_request(self, request: CTPMessage):
        """
        Handle an unknown request.
        We shouldn't be able to reach this point, but if there's a request defined in the future \
            that isn't handled by the above methods, it will be handled here.
        """

class CTPConnectionError(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)

class CTPConnection:
    """
    A bidirectional connection over UDP. This is a connection that has already been \
    established over the Server.
    - local_addr: Local address, where a CTP service is listening.
    - remote_addr: Remote address, where a CTP service is listening.
    """
    def __init__(self, peer: 'CTPPeer', local_addr: AddressType, remote_addr: AddressType):
        self.local_addr = local_addr
        self.remote_addr = remote_addr
        self.peer = peer
        
    def send_message(self, message: CTPMessage):
        """
        Sends `message` over the connection.
        - Raises a `CTPConnectionError` if there was an error in the connection.
        """
        message.src_port = self.local_addr[1]
        packet = message.pack()
        self.peer._log("debug", f"Sending packet to {self.remote_addr} from {self.local_addr}")

        self.peer.sock.sendto(packet, self.remote_addr)

    def recv_message(self) -> CTPMessage:
        """
        Receives a full message from the listener socket.

        Ideally, you would want to handle this using the `.listen()` method, handling requests with a separate `RequestHandler`.
        - Raises a `InvalidCTPMessageError` if the given message is invalid.
        """
        self.peer._log("debug", "Receiving...")
        data, addr = self.peer.sock.recvfrom(CTPMessage.MAX_PACKET_SIZE)
        if addr != self.remote_addr:
            print("Received message, but not from there")
            pass
        return CTPMessage.unpack(data)

    def close(self):
        pass

class CTPPeer:
    """
    A single peer using the CTP protocol.
    - `cluster_id`: 32-byte string representing ID of the cluster.
    - `peer_id`: 32-byte string representing ID of peer.
    """

    def __init__(self, peer_addr: AddressType, cluster_id: str=PLACEHOLDER_CLUSTER_ID, peer_id: str=PLACEHOLDER_SENDER_ID, requestHandlerClass: Type[RequestHandler]=None):
        """
        Initialise a CTP peer.
        """
        cluster_id_b = cluster_id.encode(ENCODING)
        peer_id_b = peer_id.encode(ENCODING)
        if not isinstance(cluster_id, str):
            raise TypeError("Invalid type for cluster_id: cluster_id is not a str.")
        if not isinstance(peer_id, str):
            raise TypeError("Invalid type for peer_id: peer_id is not a str.")
        if len(cluster_id_b) != 32:
            raise ValueError(f"cluster_id of invalid length: {len(cluster_id_b)} != 32")
        if len(peer_id_b) != 32:
            raise ValueError(f"peer_id of invalid length: {len(peer_id_b)} != 32")
    
        self.peer_id = peer_id
        self.cluster_id = cluster_id
        self.peer_addr = peer_addr
        self.requestHandlerClass:Type[RequestHandler] = requestHandlerClass
        self.sock = socket(AF_INET, SOCK_DGRAM)
        self.sock.bind(peer_addr)

    def _log(self, level: str, message: str):
        """
        Helper function to log messages regarding this peer.
        """
        level = level.lower()
        message = f"{self.peer_id}: {message}"
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

    def send_request(self, msg_type: CTPMessageType, data: bytes, dest_addr: AddressType, default_timeout: float=3.0, retries: int=0) -> CTPMessage:
        """
        Sends a request of type `msg_type` containing data `data` to `(dest_ip, dest_port)`.
        Returns the response received.
        - Raises a `ValueError` if the given `msg_type` is not a request, or if `dest_addr` is not a valid address.
        - If there was a timeout or an invalid response, a `CTPSendError` would be raised after `retries` reattempts.
        """
        if not isinstance(msg_type, CTPMessageType) or not msg_type.is_request():
            raise ValueError("Invalid msg_type: msg_type should be a CTPMessageType and a request.")
        #TODO: validation functions
        if not isinstance(dest_addr, Tuple):
            if not isinstance(dest_addr[0], str) or not isinstance(dest_addr[1], int):
                raise ValueError("Invalid dest_addr: dest_addr should be a tuple of an IP address and a port.")

        #TODO: do this in a separate thread
        self.sock.settimeout(default_timeout)

        message = CTPMessage(msg_type, data, self.cluster_id, self.peer_id)
        
        self._log("info", f"Sending {msg_type.name} with data {data}.")
        
        connection = CTPConnection(self, self.peer_addr, dest_addr)
        # Keep sending until we get a response/reach max attempts
        attempts = 0
        successful_send = False
        fail_reason = ""
        while attempts <= retries:
            attempts += 1
            self._log("info", f"Sending attempt {attempts}")
            try:
                connection.send_message(message)
                response = connection.recv_message()
                successful_send = True
                # Successful response received, break from loop
                break
            except TimeoutError:
                self._log("debug", f"Attempt {attempts} to send message failed.")
                fail_reason = "TIMEOUT"
                pass
            except InvalidCTPMessageError:
                self._log("debug", f"Invalid response received, retrying.")
                fail_reason = "INVALID RESPONSE"
                pass
            except Exception as e:
                self._log("debug", f"send_request Exception: {str(e)}")
                fail_reason = "EXCEPTION"
                pass
        if successful_send:
            self._log("info", f"Message sent, received response after attempts {attempts}: {response.msg_type.name} with data: {response.data}")
        else:
            if fail_reason == "":
                fail_reason = "TIMEOUT?"
            raise CTPConnectionError(f"Failed to send message after attempts {attempts}, reason was: {fail_reason}")

        return response
    
    def listen(self):
        """
        Listens on the given `src_addr`.
        - Raises a `ValueError` if `src_addr` is invalid.
        - Raises a `CTPListenError` if there was an error.
        """
        data, addr = self.sock.recvfrom(CTPMessage.MAX_PACKET_SIZE)
        
        #TODO: check if addr is in the peerlist?
        connection = CTPConnection(self, self.peer_addr, addr)
        try:
            request = CTPMessage.unpack(data)
            handler = self.requestHandlerClass(self, connection)
            handler.handle(request)
            self.listen()

        except InvalidCTPMessageError:
            self._log("info", "received invalid CTP request")
            pass
    
    def end(self):
        pass