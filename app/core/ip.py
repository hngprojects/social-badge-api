from fastapi import Request


def get_client_ip(request: Request) -> str | None:
    if forwarded := request.headers.get("X-Forwarded-For"):
        return forwarded.split(",")[0].strip()

    if real_ip := request.headers.get("X-Real-IP"):
        return real_ip.strip()

    return request.client.host if request.client else None


def mask_ip(ip_address: str | None) -> str | None:
    """Partially mask an IP address before returning it in API responses.

    IPv4: replace the last octet with 'x' (e.g. 41.184.22.5 → 41.184.22.x)
    IPv6: replace the last group with 'x' (e.g. 2001:db8::1 → 2001:db8::x)
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
