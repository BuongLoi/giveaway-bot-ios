import logging
from bot.sources.base import BaseSource
from bot.config import REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT

try:
    import praw
    from praw.exceptions import PRAWException
except ImportError:
    praw = None
    PRAWException = Exception


class RedditAPI(BaseSource):
    """
    Sử dụng thư viện praw để kết nối Reddit API, thay thế cho RSS để lấy dữ liệu nhanh và chính xác hơn.
    Nếu chưa cài đặt praw hoặc thiếu REDDIT_CLIENT_ID, hệ thống tự động fallback sang RSS.
    """
    def __init__(self, name: str, subreddit_name: str, enabled: bool = True):
        super().__init__(name, enabled)
        self.subreddit_name = subreddit_name
        self.reddit = None

        if self.enabled and praw is None:
            self.logger.warning(f"Thư viện 'praw' chưa cài đặt, bỏ qua RedditAPI ({name}).")
            self.enabled = False
            return

        if self.enabled and REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET:
            try:
                self.reddit = praw.Reddit(
                    client_id=REDDIT_CLIENT_ID,
                    client_secret=REDDIT_CLIENT_SECRET,
                    user_agent=REDDIT_USER_AGENT
                )
                self.logger.info(f"Reddit API khởi tạo thành công cho r/{subreddit_name}")
            except Exception as e:
                self.logger.error(f"Lỗi khởi tạo Reddit API: {e}")
                self.enabled = False
        elif self.enabled:
            self.logger.warning(f"Bỏ qua Reddit API {name} do thiếu cấu hình REDDIT_CLIENT_ID/SECRET.")
            self.enabled = False

    def fetch(self) -> list:
        if not self.enabled or not self.reddit:
            return []

        self.logger.info(f"Đang tải Reddit API từ r/{self.subreddit_name}")
        results = []

        try:
            subreddit = self.reddit.subreddit(self.subreddit_name)
            # Lấy 15 bài mới nhất
            for post in subreddit.new(limit=15):
                guid = f"reddit_{post.id}"
                link = f"https://www.reddit.com{post.permalink}"

                content = ""
                if post.is_self:
                    content = post.selftext_html or post.selftext or ""

                html_content = f"<h1>{post.title}</h1>\n{content}"

                results.append({
                    'title': post.title,
                    'link': link,
                    'guid': guid,
                    'published': post.created_utc,
                    'content': html_content
                })
        except PRAWException as e:
            self.logger.error(f"Lỗi Reddit API PRAW: {e}")
        except Exception as e:
            self.logger.error(f"Lỗi phân tích Reddit API r/{self.subreddit_name}: {e}")

        return results
