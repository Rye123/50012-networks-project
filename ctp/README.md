# Cluster Transfer Protocol
An application-level protocol for handling block transfers. This should be done over TCP.

## Note
Due to Python's import rules (and my laziness to understand `setup.py`), to import this code, we need some deep dark magic to allow us to access the package.
```py
### DEEP DARK MAGIC TO ALLOW FOR ABSOLUTE IMPORT
from pathlib import Path
import sys
path = str(Path(Path(__file__).parent.absolute()).parent.absolute())
sys.path.insert(0, path)
### END OF DEEP DARK MAGIC

from ctp import ...
```

## API
The intent of the API is to abstract away socket handling and byte manipulation in favour of something like Python's HTTP server implementation. For our use case, the API needed to allow for peers to act both as server and client:
- Peers should be able to send a request.
- At the same time, peers should be able to listen for incoming requests and handle them. This handling is done with a subclass of the `RequestHandler` abstract base class.

### `CTPPeer(cluster_id: str, handler: Type[RequestHandler] max_connections: int = 5)`
A single peer using the CTP protocol. A single host could have multiple peers -- this is simply a class encapsulating the `send_request` and `listen` methods.
- `cluster_id`: A 32-byte string representing the ID of the cluster.
- `handler`: A subclass of `RequestHandler`, an abstraction to handle requests.

#### `send_request(msg_type: CTPMessageType, data: bytes, dest_ip: str, dest_port: int=6969)`
Sends a single `CTPMessage` to the destination. Returns the corresponding response.
- `msg_type` should be a request. If it is not, a `ValueError` is thrown.

#### `listen(src_ip: str='', max_requests: int=1)`
A function that runs a thread that listens on `(src_ip, src_port)` for CTP connections.
- Upon receiving a request, it parses it, and constructs an appropriate response.
- Note that this function is **not blocking**. An infinite loop in the main thread is necessary if you want to keep this running, otherwise the end of the main thread will cause problems.

### `RequestHandler`

An **abstract base class** that abstracts away socket control for handling a given `CTPMessage` and sending a response.

This class has several abstract methods that should be implemented, these provide functionality to handle given requests. We almost always want to respond to the request, since the client's default state is to wait for a response. 
- The `RequestHandler` always has access to the peer handling the request (i.e. the *server*, in client-server architecture), through the `peer` attribute.

An example implementation is the `DefaultRequestHandler`.

#### `close()`:
Ends the connection.

#### `send_response(msg_type: CTPMessageType, data: bytes)`: 
Sends a response.
- `msg_type`: A `CTPMessageType`. Should be a response, otherwise a `ValueError` is thrown.
- `data`: The data to be encapsulated in the message.

#### `cleanup()` (**Abstract Method**): 
Defines the action to be done after the request has been handled.
Most of the time, we want to end the interaction with a `close()` call.

#### `handle_status_request(request: CTPMessage)`  (**Abstract Method**): 
Handle a `STATUS_REQUEST`.

#### `handle_notification(request: CTPMessage)`  (**Abstract Method**)
Handle a `NOTIFICATION`.

#### `handle_block_request(request: CTPMessage)`  (**Abstract Method**): 
Handle a `BLOCK_REQUEST`.

#### `handle_unknown_request(request: CTPMessage)`  (**Abstract Method**): 
Handle an unknown message. This will be reached should a new request type be defined.

#### Example Implementation (`DefaultRequestHandler`)

```py
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
```

## CTP Message
The above API abstracts away the handling of socket sending and receiving of the message. For the most part, only processing of the data needs to be implemented for any code that uses `ctp`.

### Header
- Message Type (2 bytes):
  - The first bit determines if the message is a **request** (`0`) or a **response** (`1`).
  
| Message Type       | Bit Representation |
| ------------------ | ------------------ |
| `STATUS_REQUEST`   | `0000 0000`        |
| `STATUS_RESPONSE`  | `0000 0001`        |
| `NOTIFICATION`     | `0000 0010`        |
| `NOTIFICATION_ACK` | `0000 0011`        |
| `BLOCK_REQUEST`    | `0000 0100`        |
| `BLOCK_RESPONSE`   | `0000 0101`        |

- Data Length (4 bytes): An unsigned integer representing the length of the message body.
- Cluster ID (32 bytes): A 32-byte value representing the ID of the cluster.
- Sender ID (32 bytes): A 32-byte value representing the ID of the message sender.

Total header length is 70.

### Data
Depends on message type:
- `STATUS_REQUEST`: Request a status update from the destination.
- `STATUS_RESPONSE`: Respond to a status request.
  - Status
    - `0`: Cannot service further requests
    - `1`: Alive
- `NOTIFICATION`: Inform the destination of something
  - Message
- `NOTIFICATION_ACK`: Acknowledge a notification
- `BLOCK_REQUEST`: Request a given block from the destination.
  - File ID
  - Block ID
- `BLOCK_RESPONSE`: Respond to a given block request
  - File ID
  - Block ID
  - Block Data
