# Cluster Transfer Protocol
An application-level protocol for handling block transfers. This should be done over TCP.

## CTP Message
### Header
- Message Type (2 byte)
  - `0`: `STATUS_REQUEST`
  - `1`: `STATUS_RESPONSE`
  - `2`: `MANIFEST_UPDATED`
  - `3`: `BLOCK_REQUEST`
  - `4`: `BLOCK_RESPONSE`
- Length of Body in bytes (4 bytes)

Total size of header: 9 bytes

### Body
Depends on message type:
- `STATUS_REQUEST`: Request a status update from the destination.
  - Cluster ID
  - Source IP, Port
- `STATUS_RESPONSE`: Respond to a status request.
  - Cluster ID
  - Source IP, Port
  - Status
    - `0`: Cannot service further requests
    - `1`: Alive
- `MANIFEST_UPDATED`: Inform the destination that the file manifest has been updated.
  - Cluster ID
  - Manifest Hash
- `BLOCK_REQUEST`: Request a given block from the destination.
  - Cluster ID
  - Source IP, Port
  - File ID
  - Block ID
- `BLOCK_RESPONSE`: Respond to a given block request
  - Cluster ID
  - Source IP, Port
  - File ID
  - Block ID
  - Block Data
