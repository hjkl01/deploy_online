import asyncio
import os
import signal

def shell_command(shell, command):
    return ["/bin/bash", "-lic", command] if shell == "bash" else ["/bin/zsh", "-lic", command]

def kill_process_group(proc):
    if not proc or proc.returncode is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass

async def git_sha(cwd):
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "rev-parse", "HEAD",
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await proc.communicate()
        return out.decode().strip() if proc.returncode == 0 else None
    except Exception:
        return None
