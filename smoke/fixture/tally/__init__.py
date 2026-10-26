"""tally: count the words in a text."""
import re

WORD = re.compile(r"[a-z0-9']+")


def count_words(text):
    """{word: count} for the lowercased words of text."""
    counts = {}
    for word in WORD.findall(text.lower()):
        counts[word] = counts.get(word, 0) + 1
    return counts


def top_words(text, n):
    """The n most frequent (word, count) pairs, ties in alphabetical order."""
    return sorted(count_words(text).items(), key=lambda kv: (-kv[1], kv[0]))[:n]
