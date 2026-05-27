from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import Message


class ContentSizeLimitMiddleware:
    def __init__(self, app, max_body_bytes: int = 1 * 1024 * 1024):
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)

        content_length = request.headers.get("content-length")

        # ---- Header check (fast fail) ----
        if content_length is not None:
            try:
                if int(content_length) > self.max_body_bytes:
                    response = JSONResponse(
                        status_code=413,
                        content={
                            "status": "error",
                            "message": "Request body too large",
                        },
                    )
                    await response(scope, receive, send)
                    return
            except ValueError:
                response = JSONResponse(
                    status_code=400,
                    content={
                        "status": "error",
                        "message": "Invalid Content-Length header",
                    },
                )
                await response(scope, receive, send)
                return

        # ---- Streaming protection ----
        received_size = 0

        class _PayloadTooLarge(Exception):
            pass

        async def limited_receive() -> Message:
            nonlocal received_size

            message = await receive()

            if message["type"] == "http.request":
                body = message.get("body", b"")
                if received_size + len(body) > self.max_body_bytes:
                    raise _PayloadTooLarge
                received_size += len(body)

            return message

        try:
            await self.app(scope, limited_receive, send)
        except _PayloadTooLarge:
            response = JSONResponse(
                status_code=413,
                content={"status": "error", "message": "Request body too large"},
            )
            await response(scope, receive, send)
            return
