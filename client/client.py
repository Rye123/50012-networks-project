from ctp import ctp
from typing import List
import requests # for HTTP interaction with the server

class File:
    """
    TODO: Determine file components
    """
    class FileInfo:
        pass
    pass

class Peer:
    def __init__(self, id: str):
        """
        #TODO
        """
        self.id = id
        self.file_manifest:List[File.FileInfo] = []
        self.peer_list:List[Peer] = []
    
    def share(self, cluster, file: File):
        """
        Shares `file` with the given `cluster`. 
        This should call the lower level CTP functions.
        """
        pass

    def listen(self, cluster):
        """
        Listen to changes on the given cluster.
        This should call the lower level CTP functions.
        """
        pass

    def _update(self):
        """
        Update changes based on a new manifest.
        """
        pass
    
    def _report(self, peer):
        """
        Report the given peer for inactivity to the server.
        """
        pass