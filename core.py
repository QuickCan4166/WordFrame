import re
from dataclasses import dataclass
from difflib import SequenceMatcher


def tokens(text):
    return re.findall(r"\w+(?:['’]\w+)*", text.casefold())


def alternatives(text):
    """Commas separate alternatives; spaces within an alternative form a phrase."""
    return [tuple(tokens(part)) for part in text.split(',') if tokens(part)]


@dataclass(frozen=True)
class Hit:
    start: int
    end: int
    phrase: tuple
    rule_index: int


def rule_hits(text, rules):
    words = tokens(text)
    hits = []
    for index, rule in enumerate(rules):
        if not rule.get('enabled', True):
            continue
        for phrase in set(alternatives(rule.get('word', ''))):
            for start in range(len(words) - len(phrase) + 1):
                if tuple(words[start:start + len(phrase)]) == phrase:
                    hits.append(Hit(start, start + len(phrase), phrase, index))
    # At the same ending word, prefer a longer matching phrase. Earlier rules
    # break remaining ties consistently for legacy settings with duplicates.
    best = {}
    for hit in sorted(hits, key=lambda h: (h.end, -len(h.phrase), h.rule_index)):
        best.setdefault(hit.end, hit)
    return sorted(best.values(), key=lambda h: h.end)


def match_rules(text, rules):
    hits = rule_hits(text, rules)
    return rules[hits[-1].rule_index] if hits else None


class LiveMatcher:
    """Remember fired occurrences within one Vosk speech segment.

    Partial hypotheses can be revised. We never retract a shown visual, and a
    previously fired phrase at the same word position does not fire twice.
    Final results are processed for unseen occurrences, then reset the segment.
    """
    def __init__(self):
        self.seen = set()
        self.previous_words = []
    def reset(self):
        self.seen.clear()
        self.previous_words = []
    def feed(self, text, rules, final=False):
        words = tokens(text)
        if words and self.previous_words and words != self.previous_words:
            # Follow occurrences when Vosk inserts/removes earlier words, so an
            # unchanged trigger shifted by a correction does not restart a GIF.
            mapping = {}
            for block in SequenceMatcher(None, self.previous_words, words, autojunk=False).get_matching_blocks():
                for offset in range(block.size):
                    mapping[block.a + offset] = block.b + offset
            relocated = set()
            for start, end, phrase, index in self.seen:
                positions = [mapping.get(i) for i in range(start, end)]
                if all(i is not None for i in positions) and positions == list(range(positions[0], positions[0] + len(phrase))):
                    relocated.add((positions[0], positions[-1] + 1, phrase, index))
                else:
                    relocated.add((start, end, phrase, index))
            self.seen = relocated
        if words:
            self.previous_words = words
        fresh = []
        for hit in rule_hits(text, rules):
            key = (hit.start, hit.end, hit.phrase, hit.rule_index)
            if key not in self.seen:
                self.seen.add(key)
                fresh.append(hit)
        if final:
            self.reset()
        return fresh
