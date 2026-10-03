#!/usr/bin/env python3
"""Render an offline source lesson from reviewed JSON; Python standard library only."""
import argparse
import ast
import hashlib
import html
from html.parser import HTMLParser
import io
import json
import keyword
from pathlib import Path
import re
import tokenize
from urllib.parse import urlparse

ASSETS = Path(__file__).resolve().parent.parent / 'assets'


def ensure(condition, message):
    if not condition:
        raise ValueError(message)


def source_path(root, value):
    ensure(isinstance(value, str) and value, 'source path must be a relative string')
    ensure(not Path(value).is_absolute(), f'absolute source path forbidden: {value}')
    target = (root / value).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise ValueError(f'source path escapes --root: {value}') from None
    ensure(target.is_file(), f'source file missing: {value}')
    return target


def identifier(value):
    ensure(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', value),
           f'identifier must use ASCII letters/digits/hyphens/underscores: {value}')
    return value


def inline(text):
    """Small, escaped inline notation: `code` and **bold**, not a Markdown engine."""
    text = str(text)
    tokens = re.split(r'(`[^`\n]+`|\*\*[^*\n]+\*\*)', text)
    result = []
    for value in tokens:
        if value.startswith('`') and value.endswith('`'):
            result.append('<code>' + html.escape(value[1:-1]) + '</code>')
        elif value.startswith('**') and value.endswith('**'):
            result.append('<strong>' + html.escape(value[2:-2]) + '</strong>')
        else:
            result.append(html.escape(value))
    return ''.join(result)


def paragraphs(value, span=False):
    values = [value] if isinstance(value, str) else value
    ensure(isinstance(values, list) and values and all(isinstance(x, str) and x.strip() for x in values),
           'paragraphs must be a nonempty string or list of nonempty strings')
    if span:
        return ''.join('<span class="step-paragraph">' + inline(x) + '</span>' for x in values)
    return ''.join('<p>' + inline(x) + '</p>' for x in values)


class ProseValidator(HTMLParser):
    """Accept authored prose, not executable markup or repository-supplied HTML."""
    tags = {'p', 'h3', 'h4', 'strong', 'em', 'code', 'pre', 'table', 'thead', 'tbody',
            'tr', 'td', 'th', 'ul', 'ol', 'li', 'a', 'br', 'blockquote', 'div', 'small', 'span'}

    def handle_starttag(self, tag, attrs):
        ensure(tag in self.tags, f'unsupported prose tag: {tag}')
        for key, value in attrs:
            ensure(key in {'class', 'href', 'colspan', 'rowspan'}, f'unsupported prose attribute: {key}')
            if key == 'href':
                ensure(tag == 'a' and urlparse(value or '').scheme.lower() in {'', 'http', 'https'},
                       'prose href must be a local link or http(s) reference')
                ensure(not any(ord(c) < 32 for c in value or ''), 'control characters in href')

    def handle_endtag(self, tag):
        ensure(tag in self.tags, f'unsupported prose end tag: {tag}')


def prose_html(value):
    ensure(isinstance(value, str) and value.strip(), 'prose html is required')
    parser = ProseValidator(convert_charrefs=True)
    parser.feed(value)
    parser.close()
    return value


def symbol_range(text, qualified):
    node = ast.parse(text)
    for name in qualified.split('.'):
        choices = [n for n in getattr(node, 'body', []) if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
        ensure(len(choices) == 1, f'cannot uniquely locate Python symbol: {qualified}')
        node = choices[0]
    start = min([node.lineno] + [x.lineno for x in node.decorator_list])
    return start, node.end_lineno


def highlight(text, suffix):
    raw = text.splitlines()
    spans = [[] for _ in raw]
    if suffix in {'.py', '.pyi'}:
        try:
            tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
            for i, token in enumerate(tokens):
                cls = None
                if token.type == tokenize.COMMENT:
                    cls = 'comment'
                elif token.type == tokenize.STRING:
                    cls = 'string'
                elif token.type == tokenize.NUMBER:
                    cls = 'number'
                elif token.type == tokenize.NAME:
                    if keyword.iskeyword(token.string):
                        cls = 'keyword'
                    elif token.string in {'str', 'int', 'float', 'bool', 'dict', 'list', 'set', 'tuple', 'len', 'range', 'getattr', 'isinstance'}:
                        cls = 'builtin'
                    elif (i and tokens[i-1].string in {'def', 'class'}) or (i+1 < len(tokens) and tokens[i+1].string == '('):
                        cls = 'function'
                    elif token.string[:1].isupper():
                        cls = 'type'
                if cls:
                    (a, c), (b, d) = token.start, token.end
                    for n in range(a, b+1):
                        if 1 <= n <= len(raw):
                            spans[n-1].append((c if n == a else 0, d if n == b else len(raw[n-1]), cls))
        except (tokenize.TokenError, IndentationError):
            spans = [[] for _ in raw]  # Preserve source even when tokenization is unavailable.
    elif suffix in {'.js', '.jsx', '.ts', '.tsx', '.json', '.vue'}:
        pattern = re.compile(r'//.*$|(?:\'(?:\\.|[^\'\\])*\'|"(?:\\.|[^"\\])*"|`[^`]*`)|\b(?:async|await|function|const|let|return|if|else|try|catch|finally|new|true|false|null|undefined|export|import|class|interface|type)\b|\b\d+\b')
        for i, line in enumerate(raw):
            for match in pattern.finditer(line):
                word = match.group()
                cls = 'comment' if word.startswith('//') else 'string' if word[0] in "'\"`" else 'number' if word[0].isdigit() else 'keyword'
                spans[i].append((match.start(), match.end(), cls))
    result = []
    for line, items in zip(raw, spans):
        pos, buf = 0, ''
        for a, b, cls in sorted(items):
            if a < pos:
                continue
            buf += html.escape(line[pos:a]) + '<span class="tok-' + cls + '">' + html.escape(line[a:b]) + '</span>'
            pos = b
        result.append(buf + html.escape(line[pos:]))
    return result


def ranges_checked(ranges, start, end, raw):
    ensure(isinstance(ranges, list) and ranges, 'each explanation requires explicit ranges')
    selected = []
    for pair in ranges:
        ensure(isinstance(pair, list) and len(pair) == 2 and all(type(n) is int for n in pair), 'range must be [start, end] integers')
        a, b = pair
        ensure(start <= a <= b <= end, f'explanation range {pair} escapes card {start}–{end}')
        ensure(any(raw[n-1].strip() for n in range(a, b+1)), 'blank-only explanation target')
        selected.extend(range(a, b+1))
    ensure(selected == sorted(set(selected)), 'ranges must be ordered, disjoint, and nonduplicated')
    return selected


def compile_lesson(spec, root, output):
    root, output = root.resolve(), output.resolve()
    ensure(root.is_dir(), '--root must be a directory')
    course_id = identifier(spec['project_id'])
    lesson_id = identifier(spec['lesson_id'])
    title = spec['title']
    ensure(isinstance(title, str) and title.strip(), 'title is required')
    questions = spec.get('questions', [])
    expected = spec.get('question_count', 10)
    ensure(type(expected) is int and expected >= 0 and len(questions) == expected,
           f'question_count={expected}, actual={len(questions)}')
    timings = spec.get('time_budget', {'core_minutes': 180, 'optional_minutes': 120})
    core, extra = timings['core_minutes'], timings['optional_minutes']
    ensure(type(core) is int and core > 0 and type(extra) is int and extra >= 0, 'invalid time budget')
    storage = f'learning-code:{course_id}:{lesson_id}:{spec.get("notes_version", 1)}:'
    sources, snippets, section_ids, toc, body = {}, [], set(), [], []
    markdown = ['# ' + title, spec.get('subtitle', '')]

    def read(path):
        if path not in sources:
            sources[path] = source_path(root, path).read_text(encoding='utf-8')
        return sources[path]

    for section in spec['sections']:
        sid = identifier(section['id'])
        ensure(sid not in section_ids and sid not in {'questions', 'evidence', 'wrap', 'wide', 'expand', 'export', 'print'} and not re.fullmatch(r'(?:code-\d+|q\d+)', sid), 'duplicate or reserved section id')
        section_ids.add(sid)
        heading = section['title']
        toc.append(f'<a href="#{sid}">{html.escape(heading)}</a>')
        body.append(f'<section id="{sid}"><header class="section-header"><h2>{html.escape(heading)}</h2><p>{html.escape(section.get("subtitle", ""))}</p></header>')
        markdown.append('## ' + heading)
        for item in section['blocks']:
            if item['kind'] == 'prose':
                value = prose_html(item['html'])
                body.append('<div class="prose">' + value + '</div>')
                markdown.append(value)
                continue
            ensure(item['kind'] == 'code', 'block kind must be prose or code')
            path = item['path']
            text = read(path)
            raw = text.splitlines()
            if 'symbol' in item:
                ensure('start' not in item and 'end' not in item, 'choose symbol OR start/end')
                ensure(Path(path).suffix in {'.py', '.pyi'}, 'symbol lookup currently supports Python only')
                start, end = symbol_range(text, item['symbol'])
            else:
                start, end = item['start'], item['end']
            ensure(type(start) is int and type(end) is int and 1 <= start <= end <= len(raw), f'invalid source range: {path}')
            cid = f'code-{len(snippets)+1:02d}'
            colored = highlight(text, Path(path).suffix.lower())
            source = '\n'.join(raw[start-1:end])
            lines = ''.join(f'<span class="code-line" id="{cid}-L{n}" data-line="{n}"><span class="line-no" aria-hidden="true">{n}</span><span class="line-src">{colored[n-1]}</span></span>' for n in range(start, end+1))
            ensure(item.get('steps'), f'{cid}: explanation steps required')
            buttons = []
            for step in item['steps']:
                numbers = ranges_checked(step['ranges'], start, end, raw)
                value = ','.join(str(a) if a == b else f'{a}-{b}' for a, b in step['ranges'])
                label = '、'.join(f'L{a}' if a == b else f'L{a}–{b}' for a, b in step['ranges'])
                controls = ' '.join(f'{cid}-L{n}' for n in numbers)
                buttons.append(f'<li><button type="button" class="explanation-step" data-lines="{value}" aria-controls="{controls}" aria-pressed="false"><span class="step-hint">↖ 对应代码 {label}</span>{paragraphs(step["paragraphs"], span=True)}</button></li>')
            explain = '<p><strong>关键代码：</strong></p>' + paragraphs(item['key'])
            explain += '<p><strong>逐行/分组含义：</strong></p><ul class="explanation-steps">' + ''.join(buttons) + '</ul>'
            explain += '<p><strong>调用关系/作用：</strong></p>' + paragraphs(item['call'])
            if item.get('critical'):
                explain += '<strong class="critical">面试关键设计｜' + inline(item['critical']) + '</strong>'
            label = f'{path} · L{start}–{end}'
            card = f'<article id="{cid}" class="code-card" data-path="{html.escape(path, quote=True)}" data-start="{start}" data-end="{end}"><div class="code-title"><h3>{html.escape(item["title"])}</h3><button class="copy" data-copy="{cid}">复制代码</button></div><div class="code-meta">{html.escape(label)}</div><div class="column-head"><span>关键代码 · 原文与真实行号</span><span>点击说明定位对应代码</span></div><div class="code-grid"><div class="code-pane"><pre><code>{lines}</code></pre></div><div class="explanation">{explain}</div></div></article>'
            if item.get('optional', False):
                card = f'<details class="source-detail"><summary>选读 · {html.escape(item["title"])}<span>{end-start+1} 行完整摘录</span></summary>{card}</details>'
            body.append(card)
            snippets.append(dict(id=cid, title=item['title'], path=path, start=start, end=end, steps=item['steps']))
            lang = 'python' if Path(path).suffix in {'.py', '.pyi'} else Path(path).suffix.lstrip('.')
            runs = [len(x.group()) for x in re.finditer(r'`+', source)]
            fence = '`' * max(3, max(runs, default=0)+1)
            markdown += ['### ' + item['title'], '来源：`' + label + '`', f'{fence}{lang}\n{source}\n{fence}', explain]
        body.append('</section>')

    for claim in spec.get('required_symbols', []):
        text = read(claim['path'])
        start, end = symbol_range(text, claim['symbol'])
        covered = {n for entry in snippets if entry['path'] == claim['path'] for n in range(entry['start'], entry['end']+1)}
        missing = [n for n in range(start, end+1) if text.splitlines()[n-1].strip() and n not in covered]
        ensure(not missing, f'incomplete promised symbol {claim}: missing lines {missing}')

    qmd = ['# ' + title + ' · 课后题', '按题独立回答，再补源码证据。']
    toc += ['<a href="#questions">课后题与个人回答</a>', '<a href="#evidence">源码依据与笔记</a>']
    body.append('<section id="questions"><header class="section-header"><h2>课后题与个人回答</h2><p>题目来源逐题标明。个人回答在本地保存，建议导出备份。</p></header>')
    include_answers = spec.get('include_answers', False)
    for i, q in enumerate(questions, 1):
        ensure(q['origin'] in {'原题', '改编', '新增'}, 'unknown question origin')
        ensure(not q.get('answer') or include_answers, 'answers forbidden unless include_answers is explicitly true')
        if q['origin'] != '新增':
            ensure(q.get('evidence') and q.get('original'), 'original/adapted questions need evidence and original text')
        evidence = q.get('evidence')
        cite = html.escape(q.get('source_note', '本课补充'))
        if evidence:
            original_text = read(evidence['path']).splitlines()
            a, b = evidence['start'], evidence['end']
            ensure(type(a) is int and type(b) is int and 1 <= a <= b <= len(original_text), 'question source lines out of bounds')
            excerpt = '\n'.join(original_text[a-1:b])
            ensure(not q.get('original') or q['original'] in excerpt, f'question {i}: original text absent from cited range')
            cite += f' · {html.escape(evidence["path"])} L{a}–{b}'
        text = html.escape(q['question'])
        body.append(f'<article class="question" id="q{i}"><div class="q-number">{i:02d}</div><div><h3>{html.escape(q["title"])}</h3><p>{text}</p><p class="question-source"><b>{q["origin"]}</b> · {cite}</p>')
        if q['origin'] == '改编':
            body.append('<p class="question-source">原题：' + html.escape(q['original']) + '</p>')
        if include_answers and q.get('answer'):
            body.append('<details><summary>参考答案（本次明确要求）</summary>' + paragraphs(q['answer']) + '</details>')
        body.append(f'<textarea data-save="answer-{i}" aria-label="第 {i} 题个人回答" placeholder="先独立回答，再补源码证据。不会的地方直接写不会。"></textarea></div></article>')
        qmd += [f'## Q{i}｜{q["title"]}', q['question'], f'来源：{q["origin"]} · {q.get("source_note", "本课补充")}' + (f' · {evidence["path"]} L{evidence["start"]}–{evidence["end"]}' if evidence else ''), '我的回答：']
        if include_answers and q.get('answer'):
            qmd += ['参考答案：', '\n\n'.join(q['answer']) if isinstance(q['answer'], list) else q['answer']]
    body.append('</section>')
    files = {path: dict(sha256=hashlib.sha256(source_path(root, path).read_bytes()).hexdigest(), lines=len(text.splitlines())) for path, text in sources.items()}
    rows = ''.join(f'<tr><td><code>{html.escape(path)}</code></td><td>{value["lines"]}</td><td><code>{value["sha256"]}</code></td></tr>' for path, value in files.items())
    body.append('<section id="evidence"><header class="section-header"><h2>源码依据与个人笔记</h2></header><div class="prose"><p>文件摘要记录生成时的本地来源。代码摘录与语法检查不等于真实服务或模型质量验收。</p><table><thead><tr><th>来源</th><th>行数</th><th>SHA-256</th></tr></thead><tbody>' + rows + '</tbody></table><p><a href="lesson.md">文本版</a> · <a href="questions.md">课后题</a> · <a href="source-index.json">源码索引</a></p><p>个人回答与笔记仅尝试保存到当前浏览器，本地文件的存储策略因浏览器而异。重要内容请导出备份。</p><textarea data-save="notes" aria-label="个人学习笔记" placeholder="我能解释什么？什么还不理解？实际验证了什么？"></textarea></div></section>')
    css = (ASSETS / 'lesson.css').read_text(encoding='utf-8')
    js = (ASSETS / 'lesson.js').read_text(encoding='utf-8')
    total = core + extra
    if total < 60:
        duration = f'{core}–{total} 分钟' if extra else f'{core} 分钟'
    else:
        duration = f'{core/60:.2f}–{total/60:.2f} 小时' if extra else f'{core/60:.2f} 小时'
        duration = re.sub(r'(\d+)\.00', r'\1', duration)
    document = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title><style>{css}</style></head><body data-question-count="{expected}" data-storage-key="{html.escape(storage, quote=True)}" data-lesson-id="{lesson_id}"><nav><div class="brand">{html.escape(spec.get('project_name',course_id))}</div><div class="edition">SOURCE READING / {lesson_id}<br>源码与讲解对照</div>{''.join(toc)}<div class="nav-foot">离线阅读 · 点击高亮<br>个人答案可导出</div></nav><div class="toolbar"><span>{lesson_id} · 代码与解释逐段对照</span><div class="actions"><button id="wrap">代码折行</button><button id="wide">加宽阅读</button><button id="expand">展开选读</button><button id="export">导出学习笔记</button><button id="print">打印 / 存 PDF</button></div></div><main><header class="hero"><div class="eyebrow">{lesson_id} / SOURCE READING</div><h1>{html.escape(title)}</h1><p>{html.escape(spec.get('subtitle',''))}</p><div class="pills"><span>{duration} · 核心 {core} 分钟</span><span>源码配色与点击高亮</span><span>{expected} 道课后题</span></div></header>{''.join(body)}<footer>learning-code · 源码课程 · 关键设计以红色粗体标记</footer></main><div class="toast" role="status"></div><script>{js}</script></body></html>'''
    manifest = dict(project_id=course_id, lesson_id=lesson_id, title=title, time_budget=timings,
                    question_count=expected, files=files, snippets=snippets,
                    html_sha256=hashlib.sha256(document.encode()).hexdigest())
    return {'lesson.html': document, 'lesson.md': '\n\n'.join(markdown+qmd)+'\n',
            'questions.md': '\n\n'.join(qmd)+'\n',
            'source-index.json': json.dumps(manifest, ensure_ascii=False, indent=2)+'\n'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--check', action='store_true', help='Validate all references and coverage without writing')
    parser.add_argument('--replace', action='store_true', help='Rebuild generated files; make timestamped backups of changed outputs')
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text(encoding='utf-8'))
    outputs = compile_lesson(spec, args.root, args.out)
    if not args.check:
        from datetime import datetime
        import shutil
        conflicts = [name for name, data in outputs.items() if (args.out/name).exists() and (args.out/name).read_text(encoding='utf-8') != data]
        ensure(not conflicts or args.replace, 'generated files already differ; review edits before --replace: ' + ', '.join(conflicts))
        # Never overwrite a source input, including one reached through a symlink.
        sources = json.loads(outputs['source-index.json'])['files']
        resolved_inputs = {source_path(args.root.resolve(), path) for path in sources}
        resolved_inputs.add(args.spec.resolve())
        ensure(not any((args.out/name).resolve() in resolved_inputs for name in outputs), 'output would overwrite a source input')
        args.out.mkdir(parents=True, exist_ok=True)
        if conflicts:
            backup = args.out / 'backups' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
            backup.mkdir(parents=True)
            for name in conflicts:
                shutil.copy2(args.out/name, backup/name)
        for name, data in outputs.items():
            # The containing directory was explicitly chosen; refuse existing
            # output symlinks so a rebuild cannot redirect writes elsewhere.
            ensure(not (args.out/name).is_symlink(), 'output file must not be a symlink: ' + name)
        for name, data in outputs.items():
            (args.out/name).write_text(data, encoding='utf-8')
    manifest = json.loads(outputs['source-index.json'])
    print(json.dumps(dict(status='checked' if args.check else 'rendered', cards=len(manifest['snippets']),
                         steps=sum(len(x['steps']) for x in manifest['snippets']), questions=manifest['question_count'], output=str(args.out.resolve())), ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError, SyntaxError) as error:
        raise SystemExit(f'learning-code: {error}') from error
