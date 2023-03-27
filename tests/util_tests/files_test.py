import unittest
from util.files import *

TEST_FILE_DIR_PATH = "./tests/util_tests/test_files"

def get_test_filepath(filename: str) -> str:
    return f"{TEST_FILE_DIR_PATH}/{filename}"

class TestFileInfo(unittest.TestCase):
    def test_same_data_files_give_same_hash(self):
        fileinfo1 = FileInfo.generate_fileInfo_from_file(get_test_filepath('test_same_data_1.txt'))
        fileinfo2 = FileInfo.generate_fileInfo_from_file(get_test_filepath('test_same_data_2.txt'))
        self.assertEqual(fileinfo1, fileinfo2)

    def test_data_file_name_read(self):
        filename = "test_same_data_1.txt"
        fileinfo1 = FileInfo.generate_fileInfo_from_file(get_test_filepath(filename))
        self.assertEqual(fileinfo1.filename, filename)
        
    def test_data_file_size_read(self):
        filename = "test_same_data_1.txt"
        full_path = get_test_filepath(filename)
        filesize = Path(full_path).stat().st_size
        fileinfo1 = FileInfo.generate_fileInfo_from_file(full_path)
        self.assertEqual(fileinfo1.filesize, filesize)
