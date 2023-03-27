"""
init_test.py:
Helper file to import py tests from directories in this directory.

To use with VSCode:
1. In the Testing tab, select Configure Python Tests
2. For the test framework, select `unittest`.
3. For the directory containing the tests, select `tests`.
4. For the pattern to identify test files, select `*_test.py`.
"""

### DEEP DARK MAGIC TO ALLOW FOR ABSOLUTE IMPORT
from pathlib import Path
import sys
path = str(Path(Path(__file__).parent.absolute()).parent.absolute())
sys.path.insert(0, path)
### END OF DEEP DARK MAGIC

from ctp_tests import *
from util_tests import *