"""Linux MAC filesystem policy + default-deny seccomp; never silently degrades."""
import ctypes
import errno
import math
import os
from pathlib import Path
import platform
import sys
import sysconfig


class SandboxUnavailable(Exception):
    pass


# No networking, exec, process/thread creation, signalling another process, ptrace,
# process_vm_*, pidfd_*, io_uring, mount, bpf, capabilities, or namespace operations.
SYSCALLS = (
    'read write readv writev pread64 close close_range lseek fstat newfstatat stat lstat statx '
    'getdents64 readlink readlinkat access faccessat faccessat2 open openat '
    'mmap mprotect munmap mremap madvise brk '
    'rt_sigaction rt_sigprocmask rt_sigreturn sigaltstack '
    'futex futex_waitv sched_yield sched_getaffinity getcpu '
    'clock_gettime clock_getres gettimeofday time nanosleep clock_nanosleep '
    'getrandom uname sysinfo getpid getppid gettid getuid geteuid getgid getegid '
    'getcwd getrlimit restart_syscall exit exit_group'
).split()


def runtime_paths(library_path=None):
    # No /app as a whole, /tmp, /proc, /dev, /etc as a whole, HOME or writable mounts.
    paths = {Path(__file__).resolve().parent,
             Path(sysconfig.get_path('stdlib')).resolve(), Path(sysconfig.get_path('platstdlib')).resolve(),
             Path(sysconfig.get_path('purelib')).resolve(), Path(sysconfig.get_path('platlib')).resolve()}
    if library_path is not None: paths.add(Path(library_path).resolve(strict=True))
    for name in ('/lib', '/lib64', '/usr/lib', '/usr/local/lib', '/usr/share/fonts', '/etc/fonts'):
        path = Path(name)
        if path.is_dir(): paths.add(path.resolve())
    return sorted(paths)


def confine(memory_mb=512, timeout=30, library_path=None):
    if sys.platform != 'linux' or platform.machine() not in {'x86_64', 'aarch64'}:
        raise SandboxUnavailable()
    import resource
    # Loaded BEFORE the policy; no library-name search/subprocess after confinement.
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        seccomp = ctypes.CDLL('libseccomp.so.2', use_errno=True)
        paths = runtime_paths(library_path)
        cpu = max(1, math.ceil(min(timeout, 30)))
        for kind, limit in [(resource.RLIMIT_AS, min(memory_mb, 512) * 1024 * 1024),
                            (resource.RLIMIT_CPU, cpu), (resource.RLIMIT_CORE, 0),
                            (resource.RLIMIT_FSIZE, 0), (resource.RLIMIT_NOFILE, 32),
                            (resource.RLIMIT_NPROC, 1)]:
            resource.setrlimit(kind, (limit, limit))
        libc.syscall.restype = ctypes.c_long
        if libc.prctl(38, 1, 0, 0, 0) != 0 or libc.prctl(4, 0, 0, 0, 0) != 0:
            raise SandboxUnavailable()
        # Syscall numbers common to the two supported architectures. ABI 3 handles truncation.
        if libc.syscall(444, 0, 0, 1) < 3: raise SandboxUnavailable()

        class Ruleset(ctypes.Structure):
            _fields_ = [('handled_access_fs', ctypes.c_uint64)]

        class PathRule(ctypes.Structure):
            _pack_ = 1
            _fields_ = [('allowed_access', ctypes.c_uint64), ('parent_fd', ctypes.c_int32)]

        ruleset = Ruleset((1 << 15) - 1)
        descriptor = libc.syscall(444, ctypes.byref(ruleset), ctypes.sizeof(ruleset), 0)
        if descriptor < 0: raise SandboxUnavailable()
        try:
            for path in paths:
                parent = os.open(path, os.O_PATH | os.O_CLOEXEC)
                try:
                    rule = PathRule((1 << 2) | (1 << 3), parent)  # READ_FILE / READ_DIR only.
                    if libc.syscall(445, descriptor, 1, ctypes.byref(rule), 0) != 0:
                        raise SandboxUnavailable()
                finally: os.close(parent)
            if libc.syscall(446, descriptor, 0) != 0: raise SandboxUnavailable()
        finally: os.close(descriptor)

        seccomp.seccomp_init.argtypes = [ctypes.c_uint32]
        seccomp.seccomp_init.restype = ctypes.c_void_p
        seccomp.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
        seccomp.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
        seccomp.seccomp_load.argtypes = [ctypes.c_void_p]
        seccomp.seccomp_release.argtypes = [ctypes.c_void_p]
        context = seccomp.seccomp_init(0x00050000 | errno.EPERM)  # default ERRNO(EPERM)
        if not context: raise SandboxUnavailable()
        try:
            for name in SYSCALLS:
                number = seccomp.seccomp_syscall_resolve_name(name.encode('ascii'))
                if number >= 0 and seccomp.seccomp_rule_add(context, 0x7fff0000, number, 0) != 0:
                    raise SandboxUnavailable()
            if seccomp.seccomp_load(context) != 0: raise SandboxUnavailable()
        finally: seccomp.seccomp_release(context)
    except (OSError, ValueError, OverflowError, AttributeError):
        raise SandboxUnavailable() from None
