"""
InfraAuto v6 - Ollama HTTP API Client

Provides an HTTP client for the Ollama LLM server using only stdlib modules.
Supports vision-based image analysis, text generation, and structured JSON output
for construction estimation workflows.
"""

import base64
import json
import logging
import socket
import urllib.error
import urllib.request
from pathlib import Path
from typing import Union

from config import (
    OLLAMA_BASE_URL,
    OLLAMA_MAX_RETRIES,
    OLLAMA_TEXT_MODEL,
    OLLAMA_TIMEOUT,
    OLLAMA_VISION_MODEL,
)

logger = logging.getLogger(__name__)


class OllamaClient:
    """HTTP client for the Ollama local LLM server.

    Communicates with Ollama's REST API to perform image analysis,
    text generation, and structured JSON generation using locally
    hosted models. All methods are fault-tolerant and return safe
    defaults on failure.
    """

    def __init__(
        self,
        base_url: Union[str, None] = None,
        timeout: Union[int, float, None] = None,
    ) -> None:
        self.base_url = (base_url or OLLAMA_BASE_URL).rstrip("/")
        self.timeout = timeout if timeout is not None else OLLAMA_TIMEOUT
        self.max_retries = OLLAMA_MAX_RETRIES

    # ── Public API ──────────────────────────────────────────────────

    def is_available(self) -> bool:
        """Check whether the Ollama server is reachable.

        Sends a GET request to /api/tags. Returns True if the server
        responds with HTTP 200, False otherwise.
        """
        try:
            url = f"{self.base_url}/api/tags"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=min(self.timeout, 10)) as resp:
                return resp.status == 200
        except (
            urllib.error.URLError,
            socket.timeout,
            ConnectionRefusedError,
            ConnectionResetError,
            OSError,
        ):
            return False

    def list_models(self) -> list:
        """Return a list of installed model name strings.

        Queries GET /api/tags and extracts the 'name' field from each
        entry in the 'models' array.
        """
        try:
            url = f"{self.base_url}/api/tags"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            models = data.get("models", [])
            return [m["name"] for m in models if "name" in m]
        except (
            urllib.error.URLError,
            socket.timeout,
            ConnectionRefusedError,
            ConnectionResetError,
            OSError,
            json.JSONDecodeError,
            KeyError,
        ):
            logger.warning("Failed to list models from Ollama server.")
            return []

    def analyze_image(
        self,
        image_path: str,
        prompt: str,
        model: Union[str, None] = None,
    ) -> str:
        """Analyze an image using a vision-capable model.

        Reads the image file at *image_path*, base64-encodes it, and
        sends it alongside *prompt* to the Ollama /api/generate endpoint.
        Returns the model's response text, or an empty string on failure.
        """
        model = model or OLLAMA_VISION_MODEL

        image_b64 = self._encode_image(image_path)
        if not image_b64:
            return ""

        payload = {
            "model": model,
            "prompt": prompt,
            "images": [image_b64],
            "stream": False,
            "options": {
                "temperature": 0.1,
            },
        }

        return self._post_generate(payload)

    def generate_text(
        self,
        prompt: str,
        model: Union[str, None] = None,
    ) -> str:
        """Generate a text completion from a text-only prompt.

        Sends *prompt* to the Ollama /api/generate endpoint using the
        configured text model. Returns the response text, or an empty
        string on failure.
        """
        model = model or OLLAMA_TEXT_MODEL

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
            },
        }

        return self._post_generate(payload)

    def generate_json(
        self,
        prompt: str,
        model: Union[str, None] = None,
    ) -> dict:
        """Generate a structured JSON response from a prompt.

        Sends *prompt* with ``format='json'`` so the model is
        constrained to produce valid JSON. Parses and returns the
        result as a dict, or an empty dict on parse failure.
        """
        model = model or OLLAMA_TEXT_MODEL

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.1,
            },
        }

        raw = self._post_generate(payload)
        if not raw:
            return {}

        try:
            result = json.loads(raw)
            if isinstance(result, dict):
                return result
            logger.warning(
                "Ollama JSON response was not a dict (got %s). Wrapping.",
                type(result).__name__,
            )
            return {"result": result}
        except json.JSONDecodeError:
            logger.warning("Failed to parse Ollama response as JSON: %.200s", raw)
            return {}

    # ── Internal helpers ────────────────────────────────────────────

    def _encode_image(self, image_path: str) -> str:
        """Read an image file and return its base64-encoded contents.

        Returns an empty string if the file cannot be read.
        """
        path = Path(image_path)
        if not path.is_file():
            logger.error("Image file not found: %s", image_path)
            return ""

        try:
            image_bytes = path.read_bytes()
            if not image_bytes:
                logger.error("Image file is empty: %s", image_path)
                return ""
            return base64.b64encode(image_bytes).decode("ascii")
        except OSError as exc:
            logger.error("Failed to read image file %s: %s", image_path, exc)
            return ""

    def _post_generate(self, payload: dict) -> str:
        """Send a POST request to /api/generate and return the response text.

        Retries up to ``self.max_retries`` times on transient network
        errors. Returns an empty string on persistent failure.
        """
        url = f"{self.base_url}/api/generate"
        body = json.dumps(payload).encode("utf-8")

        last_exc = None
        for attempt in range(1, self.max_retries + 1):
            try:
                req = urllib.request.Request(
                    url,
                    data=body,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read().decode("utf-8")

                data = json.loads(raw)
                return data.get("response", "")

            except (socket.timeout, ConnectionResetError) as exc:
                last_exc = exc
                logger.warning(
                    "Ollama request attempt %d/%d timed out: %s",
                    attempt,
                    self.max_retries,
                    exc,
                )
                continue

            except urllib.error.HTTPError as exc:
                logger.error(
                    "Ollama HTTP error %d for model '%s': %s",
                    exc.code,
                    payload.get("model", "unknown"),
                    exc.reason,
                )
                return ""

            except urllib.error.URLError as exc:
                logger.error("Ollama server unreachable: %s", exc.reason)
                return ""

            except ConnectionRefusedError:
                logger.error(
                    "Ollama server refused connection at %s", self.base_url
                )
                return ""

            except json.JSONDecodeError as exc:
                logger.error("Failed to decode Ollama response JSON: %s", exc)
                return ""

            except OSError as exc:
                last_exc = exc
                logger.warning(
                    "Ollama request attempt %d/%d failed with OS error: %s",
                    attempt,
                    self.max_retries,
                    exc,
                )
                continue

        logger.error(
            "Ollama request failed after %d attempts. Last error: %s",
            self.max_retries,
            last_exc,
        )
        return ""
