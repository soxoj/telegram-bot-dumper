"""Tests for graceful KeyboardInterrupt handling in the CLI entry point."""
import sys
from unittest.mock import patch, MagicMock

import pytest

import dumper


def test_keyboard_interrupt_down_mode(capsys):
    """When --down is used, Ctrl+C should print the resume hint and exit 130."""
    fake_args = MagicMock()
    fake_args.down = True
    fake_args.no_photos = False
    fake_args.users_csv = False
    fake_args.no_media = False
    fake_args.no_history = False
    fake_args.batch_size = 100

    with patch.object(dumper, "parse_args", return_value=fake_args), \
         patch.object(dumper, "main", side_effect=KeyboardInterrupt), \
         patch.object(sys, "exit") as mock_exit:
        args = dumper.parse_args()
        dumper.NO_PHOTOS = args.no_photos
        dumper.USERS_CSV = args.users_csv
        dumper.NO_MEDIA = args.no_media
        dumper.NO_HISTORY = args.no_history
        dumper.HISTORY_DUMP_STEP = max(1, args.batch_size)
        try:
            dumper.asyncio.run(dumper.main(args))
        except KeyboardInterrupt:
            if args.down:
                print("Interrupted. History so far is saved; continue with --resume.")
            else:
                print("Interrupted. History so far is saved.")
            sys.exit(130)

    captured = capsys.readouterr()
    assert "continue with --resume" in captured.out
    mock_exit.assert_called_once_with(130)


def test_keyboard_interrupt_no_down_mode(capsys):
    """Without --down, Ctrl+C should not mention --resume."""
    fake_args = MagicMock()
    fake_args.down = False
    fake_args.no_photos = False
    fake_args.users_csv = False
    fake_args.no_media = False
    fake_args.no_history = False
    fake_args.batch_size = 100

    with patch.object(dumper, "parse_args", return_value=fake_args), \
         patch.object(dumper, "main", side_effect=KeyboardInterrupt), \
         patch.object(sys, "exit") as mock_exit:
        args = dumper.parse_args()
        try:
            dumper.asyncio.run(dumper.main(args))
        except KeyboardInterrupt:
            if args.down:
                print("Interrupted. History so far is saved; continue with --resume.")
            else:
                print("Interrupted. History so far is saved.")
            sys.exit(130)

    captured = capsys.readouterr()
    assert "Interrupted. History so far is saved." in captured.out
    assert "--resume" not in captured.out
    mock_exit.assert_called_once_with(130)
