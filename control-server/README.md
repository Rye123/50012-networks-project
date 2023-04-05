# `control-server`

## File Manifest
A file `./manifest/.crmanifest`, stored in the working directory of the server (and each client).
- This is stored as a list of ASCII filenames, separated by `\r\n`.
- When a client requests for an update, it will first delete its local copy of the manifest `CRINFO` (`./manifest/crinfo/.crmanifest.crinfo`) and send a `MANIFEST_REQUEST` message for the updated manifest `CRINFO`.
  - Then, it will request the entire manifest file in a series of `BLOCK_REQUEST`s.
- Each file's `CRINFO` file will be stored on the server in `./crinfo`.
