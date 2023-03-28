import unittest
from tempfile import TemporaryDirectory
from util.files import *
from time import sleep
from copy import deepcopy
from random import randint

TEST_FILE_DIR_PATH = "./tests/util_tests/test_files"


def copy_dir(src_dir: str, tgt_dir: str):
    for child in Path(src_dir).iterdir():
        if child.is_file():
            # Open and write
            copy_path = f"{tgt_dir}/{child.name}"
            with child.open('rb') as f:
                with Path(copy_path).open('wb') as f2:
                    f2.write(f.read())
        elif child.is_dir():
            copy_path = f"{tgt_dir}/{child.name}"
            # Make directory
            copy_dir_pathobj = Path(copy_path).mkdir(exist_ok=True)
            copy_dir(str(child), copy_path)

class TestFileInfo(unittest.TestCase):
    def setUp(self):
        self._test_dir = TemporaryDirectory()
        self.test_dir:str = self._test_dir.name

        # Load test files into test_dir
        copy_dir(TEST_FILE_DIR_PATH, self.test_dir)
    
    def get_test_filepath(self, filename: str) -> str:
        return f"{self.test_dir}/{filename}"

    def test_same_data_files_give_same_hash(self):
        fileinfo1 = FileInfo.from_file(self.get_test_filepath('test_same_data_1.txt'))
        fileinfo2 = FileInfo.from_file(self.get_test_filepath('test_same_data_2.txt'))
        self.assertEqual(fileinfo1, fileinfo2)

    def test_diff_data_files_give_same_hash(self):
        fileinfo1 = FileInfo.from_file(self.get_test_filepath('test_same_data_1.txt'))
        fileinfo2 = FileInfo.from_file(self.get_test_filepath('huge_text_file.txt'))
        self.assertNotEqual(fileinfo1, fileinfo2)
    
    def test_same_data_file_gives_same_data(self):
        fileinfo1 = FileInfo.from_file(self.get_test_filepath('test_same_data_1.txt'))
        self.assertEqual(fileinfo1, fileinfo1)
        self.assertTrue(fileinfo1.is_synced(fileinfo1))
        self.assertTrue(fileinfo1.strictly_equal(fileinfo1))
    
    def test_different_metadata_gives_different_result(self):
        fileinfo1 = FileInfo.from_file(self.get_test_filepath('test_same_data_1.txt'))
        sleep(0.5)
        fileinfo2 = FileInfo.from_file(self.get_test_filepath('test_same_data_1.txt'))
        self.assertFalse(fileinfo1.is_synced(fileinfo2))
        self.assertFalse(fileinfo1.strictly_equal(fileinfo2))

    def test_data_file_name_read(self):
        filename = "test_same_data_1.txt"
        fileinfo1 = FileInfo.from_file(self.get_test_filepath(filename))
        self.assertEqual(fileinfo1.filename, filename)
        
    def test_data_file_size_read(self):
        filename = "test_same_data_1.txt"
        full_path = self.get_test_filepath(filename)
        filesize = Path(full_path).stat().st_size
        fileinfo1 = FileInfo.from_file(full_path)
        self.assertEqual(fileinfo1.filesize, filesize)

    def test_crinfo_loading(self):
        fileinfo1 = FileInfo.from_file(self.get_test_filepath('huge_text_file.txt'))
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
        self.temp_files:List[File] = []

        # Load test files into test_dir
        copy_dir(TEST_FILE_DIR_PATH, self.test_dir)
        self.generate_test_temp_files()
    
    def get_test_filepath(self, filename: str) -> str:
        return f"{self.test_dir}/{filename}"

    def generate_test_temp_files(self):
        self.filename = "bee.txt"
        filename = "bee.txt"
        file = File.from_file(self.get_test_filepath(filename))

        # Temp file 1: Empty temp file
        temp_file_1 = File(file.fileinfo, self.test_dir)
        temp_file_1.__temp_type = "Empty Temp File"
        self.temp_files.append(temp_file_1)

        # Temp file 2: File with first block missing
        blocks_2 = deepcopy(file.blocks)
        blocks_2[0].data = b''
        blocks_2[0].downloaded = False
        temp_file_2 = File(file.fileinfo, self.test_dir)
        temp_file_2.__temp_type = "File with first block missing"
        temp_file_2.blocks = blocks_2
        self.temp_files.append(temp_file_2)

        # Temp file 3: File with last block missing
        blocks_3 = deepcopy(file.blocks)
        blocks_3[-1].data = b''
        blocks_3[-1].downloaded = False
        temp_file_3 = File(file.fileinfo, self.test_dir)
        temp_file_3.__temp_type = "File with last block missing"
        temp_file_3.blocks = blocks_3
        self.temp_files.append(temp_file_3)

        # Temp file 4: File with arbitrary block missing
        blocks_4 = deepcopy(file.blocks)
        chosen_index = randint(0, len(blocks_4)-1)
        blocks_4[chosen_index].data = b''
        blocks_4[chosen_index].downloaded = False
        temp_file_4 = File(file.fileinfo, self.test_dir)
        temp_file_4.__temp_type = "File with arbitrary block missing"
        temp_file_4.blocks = blocks_4
        self.temp_files.append(temp_file_4)

        # Temp file 5: File with random number of arbitrary blocks missing
        blocks_5 = deepcopy(file.blocks)
        number_of_missing_blocks = randint(1, len(blocks_5)-1)
        for i in range(number_of_missing_blocks):
            chosen_index = randint(0, len(blocks_5)-1)
            blocks_5[chosen_index].data = b''
            blocks_5[chosen_index].downloaded = False
        temp_file_5 = File(file.fileinfo, self.test_dir)
        temp_file_5.__temp_type = "File with random number of arbitrary blocks missing"
        temp_file_5.blocks = blocks_5
        self.temp_files.append(temp_file_5)

        for temp_file in self.temp_files:
            pathstr = temp_file.save_temp_file()

    def test_file_info_preserved_from_file(self):
        filename = 'huge_text_file.txt'
        file = File.from_file(self.get_test_filepath(filename))
        
        file_loc = file.save_file()
        fileinfo = FileInfo.from_crinfo(f"{self.test_dir}/crinfo/{filename}.crinfo")

        self.assertTrue(file.fileinfo.strictly_equal(fileinfo))

    def test_file_info_preserved_from_multiple_loads(self):
        filename = 'huge_text_file.txt'
        file = File.from_file(self.get_test_filepath(filename))
        file.save_file()
            
        file1 = File.from_file(f"{self.test_dir}/{filename}")
        file2 = File.from_file(f"{self.test_dir}/{filename}")
        file3 = File.from_file(f"{self.test_dir}/{filename}")

        self.assertTrue(file1.fileinfo.strictly_equal(file2.fileinfo))
        self.assertTrue(file1.fileinfo.strictly_equal(file3.fileinfo))

    def test_save_file_and_load(self):
        filename = 'huge_text_file.txt'
        file = File.from_file(self.get_test_filepath(filename))

        file.save_file()
        file2 = File.from_file(f"{self.test_dir}/{filename}")

        fileinfo1 = file.fileinfo
        fileinfo2 = file2.fileinfo
        self.assertEqual(fileinfo1.filename, fileinfo2.filename)
        self.assertEqual(fileinfo1.filehash, fileinfo2.filehash)
        self.assertEqual(fileinfo1.timestamp, fileinfo2.timestamp)
        self.assertEqual(fileinfo1.filesize, fileinfo2.filesize)
        self.assertEqual(fileinfo1.block_count, fileinfo2.block_count)
    
    def test_file_info_preserved_from_temp(self):
        for temp_file in self.temp_files:
            file = File.from_temp_file(self.get_test_filepath(f"{self.filename}.crtemp"))
            sleep(0.1)
            temp_file.save_temp_file()

            self.assertTrue(file.fileinfo.strictly_equal(temp_file.fileinfo), f"FileInfo does not match for {temp_file.__temp_type}")

    def test_save_temp_file_and_load(self):
        for temp_file in self.temp_files:
            file = File.from_temp_file(self.get_test_filepath(f"{self.filename}.crtemp"))

            # Verify blocks
            for b1, b2 in zip(temp_file.blocks, file.blocks):
                self.assertEqual(b1.block_id, b2.block_id, f"{b1.block_id} != {b2.block_id} for {temp_file.__temp_type}.")

    #TODO: tests for invalid temp files.
    
    def tearDown(self):
        self._test_dir.cleanup()


