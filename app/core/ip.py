from fastapi import Request


def get_client_ip(request: Request) -> str | None:
    """Extracts the client's IP address from incoming request headers or connection
    metadata.

    Prioritizes headers set by reverse proxies or load balancers ('X-Forwarded-For' and
    'X-Real-IP') before falling back to the client host from the ASGI connection.
    """
    if forwarded := request.headers.get("X-Forwarded-For"):
        return forwarded.split(",")[0].strip()

    if real_ip := request.headers.get("X-Real-IP"):
        return real_ip.strip()

    return request.client.host if request.client else None


def mask_ip(ip_address: str | None) -> str | None:
    """Partially masks an IP address before returning it in API responses or logs.

    Replaces the last block of an IPv4 or IPv6 address with 'x' to protect user privacy
    while leaving enough info for diagnostic analysis.
    """
    if ip_address is None:
        return None

    if ":" in ip_address:
        parts = ip_address.rsplit(":", 1)
        return f"{parts[0]}:x"

    if "." in ip_address:
        parts = ip_address.rsplit(".", 1)
        return f"{parts[0]}.x"

    return ip_address
