# Cluster Transfer Protocol
An application-level protocol for handling block transfers. This should be done over TCP.

## CTP Message
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
- `MANIFEST_UPDATED`: Inform the destination that the file manifest has been updated.
  - Manifest Hash
- `BLOCK_REQUEST`: Request a given block from the destination.
  - File ID
  - Block ID
- `BLOCK_RESPONSE`: Respond to a given block request
  - File ID
  - Block ID
  - Block Data
