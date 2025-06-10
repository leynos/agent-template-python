"""Package entry point."""

PACKAGE_NAME = "{{ package_name }}"

try:
    placeholder_mod = __import__(f"_{PACKAGE_NAME}_rs")
    placeholder = placeholder_mod.placeholder  # type: ignore[attr-defined]
except ModuleNotFoundError:

    def placeholder() -> None:
        """Placeholder function."""
        raise NotImplementedError("Implement logic here")


__all__ = ["placeholder"]
