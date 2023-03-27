import unittest
from tempfile import TemporaryDirectory
from util.files import *
from time import sleep
from copy import deepcopy
from random import randint

TEST_FILE_DIR_PATH = "./tests/util_tests/test_files"

def get_test_filepath(filename: str) -> str:
    return f"{TEST_FILE_DIR_PATH}/{filename}"

class TestFileInfo(unittest.TestCase):
    def setUp(self):
        self._test_dir = TemporaryDirectory()
        self.test_dir:str = self._test_dir.name

    def test_same_data_files_give_same_hash(self):
        fileinfo1 = FileInfo.from_file(get_test_filepath('test_same_data_1.txt'))
        fileinfo2 = FileInfo.from_file(get_test_filepath('test_same_data_2.txt'))
        self.assertEqual(fileinfo1, fileinfo2)

    def test_diff_data_files_give_same_hash(self):
        fileinfo1 = FileInfo.from_file(get_test_filepath('test_same_data_1.txt'))
        fileinfo2 = FileInfo.from_file(get_test_filepath('huge_text_file.txt'))
        self.assertNotEqual(fileinfo1, fileinfo2)
    
    def test_same_data_file_gives_same_data(self):
        fileinfo1 = FileInfo.from_file(get_test_filepath('test_same_data_1.txt'))
        self.assertEqual(fileinfo1, fileinfo1)
        self.assertTrue(fileinfo1.is_synced(fileinfo1))
        self.assertTrue(fileinfo1.strictly_equal(fileinfo1))
    
    def test_different_metadata_gives_different_result(self):
        fileinfo1 = FileInfo.from_file(get_test_filepath('test_same_data_1.txt'))
        sleep(0.5)
        fileinfo2 = FileInfo.from_file(get_test_filepath('test_same_data_1.txt'))
        self.assertFalse(fileinfo1.is_synced(fileinfo2))
        self.assertFalse(fileinfo1.strictly_equal(fileinfo2))

    def test_data_file_name_read(self):
        filename = "test_same_data_1.txt"
        fileinfo1 = FileInfo.from_file(get_test_filepath(filename))
        self.assertEqual(fileinfo1.filename, filename)
        
    def test_data_file_size_read(self):
        filename = "test_same_data_1.txt"
        full_path = get_test_filepath(filename)
        filesize = Path(full_path).stat().st_size
        fileinfo1 = FileInfo.from_file(full_path)
        self.assertEqual(fileinfo1.filesize, filesize)

    def test_crinfo_loading(self):
        fileinfo1 = FileInfo.from_file(get_test_filepath('huge_text_file.txt'))
        fileinfo1.save_crinfo(self.test_dir)
        fileinfo2 = FileInfo.from_crinfo(f"{self.test_dir}/crinfo/huge_text_file.txt.crinfo")

        self.assertEqual(fileinfo1.filename, fileinfo2.filename)
        self.assertEqual(fileinfo1.filehash, fileinfo2.filehash)
        self.assertEqual(fileinfo1.timestamp, fileinfo2.timestamp)
        self.assertEqual(fileinfo1.filesize, fileinfo2.filesize)
        self.assertEqual(fileinfo1.block_count, fileinfo2.block_count)

    def tearDown(self):
        self._test_dir.cleanup()

class TestFile(unittest.TestCase):
    def setUp(self):
        self._test_dir = TemporaryDirectory()
        self.test_dir:str = self._test_dir.name


    def test_file_info_preserved_from_file(self):
        filename = 'huge_text_file.txt'
        file = File.from_file(get_test_filepath(filename))
        
        file_loc = file.save_file(self.test_dir)
        fileinfo = FileInfo.from_crinfo(f"{self.test_dir}/crinfo/{filename}.crinfo")

        self.assertTrue(file.fileinfo.strictly_equal(fileinfo))

    def test_file_info_preserved_from_multiple_loads(self):
        filename = 'huge_text_file.txt'
        file = File.from_file(get_test_filepath(filename))
        file.save_file(self.test_dir)
            
        file1 = File.from_file(f"{self.test_dir}/{filename}")
        file2 = File.from_file(f"{self.test_dir}/{filename}")
        file3 = File.from_file(f"{self.test_dir}/{filename}")

        self.assertTrue(file1.fileinfo.strictly_equal(file2.fileinfo))
        self.assertTrue(file1.fileinfo.strictly_equal(file3.fileinfo))

    def test_save_file_and_load(self):
        filename = 'huge_text_file.txt'
        file = File.from_file(get_test_filepath(filename))

        file.save_file(self.test_dir)
        file2 = File.from_file(f"{self.test_dir}/{filename}")

        fileinfo1 = file.fileinfo
        fileinfo2 = file2.fileinfo
        self.assertEqual(fileinfo1.filename, fileinfo2.filename)
        self.assertEqual(fileinfo1.filehash, fileinfo2.filehash)
        self.assertEqual(fileinfo1.timestamp, fileinfo2.timestamp)
        self.assertEqual(fileinfo1.filesize, fileinfo2.filesize)
        self.assertEqual(fileinfo1.block_count, fileinfo2.block_count)
    
    def tearDown(self):
        self._test_dir.cleanup()


