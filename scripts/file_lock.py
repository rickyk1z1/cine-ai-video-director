"""Process-wide exclusive file lock using only the host's Python standard library."""
from contextlib import contextmanager
import errno
import os
import time

if os.name=='nt':
    import msvcrt
else:
    import fcntl


@contextmanager
def exclusive_lock(path):
    if path.is_symlink():raise ValueError('锁文件不能是符号链接：'+str(path))
    flags=os.O_CREAT|os.O_RDWR|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_BINARY',0)
    fd=os.open(path,flags,0o600)
    try:
        if os.name=='nt':
            # locking() starts at the current offset and supports an empty file.
            # LK_LOCK stops after ten attempts; retry nonblocking contention so
            # long exports retain the same waiting semantics as Unix flock.
            while True:
                os.lseek(fd,0,os.SEEK_SET)
                try:
                    msvcrt.locking(fd,msvcrt.LK_NBLCK,1)
                    break
                except OSError as exc:
                    if exc.errno not in (errno.EACCES,errno.EAGAIN,errno.EDEADLK):raise
                    time.sleep(.05)
            try:yield
            finally:
                os.lseek(fd,0,os.SEEK_SET)
                msvcrt.locking(fd,msvcrt.LK_UNLCK,1)
        else:
            fcntl.flock(fd,fcntl.LOCK_EX)
            try:yield
            finally:fcntl.flock(fd,fcntl.LOCK_UN)
    finally:
        os.close(fd)
