import re

def tokens(text):
    return re.findall(r"\w+(?:['’]\w+)*", text.casefold())

def match_rules(text, rules):
    words = tokens(text)
    hits = []
    for rule in rules:
        phrase = tokens(rule.get('word', ''))
        if rule.get('enabled', True) and phrase:
            positions = [i for i in range(len(words)-len(phrase)+1) if words[i:i+len(phrase)] == phrase]
            if positions:
                hits.append((positions[-1], len(phrase), rule))
    return max(hits, key=lambda hit: (hit[0], hit[1]))[2] if hits else None
