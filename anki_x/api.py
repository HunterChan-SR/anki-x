"""AnkiConnect v1 transport. Never retry a mutation after a lost response."""

import itertools
import json
import os
import time
import urllib.error
import urllib.request


class AnkiError(Exception):
    def __init__(self, message, code=None, data=None):
        super().__init__(message)
        self.code = code
        self.data = data


class ConnectionError(AnkiError):
    pass


class PendingOperation(AnkiError):
    def __init__(self, handle, state="running"):
        self.handle = handle
        self.state = state
        super().__init__("Anki 仍在处理；请稍后继续检查，勿重复评分。")


class Client:
    def __init__(self, endpoint=None, key=None, timeout=15, operation_timeout=30,
                 journal=None):
        self.endpoint = (endpoint or os.environ.get("ANKI_CONNECT_URL", "http://127.0.0.1:8765")).rstrip("/")
        if not self.endpoint.endswith("/api/v1"):
            self.endpoint += "/api/v1"
        self.key = key or os.environ.get("ANKI_API_KEY")
        self.timeout = timeout
        self.operation_timeout = operation_timeout
        self.ids = itertools.count(1)
        self.session = None
        self.journal = journal
        # Local requests should not be redirected through a corporate HTTP proxy.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def call(self, method, **params):
        request_id = next(self.ids)
        body = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        headers = {"Content-Type": "application/json"}
        if self.key:
            headers["Authorization"] = "Bearer " + self.key
        request = urllib.request.Request(self.endpoint, json.dumps(body).encode("utf-8"),
                                         headers=headers, method="POST")
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                reply = json.load(response)
        except urllib.error.HTTPError as exc:
            raise ConnectionError("AnkiConnect HTTP %s；请检查插件版本和 API key。" % exc.code) from exc
        except (OSError, ValueError, urllib.error.URLError) as exc:
            raise ConnectionError("无法取得 Anki 响应。请保持 Anki 打开；本次请求不会自动重发。") from exc
        if not isinstance(reply, dict) or reply.get("id") != request_id or reply.get("jsonrpc") != "2.0":
            raise AnkiError("AnkiConnect 响应格式不符；需要支持 API v1 的官方新版插件。")
        if "error" in reply:
            error = reply["error"]
            raise AnkiError(error.get("message", str(error)), error.get("code"), error.get("data"))
        if "result" not in reply:
            raise AnkiError("AnkiConnect 响应缺少 result。")
        return reply["result"]

    def connect(self):
        collection = self.call("collection.get")
        self.session = collection["session"]
        return collection

    def col(self, method, **params):
        if self.session is None:
            self.connect()
        return self.call(method, session=self.session, **params)

    def deck_counts(self, deck):
        try:
            return self.col("decks.getCounts", deck=deck)
        except AnkiError as exc:
            if not isinstance(exc.data, dict) or exc.data.get("type") != "notFound":
                raise
            # Anki omits an empty Default deck from its due tree when another
            # deck is present. Verify emptiness instead of hiding other errors.
            record = self.col("decks.get", deck=deck)
            name = record["name"].replace("\\", "\\\\").replace('"', '\\"')
            found = self.col("cards.search", query='deck:"' + name + '"', limit=1)
            if found["ids"]:
                raise exc
            return {"deckId": record["id"], "new": 0, "learning": 0, "review": 0, "total": 0}

    def _save_pending(self, value):
        if self.journal is None:
            return
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.journal.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(self.journal)

    def _clear_pending(self):
        if self.journal is not None:
            self.journal.unlink(missing_ok=True)

    def complete(self, result, progress=None):
        if not isinstance(result, dict) or "operationId" not in result:
            return result
        deadline = time.monotonic() + self.operation_timeout
        delay = 0.1
        while True:
            operation = self.call("operations.get", operationId=result["operationId"])
            state = operation["state"]
            if progress:
                progress(state)
            if state == "succeeded":
                self._clear_pending()
                return operation["result"]
            if state in ("failed", "cancelled"):
                self._clear_pending()
                error = operation.get("error", {})
                raise AnkiError(error.get("message", "Anki 操作未完成"), error.get("code"), error.get("data"))
            if time.monotonic() >= deadline:
                raise PendingOperation(result, state)
            time.sleep(delay)
            delay = min(delay * 1.4, 0.5)

    def change(self, method, progress=None, **params):
        """Journal intent before sending, so a lost response never looks successful."""
        if self.journal is not None and self.journal.exists():
            raise AnkiError("上次操作结果尚未确认。请先运行 anki-x recover。")
        record = {"endpoint": self.endpoint, "method": method, "session": self.session,
                  "state": "sending", "params": params}
        self._save_pending(record)
        try:
            result = self.col(method, **params)
        except ConnectionError:
            # The server might have committed it. Keep the intent; never resend.
            raise
        except AnkiError:
            self._clear_pending()
            raise
        if isinstance(result, dict) and "operationId" in result:
            self._save_pending(dict(record, state="accepted", handle=result))
            return self.complete(result, progress)
        self._clear_pending()
        return result

    def recover(self, progress=None):
        if self.journal is None or not self.journal.exists():
            return None
        record = json.loads(self.journal.read_text(encoding="utf-8"))
        if record["endpoint"] != self.endpoint:
            raise AnkiError("未确认的操作来自另一个 Anki 服务，请使用原来的 --url。")
        if "handle" in record:
            return self.complete(record["handle"], progress)
        raise AnkiError("上次请求中断，未拿到操作编号。请在 Anki 中核对实际结果，再运行 anki-x recover --acknowledge；不会重新提交。")
