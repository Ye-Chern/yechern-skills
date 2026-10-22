"""Check installable skill packages and local Markdown links using the standard library."""
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    'durable-task', 'durable-task-qwen-cloud', 'progressive-reading',
    'novel-worldbook', 'palimpsest', 'gpt-human-style', 'boundforge',
}


def validate(root=ROOT):
    problems = []
    skills = {p.name for p in (root / 'skills').iterdir() if p.is_dir()}
    if skills != EXPECTED:
        problems.append(f'Unexpected skill set: {sorted(skills)}')
    for name in sorted(EXPECTED):
        folder = root / 'skills' / name
        for required in ('SKILL.md', 'NOTICE.md', 'HELP.md', 'LICENSE'):
            if not (folder / required).is_file():
                problems.append(f'{name}: missing {required}')
        entry = folder / 'SKILL.md'
        if not entry.is_file():
            continue
        text = entry.read_text(encoding='utf-8')
        front = re.match(r'\A---\n(.*?)\n---(?:\n|$)', text, re.S)
        if not front:
            problems.append(f'{name}: invalid frontmatter')
            continue
        header = front.group(1)
        if not re.search(rf'^name:\s*{re.escape(name)}\s*$', header, re.M):
            problems.append(f'{name}: name does not match directory')
        if not re.search(r'^description:\s*\S', header, re.M):
            problems.append(f'{name}: missing description')
    checked_links = 0
    for path in root.rglob('*.md'):
        if '.git' in path.relative_to(root).parts:
            continue
        text = path.read_text(encoding='utf-8')
        # Fenced examples are literal instructions, not document hyperlinks.
        text = re.sub(r'^```.*?^```[^\n]*$', '', text, flags=re.M | re.S)
        for match in re.finditer(r'\[[^\]\n]*\]\(([^\s)]+)\)', text):
            target = match.group(1).strip('<>')
            parsed = urlsplit(target)
            if parsed.scheme or target.startswith(('#', '/')):
                continue
            local = unquote(parsed.path)
            if not local:
                continue
            checked_links += 1
            if not (path.parent / local).exists():
                problems.append(f'{path.relative_to(root)}: missing link target {target}')
    if problems:
        raise SystemExit('\n'.join(problems))
    print(f'{len(EXPECTED)} skills; {checked_links} relative links; package structure valid')


if __name__ == '__main__':
    validate()
