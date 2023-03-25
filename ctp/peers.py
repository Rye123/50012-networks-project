import logging
from abc import ABC, abstractmethod
from threading import Thread, Event
from socket import socket, AF_INET, SOCK_DGRAM # UDP
from uuid import uuid1, UUID
from queue import Queue, Empty
from typing import Any, Type, List, Callable, Tuple
from time import sleep

from ctp.ctp import CTPMessage, CTPMessageType, InvalidCTPMessageError
from ctp.ctp import PLACEHOLDER_CLUSTER_ID, PLACEHOLDER_SENDER_ID

AddressType = Tuple[str, int]
ENCODING = 'ascii'
# logging.basicConfig(filename='example.log', encoding='utf-8', level=logging.DEBUG)

class RequestHandler(ABC):
    """
    An abstract base class that handles a request. When a request is \
        received, a new request handler instance is created, and handles \
            the request.
    - `self.peer`: The peer responsible for handling the request.
    - `self.client_addr`: The request sender's address
    - `self.request`: The actual request

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
    def __init__(self, peer: 'CTPPeer', request: CTPMessage, client_addr: AddressType):
        """
        Initialise the RequestHandler with a new request.
        """
        self.peer = peer
        self.client_addr = client_addr
        self.request = request
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
        self.peer._send_message(response, self.client_addr)
        self.peer._log("info", f"Responded with {response.msg_type.name}.")
    
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

class Listener:
    """
    Manages the sole listening socket of the peer.
    """
    CHECK_FOR_INTERRUPT_INTERVAL = 1 # Time in seconds to listen on socket before checking for an interrupt.

    def __init__(self, peer: 'CTPPeer'):
        self.peer = peer
        self.sock = self.peer.sock
        self.sock.settimeout(self.CHECK_FOR_INTERRUPT_INTERVAL)
        self.handlerClass = self.peer.requestHandlerClass
        self._responses:Queue[Tuple[CTPMessage, AddressType]] = Queue()
        self._listen_thread = None
        self._stop_listening = Event()
    
    def listen(self):
        self._listen_thread = Thread(target=self._listen, args=[self.peer, self._stop_listening, self.handlerClass, self._responses])
        self._listen_thread.start()
        self._stop_listening.clear()
        self.peer._log("info", f"Listening on {self.peer.peer_addr}.")
    
    def stop(self):
        """
        Stops the listener.
        """
        self._stop_listening.set()
    
    def get_response(self, expected_addr: AddressType=None, expected_type: CTPMessageType=None, block_time: int=0.5) -> CTPMessage:
        """
        Checks the listener for a response. Blocks for `block_time` to allow time for the response to be returned.
        - Returns the response, or None.
        TODO: should we check for sender ID?
        TODO: change to a better method -- maybe a pub-sub method?
        """
        sleep(block_time)
        with self._responses.mutex:
            for tup in self._responses.queue:
                response, addr = tup
                if (expected_addr is None and expected_type == response.msg_type) \
                    or (expected_addr == addr and expected_type is None) \
                    or (expected_addr == addr and expected_type == response.msg_type):
                    self._responses.queue.remove(tup)
                    return response
        
    @staticmethod
    def _listen(peer: 'CTPPeer', stop_signal: Event, req_h: RequestHandler, res_q: Queue):
        sock = peer.sock
        src_addr = peer.peer_addr
        while not stop_signal.is_set():
            try:
                data, addr = sock.recvfrom(CTPMessage.MAX_PACKET_SIZE)
                try:
                    msg = CTPMessage.unpack(data)
                    msg_addr_tup = (msg, addr)
                    if msg.msg_type.is_request():
                        # Handle the request with a new request handler
                        handler:RequestHandler = req_h(peer, msg, addr)
                    else:
                        res_q.put(msg_addr_tup)
                except InvalidCTPMessageError:
                    pass
            except ConnectionError as e:
                pass
            except TimeoutError:
                pass
            except Exception as e:
                logging.error(f"Listener crashed with exception: {str(e)}")
                break
        sock.close()

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
        self.listener = Listener(self)

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

    def _send_message(self, message: CTPMessage, destination_addr: AddressType):
        """
        Sends `message` to the desired destination.
        - This method isn't meant to be used -- use the higher-level `send_request` or `send_response` methods instead.
        """
        packet = message.pack()
        self._log("debug", f"Sending packet to {destination_addr} from {self.peer_addr}")
        self.sock.sendto(packet, destination_addr)

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

        message = CTPMessage(msg_type, data, self.cluster_id, self.peer_id)
        
        self._log("info", f"Sending {msg_type.name} with data {data}.")
        
        # Keep sending until we get a response/reach max attempts
        attempts = 0
        successful_send = False
        fail_reason = ""
        while attempts <= retries:
            attempts += 1
            self._log("info", f"Sending attempt {attempts}")
            try:
                self._send_message(message, dest_addr)
                response = self.listener.get_response(dest_addr) #TODO: expected response based on request
                if response is None:
                    raise TimeoutError()
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
            except ConnectionError as e:
                self._log("debug", f"Connection error.")
                fail_reason = "CONNECTION"
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
            raise TimeoutError(f"Failed to send message after attempts {attempts}, reason was: {fail_reason}") #TODO

        return response
    
    def listen(self):
        """
        Listens on the given `src_addr`.
        - Raises a `ValueError` if `src_addr` is invalid.
        - Raises a `CTPListenError` if there was an error.
        """
        self.listener.listen()
    
    def end(self):
        self.listener.stop()