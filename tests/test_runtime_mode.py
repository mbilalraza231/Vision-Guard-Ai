import asyncio
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_ROOT = os.path.join(PROJECT_ROOT, "backend")

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.app.core import config as config_module
from backend.app.services import ecs_manager as ecs_manager_module
from backend.app.services import camera_manager as camera_manager_module


def _reset_singletons() -> None:
    config_module._settings = None
    ecs_manager_module._ecs_manager = None
    camera_manager_module._camera_manager = None


def test_default_runtime_mode_is_docker(monkeypatch):
    monkeypatch.delenv("VG_RUNTIME_MODE", raising=False)
    _reset_singletons()

    settings = config_module.get_settings()

    assert settings.runtime_mode == "docker"
    assert settings.is_docker_runtime is True
    assert settings.allow_local_process_control is False


def test_ecs_manager_blocks_local_lifecycle_in_docker_mode(monkeypatch):
    monkeypatch.setenv("VG_RUNTIME_MODE", "docker")
    _reset_singletons()

    manager = ecs_manager_module.get_ecs_manager()
    result = asyncio.run(manager.start())

    assert result["success"] is False
    assert "disabled in docker runtime mode" in result["message"].lower()


def test_camera_manager_blocks_local_lifecycle_in_docker_mode(monkeypatch):
    monkeypatch.setenv("VG_RUNTIME_MODE", "docker")
    _reset_singletons()

    manager = camera_manager_module.get_camera_manager()
    manager.register(
        camera_id="cam-test",
        rtsp_url="rtsp://localhost:8554/test",
        fps=5,
        motion_threshold=0.02,
    )

    start_result = asyncio.run(manager.start_camera("cam-test"))
    stop_result = asyncio.run(manager.stop_camera("cam-test"))

    assert start_result["success"] is False
    assert stop_result["success"] is False
    assert "disabled in docker runtime mode" in start_result["message"].lower()
    assert "disabled in docker runtime mode" in stop_result["message"].lower()
