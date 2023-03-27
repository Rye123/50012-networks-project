from datetime import datetime
from hashlib import md5
from pathlib import Path

class FileInfo:
    """
    Defines the file information associated with a file.
    - Uniquely identified by the filehash.
    """

    def __init__(self, filehash: bytes, filename: str, filesize: int, last_updated: datetime=None):
        self.filehash = filehash
        self.filename = filename
        self.filesize = filesize
        self.last_updated = last_updated

    def __eq__(self, other: 'FileInfo') -> bool:
        """
        Returns true if both filehashes match.
        """
        return self.filehash == other.filehash

    def __repr__(self) -> str:
        return f"{self.filename}: {self.filehash} ({self.filesize} B)."
    
    @staticmethod
    def generate_fileInfo(filename: str, data: bytes) -> 'FileInfo':
        """
        Generates a `FileInfo` object from a given file in the form of bytes.
        """
        filehash = md5(data).digest()
        filesize = len(data)
        return FileInfo(filehash, filename, filesize)

    @staticmethod
    def generate_fileInfo_from_file(path: str) -> 'FileInfo':
        """
        Generates a `FileInfo` object from a given file at a path.
        """
        pathobj = Path(path)

        if not pathobj.is_file():
            raise ValueError("path provided not a file.")
        filename = pathobj.name
        fileinfo = None
        with pathobj.open('rb') as f:
            fileinfo = FileInfo.generate_fileInfo(
                filename=filename,
                data=f.read()
            )
        return fileinfo
    