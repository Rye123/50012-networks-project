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