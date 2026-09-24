"""Windows control-flow simulation and native process exclusion are distinct checks."""
import builtins
import errno
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import file_lock
import storyboard


class FileLockTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'shared.lock'

    def windows_module(self,backend):
        # Simulate imports without changing os.name globally (or pathlib's host).
        windows_os=types.SimpleNamespace(**{key:getattr(os,key) for key in dir(os)})
        windows_os.name='nt'
        sleeper=types.SimpleNamespace(sleep=Mock())
        real_import=builtins.__import__
        def imports(name,*args,**kwargs):
            if name=='os':return windows_os
            if name=='msvcrt':return backend
            if name=='time':return sleeper
            if name=='fcntl':raise AssertionError('Windows must not import fcntl')
            return real_import(name,*args,**kwargs)
        namespace={'__name__':'isolated_windows_file_lock'}
        with patch('builtins.__import__',side_effect=imports):
            exec(compile(Path(file_lock.__file__).read_text(),file_lock.__file__,'exec'),namespace)
        return namespace['exclusive_lock'],sleeper

    def test_windows_retries_contention_and_unlocks_same_byte_on_exception(self):
        events=[];failures=[errno.EACCES,errno.EAGAIN,errno.EDEADLK]
        def locking(fd,mode,length):
            events.append((fd,mode,length,os.lseek(fd,0,os.SEEK_CUR)))
            if mode==2 and failures:raise OSError(failures.pop(0),'occupied')
        backend=types.SimpleNamespace(LK_NBLCK=2,LK_UNLCK=0,locking=locking)
        exclusive,sleeper=self.windows_module(backend)
        with self.assertRaisesRegex(RuntimeError,'body failure'):
            with exclusive(self.path):
                os.lseek(events[-1][0],9,os.SEEK_SET)
                raise RuntimeError('body failure')
        self.assertEqual([event[1:] for event in events],[(2,1,0)]*4+[(0,1,0)])
        self.assertEqual(sleeper.sleep.call_count,3)
        with self.assertRaises(OSError):os.fstat(events[-1][0])
        self.assertEqual(self.path.read_bytes(),b'')

    def test_windows_permanent_error_is_not_retried_or_unlocked(self):
        backend=types.SimpleNamespace(LK_NBLCK=2,LK_UNLCK=0,locking=Mock(side_effect=OSError(errno.EBADF,'invalid descriptor')))
        exclusive,sleeper=self.windows_module(backend)
        with self.assertRaises(OSError):
            with exclusive(self.path):self.fail('must not enter without lock')
        self.assertEqual(backend.locking.call_count,1);sleeper.sleep.assert_not_called()
        with self.assertRaises(OSError):os.fstat(backend.locking.call_args.args[0])

    def test_lock_rejects_symlink_without_changing_target(self):
        target=self.path.parent/'target';target.write_bytes(b'keep')
        try:self.path.symlink_to(target)
        except OSError as exc:self.skipTest('Host does not permit creating a symlink: '+str(exc))
        with self.assertRaises(ValueError):
            with file_lock.exclusive_lock(self.path):self.fail('linked lock must be rejected')
        self.assertEqual(target.read_bytes(),b'keep')

    @unittest.skipUnless(os.name=='posix','Real Unix process test; not Windows evidence')
    def test_real_unix_process_waits_and_exception_releases_lock(self):
        code="from pathlib import Path; import sys;sys.path.insert(0,sys.argv[1]);from file_lock import exclusive_lock;print('started',flush=True)\nwith exclusive_lock(Path(sys.argv[2])):print('acquired',flush=True)"
        process=None
        try:
            with self.assertRaisesRegex(RuntimeError,'release'):
                with file_lock.exclusive_lock(self.path):
                    process=subprocess.Popen([sys.executable,'-c',code,str(storyboard.ROOT/'scripts'),str(self.path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                    self.assertEqual(process.stdout.readline().strip(),'started')
                    with self.assertRaises(subprocess.TimeoutExpired):process.wait(timeout=.15)
                    raise RuntimeError('release')
            stdout,stderr=process.communicate(timeout=5)
            self.assertEqual(process.returncode,0,stderr);self.assertEqual(stdout.strip(),'acquired')
        finally:
            if process is not None:
                if process.poll() is None:process.kill();process.wait(timeout=5)
                process.stdout.close();process.stderr.close()

    def test_service_spawn_uses_host_specific_detachment(self):
        with patch.object(storyboard.sys,'platform','win32'),patch.object(storyboard.subprocess,'DETACHED_PROCESS',8,create=True):
            self.assertEqual(storyboard.service_process_options(),{'creationflags':8})
        with patch.object(storyboard.sys,'platform','darwin'):
            self.assertEqual(storyboard.service_process_options(),{'start_new_session':True})


if __name__=='__main__':unittest.main()
