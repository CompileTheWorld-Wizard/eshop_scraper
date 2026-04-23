"""
Aggregated health checks for platform subsystems (scraping, remotion, pipelines).
Used by GET /health on the main app.
"""

from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.config import settings
from app.logging_config import get_logger
from app.middleware.remotion_proxy import remotion_proxy
from app.utils.mongodb_manager import mongodb_manager
from app.utils.vertex_utils import vertex_manager
from app.services.merging_service import merging_service
from app.services.background_generation_service import background_generation_service
from app.services.audio_generation_service import audio_generation_service

logger = get_logger(__name__)


def _check_ffmpeg() -> Tuple[bool, str]:
    try:
        r = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            timeout=5,
        )
        if r.returncode == 0:
            return True, ""
        return False, "ffmpeg returned non-zero exit code"
    except FileNotFoundError:
        return False, "ffmpeg not found on PATH"
    except Exception as e:
        return False, str(e)


def _check_opencv() -> Tuple[bool, str]:
    try:
        import cv2  # noqa: F401
        return True, ""
    except Exception as e:
        return False, f"OpenCV not available: {e}"


def _check_pillow() -> Tuple[bool, str]:
    try:
        from PIL import Image  # noqa: F401
        return True, ""
    except Exception as e:
        return False, f"Pillow not available: {e}"


@dataclass
class ServiceCheck:
    name: str
    healthy: bool
    detail: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "status": "healthy" if self.healthy else "unhealthy",
        }
        if self.detail:
            out["detail"] = self.detail
        out.update(self.extra)
        return out


def _check_scraping() -> ServiceCheck:
    try:
        ok = mongodb_manager.health_check()
        if ok:
            return ServiceCheck("scraping", True, "MongoDB reachable (task store)")
        return ServiceCheck("scraping", False, "MongoDB ping failed or client not connected")
    except Exception as e:
        return ServiceCheck("scraping", False, str(e))


async def _check_remotion() -> ServiceCheck:
    try:
        st = await remotion_proxy.health_check()
        if st.get("remotion_server") == "connected":
            return ServiceCheck(
                "remotion",
                True,
                "Remotion server reachable",
                {k: v for k, v in st.items() if k in ("remotion_server", "base_url")},
            )
        err = st.get("error") or "Remotion server unreachable"
        return ServiceCheck(
            "remotion",
            False,
            str(err),
            {k: v for k, v in st.items() if k in ("remotion_server", "base_url", "error")},
        )
    except Exception as e:
        return ServiceCheck("remotion", False, str(e))


def _check_scene2(ffmpeg_ok: bool, ffmpeg_err: str, opencv_ok: bool, opencv_err: str) -> ServiceCheck:
    parts: List[str] = []
    if not ffmpeg_ok:
        parts.append(f"ffmpeg: {ffmpeg_err or 'unavailable'}")
    if not opencv_ok:
        parts.append(f"opencv: {opencv_err or 'unavailable'}")
    if not parts:
        return ServiceCheck("scene2_generation", True, "FFmpeg and OpenCV available for Scene2")
    return ServiceCheck("scene2_generation", False, "; ".join(parts))


def _check_background_merge(
    supabase: Optional[Dict[str, Any]], pil_ok: bool, pil_err: str
) -> ServiceCheck:
    if not supabase or not supabase.get("success"):
        err = (supabase or {}).get("error") or "Supabase check not run or failed"
        return ServiceCheck("background_merge", False, str(err))
    if not pil_ok:
        return ServiceCheck("background_merge", False, pil_err)
    return ServiceCheck(
        "background_merge",
        True,
        "Supabase and Pillow OK (image compositing / uploads)",
    )


def _check_video_merge(
    supabase: Optional[Dict[str, Any]], ffmpeg_ok: bool, ffmpeg_err: str
) -> ServiceCheck:
    if not supabase or not supabase.get("success"):
        err = (supabase or {}).get("error") or "Supabase check not run or failed"
        return ServiceCheck("video_merge", False, str(err))
    if not ffmpeg_ok:
        return ServiceCheck("video_merge", False, f"ffmpeg: {ffmpeg_err or 'unavailable'}")
    return ServiceCheck(
        "video_merge",
        True,
        "Supabase and FFmpeg OK (final merge / concat pipeline)",
    )


def _check_background_generation() -> ServiceCheck:
    try:
        oai = background_generation_service.openai_client is not None
        vert = vertex_manager.is_available()
        if oai and vert:
            return ServiceCheck(
                "background_generation",
                True,
                "OpenAI and Vertex Imagen available",
            )
        reasons: List[str] = []
        if not oai:
            reasons.append("OpenAI client not initialized (check OPENAI_API_KEY)")
        if not vert:
            reasons.append(
                "Vertex AI not available (credentials / google-genai / key file)"
            )
        return ServiceCheck("background_generation", False, "; ".join(reasons))
    except Exception as e:
        return ServiceCheck("background_generation", False, str(e))


def _check_audio_generation() -> ServiceCheck:
    try:
        if not settings.ELEVENLABS_API_KEY:
            return ServiceCheck(
                "audio_generation",
                False,
                "ELEVENLABS_API_KEY not set",
            )
        if not audio_generation_service.elevenlabs_client:
            return ServiceCheck(
                "audio_generation",
                False,
                "ElevenLabs client failed to initialize",
            )
        return ServiceCheck(
            "audio_generation",
            True,
            "ElevenLabs client ready",
        )
    except Exception as e:
        return ServiceCheck("audio_generation", False, str(e))


async def collect_platform_health() -> Dict[str, Any]:
    """
    Run all service checks (mostly in parallel) and return a result dict
    and whether every check passed.
    """
    ffmpeg_ok, ffmpeg_err = _check_ffmpeg()
    opencv_ok, opencv_err = await asyncio.to_thread(_check_opencv)
    pil_ok, pil_err = await asyncio.to_thread(_check_pillow)

    scraping, remotion, supabase_test, background_gen, audio = await asyncio.gather(
        asyncio.to_thread(_check_scraping),
        _check_remotion(),
        asyncio.to_thread(merging_service.test_supabase_connection),
        asyncio.to_thread(_check_background_generation),
        asyncio.to_thread(_check_audio_generation),
    )

    scene2 = _check_scene2(ffmpeg_ok, ffmpeg_err, opencv_ok, opencv_err)
    background_merge = _check_background_merge(supabase_test, pil_ok, pil_err)
    video_merge = _check_video_merge(supabase_test, ffmpeg_ok, ffmpeg_err)

    services: Dict[str, Dict[str, Any]] = {
        scraping.name: scraping.as_dict(),
        remotion.name: remotion.as_dict(),
        scene2.name: scene2.as_dict(),
        background_merge.name: background_merge.as_dict(),
        background_gen.name: background_gen.as_dict(),
        audio.name: audio.as_dict(),
        video_merge.name: video_merge.as_dict(),
    }

    checks: List[ServiceCheck] = [
        scraping,
        remotion,
        scene2,
        background_merge,
        background_gen,
        audio,
        video_merge,
    ]
    all_ok = all(c.healthy for c in checks)
    failed = [c.name for c in checks if not c.healthy]

    out: Dict[str, Any] = {
        "ok": all_ok,
        "version": settings.VERSION,
        "failed_services": failed,
        "services": services,
    }
    if not all_ok:
        out["message"] = "Unhealthy services: " + ", ".join(failed)
    return out
