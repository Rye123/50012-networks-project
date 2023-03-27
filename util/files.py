from hashlib import md5
from pathlib import Path
from ctp import CTPMessage
from util import get_current_timestamp
from struct import pack, unpack
from typing import List
from math import ceil
import logging

FILENAME_MAX_LENGTH = 255
MAX_BLOCK_SIZE = CTPMessage.MAX_DATA_LENGTH
DEFAULT_SHARED_DIR = './shared'

def ensure_shared_folder(shared_dir: str):
    """
    Ensures the shared folder exists.
    If it doesn't it will be created.
    """
    pathobj = Path(shared_dir)
    pathobj2 = Path(f"{shared_dir}/{FileInfo.CRINFO_DIR_NAME}")
    pathobj.mkdir(exist_ok=True)
    pathobj2.mkdir(exist_ok=True)

def write_file(path: str, data: bytes):
    """
    Writes `data` to the file in `path`. This will create the file if it doesn't exist.
    - Note that if the directory containing the file doesn't exist, an error will be raised.
    - This function will OVERWRITE the file.
    """
    pathobj = Path(path)
    pathobj.touch(exist_ok=True)
    with pathobj.open('wb') as f:
        f.write(data)

class FileInfo:
    """
    Defines the file information associated with a file.
    - Uniquely identified by the filehash.
    """

    # (MD5 output size) + (filename max size) + (int size) + (float size (for UTC timestamp))
    FILEINFO_MAX_LENGTH = 16 + FILENAME_MAX_LENGTH + 4 + 8
    CRINFO_DIR_NAME = 'crinfo'
    CRINFO_EXT = 'crinfo'

    def __init__(self, filehash: bytes, filename: str, filesize: int, timestamp: float=None):
        if timestamp is None:
            timestamp = get_current_timestamp()
        self.filehash = filehash
        self.filename = filename
        self.filesize = filesize
        self.timestamp = timestamp
        self.block_count = ceil(filesize / MAX_BLOCK_SIZE)
    
    def is_synced(self, other: 'FileInfo') -> bool:
        """
        Returns true if this FileInfo and the other FileInfo have:
        - the same filehash
        - the same timestamp
        """
        return (self.filehash == other.filehash) and (self.timestamp == other.timestamp)

    def __eq__(self, other: 'FileInfo') -> bool:
        """
        Returns true if both filehashes match.
        """
        return self.filehash == other.filehash
    
    def strictly_equal(self, other: 'FileInfo') -> bool:
        return (self.filename == other.filename) and \
            (self.filehash == other.filehash) and \
            (self.timestamp == other.timestamp) and \
            (self.filesize == other.filesize) and \
            (self.block_count == other.block_count)

    def __repr__(self) -> str:
        return f"{self.filename}: {self.filehash} ({self.filesize} B)."
    
    def save_crinfo(self, shared_dir: str=DEFAULT_SHARED_DIR) -> str:
        """
        Saves this `FileInfo` object on disk as a `.crinfo` file.
        Returns the path to the saved CRINFO file.
        """
        ensure_shared_folder(shared_dir)
        filename = f"{shared_dir}/{self.CRINFO_DIR_NAME}/{self.filename}.{self.CRINFO_EXT}"
        line_1 = f"CRINFO {self.filesize} {self.timestamp}"
        data = line_1.encode('ascii') + b'\r\n' + self.filehash
        write_file(filename, data)
        return filename
    
    @staticmethod
    def from_crinfo(filename: str) -> 'FileInfo':
        """
        Generates a `FileInfo` object from a given CRINFO file name.
        """
        if not filename.endswith(f".{FileInfo.CRINFO_EXT}"):
            raise ValueError("from_crinfo: Invalid CRINFO file (Invalid extension)")
        pathobj = Path(filename)
        if not pathobj.is_file():
            raise FileNotFoundError("from_crinfo: Invalid CRINFO file (Not a file)")
        with pathobj.open('rb') as f:
            data_split = f.read().split(b'\r\n')
            if len(data_split) != 2:
                raise ValueError("from_crinfo: Invalid CRINFO file (Invalid file)")
            
            l1_split = data_split[0].decode('ascii').split(' ')
            filehash = data_split[1]

            if len(l1_split) != 3:
                raise ValueError("from_crinfo: Invalid CRINFO file (Invalid first line)")
            
            filesig, filesize, timestamp = l1_split[0], int(l1_split[1]), float(l1_split[2])
            if filesig != "CRINFO":
                raise ValueError("from_crinfo: Invalid CRINFO file (Invalid file signature)")
            
            return FileInfo(filehash, pathobj.name.removesuffix(f'.{FileInfo.CRINFO_EXT}'), filesize, timestamp)
        
    @staticmethod
    def from_data(filename: str, data: bytes) -> 'FileInfo':
        """
        Generates a `FileInfo` object from a given file in the form of bytes.
        """
        filehash = md5(data).digest()
        filesize = len(data)
        return FileInfo(filehash, filename, filesize)

    @staticmethod
    def from_file(path: str) -> 'FileInfo':
        """
        Generates a `FileInfo` object from a given file at a path.
        """
        pathobj = Path(path)

        if not pathobj.is_file():
            raise ValueError("path provided not a file.")
        filename = pathobj.name
        fileinfo = None
        with pathobj.open('rb') as f:
            fileinfo = FileInfo.from_data(
                filename=filename,
                data=f.read()
            )
        return fileinfo

class Block:
    """
    Associated with a filehash and a block ID. 
    
    The filehash matches this block to the appropriate local FileInfo object, the block ID identifies the \
    index of the block in relation to the local file.
    """

    def __init__(self, filehash: str, block_id: int, data: bytes=b''):
        self.filehash = filehash
        self.block_id = block_id
        self.downloaded = not (len(data) == 0)
        self.data = data

class FileError(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)

class File:
    """
    Associated with a **local** file -- could be fully or partially downloaded.
    - `fileinfo`: `FileInfo` associated with the file. Uniquely identifies the file.
    - `path`: Path of the file.
    - `blocks`
    """
    TEMP_FILE_EXT = 'crtemp'

    def __init__(self, fileinfo: FileInfo):
        """
        Initialise an empty File object, associated with `fileinfo`.

        This shouldn't be called directly when loading local files.
        """
        self.fileinfo = fileinfo
        self.blocks:List[Block] = []

        # Initialise blocks list
        for i in range(self.fileinfo.block_count):
            self.blocks.append(Block(self.fileinfo.filehash, i))

    @property
    def downloaded(self) -> bool:
        """
        True if this file has been fully downloaded.
        """
        for block in self.blocks:
            if not block.downloaded:
                return False
        return True

    def save_file(self, shared_dir: str=DEFAULT_SHARED_DIR):
        if not self.downloaded:
            raise FileError("save_file Error: File not fully downloaded.")
        
        # Save the fileinfo
        fileinfo = self.fileinfo
        crinfo_file = fileinfo.save_crinfo(shared_dir)
        logging.debug(f"CRINFO for {self.fileinfo.filename} saved as {crinfo_file}.")

        data = b''.join([block.data for block in self.blocks])
        path = f"{shared_dir}/{self.fileinfo.filename}"
        ensure_shared_folder(shared_dir)
        write_file(path, data)
        logging.info(f"{self.fileinfo.filename} written to directory.")
    
    @staticmethod
    def from_file(path: str) -> 'File':
        if path.endswith(File.TEMP_FILE_EXT):
            raise ValueError("from_file: Invalid file (path is a temp file)")
        
        pathobj = Path(path)
        if not pathobj.is_file():
            raise ValueError('from_file: Invalid file.')
        
        # Get FileInfo header, if not create one.
        filedir = pathobj.parent
        
        fileinfo_filename = f"{filedir}/{FileInfo.CRINFO_DIR_NAME}/{pathobj.name}.{FileInfo.CRINFO_EXT}"
        fileinfo = None
        try:
            fileinfo = FileInfo.from_crinfo(fileinfo_filename)
        except FileNotFoundError:
            fileinfo = FileInfo.from_file(path)

        file = File(fileinfo)

        # Populate blocks
        with pathobj.open('rb') as f:
            for i in range(fileinfo.block_count):
                file.blocks[i].data = f.read(MAX_BLOCK_SIZE)
                file.blocks[i].downloaded = True
        
        return file
