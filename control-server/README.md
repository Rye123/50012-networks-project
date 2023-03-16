# `control-server`

## API
### `GET /cluster/{cluster_id}`: 
Get a cluster.
- Authentication should be done at this stage.
- Returns a list of active peers:
  - Peer ID
  - Peer IP:port

### `PUT /cluster/{cluster_id}/`:
Join a cluster. In the request body:
- Peer ID
- IP Address
- Port

### `POST /cluster/`:
Create a new cluster.

### `POST /cluster/{cluster_id}/wellness_check`
Requests the server to update the peerlist regarding the given peer. The server will then conduct a `CTP STATUS_REQUEST` to the given peer.

In the request body:
- Peer ID

### `GET /cluster/{cluster_id}/manifestHash`
Returns the hash of the entire manifest.

### `GET /cluster/{cluster_id}/manifest`
Request the manifest from the server. 
Returns the given manifest data.

### `POST /cluster/{cluster_id}/manifest`
Sends an update to the manifest. Request body should contain the local manifest.
Returns the updated manifest hash.
- An update will only occur if a **new** file has been added.

### `GET/cluster/{cluster_id}/getFileCreator?fileId={fileId}`
Gets the IP address of the creator of the given file.
- Since the IP address can be changed, the server will return the *current* IP address of the file owner. If the owner is offline, the server returns an empty response.