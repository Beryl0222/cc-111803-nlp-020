import json
from pathlib import Path

def load_facts(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def summarize(facts):
    return [example['id'] for example in facts['examples']
            if any(section['id'] == example['section'] for section in facts['sections'])]
