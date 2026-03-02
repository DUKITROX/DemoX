import os
import subprocess
import sys
import logging

logger = logging.getLogger(__name__)

_processes: dict[str, list[subprocess.Popen]] = {}


def launch_researcher(room_id: str, website_url: str):
    """Launch the researcher agent as a subprocess for a specific room."""
    env = {**os.environ, "ROOM_ID": room_id, "WEBSITE_URL": website_url}
    proc = subprocess.Popen(
        [sys.executable, "-m", "researcher_agent.researcher"],
        cwd=os.path.join(os.path.dirname(__file__), ".."),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    _processes.setdefault(room_id, []).append(proc)
    logger.info(f"Launched researcher agent for room {room_id}, pid={proc.pid}")
    return proc


def launch_presenter(room_id: str, website_url: str):
    """
    The presenter agent runs as a LiveKit Agents worker.
    It auto-dispatches to rooms when participants join.
    This is a no-op if the worker is already running.
    For local dev, run: python -m presenter_agent.agent dev
    """
    logger.info(
        f"Presenter agent should join room {room_id} automatically "
        "(ensure the worker is running: python -m presenter_agent.agent dev)"
    )


def stop_agents(room_id: str):
    """Stop researcher processes for a room. Presenter stops when room closes."""
    procs = _processes.pop(room_id, [])
    for proc in procs:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
    logger.info(f"Stopped {len(procs)} agent(s) for room {room_id}")
