import logging
from abc import ABC, abstractmethod
from threading import Thread, Event, Timer
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

class CTPConnectionError(Exception):
    """
    Indicates an error to do with the CTP connection.
    """

    def __init__(self, *args: object) -> None:
        super().__init__(*args)

class Listener:
    """
    Manages the sole listening socket of the peer.    
    Any incoming messages are handled by this class, with requests being \
    redirected to the RequestHandler subclass assigned to the peer, and \
    responses being added to a threadsafe queue.

    Requests waiting for responses will call the `get_response()` method \
    to attempt to retrieve a relevant response.
    """
    CHECK_FOR_INTERRUPT_INTERVAL = 1 # Time in seconds to listen on socket before checking for an interrupt.

    def __init__(self, peer: 'CTPPeer'):
        self.peer = peer
        self.sock = self.peer.sock
        self.sock.settimeout(self.CHECK_FOR_INTERRUPT_INTERVAL)
        self.handlerClass = self.peer.requestHandlerClass
        self._responses:Queue[Tuple[CTPMessage, AddressType]] = Queue() # queue of responses for request-senders to check
        self._new_response_arrived = Event() # signal to indicate a new response has arrived
        self._listen_thread = None
        self._stop_listening = Event()
    
    def listen(self):
        self._listen_thread = Thread(target=self._listen, args=[self.peer, self._stop_listening, self.handlerClass, self._responses, self._new_response_arrived])
        self._listen_thread.start()
        self._stop_listening.clear()
        self.peer._log("info", f"Listening on {self.peer.peer_addr}.")
    
    def stop(self):
        """
        Stops the listener.
        """
        self._stop_listening.set()
    
    
    def get_response(self, expected_addr: AddressType=None, expected_type: CTPMessageType=None, block_time: int=1.0) -> CTPMessage:
        """
        Checks the listener for a response. Blocks for at least `block_time` until the response is returned.
        - Returns the response, or None.
        TODO: should we check for sender ID?
        """
        timeout_signal = Event()
        timer = Timer(block_time, self._response_timer, args=[timeout_signal])

        # Check if response is already in queue
        with self._responses.mutex:
            for tup in self._responses.queue:
                response, addr = tup
                if (expected_addr is None and expected_type == response.msg_type) \
                    or (expected_addr == addr and expected_type is None) \
                    or (expected_addr == addr and expected_type == response.msg_type):
                    self._responses.queue.remove(tup)
                    return response
        # Add watch signal to the response_signal
        timer.start()
        while not timeout_signal.is_set():
            # Block until a response arrives or timeout occurs
            while not (self._new_response_arrived.is_set() or timeout_signal.is_set()):
                pass

            if not timeout_signal.is_set():
                # New Response arrived, check
                with self._responses.mutex:
                    for tup in self._responses.queue:
                        response, addr = tup
                        if (expected_addr is None and expected_type == response.msg_type) \
                            or (expected_addr == addr and expected_type is None) \
                            or (expected_addr == addr and expected_type == response.msg_type):
                            timer.cancel()
                            self._responses.queue.remove(tup)
                            return response
        # Timeout, gg
        return None
        
    @staticmethod
    def _response_timer(timeout_signal: Event):
        timeout_signal.set()

    @staticmethod
    def _listen(peer: 'CTPPeer', stop_signal: Event, req_h: RequestHandler, res_q: Queue, resp_arrived: Event):
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
                        resp_arrived.clear()
                        res_q.put(msg_addr_tup)
                        resp_arrived.set()
                        
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
        - `peer_addr`: A tuple containing the IP address and the port number of the host to run the CTP service on.
        - `peer_id`: A 32-byte string representing the ID of the peer.
        - `cluster_id`: A 32-byte string representing the ID of the cluster.
        - `handler`: A subclass of `RequestHandler`, an abstraction to handle requests.
        """
        if not isinstance(cluster_id, str):
            raise TypeError("Invalid type for cluster_id: cluster_id is not a str.")
        if not isinstance(peer_id, str):
            raise TypeError("Invalid type for peer_id: peer_id is not a str.")
        if not isinstance(peer_addr, Tuple):
            if not isinstance(peer_addr[0], str) or not isinstance(peer_addr[1], int):
                raise TypeError("Invalid peer_addr: peer_addr should be a tuple of an IP address and a port.")
        cluster_id_b = cluster_id.encode(ENCODING)
        peer_id_b = peer_id.encode(ENCODING)
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

    def send_request(self, msg_type: CTPMessageType, data: bytes, dest_addr: AddressType, timeout: float=1.0, retries: int=0) -> CTPMessage:
        """
        Sends a request of type `msg_type` containing data `data` to `(dest_ip, dest_port)`. Returns the response received.
        - `msg_type`: The type of `CTPMessage` to be sent.
            - If `msg_type` is `NO_OP`, no response is expected, and this will return `None`.
            - Raises a `ValueError` if this is not a request.
        - `data`: The data in bytes. 
            - Raises a `ValueError` if this is larger than the maximum packet size.
        - `dest_addr`: A tuple, with the destination IP address and port.
            - Raises a `TypeError` if this is an invalid address.
        - `timeout`: Sets the number of seconds before timeout for *each request*.
        - `retries`: Sets the number of times to resend the request before raising a `CTPConnectionError`.

        If there was a timeout or an invalid response, a `CTPConnectionError` would be raised after `retries` reattempts.
        """
        if not isinstance(msg_type, CTPMessageType) or not msg_type.is_request():
            raise ValueError("Invalid msg_type: msg_type should be a CTPMessageType and a request.")
        if not isinstance(dest_addr, Tuple):
            if not isinstance(dest_addr[0], str) or not isinstance(dest_addr[1], int):
                raise TypeError("Invalid dest_addr: dest_addr should be a tuple of an IP address and a port.")

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
                response = None
                expected_response_type = None
                match message.msg_type:
                    case CTPMessageType.STATUS_REQUEST:
                        expected_response_type = CTPMessageType.STATUS_RESPONSE
                    case CTPMessageType.NOTIFICATION:
                        expected_response_type = CTPMessageType.NOTIFICATION_ACK
                    case CTPMessageType.BLOCK_REQUEST:
                        expected_response_type = CTPMessageType.BLOCK_RESPONSE
                if expected_response_type is None:
                    # Return none if msg_type doesn't match any, i.e. no response expected
                    return None
                
                response = self.listener.get_response(
                    expected_addr=dest_addr,
                    expected_type=expected_response_type,
                    block_time=timeout
                )
                if response is None:
                    # No response from get_response, message was a timeout.
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
                fail_reason = "Unknown error."
            raise CTPConnectionError(f"Failed to send message after attempts {attempts}, reason was: {fail_reason}")

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