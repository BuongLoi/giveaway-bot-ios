import pytest
import responses
from bot.telegram import send_message
import bot.config as config_module

@responses.activate
def test_send_message_success(monkeypatch):
    monkeypatch.setattr(config_module, 'TELEGRAM_BOT_TOKEN', 'fake_token')
    monkeypatch.setattr(config_module, 'TELEGRAM_CHAT_ID', 'fake_id')
    
    responses.add(
        responses.POST,
        "https://api.telegram.org/botfake_token/sendMessage",
        json={"ok": True},
        status=200
    )
    
    result = send_message("Hello")
    assert result is True

@responses.activate
def test_send_message_429(monkeypatch, mocker):
    monkeypatch.setattr(config_module, 'TELEGRAM_BOT_TOKEN', 'fake_token')
    monkeypatch.setattr(config_module, 'TELEGRAM_CHAT_ID', 'fake_id')
    
    # Mock time.sleep to avoid actually waiting during tests
    mock_sleep = mocker.patch('time.sleep')
    
    # Lần 1 trả về 429
    responses.add(
        responses.POST,
        "https://api.telegram.org/botfake_token/sendMessage",
        json={"ok": False, "description": "Too Many Requests", "parameters": {"retry_after": 2}},
        status=429
    )
    # Lần 2 trả về 200
    responses.add(
        responses.POST,
        "https://api.telegram.org/botfake_token/sendMessage",
        json={"ok": True},
        status=200
    )
    
    result = send_message("Hello")
    assert result is True
    mock_sleep.assert_called_once_with(2)

def test_send_message_truncate(monkeypatch):
    # Test cắt ngắn chuỗi
    monkeypatch.setattr(config_module, 'TELEGRAM_BOT_TOKEN', 'fake_token')
    monkeypatch.setattr(config_module, 'TELEGRAM_CHAT_ID', 'fake_id')
    
    long_text = "A" * 5000
    
    # Bypass requests.post
    import requests
    class MockResponse:
        status_code = 200
        def json(self):
            return {"ok": True}
            
    def mock_post(url, json, timeout):
        # json['text'] phải ngắn hơn 4096 (cụ thể là 4000 + phần cắt bớt)
        assert len(json['text']) <= 4096
        return MockResponse()
        
    monkeypatch.setattr(requests, 'post', mock_post)
    
    result = send_message(long_text)
    assert result is True
