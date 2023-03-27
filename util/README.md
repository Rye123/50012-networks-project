# util

Defines various utility functions and classes.

## `FileInfo`

### Info Files: `.crinfo`
Stores information about each file. The full info file name will be `{filename}.crinfo`, and it will be stored in the `/crinfo` subdirectory of the shared directory.

```
CRINFO {File Size} {Timestamp}<CRLF>
{File Hash}
```
- Note that the first line is in ASCII, and is separated from the second line with a single `CRLF`.


### Temp Files: `.crtemp`
Stores the temporary data of each file.

```
CRTEMP {Block Count}<CRLF>
{Block Pointers}<CRLF><CRLF>
```
- After the first line, the next few lines are the block pointers.
- Each block pointer is a 4-byte signed integer pointing to the first byte of the block data later in the file.
  - If the integer is `-1`, the block does not exist.

Header is ended with `\r\n\r\n`.