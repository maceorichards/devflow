# tally

A tiny word-counting library, the throwaway repo for devflow smoke runs.
Standard library only.

```python
from tally import count_words, top_words

count_words("the cat and the hat")      # {"the": 2, "cat": 1, "and": 1, "hat": 1}
top_words("the cat and the hat", 1)     # [("the", 2)]
```

Run the tests with `python3 -m unittest`.
