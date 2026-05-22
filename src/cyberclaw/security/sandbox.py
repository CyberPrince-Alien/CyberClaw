"""Secure sandbox subsystem for executing subprocesses with resource controls and Docker wrapping."""

import asyncio
import os
import sys
import shutil
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Tuple

if TYPE_CHECKING:
    from cyberclaw.core.agent import AgentSession

logger = logging.getLogger(__name__)


def limit_process_memory_win32(pid: int, limit_bytes: int = 50 * 1024 * 1024):
    """Assign process to a Win32 Job Object configured with process memory limits."""
    import ctypes
    
    # Constants
    JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
    JobObjectExtendedLimitInformation = 9
    PROCESS_SET_QUOTA = 0x0100
    PROCESS_TERMINATE = 0x0001
    
    kernel32 = ctypes.windll.kernel32
    
    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_uint64),
            ("WriteOperationCount", ctypes.c_uint64),
            ("OtherOperationCount", ctypes.c_uint64),
            ("ReadTransferCount", ctypes.c_uint64),
            ("WriteTransferCount", ctypes.c_uint64),
            ("OtherTransferCount", ctypes.c_uint64),
        ]

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", ctypes.c_uint32),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", ctypes.c_uint32),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", ctypes.c_uint32),
            ("SchedulingClass", ctypes.c_uint32),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]
        
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError()
        
    limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_PROCESS_MEMORY
    limits.ProcessMemoryLimit = limit_bytes
    
    res = kernel32.SetInformationJobObject(
        job,
        JobObjectExtendedLimitInformation,
        ctypes.byref(limits),
        ctypes.sizeof(limits)
    )
    if not res:
        kernel32.CloseHandle(job)
        raise ctypes.WinError()
        
    handle = kernel32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, pid)
    if not handle:
        kernel32.CloseHandle(job)
        raise ctypes.WinError()
        
    try:
        assigned = kernel32.AssignProcessToJobObject(job, handle)
        if not assigned:
            raise ctypes.WinError()
    finally:
        kernel32.CloseHandle(handle)
        
    return job


async def run_in_docker(command: str, workspace_path: str) -> Tuple[int, str, str]:
    """Execute command within docker sandbox environment."""
    # Convert workspace_path to absolute style for mounting
    abs_workspace = str(Path(workspace_path).resolve())
    
    # Escape quotes for command execution inside shell
    escaped_command = command.replace('"', '\\"')
    
    docker_args = [
        "run", "--rm", "-i",
        "--network", "none",
        "-v", f"{abs_workspace}:/workspace",
        "-w", "/workspace",
        "python:3.11-slim",
        "sh", "-c", command
    ]
    
    logger.info(f"Routing command inside Docker: {command}")
    process = await asyncio.create_subprocess_exec(
        "docker", *docker_args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    return process.returncode, stdout.decode(errors="replace"), stderr.decode(errors="replace")


async def execute_command_in_sandbox(command: str, cwd: str, session: "AgentSession", shell_type: str = "bash") -> Tuple[int, str, str]:
    """Execute command inside sandbox environment or fall back to native execution with Job limits."""
    sandbox_mode = getattr(session.shared_context.config, "sandbox", "danger-full-access")
    workspace_dir = str(session.shared_context.config.workspace)
    
    # Git baseline snapshotting
    git_commit = None
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "rev-parse", "HEAD",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workspace_dir
        )
        stdout, _ = await proc.communicate()
        if proc.returncode == 0:
            git_commit = stdout.decode().strip()
    except Exception:
        pass

    returncode = 0
    stdout_str = ""
    stderr_str = ""

    # Docker Sandboxing Routing
    if sandbox_mode == "docker":
        try:
            returncode, stdout_str, stderr_str = await run_in_docker(command, workspace_dir)
        except Exception as e:
            logger.warning(f"Docker sandbox failed, falling back to local runner: {e}")
            sandbox_mode = "workspace-write"  # Fallback to local with Job Objects

    # Local / Win32 Job Object Execution
    if sandbox_mode != "docker":
        git_bash_path = None
        if sys.platform.startswith("win") and shell_type == "bash":
            path_which = shutil.which("bash")
            if path_which and ("Git" in path_which or "git" in path_which):
                git_bash_path = path_which
            else:
                typical_paths = [
                    Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Git" / "bin" / "bash.exe",
                    Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")) / "Git" / "bin" / "bash.exe",
                    Path.home() / "AppData" / "Local" / "Programs" / "Git" / "bin" / "bash.exe",
                    Path("C:\\Git\\bin\\bash.exe"),
                ]
                for p in typical_paths:
                    if p.exists():
                        git_bash_path = str(p)
                        break
                if not git_bash_path:
                    git_bash_path = path_which

        job = None
        try:
            if sys.platform.startswith("win"):
                if shell_type == "powershell":
                    process = await asyncio.create_subprocess_exec(
                        "powershell.exe",
                        "-NoProfile",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-Command",
                        command,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        cwd=cwd
                    )
                else:
                    if git_bash_path:
                        # Windows to POSIX path style translation for Git Bash
                        import re
                        posix_cmd = re.sub(r"([A-Za-z]):\\", r"/\1/", command)
                        posix_cmd = posix_cmd.replace("\\", "/")
                        process = await asyncio.create_subprocess_exec(
                            git_bash_path,
                            "-c",
                            posix_cmd,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                            cwd=cwd
                        )
                    else:
                        process = await asyncio.create_subprocess_shell(
                            command,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                            cwd=cwd
                        )
                
                # Apply Win32 Job Object clamps (50MB memory)
                try:
                    job = limit_process_memory_win32(process.pid, 50 * 1024 * 1024)
                except Exception as e:
                    logger.warning(f"Failed to apply Windows Job Object memory clamps: {e}")
            else:
                # Linux/macOS standard subprocess execution
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd
                )

            stdout, stderr = await process.communicate()
            returncode = process.returncode
            stdout_str = stdout.decode(errors="replace") if stdout else ""
            stderr_str = stderr.decode(errors="replace") if stderr else ""

        except Exception as e:
            returncode = -1
            stderr_str = f"Error during subprocess execution: {e}"
        finally:
            # Safely close job object handle if created
            if job:
                import ctypes
                ctypes.windll.kernel32.CloseHandle(job)

    # Git Baseline Rollback triggered on command failure (non-zero return code)
    if returncode != 0 and git_commit:
        logger.warning(f"Command execution failed with returncode {returncode}. Rolling back workspace modifications to: {git_commit}")
        try:
            rollback_proc = await asyncio.create_subprocess_exec(
                "git", "reset", "--hard", git_commit,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workspace_dir
            )
            await rollback_proc.communicate()
            
            # Clean untracked files
            clean_proc = await asyncio.create_subprocess_exec(
                "git", "clean", "-fd",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workspace_dir
            )
            await clean_proc.communicate()
            
            stderr_str += "\n[SYSTEM WARNING] Command failed. Workspace changes have been automatically rolled back to clean state."
        except Exception as re_err:
            logger.error(f"Failed workspace baseline rollback: {re_err}")

    return returncode, stdout_str, stderr_str
