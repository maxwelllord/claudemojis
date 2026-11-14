"""Builds index.html, a searchable gallery of every flower face (custom/ wins over out/svg/)."""
import re, glob, os, json

names = {}
for line in open('data/emoji-test.txt', encoding='utf8'):
    r = re.match(r'([0-9A-F ]+?)\s*;\s*[\w-]+\s*#\s*\S+\s+E[\d.]+\s+(.*)', line)
    if r:
        names.setdefault('-'.join(x for x in r[1].lower().split() if x != 'fe0f'), r[2])

items = {}
for folder, svgdir in (('out', 'out/svg'), ('custom', 'custom')):
    for f in sorted(glob.glob(svgdir + '/*.svg')):
        code = os.path.basename(f)[:-4]
        key = code.replace('-fe0f', '')
        name = names[key]
        slug = re.sub(r'[^a-z0-9]+', '-', name.lower().replace('’', '')).strip('-')
        items[key] = dict(
            name=name, code=code,
            png=f'{folder}/png/claude-{slug}.png', svg=f.replace(os.sep, '/'),
            char=''.join(chr(int(c, 16)) for c in code.split('-')))
data = sorted(items.values(), key=lambda i: i['code'])
for i in data:
    assert os.path.exists(i['png']), i['png']

html = open('site_template.html', encoding='utf8').read().replace('__DATA__', json.dumps(data, ensure_ascii=False))
open('index.html', 'w', encoding='utf8').write(html)
print(len(data), 'faces')
