import json
from typing import Any


class LogFormat:
    """Produce consistent Loguru-compatible format strings for console and file sinks.

    Keeps colour markup in a single place so changing the palette only requires editing
    this class.
    """

    _LEVEL_COLOURS: dict[str, str] = {
        "CRITICAL": "red",
        "ERROR": "magenta",
        "WARNING": "yellow",
        "SUCCESS": "green",
        "INFO": "blue",
        "DEBUG": "white",
        "TRACE": "dim",
    }

    def __init__(self, record: Any) -> None:
        """Initializes the LogFormat by parsing and structuring log record
        attributes."""
        self._record = record
        self.time_str = record["time"].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        self.level = record["level"].name
        self._colour = self._LEVEL_COLOURS.get(self.level, "white")

        func = record["function"]
        variable_location = "<module>" if func == "<module>" else func
        self.location = f"{record['file'].name}:{variable_location}:{record['line']}"

    def console(self) -> str:
        """Produces a colorized, human-readable format string for stdout/console
        destinations."""
        colour = self._colour
        return (
            f"<dim><bold>{self.time_str}</bold></dim> | "
            f"<{colour}>{self.level:<8}</{colour}> | "
            f"<cyan>{self.location}</cyan> - "
            f"<{colour}>{self._record['message']}</{colour}>"
            "\n"
        )

    def file(self) -> str:
        """Produces a structured, serialized format string with extra ctx fields for
        file sinks."""
        extras = {
            key: value
            for key, value in self._record["extra"].items()
            if key != "request_id" and value is not None
        }

        context_parts = []

        for key, value in extras.items():
            if isinstance(value, dict | list | tuple):
                safe_value = json.dumps(value, default=str)
            else:
                safe_value = str(value)

            safe_value = safe_value.replace("{", "{{").replace("}", "}}")
            context_parts.append(f"{key}={safe_value}")

        context_str = f" | {', '.join(context_parts)}" if context_parts else ""

        request_id = self._record["extra"].get("request_id", "")
        rid_str = f" | rid={request_id}" if request_id else ""

        return (
            f"{self.time_str} | "
            f"{self.level:<8} | "
            f"{self.location}"
            f"{rid_str}"
            f" - {self._record['message']}"
            f"{context_str}"
            "\n"
        )
