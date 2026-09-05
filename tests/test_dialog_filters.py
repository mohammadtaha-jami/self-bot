"""Tests for Telegram folder peer-id normalization."""

from __future__ import annotations

import unittest

from modules.listener.dialog_filters import collect_peer_ids, summarize_dialog_filters


class _Peer:
    def __init__(self, channel_id=None, chat_id=None, user_id=None):
        self.channel_id = channel_id
        self.chat_id = chat_id
        self.user_id = user_id


class DialogFilterDefault:
    pass


class FakeDialogFilter:
    def __init__(self, folder_id, title):
        self.id = folder_id
        self.title = title


class PeerIdTests(unittest.TestCase):
    def test_channel_peer_adds_marked_and_raw_ids(self) -> None:
        ids = collect_peer_ids(_Peer(channel_id=123456))
        self.assertIn(123456, ids)
        self.assertIn(-100123456, ids)

    def test_basic_group_peer_adds_negative_id(self) -> None:
        ids = collect_peer_ids(_Peer(chat_id=99))
        self.assertIn(99, ids)
        self.assertIn(-99, ids)


class SummarizeFilterTests(unittest.TestCase):
    def test_skips_default_all_chats_folder(self) -> None:
        items = [DialogFilterDefault(), FakeDialogFilter(7, "Leads")]
        folders = summarize_dialog_filters(items)
        self.assertEqual(folders, [{"id": 7, "title": "Leads", "kind": "FakeDialogFilter"}])


if __name__ == "__main__":
    unittest.main()
