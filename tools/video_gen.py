"""Video generation service abstraction — agents call this interface, never raw APIs."""

from abc import ABC, abstractmethod
from http import HTTPStatus
from pathlib import Path

import dashscope
import requests
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from backend.config import VideoConfig


def _is_transient_error(exc: BaseException) -> bool:
    if isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
        return True
    if isinstance(exc, requests.exceptions.HTTPError) and exc.response is not None:
        return exc.response.status_code in {429, 502, 503, 504}
    return False


class VideoGenService(ABC):
    """Abstract interface for video generation."""

    @abstractmethod
    def generate(self, prompt: str, output_path: str) -> str:
        """Generate video from a text prompt and save to file.

        Args:
            prompt: Text description of the desired video.
            output_path: Path to save the video file.

        Returns:
            The path to the generated video file.
        """
        ...


class DashScopeVideoGenService(VideoGenService):
    """Concrete video generation service using Alibaba Cloud Model Studio Wan.

    Uses the ``dashscope`` Python SDK's VideoSynthesis for
    text-to-video generation via the Wan model (wan2.7-t2v). Video generation is
    asynchronous — this service submits the task and polls until complete.
    
    The service configures dashscope.base_http_api_url for workspace endpoints
    and passes api_key explicitly to each call.
    """

    def __init__(self, config: VideoConfig) -> None:
        self.config = config
        self._configured = bool(config.api_key)

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception(_is_transient_error),
    )
    def generate(self, prompt: str, output_path: str) -> str:
        if not self._configured:
            raise RuntimeError(
                "DashScopeVideoGenService has no API key configured — "
                "set VIDEO_API_KEY in .env or pass api_key to VideoConfig"
            )

        # Set the workspace endpoint URL from config or default
        dashscope.base_http_api_url = self.config.base_url or (
            "https://ws-pd7pxz3ci9h4zpr0.ap-southeast-1.maas.aliyuncs.com/api/v1"
        )

        response = dashscope.VideoSynthesis.async_call(
            api_key=self.config.api_key,
            model=self.config.model,
            prompt=prompt,
        )

        if response.status_code != HTTPStatus.OK:
            raise RuntimeError(
                f"Video synthesis async_call failed: status_code={response.status_code}, "
                f"code={response.code}, message={response.message}"
            )

        # Wait for task completion
        result = dashscope.VideoSynthesis.wait(task=response, api_key=self.config.api_key)

        if result.status_code != HTTPStatus.OK:
            raise RuntimeError(
                f"Video synthesis wait failed: status_code={result.status_code}, "
                f"code={result.code}, message={result.message}"
            )

        video_url = result.output.video_url

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        resp = requests.get(video_url)
        resp.raise_for_status()
        path.write_bytes(resp.content)
        return str(path)
