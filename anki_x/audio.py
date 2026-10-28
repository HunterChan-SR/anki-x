"""Bundled cross-platform audio decoding and playback; no external player."""

import os
import threading
from pathlib import Path


class Playback:
    def __init__(self, filename):
        import miniaudio
        self.done = threading.Event()
        self.device = None
        self.stream = None
        self.source = None
        self._closed = False
        backends = [miniaudio.Backend.NULL] if os.environ.get("ANKI_X_AUDIO_BACKEND") == "null" else None
        try:
            self.source = miniaudio.stream_memory(Path(filename).read_bytes())
            self.stream = miniaudio.stream_with_callbacks(self.source, end_callback=self.done.set)
            next(self.stream)
            self.device = miniaudio.PlaybackDevice(backends=backends, app_name="anki-x")
            self.device.start(self.stream)
        except Exception:
            self.terminate()
            raise

    def poll(self):
        return 0 if self.done.is_set() else None

    def wait(self, timeout=None):
        if not self.done.wait(timeout):
            raise TimeoutError("音频播放尚未结束。")
        self.terminate()
        return 0

    def terminate(self):
        if not self._closed:
            self._closed = True
            if self.device:
                self.device.close()
            if self.stream:
                self.stream.close()
            if self.source:
                self.source.close()
            self.done.set()


def play(filename):
    from .api import AnkiError
    try:
        return Playback(filename)
    except Exception as exc:
        raise AnkiError("无法播放音频，请检查声音输出设备或换一张词卡。") from exc
