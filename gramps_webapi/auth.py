"""Define methods of providing authentication for users."""

from abc import abstractmethod, ABCMeta


class AuthProvider(metaclass=ABCMeta):
    """Base class for authentication providers."""

    @abstractmethod
    def authorized(self, username: str, password: str) -> bool:
        """Return true if the username is authorized."""
        return False


class DummyAuthProvider(AuthProvider):
    """Dummy auth provider that always logs in."""

    def authorized(self, username: str, password: str) -> bool:
        """Return true if the username is authorized."""
        return True
