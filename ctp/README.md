# Cluster Transfer Protocol
An application-level protocol for handling block transfers. This should be done over UDP.

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

### `CTPPeer(peer_addr: AddressType, cluster_id: str, peer_id: str, handler: Type[RequestHandler])`
A single peer using the CTP protocol. A single host could have multiple peers -- this is simply a class encapsulating the `send_request` and `listen` methods.
- `peer_addr`: A tuple containing the IP address and the port number of the host to run the CTP service on.
- `peer_id`: A 32-byte string representing the ID of the peer.
- `cluster_id`: A 32-byte string representing the ID of the cluster.
- `handler`: A subclass of `RequestHandler`, an abstraction to handle requests.

#### `send_request(msg_type: CTPMessageType, data: bytes, dest_addr: AddressType, timeout: float=3.0, retries: int=0)`
Sends a single `CTPMessage(msg_type, data)` to the destination `dest_addr`. Returns the corresponding response.
- `msg_type`: Should be a request. If it is not, a `ValueError` is thrown.
- If a response is not received, this method will **block** for `timeout` seconds every time it tries to send a request. The number of retransmissions is set by the `retries` parameter.
  - A `CTPConnectionError` is raised if no response was received after `retries + 1` requests are sent.

#### `listen(src_ip: str='', max_requests: int=1)`
A function that runs a thread that listens on `(src_ip, src_port)` for CTP connections.
- Upon receiving a request, it parses it, and constructs an appropriate response. This is handled by the `RequestHandler` subclass provided to the `CTPPeer` constructor.
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

#### `handle_no_op(request: CTPMessage)` (**Abstract Method**):
Handle a `NO_OP`. This should not send a response, as the sender would not expect one.

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
    
    def handle_no_op(self, request: CTPMessage):
        pass
    
    def handle_unknown_request(self, request: CTPMessage):
        self.send_response(CTPMessageType.STATUS_RESPONSE, request.data)
    
    def cleanup(self):
        self.close()
```

## CTP Message
The above API abstracts away the handling of socket sending and receiving of the message. For the most part, only processing of the data needs to be implemented for any code that uses `ctp`.

### Header
- **Message Type (1 byte)**:
  - The first bit determines if the message is a **request** (`0`) or a **response** (`1`).
  - Note that for `NO_OP`, no response is expected. This is intended to be a data-less packet used for liveness checks with the server. By convention, we leave the first bit as `0`.
  
| Message Type            | Bit Representation | Description                                                                                            |
| ----------------------- | ------------------ | ------------------------------------------------------------------------------------------------------ |
| `STATUS_REQUEST`        | `0000 0000`        | (No data)                                                                                              |
| `STATUS_RESPONSE`       | `0000 0001`        | Data in ASCII, `status: 0/1`                                                                           |
| `NOTIFICATION`          | `0000 0010`        | Data in ASCII.                                                                                         |
| `NOTIFICATION_ACK`      | `0000 0011`        | Data in ASCII.                                                                                         |
| `BLOCK_REQUEST`         | `0000 0100`        | Data packetised according to `util.files.Block`.                                                       |
| `BLOCK_RESPONSE`        | `0000 0101`        | Data packetised according to `util.files.Block`.                                                       |
| `CLUSTER_JOIN_REQUEST`  | `0000 0110`        | Peer requesting the server to join a client. No data expected.                                         |
| `CLUSTER_JOIN_RESPONSE` | `0000 0111`        | Response from the server in ASCII. A list of peers, separated by `\r\n`.                               |
| `MANIFEST_REQUEST`      | `0000 1000`        | Request for the manifest `CRINFO` file from the server.                                                |
| `MANIFEST_RESPONSE`     | `0000 1001`        | Response containing the manifest `CRINFO` file. This file contains a list of filenames in the cluster. |
| `CRINFO_REQUEST`        | `0000 1010`        | Request a specific file's `CRINFO`. Data in ASCII, `filename: ...`.                                    |
| `CRINFO_RESPONSE`       | `0000 1011`        | Response containing the file's `CRINFO`. Data in bytes.                                                |
| `INVALID_REQUEST`       | `1111 1101`        | Response regarding an invalid request (client-side error).                                             |
| `NO_OP`                 | `1111 1110`        | A request that expects no response. Error message will be in ASCII.                                    |
| `UNEXPECTED_REQ`        | `1111 1111`        | Response stating that a given request was unexpected or unsupported. Error message will be ASCII.      |

- **Cluster ID (32 bytes)**: A 32-byte value representing the ID of the cluster.
- **Sender ID (32 bytes)**: A 32-byte value representing the ID of the message sender.

Total header length is 65 bytes.
- To avoid fragmentation, we use a maximum packet size of **1400 bytes** -- that is, the data must hence be restricted to **1335 bytes**.

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
  ```
  {filehash}-{block id}
  ```
- `BLOCK_RESPONSE`: Respond to a given block request
  ```
  {filehash}-{block id}-{status}\r\n\r\n
  {block data (if any)}
  ```
