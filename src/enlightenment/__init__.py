"""Enlightenment: an orbital warfare training application.

Server archetype, deployed to the Bluestaq App Store as a container. The HTTP app is
built by the ``create_app`` factory in :mod:`enlightenment.app` so it can be mounted
in-process by the test suite with injected fakes.
"""

__all__ = ["__version__"]

# Release version. Bump with every change, alongside a docs/CHANGELOG.md audit row.
__version__ = "0.26.27"
