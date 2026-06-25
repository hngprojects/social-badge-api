from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import Message


class ContentSizeLimitMiddleware:
    """
    Enforces a maximum body size limit on incoming HTTP request payloads.

    Intercepts HTTP scope calls at the ASGI layer and dynamically tracks bytes received
    to guard against request body overflow attacks and memory degradation.
    """

    def __init__(self, app, max_body_bytes: int = 1 * 1024 * 1024):
        """
        Initializes the ASGI middleware with application scope reference
        and body limits.
        """
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope, receive, send):
        """
        Processes the ASGI request flow, validating and enforcing the payload
        size constraint.

        Bypasses checks for non-HTTP scope types. Validates headers first,
        and if not present, instruments the receive generator dynamically to
        compute payload bytes received on the fly.
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)

        content_length = request.headers.get("content-length")
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

        received_size = 0

        class _PayloadTooLarge(Exception):
            """
            Internal signal exception raised when received request payload size limit
            is exceeded.
            """

            pass

        async def limited_receive() -> Message:
            """
            ASGI receive wrapper that monitors incoming body chunk sizes
            and enforces size restrictions.
            """
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
