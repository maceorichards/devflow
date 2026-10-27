import unittest

from tally import count_words, top_words


class CountWordsTest(unittest.TestCase):
    def test_counts_lowercased_words(self):
        self.assertEqual(count_words("The cat and the hat."),
                         {"the": 2, "cat": 1, "and": 1, "hat": 1})

    def test_empty_text_has_no_words(self):
        self.assertEqual(count_words(""), {})


class TopWordsTest(unittest.TestCase):
    def test_most_frequent_first_ties_alphabetical(self):
        self.assertEqual(top_words("b a b c a b", 2), [("b", 3), ("a", 2)])


if __name__ == "__main__":
    unittest.main()
