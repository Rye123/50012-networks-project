import logging
from ctp.ctp import CTPMessage, CTPMessageType, InvalidCTPMessageError
from ctp.ctp import PLACEHOLDER_CLUSTER_ID, PLACEHOLDER_SENDER_ID
from abc import ABC, abstractmethod
from threading import Thread, Event
from socket import socket, AF_INET, SOCK_STREAM
from uuid import uuid1, UUID
from typing import List, Type, Callable, Any

class ListenerThread(Thread):
    """
    Thread that sets up a listening socket for the given peer.
    #TODO: generalise?
    """
    def __init__(self, peer: 'CTPPeer', src_ip: str, src_port: int, max_requests: int):
        super().__init__()
        self.shut_down_check_interval = 1 # how often we check for shutdown
        self.peer = peer
        self.src_addr = (src_ip, src_port)
        self.max_requests = max_requests
        self.stop_event = Event()
    
    def run(self):
        self.peer._log("info", f"Listening on {self.src_addr} (Max Request: {self.max_requests}).")
        self.sock = socket(AF_INET, SOCK_STREAM)
        self.sock.bind(self.src_addr)
        self.sock.settimeout(self.shut_down_check_interval)
        self.sock.listen(self.max_requests)
        while not self.stop_event.is_set():
            try:
                conn_sock, conn_addr = self.sock.accept()
                self.peer._log("info", f"Received connection from ({conn_addr})")
                conn = Connection(conn_sock)
                client_msg = conn.recv_message()
                self.peer._handle_request(conn, client_msg)
            except ConnectionError:
                self.peer._log("info", f"Client disconnected.")
                conn.close() #TODO: test with random messages
                continue
            except TimeoutError:
                pass # check if shutdown signal passed
        self.sock.close()
    
    @staticmethod
    def stop_thread(thread: 'ListenerThread'):
        thread.stop_event.set()

class RequestHandler(ABC):
    """
    An abstract base class that abstracts away socket control for \
        handling a given `CTPMessage` and sending a response.

    This class has several abstract methods that should be \
        implemented, these provide functionality to handle given requests. We almost always want to respond to the request, since the client's default state is to wait for a response. 

    An example implementation is the `DefaultRequestHandler`.
    """
    def __init__(self, peer: 'CTPPeer', connection: 'Connection'):
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
            self.peer.id
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

class HandlerThread(Thread):
    """
    Thread that contains the state of a `RequestHandler`.
    - This allows us to handle a request with a `RequestHandler` in a separate thread.
    """
    def __init__(self, requestHandler: RequestHandler, request: CTPMessage):
        super().__init__()
        self.requestHandler = requestHandler
        self.request = request
        #TODO: use event?
    
    def run(self):
        self.requestHandler.handle(self.request)
    
    def join(self):
        self.requestHandler.cleanup()
        super().join()
        
class DefaultRequestHandler(RequestHandler):
    """
    The default request handler, that simply echos the given data.
    """
    def handle_status_request(self, request: CTPMessage):
        self.send_response(CTPMessageType.STATUS_RESPONSE, request.data)

    def handle_notification(self, request: CTPMessage):
        self.send_response(CTPMessageType.NOTIFICATION_ACK, request.data)
    
    def handle_block_request(self, request: CTPMessage):
        self.send_response(CTPMessageType.BLOCK_RESPONSE, request.data)
    
    def handle_unknown_request(self, request: CTPMessage):
        self.send_response(CTPMessageType.STATUS_RESPONSE, request.data)
    
    def cleanup(self):
        self.close()

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

        Ideally, you would want to handle this using the `.listen()` method, handling requests with a separate `RequestHandler`.
        - Raises a `ConnectionError` if the given message is invalid.
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
    def __init__(self, cluster_id:str = PLACEHOLDER_CLUSTER_ID, requestHandlerClass: Type[RequestHandler] = DefaultRequestHandler, max_connections: int = 5):
        if not isinstance(cluster_id, str):
            raise TypeError("Invalid type for cluster_id: cluster_id is not a str.")
        if len(cluster_id.encode('ascii')) != 32:
            raise ValueError(f"cluster_id of invalid length: {len(cluster_id)} != 32")
        
        if not issubclass(requestHandlerClass, RequestHandler):
            raise TypeError("Invalid type for handler: Expected a subclass of RequestHandler")
        
        self.id = uuid1().hex
        self._listen_thread:ListenerThread = None
        self.cluster_id = cluster_id
        self.requestHandlerClass:Type[RequestHandler] = requestHandlerClass
        self.requestHandlerThreads:List[HandlerThread] = []

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
            #TODO: handler for response?
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
        Listen on `(src_ip, src_port)`.
        """
        # Listen on another thread
        self._listen_thread = ListenerThread(self, src_ip, src_port, max_requests)
        self._listen_thread.start()

    def _handle_request(self, connection: Connection, request: CTPMessage):
        """
        Handles a given `request`.
        - Request handling code is handled by the `handler` attribute.
        """
        handler = self.requestHandlerClass(self, connection)
        handlerThread = HandlerThread(handler, request)
        self.requestHandlerThreads.append(handlerThread)
        handlerThread.start()
        
    def end(self):
        """
        End the connection.
        """
        self._log("info", "End request received.")
        for requestHandlerThread in self.requestHandlerThreads:
            if requestHandlerThread.is_alive():
                requestHandlerThread.join()
        ListenerThread.stop_thread(self._listen_thread)
        self._log("info", "End request completed.")