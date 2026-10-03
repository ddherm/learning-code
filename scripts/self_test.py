#!/usr/bin/env python3
"""Small offline invariants for the renderer; does not touch a user's project."""
import argparse
import copy
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from render_lesson import compile_lesson


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, help='Keep the rendered example here for browser checks')
    args = parser.parse_args()
    example = Path(__file__).resolve().parent.parent / 'assets/example'
    spec = json.loads((example/'lesson.json').read_text(encoding='utf-8'))
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in example.iterdir() if p.is_file()}
    checks = []
    with tempfile.TemporaryDirectory(prefix='learning-code-test-') as tmp:
        output = args.out or Path(tmp)/'lesson'
        results = compile_lesson(spec, example, output)

        class CodeReader(HTMLParser):
            def __init__(self):
                super().__init__(); self.level = 0; self.lines = []; self.current = ''
            def handle_starttag(self, tag, attrs):
                if tag == 'span':
                    if dict(attrs).get('class') == 'line-src':
                        self.level = 1; self.current = ''
                    elif self.level:
                        self.level += 1
            def handle_endtag(self, tag):
                if tag == 'span' and self.level:
                    self.level -= 1
                    if not self.level: self.lines.append(self.current)
            def handle_data(self, data):
                if self.level: self.current += data

        reader = CodeReader(); reader.feed(results['lesson.html'])
        manifest = json.loads(results['source-index.json'])
        expected = []
        for card in manifest['snippets']:
            expected += (example/card['path']).read_text(encoding='utf-8').splitlines()[card['start']-1:card['end']]
        assert reader.lines == expected
        checks.append('rendered text preserves every source character and indent')
        assert manifest['question_count'] == 3 and len(manifest['snippets']) == 3
        assert 'learning-code:example:C01:1:' in results['lesson.html']
        checks.append('example is configurable and uses project/lesson-specific notes')

        def rejects(label, mutate):
            changed = copy.deepcopy(spec); mutate(changed)
            try:
                compile_lesson(changed, example, output)
            except (ValueError, KeyError):
                checks.append(label)
            else:
                raise AssertionError(label + ' should reject')

        def first_code(s):
            return next(b for section in s['sections'] for b in section['blocks'] if b['kind']=='code')
        rejects('out-of-card mapping rejected', lambda s: first_code(s)['steps'][0].update(ranges=[[1,999]]))
        rejects('incorrect question count rejected', lambda s: s.update(question_count=10))
        rejects('unsupported provenance rejected', lambda s: s['questions'][0].update(original='不存在于材料的原题'))
        rejects('unrequested answer rejected', lambda s: s['questions'][0].update(answer='提前泄露的答案'))
        rejects('path traversal rejected', lambda s: first_code(s).update(path='../sample.py'))
        rejects('executable prose rejected', lambda s: s['sections'][0]['blocks'][0].update(html='<script>alert(1)</script>'))
        def incomplete(s):
            code = first_code(s); code.pop('symbol'); code.update(start=3,end=4)
            code['steps']=[dict(ranges=[[3,4]],paragraphs=['遗漏类字段。'])]
        rejects('incomplete promised symbol rejected', incomplete)

        renderer = Path(__file__).with_name('render_lesson.py')
        cmd = [sys.executable,str(renderer),'--spec',str(example/'lesson.json'),'--root',str(example),'--out',str(output)]
        subprocess.run(cmd+['--replace'], check=True, capture_output=True, text=True)
        subprocess.run(cmd+['--check'], check=True, capture_output=True, text=True)
        (output/'lesson.html').write_text('用户手改内容', encoding='utf-8')
        rejected = subprocess.run(cmd, capture_output=True, text=True)
        assert rejected.returncode != 0 and (output/'lesson.html').read_text(encoding='utf-8') == '用户手改内容'
        subprocess.run(cmd+['--replace'], check=True, capture_output=True, text=True)
        backups = list((output/'backups').glob('*/lesson.html'))
        assert any(p.read_text(encoding='utf-8') == '用户手改内容' for p in backups)
        checks.append('changed output requires explicit replacement and recoverable backup')
        collision = Path(tmp)/'input-collision'
        collision.mkdir()
        original = 'one = 1\n'
        (collision/'lesson.html').write_text(original, encoding='utf-8')
        collision_spec = copy.deepcopy(spec)
        collision_spec.update(required_symbols=[], question_count=0, questions=[])
        collision_spec['sections']=[dict(id='only',title='Collision case',blocks=[dict(
            kind='code',title='Input file',path='lesson.html',start=1,end=1,
            key=['Read an input.'],steps=[dict(ranges=[[1,1]],paragraphs=['Do not overwrite it.'])],
            call=['Return.'])])]
        (collision/'spec.json').write_text(json.dumps(collision_spec), encoding='utf-8')
        bad = subprocess.run([sys.executable,str(renderer),'--spec',str(collision/'spec.json'),
                              '--root',str(collision),'--out',str(collision),'--replace'],capture_output=True,text=True)
        assert bad.returncode != 0 and 'overwrite a source input' in bad.stderr
        assert (collision/'lesson.html').read_text(encoding='utf-8')==original
        checks.append('output cannot overwrite an input even with --replace')
        after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in example.iterdir() if p.is_file()}
        assert before == after
        checks.append('all source and question inputs remain unchanged')
    print(json.dumps(dict(status='pass',checks=checks,fixture=str(args.out.resolve()) if args.out else 'temporary example removed'), ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
