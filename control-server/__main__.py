from server import *
import traceback

server = Server(('0.0.0.0', 6969), Path('./control-server/data'))
try:
    server.add_cluster("3f80e91dc65311ed93abeddb088b3faa")

    server.listen()
    while True:
        command = input()
        if command == "list":
            print(server.clusters.get("3f80e91dc65311ed93abeddb088b3faa").peermap)
except KeyboardInterrupt:
    print("Interrupt")
except Exception:
    print(traceback.format_exc())
finally:
    server.end()