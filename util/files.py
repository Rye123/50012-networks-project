from hashlib import md5
from pathlib import Path
from ctp import CTPMessage, CTPMessageType
from util import get_current_timestamp
from typing import List, Dict
from math import ceil
import logging

logger = logging.getLogger(__name__)

FILENAME_MAX_LENGTH = 255
BLOCK_HEADER_SIZE = 25
MAX_BLOCK_SIZE = CTPMessage.MAX_DATA_LENGTH - BLOCK_HEADER_SIZE

def write_file(path: Path, data: bytes):
    """
    Writes `data` to the file in `path`. This will create the file if it doesn't exist.
    - Note that if the directory containing the file doesn't exist, an error will be raised.
    - This function will OVERWRITE the file.
    """
    if not isinstance(path, Path):
        raise TypeError("path is not a pathlib.Path.")
    path.touch(exist_ok=True)
    with path.open('wb') as f:
        f.write(data)

class SharedDirectory:
    """
    A shared directory instance.
    - `dirpath`
    - `crinfo_dirpath`
    - `filemap`
    """
    CRINFO_DIRNAME = 'crinfo'

    def __init__(self, path: Path):
        """
        Initialise the shared directory.
        - `path`: A `Path` object with the path to the shared directory.
        """
        if not isinstance(path, Path):
            raise TypeError(f"path \"{path}\" is not a pathlib.Path.")
        
        self.dirpath = path
        self.crinfo_dirpath = path.joinpath(self.CRINFO_DIRNAME)
        self.filemap:Dict[str, File] = {}

        # Ensure the directory exists
        self.dirpath.mkdir(exist_ok=True)
        self.crinfo_dirpath.mkdir(exist_ok=True)
        
    def refresh(self):
        """
        Scans the local directory for new files.
        - Any new files without a corresponding FileInfo will be processed.
        - Any new FileInfos without a corresponding File will be processed.
        """

        # Scan shared directory
        loaded_crinfos:List[Path] = []
        for child in self.dirpath.iterdir():
            if child.is_dir():
                continue # ignore other directories

            file = None
            if child.suffix == f".{File.TEMP_FILE_EXT}":
                try:
                    # Add temp file
                    file = File.from_temp_file(child)
                    self.filemap[file.fileinfo.filename] = file
                    logger.debug(f"{self.dirpath}: Loaded temp file from {child}")
                except ValueError as e:
                    logger.warning(f"Error loading from {child}: {str(e)}")
                except FileError as e:
                    logger.warning(f"Error loading from {child}: Corresponding FileInfo not found.")
            else:
                try:
                    # Add actual file
                    file = File.from_file(child)
                    self.filemap[file.fileinfo.filename] = file
                    logger.debug(f"{self.dirpath}: Loaded file from {child}")
                except ValueError as e:
                    logger.warning(f"Error loading from {child}: {str(e)}")
            if file is None:
                continue

            loaded_crinfos.append(file.crinfo_filepath)
        
        # Scan CRINFO directory
        for child in self.crinfo_dirpath.iterdir():
            if child.is_dir() or child in loaded_crinfos:
                continue
            
            # Generate empty tempfile
            file = File.from_crinfo(child)
            self.filemap[file.fileinfo.filename] = file
            logger.debug(f"{self.dirpath}: Loaded empty file from {child}")

    def add_file(self, filename: str, data: bytes):
        """
        Adds a new file to this directory, writing it to disk.
        - This creates a corresponding FileInfo object.
        - If the file already exists, it will be deleted along with its FileInfo object.
        """
        filepath = self.dirpath.joinpath(filename)
        if filepath.is_file():
            self.delete_file(filename)

        with filepath.open('wb') as f:
            f.write(data)
        
        file = File.from_file(filepath)
        file.write_file()
        self.filemap[filename] = file

    def add_fileinfo(self, filename: str, data: bytes):
        """
        Adds a new FileInfo to this directory, writing it to disk.
        - This creates the corresponding File in the parent directory (i.e. empty tempfile)
        - `filename` should be the name of the actual file, not of the CRINFO file.
        """
        fileinfo = FileInfo._from_bytes(self, filename, data)
        fileinfo.write()
        file = File.from_crinfo(fileinfo.filepath)
        file.write_temp_file()
        self.filemap[filename] = file
    
    def delete_file(self, filename: str):
        """
        Deletes a file from this directory, and removing it from disk.
        - This removes the corresponding FileInfo.
        """
        self.filemap.pop(filename, None)
        filepath = self.dirpath.joinpath(filename)
        crinfopath = self.crinfo_dirpath.joinpath(f"{filename}.{FileInfo.CRINFO_EXT}")
        filepath.unlink(missing_ok=True)
        crinfopath.unlink(missing_ok=True)

class FileInfo:
    """
    Defines the file information associated with a file.
    - Uniquely identified by the filehash.
    """

    # (MD5 output size) + (filename max size) + (int size) + (float size (for UTC timestamp))
    FILEINFO_MAX_LENGTH = 16 + FILENAME_MAX_LENGTH + 4 + 8
    CRINFO_EXT = 'crinfo'

    def __init__(self, shareddir: SharedDirectory, filehash: bytes, filename: str, filesize: int, timestamp: float=None):
        if timestamp is None:
            timestamp = get_current_timestamp()
        self.shareddir = shareddir
        self.filepath = shareddir.crinfo_dirpath.joinpath(f"{filename}.{self.CRINFO_EXT}")
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
    
    def write(self):
        """
        Writes this `FileInfo` object to disk.
        """
        line_1 = f"CRINFO {self.filesize} {self.timestamp}"
        data = line_1.encode('ascii') + b'\r\n' + self.filehash

        write_file(self.filepath, data)
    
    @staticmethod
    def from_crinfo(path: Path) -> 'FileInfo':
        """
        Generates a `FileInfo` object from a path to a CRINFO file.
        """
        if not path.suffix == f".{FileInfo.CRINFO_EXT}":
            raise ValueError(f"from_crinfo: Invalid CRINFO file ({path} has an invalid extension)")
        
        if not path.is_file():
            raise FileNotFoundError(f"from_crinfo: Invalid CRINFO file ({path} is not a file):")

        with path.open('rb') as f:
            data = f.read()
            filename = path.name.removesuffix(f'.{FileInfo.CRINFO_EXT}')
            shareddir = SharedDirectory(path.parent.parent)
            return FileInfo._from_bytes(shareddir, filename, data)

    @staticmethod
    def _from_bytes(shareddir: SharedDirectory, filename: str, data: bytes) -> 'FileInfo':
        data_split = data.split(b'\r\n')
        if len(data_split) != 2:
            raise ValueError(f"from_crinfo: Invalid CRINFO data")
        
        l1_split = data_split[0].decode('ascii').split(' ')
        filehash = data_split[1]

        if len(l1_split) != 3:
            raise ValueError("from_crinfo: Invalid CRINFO data (Invalid first line)")
        
        filesig, filesize, timestamp = l1_split[0], int(l1_split[1]), float(l1_split[2])
        if filesig != "CRINFO":
            raise ValueError("from_crinfo: Invalid CRINFO file (Invalid file signature)")
        
        return FileInfo(shareddir, filehash, filename, filesize, timestamp)

    @staticmethod
    def from_file(path: Path) -> 'FileInfo':
        """
        Generates a `FileInfo` object from a given file at a path.
        - This is for generation of the object **from an actual file**, not from a CRINFO file.
        """
        if path.suffix == f".{FileInfo.CRINFO_EXT}":
            raise ValueError("path provided is a CRINFO file.")
        
        if path.suffix == f".{File.TEMP_FILE_EXT}":
            raise ValueError("path provided is a temporary file.")

        if not path.is_file():
            raise ValueError("path provided not a file.")
        filename = path.name
        fileinfo = None
        shared_dir = SharedDirectory(path.parent)
        with path.open('rb') as f:
            data = f.read()
            filehash = md5(data).digest()
            filesize = len(data)
            fileinfo = FileInfo(shared_dir, filehash, filename, filesize)
        return fileinfo

class Block:
    """
    Associated with a filehash and a block ID. 
    
    The filehash matches this block to the appropriate local FileInfo object, the block ID identifies the \
    index of the block in relation to the local file.

    Raises a `ValueError` if the arguments are invalid.
    """

    def __init__(self, filehash: bytes, block_id: int, data: bytes=b''):
        if not(isinstance(filehash, bytes) and len(filehash) == 16):
            raise ValueError("Invalid arguments for Block: Invalid filehash")
        if not isinstance(block_id, int):
            raise ValueError("Invalid arguments for Block: block_id should be an int")
        if not isinstance(data, bytes):
            raise ValueError("Invalid arguments for Block: data should be in bytes")
        self.filehash = filehash
        self.block_id = block_id
        self.downloaded = not (len(data) == 0)
        self.data = data

    def pack(self) -> bytes:
        """
        Packs the data into a packet that can then be encapsulated.

        Returns a bytestring:
        ```
        {filehash} {block ID}\r\n
        {data}
        ```

        Header will be 25 bytes:
        - 16 bytes from filehash
        - 4 bytes from block ID
        - Additional header space and double CRLF: 5 bytes
        """
        return self.filehash + b' ' + self.block_id.to_bytes(4, 'big') + b'\r\n\r\n' + self.data

    @staticmethod
    def unpack(packet: bytes) -> 'Block':
        """
        Unpacks the data from a deencapsulated bytestring.
        Returns `None` if the `packet` does not give a proper block.
        """
        try:
            header, data = packet.split(b'\r\n\r\n', 1)
            filehash = header[:16]
            block_id_b = header[17:]
            block_id = int.from_bytes(block_id_b, 'big')
            return Block(filehash, block_id, data)
        except ValueError:
            return None

    def __eq__(self, other: 'Block'):
        return (self.filehash == other.filehash) and \
            (self.block_id == other.block_id) and \
            (self.data == other.data) and \
            (self.downloaded == other.downloaded)

class FileError(Exception):
    """
    Documents an error related to a `File`.
    """

    def __init__(self, *args: object) -> None:
        super().__init__(*args)

class File:
    """
    Associated with a **local** file -- could be fully or partially downloaded.
    - `fileinfo`: `FileInfo` associated with the file. Uniquely identifies the file.
    - `path`: Path of the file.
    - `blocks`: List of blocks associated with the file.
    - `downloaded`: Whether or not this file is fully downloaded.
    - `shared_dir`: The directory that this file, along with its temp file version and fileinfo, should be stored in.
    - `data`: The existing data of the file.
    """
    TEMP_FILE_EXT = 'crtemp'

    def __init__(self, fileinfo: FileInfo):
        """
        Initialise an empty File object, associated with `fileinfo`.
        - Shared Directory of `File` is inherited from the `FileInfo` object.

        This shouldn't be called directly when loading local files.
        """
        self.fileinfo = fileinfo
        self.blocks:List[Block] = []
        self.shareddir = fileinfo.shareddir
        self.crinfo_filepath = fileinfo.filepath

        # Initialise blocks list
        for i in range(self.fileinfo.block_count):
            self.blocks.append(Block(self.fileinfo.filehash, i))
    
    @property
    def filepath(self) -> Path:
        """
        The path of this File on the disk.
        """
        shared_dir = self.shareddir.dirpath
        
        if self.downloaded:
            return shared_dir.joinpath(f"{self.fileinfo.filename}")
        else:
            return shared_dir.joinpath(f"{self.fileinfo.filename}.{self.TEMP_FILE_EXT}")

    @property
    def downloaded_blockcount(self) -> int:
        """
        The number of downloaded blocks
        """
        count = 0
        for block in self.blocks:
            if block.downloaded:
                count += 1
        return count

    @property
    def downloaded(self) -> bool:
        """
        True if this file has been fully downloaded.
        """
        for block in self.blocks:
            if not block.downloaded:
                return False
        return True

    @property
    def data(self) -> bytes:
        """
        The concatenation of data in all blocks.
        """
        return b''.join([block.data for block in self.blocks])

    def delete_local_copy(self):
        """
        Deletes a local copy of this file (temp or otherwise).
        Note: The `FileInfo` of this file will still exist!
        """
        filepath:Path = self.shareddir.dirpath.joinpath(self.fileinfo.filename)
        tempfilepath:Path = self.shareddir.dirpath.joinpath(self.fileinfo.filename + '.' + File.TEMP_FILE_EXT)
        
        filepath.unlink(missing_ok=True)
        tempfilepath.unlink(missing_ok=True)

    def write_file(self) -> Path:
        """
        Writes this file to disk.
        - This will automatically write the corresponding `FileInfo` to disk.
        - Raises a `FileError` if the file is not fully downloaded.
        - This will OVERWRITE any existing file of the same path.
        """

        if not self.downloaded:
            raise FileError("write_file Error: File not fully downloaded.")
        
        # Save the fileinfo
        fileinfo = self.fileinfo
        fileinfo.write()
        logger.debug(f"CRINFO for {self.fileinfo.filename} written to disk.")

        data = b''.join([block.data for block in self.blocks])
        write_file(self.filepath, data)
        logger.info(f"{self.fileinfo.filename} written to directory.")
        return self.filepath
    
    def write_temp_file(self) -> Path:
        """
        Write this TEMP file to disk. Returns the path of the saved temporary file.
        - This will automatically save the corresponding `FileInfo` in the shared folder of the file.
        - Raises a `FileError` if the file is fully downloaded.
        - This will OVERWRITE any existing file of the same path.

        Refer to `README.md` for the documentation of a temp file.
        """

        if self.downloaded:
            raise FileError("write_temp_file Error: File already fully downloaded.")

        # Save the fileinfo
        fileinfo = self.fileinfo
        fileinfo.write()
        logger.debug(f"CRINFO for {self.fileinfo.filename} written to disk.")

        block_pointers:List[bytes] = []
        data = b'' 
        for block in self.blocks:
            if not block.downloaded:
                block_pointers.append((-1).to_bytes(4, byteorder='big', signed=True))
            else:
                # len(data) gives the first byte of this block
                block_pointer = len(data).to_bytes(4, byteorder='big', signed=True)
                data += block.data
                block_pointers.append(block_pointer)
        
        header_line_1 = f"CRTEMP {self.fileinfo.block_count}".encode('ascii')
        header = header_line_1 + b'\r\n' + b'\r\n'.join(block_pointers)
        full_data = header + b'\r\n\r\n' + data

        write_file(self.filepath, full_data)
        logger.info(f"{self.fileinfo.filename}.{self.TEMP_FILE_EXT} written to directory.")
        return self.filepath

    def __repr__(self) -> str:
        return f"{self.fileinfo.filename}: {self.downloaded_blockcount}/{self.fileinfo.block_count} downloaded."
    
    @staticmethod
    def from_crinfo(path: Path) -> 'File':
        """
        Loads an empty tempfile from a FileInfo `path`.
        """
        fileinfo = FileInfo.from_crinfo(path)
        file = File(fileinfo)
        return file

    @staticmethod
    def from_file(path: Path) -> 'File':
        """
        Load a file from `path`. 
        - This will automatically load the FileInfo from the `crinfo` directory in the same directory, otherwise a new FileInfo \
            object is generated. (This is important, as the timestamp will change!)
        - A `ValueError` is raised if the given path is invalid.
        """

        if path.suffix == f".{File.TEMP_FILE_EXT}":
            raise ValueError("from_file: Invalid file (path is a temp file)")
        
        if not path.is_file():
            raise ValueError(f'from_file: Invalid file {path}.')
        
        # Get FileInfo header, if not create one.
        filedir = path.parent
        
        fileinfo_filepath = filedir.joinpath(SharedDirectory.CRINFO_DIRNAME).joinpath(f"{path.name}.{FileInfo.CRINFO_EXT}")
        fileinfo = None
        try:
            fileinfo = FileInfo.from_crinfo(fileinfo_filepath)
        except FileNotFoundError:
            fileinfo = FileInfo.from_file(path)

        file = File(fileinfo)

        # Populate blocks
        with path.open('rb') as f:
            for i in range(fileinfo.block_count):
                file.blocks[i].data = f.read(MAX_BLOCK_SIZE)
                file.blocks[i].downloaded = True
        
        return file

    @staticmethod
    def from_temp_file(path: Path) -> 'File':
        """
        Load a TEMP file from `path`. 
        - This will automatically load the FileInfo from the `crinfo` directory in the same directory, otherwise a `FileError` is \
            raised (Note the difference from `from_file()`.)
        - A `ValueError` is raised if the given path is invalid.

        Refer to `README.md` for the documentation of a temp file.
        """

        if path.suffix != f".{File.TEMP_FILE_EXT}":
            raise ValueError(f"from_temp_file: Invalid file ({path} is not a temp file)")
        
        if not path.is_file():
            raise ValueError(f'from_temp_file: Invalid file {path}.')
        
        # Get FileInfo header, if not create one.
        filedir = path.parent
        filename_orig = path.name.removesuffix(f".{File.TEMP_FILE_EXT}")
        
        fileinfo_filepath = filedir.joinpath(SharedDirectory.CRINFO_DIRNAME).joinpath(f"{filename_orig}.{FileInfo.CRINFO_EXT}")
        fileinfo = None
        try:
            fileinfo = FileInfo.from_crinfo(fileinfo_filepath)
        except FileNotFoundError:
            raise FileError("from_temp_file: Given temp file has no corresponding CRINFO file.")

        file = File(fileinfo)

        # Process file
        file_raw:bytes = b''
        with path.open('rb') as f:
            file_raw = f.read()
        
        file_raw_split = file_raw.split(b'\r\n\r\n', 1)
        header = file_raw_split[0].split(b'\r\n')
        data = file_raw_split[1]

        l1_split = header[0].decode('ascii').split(' ')
        if len(l1_split) != 2:
            raise FileError("from_file: Given temp file has invalid first line.")
        
        sig, block_count = l1_split[0], int(l1_split[1])
        if sig != "CRTEMP":
            raise FileError("from_file: Given temp file has invalid file signature.")
        if block_count != len(header)-1:
            raise FileError(f"from_file: Mismatch in block count {block_count} and number of block pointers {len(header)-1}")

        # Process block pointers
        block_data:List[bytes] = []
        for i in range(1, len(header)-1):
            first_bytepos = int.from_bytes(header[i], byteorder='big', signed=True)
            if first_bytepos == -1:
                block_data.append(b'')
            else:
                last_bytepos = int.from_bytes(header[i+1], byteorder='big', signed=True)
                if last_bytepos == -1:
                    block_data.append(data[first_bytepos:])
                else:
                    block_data.append(data[first_bytepos:last_bytepos]) 

        # Process final block
        first_bytepos = int.from_bytes(header[-1], byteorder='big', signed=True)
        if first_bytepos == -1:
            block_data.append(b'')
        else:
            block_data.append(data[first_bytepos:])

        # Set blocks
        for i in range(block_count):
            file.blocks[i].data = block_data[i]
            file.blocks[i].downloaded = not (block_data[i] == b'')
        
        return file