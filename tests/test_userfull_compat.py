"""Tests for Telethon UserFull API compatibility.

Validates that the code correctly accesses attributes on the
UserFull response object returned by GetFullUserRequest.
"""
import pytest
from telethon.tl.types import User, UserFull, PeerSettings, PeerNotifySettings
from telethon.tl.types.users import UserFull as UsersUserFull


def _make_get_full_user_response(user_id=123, bot=True, first_name='TestBot', username='test_bot'):
    """Simulate the response from GetFullUserRequest in modern Telethon."""
    mock_user = User(
        id=user_id, is_self=True, bot=bot, access_hash=0,
        first_name=first_name, username=username,
    )
    mock_full_user = UserFull(
        id=user_id, settings=PeerSettings(),
        notify_settings=PeerNotifySettings(), common_chats_count=0,
    )
    return UsersUserFull(full_user=mock_full_user, chats=[], users=[mock_user])


def test_users_list_returns_user_objects():
    """GetFullUserRequest response .users[0] should be a User with basic fields."""
    result = _make_get_full_user_response()
    user = result.users[0]

    assert isinstance(user, User)
    assert user.id == 123
    assert user.bot is True
    assert user.first_name == 'TestBot'
    assert user.username == 'test_bot'


def test_users_to_dict_has_bot_field():
    """User.to_dict() should contain 'bot' key (used for bot.json)."""
    result = _make_get_full_user_response(bot=True)
    user_dict = result.users[0].to_dict()

    assert 'bot' in user_dict
    assert user_dict['bot'] is True


def test_full_user_to_dict_lacks_bot_field():
    """UserFull.to_dict() should NOT contain 'bot' key -- only User has it."""
    result = _make_get_full_user_response()
    full_user_dict = result.full_user.to_dict()

    assert 'bot' not in full_user_dict


def test_response_has_no_user_attribute():
    """The users.UserFull wrapper has no .user attribute (old API removed)."""
    result = _make_get_full_user_response()

    assert not hasattr(result, 'user')
    assert hasattr(result, 'users')
    assert hasattr(result, 'full_user')
