import logging
import hashlib
import html
import os
import sys
from logging.handlers import RotatingFileHandler

# Đường dẫn thư mục gốc dự án và file log mặc định
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE = os.path.join(PROJECT_ROOT, "cron.log")


def setup_logging(verbose: bool = False):
    """
    Thiết lập logging với RotatingFileHandler.
    - Tránh ghi trùng 2 lần mỗi dòng nếu stdout đã được cron redirect vào cron.log.
    """
    level = logging.DEBUG if verbose else logging.INFO
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    handlers = []

    # File handler với log rotation (5MB x 3 backup)
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    handlers.append(file_handler)

    # Chỉ thêm StreamHandler nếu đang chạy trực tiếp trên terminal (TTY)
    # để khi cron chạy `>> cron.log 2>&1` không bị ghi đè gấp đôi từng dòng
    if sys.stdout and hasattr(sys.stdout, "isatty") and sys.stdout.isatty():
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        handlers.append(console_handler)

    logging.basicConfig(
        level=level,
        handlers=handlers,
        force=True
    )


def generate_hash(content: str) -> str:
    """Tạo mã băm MD5 cho nội dung văn bản."""
    if not content:
        return ""
    return hashlib.md5(content.encode('utf-8')).hexdigest()


def escape_html(text: str) -> str:
    """Escape các ký tự HTML đặc biệt để gửi qua Telegram parse_mode=HTML một cách an toàn."""
    if not text:
        return ""
    return html.escape(text, quote=False)


def get_python_executable() -> str:
    """
    Tìm đường dẫn Python thực thi phù hợp trên cả Linux VPS và Windows.
    Ưu tiên virtualenv trong dự án, nếu không có thì dùng sys.executable hiện tại.
    """
    candidates = [
        os.path.join(PROJECT_ROOT, "venv", "bin", "python"),
        os.path.join(PROJECT_ROOT, ".venv", "bin", "python"),
        os.path.join(PROJECT_ROOT, "venv", "Scripts", "python.exe"),
        os.path.join(PROJECT_ROOT, ".venv", "Scripts", "python.exe"),
    ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return sys.executable
