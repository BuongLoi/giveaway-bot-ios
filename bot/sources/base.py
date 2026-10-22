from abc import ABC, abstractmethod
import logging

class BaseSource(ABC):
    def __init__(self, name: str, enabled: bool = True):
        self.name = name
        self.enabled = enabled
        self.logger = logging.getLogger(f"source.{name}")

    @abstractmethod
    def fetch(self) -> list:
        """
        Lấy danh sách các bài đăng.
        Mỗi bài đăng trả về dạng dict chứa:
        - title
        - link (canonical_url)
        - guid
        - published
        - content (HTML)
        """
        pass
