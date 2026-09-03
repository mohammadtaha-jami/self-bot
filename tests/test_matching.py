"""Unit tests for word-boundary keyword matching and lead-level guards."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from modules.processor.matching import (
    KeywordHit,
    MatchConfig,
    determine_lead_level,
    is_fuzzy_eligible,
    match_keywords,
)
from modules.processor.nlp import (
    clean_text,
    count_meaningful_tokens,
    has_phrase_match,
    tokenize_meaningful_words,
)
from shared.enums import LeadLevelEnum


class TokenBoundaryTests(unittest.TestCase):
    def test_phrase_match_rahn_as_own_token(self) -> None:
        text = clean_text("رهن کامل واحد")
        self.assertTrue(has_phrase_match(text, clean_text("رهن")))

    def test_phrase_does_not_match_inside_longer_token(self) -> None:
        text = clean_text("رهننده ملک هستم")
        self.assertFalse(has_phrase_match(text, clean_text("رهن")))

    def test_zwnj_splits_into_tokens(self) -> None:
        text = clean_text("رهن\u200cکامل واحد نزدیک ونک")
        tokens = tokenize_meaningful_words(text)
        self.assertIn("رهن", tokens)
        self.assertTrue(has_phrase_match(text, clean_text("رهن")))

    def test_multiword_phrase_requires_consecutive_tokens(self) -> None:
        text = clean_text("به دنبال فروش آپارتمان در ونک")
        self.assertTrue(has_phrase_match(text, clean_text("فروش آپارتمان")))
        self.assertFalse(has_phrase_match(text, clean_text("فروش ونک")))


class MinimumLengthGuardTests(unittest.TestCase):
    def test_single_letter_against_long_keyword_is_rejected(self) -> None:
        result = match_keywords(
            "ن",
            MatchConfig(keywords=["کسی میتونه ربات"]),
        )
        self.assertFalse(result.matched)
        self.assertEqual(result.lead_level, LeadLevelEnum.LOW)
        self.assertIn("min_text_len", result.reason)

    def test_short_reply_ne_against_long_keyword_is_rejected(self) -> None:
        result = match_keywords(
            "نه",
            MatchConfig(keywords=["کسی میتونه ربات", "ربات تلگرام"]),
        )
        self.assertFalse(result.matched)
        self.assertEqual(result.lead_level, LeadLevelEnum.LOW)

    def test_too_few_meaningful_tokens_rejected(self) -> None:
        result = match_keywords(
            "aaaaaaaa",
            MatchConfig(keywords=["aaaaaaaa extra"], require_min_tokens=True),
        )
        self.assertFalse(result.matched)
        self.assertEqual(result.reason, "Too few meaningful tokens")

    def test_token_guard_can_be_disabled(self) -> None:
        result = match_keywords(
            "aaaaaaaa",
            MatchConfig(
                keywords=["aaaaaaaa"],
                require_min_tokens=False,
                min_text_len=8,
            ),
        )
        self.assertTrue(result.matched)
        self.assertIn("aaaaaaaa", result.matched_keywords)


class FuzzyLengthGuardTests(unittest.TestCase):
    def test_partial_ratio_not_called_when_text_much_shorter_than_keyword(self) -> None:
        config = MatchConfig(
            keywords=["کسی میتونه ربات بسازه برام"],
            min_text_len=8,
            require_min_tokens=False,
        )
        with patch("modules.processor.matching.fuzz.partial_ratio") as mocked:
            mocked.return_value = 100.0
            result = match_keywords("سلام شما", config)
        mocked.assert_not_called()
        self.assertFalse(result.matched)

    def test_is_fuzzy_eligible_requires_ratio_and_min_len(self) -> None:
        config = MatchConfig()
        self.assertFalse(is_fuzzy_eligible("کسی میتونه ربات", "نه", config))
        self.assertFalse(is_fuzzy_eligible("ربات", "سلام دنیا", config))
        self.assertTrue(is_fuzzy_eligible("رباتک", "این متن نسبتا بلند است", config))


class ExactWordBoundaryLeadTests(unittest.TestCase):
    def test_rahn_in_full_sentence_matches_and_ignores_unrelated_negative(self) -> None:
        result = match_keywords(
            "رهن کامل واحد نزدیک ونک میخوام",
            MatchConfig(
                keywords=["رهن"],
                negative_keywords=["اجاره میدم"],
            ),
        )
        self.assertTrue(result.matched)
        self.assertIn("رهن", result.matched_keywords)
        self.assertEqual(result.score, 100.0)
        self.assertEqual(result.lead_level, LeadLevelEnum.HOT)

    def test_negative_phrase_veto_uses_word_boundary(self) -> None:
        result = match_keywords(
            "رهن کامل واحد را اجاره میدم فوری",
            MatchConfig(
                keywords=["رهن"],
                negative_keywords=["اجاره میدم"],
            ),
        )
        self.assertFalse(result.matched)
        self.assertEqual(result.reason, "Matched negative keyword")

    def test_negative_does_not_fire_on_partial_token(self) -> None:
        result = match_keywords(
            "دنبال رهن کامل واحد هستم نه فروشنده",
            MatchConfig(
                keywords=["رهن"],
                negative_keywords=["فروشنده هستم"],
            ),
        )
        self.assertTrue(result.matched)


class LeadLevelTests(unittest.TestCase):
    def test_single_borderline_fuzzy_hit_is_warm(self) -> None:
        config = MatchConfig()
        hits = [
            KeywordHit(keyword="ربات تلگرام", cleaned="ربات تلگرام", score=86.0, is_exact=False),
        ]
        self.assertEqual(determine_lead_level(hits, config), LeadLevelEnum.WARM)

    def test_two_distinct_fuzzy_hits_are_hot(self) -> None:
        config = MatchConfig()
        hits = [
            KeywordHit(keyword="ربات تلگرام", cleaned="ربات تلگرام", score=86.0, is_exact=False),
            KeywordHit(keyword="pentest", cleaned="pentest", score=88.0, is_exact=False),
        ]
        self.assertEqual(determine_lead_level(hits, config), LeadLevelEnum.HOT)

    def test_long_exact_hit_is_hot(self) -> None:
        config = MatchConfig()
        hits = [
            KeywordHit(keyword="رهن", cleaned="رهن", score=100.0, is_exact=True),
        ]
        self.assertEqual(determine_lead_level(hits, config), LeadLevelEnum.HOT)

    def test_match_keywords_single_fuzzy_stays_warm(self) -> None:
        config = MatchConfig(
            keywords=["کسی میتونه ربات"],
            require_min_tokens=True,
            min_text_len=8,
        )
        with patch("modules.processor.matching.fuzz.partial_ratio", return_value=86.0):
            result = match_keywords("کسی میتونه کمک کنه لطفا زود", config)
        self.assertTrue(result.matched)
        self.assertEqual(result.lead_level, LeadLevelEnum.WARM)
        self.assertEqual(result.score, 86.0)

    def test_match_keywords_two_distinct_keywords_are_hot(self) -> None:
        config = MatchConfig(
            keywords=["فروش آپارتمان", "رهن"],
        )
        result = match_keywords("فروش آپارتمان و رهن کامل در ونک", config)
        self.assertTrue(result.matched)
        self.assertEqual(result.lead_level, LeadLevelEnum.HOT)
        self.assertEqual(set(result.matched_keywords), {"فروش آپارتمان", "رهن"})


class MeaningfulTokenCountTests(unittest.TestCase):
    def test_emoji_only_has_zero_tokens_after_clean(self) -> None:
        cleaned = clean_text("🔥🔥🔥")
        self.assertEqual(count_meaningful_tokens(cleaned), 0)


if __name__ == "__main__":
    unittest.main()
