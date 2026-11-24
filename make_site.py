"""Builds index.html, a searchable gallery of every flower face (custom/ wins over out/svg/)."""
import re, glob, os, json

from flowerize import codes_by_readable_name

names = {}
for line in open('data/emoji-test.txt', encoding='utf8'):
    r = re.match(r'([0-9A-F ]+?)\s*;\s*[\w-]+\s*#\s*\S+\s+E[\d.]+\s+(.*)', line)
    if r:
        names.setdefault('-'.join(x for x in r[1].lower().split() if x != 'fe0f'), r[2])
code_of = codes_by_readable_name()  # 'claude-grinning-face' -> '1f600'

items = {}
for folder, svgdir in (('out', 'out/svg'), ('custom', 'custom')):
    for f in sorted(glob.glob(svgdir + '/*.svg')):
        stem = os.path.basename(f)[:-4]
        code = code_of[stem]
        key = code.replace('-fe0f', '')
        items[key] = dict(
            name=names[key], code=code,
            png=f'{folder}/png/{stem}.png', svg=f.replace(os.sep, '/'),
            char=''.join(chr(int(c, 16)) for c in code.split('-')))
data = sorted(items.values(), key=lambda i: i['code'])

# Original faces with no Unicode equivalent: named from the file, listed first.
extras = []
for f in sorted(glob.glob('new/*.svg')):
    stem = os.path.basename(f)[:-4]
    extras.append(dict(name=stem.removeprefix('claude-').replace('-', ' '), code='', char='',
                       png=f'new/png/{stem}.png', svg=f.replace(os.sep, '/')))
data = extras + data
for i in data:
    assert os.path.exists(i['png']), i['png']

html = open('site_template.html', encoding='utf8').read().replace('__DATA__', json.dumps(data, ensure_ascii=False))
open('index.html', 'w', encoding='utf8').write(html)
print(len(data), 'faces')
