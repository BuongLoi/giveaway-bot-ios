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
    - Giới hạn mỗi file log tối đa 5MB
    - Giữ lại 3 file log cũ (cron.log, cron.log.1, cron.log.2, cron.log.3)
    - Tổng dung lượng tối đa: ~20MB
    """
    level = logging.DEBUG if verbose else logging.INFO
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # File handler với log rotation (5MB x 3 backup)
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=5 * 1024 * 1024,  # 5MB mỗi file
        backupCount=3,             # Giữ 3 file cũ
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)

    logging.basicConfig(
        level=level,
        handlers=[console_handler, file_handler]
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
