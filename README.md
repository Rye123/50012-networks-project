# 50012-networks-project

This project works on Python 3.10. No other requirements should be necessary.

## Usage

The server must be initialised before any peer.
1. Initialise the server:
  ```bash
  py ./control-server/server.py
  ```
2. The server will be started on port 6969.

To initialise a peer:
1. The current list of peers that can be used are listed in `tests/client-tests/bootstrapped_peer_list.txt`, with each line representing:
  `<peer IP> <peer port> <peer ID> <peer directory>`.
2. To initialise a peer:
  ```bash
  py ./tests/client_tests/peer_test.py [line index of peer to initialise, starting from 0]
  ```
3. The peer will automatically create the required directories, and connect to your server on port 6969. Any additional peers will do the same, and the server will push out the new peerlists accordingly.
  - To disconnect a peer, either enter `EXIT` or perform a system interrupt.
  - The server will automatically remove that peer after 30 seconds.

To add a file to be shared:
1. Insert the file in `tests/client-tests/data/<peer index, starting from 1>_dir`. This is the directory listed in the bootstrapped peer list.
2. Enter `SHARE` into the relevant peer's console.
3. This will automatically share the file's metadata with the server. When ready, enter `SYNC` on the consoles of the other peers. This will cause those peers to request the file's metadata from the server, then the file from every other peer.
