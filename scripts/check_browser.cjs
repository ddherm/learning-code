#!/usr/bin/env node
'use strict';

// Browser acceptance checks for an offline learning-code lesson.
// This process only reads the source tree. Reports, downloads and screenshots
// go to --out. The browser uses a fresh context; clipboard writes are intercepted.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const { pathToFileURL } = require('node:url');

const usage = `Usage: node check_browser.cjs --html PATH --root PATH --out DIR [--browser PATH]

Requires Playwright. Set PLAYWRIGHT_MODULE to an installed Playwright module
directory if require('playwright') cannot resolve it. No dependencies are installed.
Omit --browser to use Playwright's installed Chromium, or pass a Chromium/Edge
executable. All HTTP(S) requests are blocked and cause the check to fail.
The HTML must declare data-question-count on <body>. Optional empty UI sections
(questions, folded source, notes) are recorded as skipped rather than assumed.
`;

function argumentsFrom(argv) {
  if (argv.includes('--help') || argv.includes('-h')) {
    process.stdout.write(usage);
    process.exit(0);
  }
  const result = {};
  for (let index = 0; index < argv.length; index += 2) {
    const name = argv[index];
    if (!['--html', '--root', '--out', '--browser'].includes(name)
        || !argv[index + 1] || argv[index + 1].startsWith('--')) {
      throw new Error(`Invalid or incomplete argument: ${name}\n${usage}`);
    }
    if (result[name.slice(2)]) throw new Error(`Repeated argument: ${name}`);
    result[name.slice(2)] = path.resolve(argv[index + 1]);
  }
  for (const name of ['html', 'root', 'out']) {
    if (!result[name]) throw new Error(`Missing --${name}\n${usage}`);
  }
  result.root = fs.realpathSync(result.root);
  assert.ok(fs.statSync(result.root).isDirectory(), '--root must be a directory');
  assert.ok(fs.statSync(result.html).isFile(), '--html must be a file');
  return result;
}

let options;
try {
  options = argumentsFrom(process.argv.slice(2));
} catch (error) {
  console.error(String(error));
  process.exit(2);
}
fs.mkdirSync(options.out, { recursive: true });
const report = {
  html: options.html,
  root: options.root,
  timestamp: new Date().toISOString(),
  checks: [],
  screenshots: [],
  errors: [],
  httpRequests: [],
  notes: [
    'Fresh temporary browser context; local file URL; all HTTP(S) requests blocked.',
    'Clipboard API arguments are captured without changing the system clipboard.',
    'Source line endings are normalized to LF as in HTML; indentation and blank lines are compared exactly.',
    'Empty optional UI sections are reported as skipped. Source code and lesson files are not modified.',
  ],
};
const sourceHashes = new Map();
const sha = filename => crypto.createHash('sha256').update(fs.readFileSync(filename)).digest('hex');
const pass = (name, details = {}) => report.checks.push({ name, status: 'pass', ...details });
const skip = (name, reason) => report.checks.push({ name, status: 'skip', reason });
let browser;

function sourcePath(relativePath) {
  assert.equal(typeof relativePath, 'string', 'Missing source path');
  assert.ok(relativePath && !path.isAbsolute(relativePath), `Source path must be relative: ${relativePath}`);
  const lexical = path.resolve(options.root, relativePath);
  const isInside = filename => {
    const relative = path.relative(options.root, filename);
    return relative !== '' && relative !== '..' && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative);
  };
  assert.ok(isInside(lexical), `Source path escapes --root: ${relativePath}`);
  const resolved = fs.realpathSync(lexical);
  assert.ok(isInside(resolved), `Source symlink escapes --root: ${relativePath}`);
  assert.ok(fs.statSync(resolved).isFile(), `Source is not a regular file: ${relativePath}`);
  return resolved;
}

function sourceLines(filename) {
  const text = fs.readFileSync(filename, 'utf8');
  const lines = text.split(/\r\n|\n|\r/);
  if (/(?:\r\n|\n|\r)$/.test(text)) lines.pop();
  return text.length ? lines : [];
}

async function main() {
  let chromium;
  try {
    ({ chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright'));
    assert.ok(chromium && typeof chromium.launch === 'function');
  } catch (error) {
    throw new Error('Playwright is unavailable. Use an existing installation via PLAYWRIGHT_MODULE, '
      + 'or make playwright resolvable by Node. This checker does not install packages. '
      + `Original error: ${error.message}`);
  }
  try {
    browser = await chromium.launch({ headless: true, ...(options.browser ? { executablePath: options.browser } : {}) });
  } catch (error) {
    throw new Error('Cannot launch the browser. Supply --browser with an installed Chromium/Edge executable, '
      + `or use an existing Playwright Chromium installation. Original error: ${error.message}`);
  }
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1100 },
    reducedMotion: 'reduce',
    acceptDownloads: true,
    serviceWorkers: 'block',
  });
  await context.route(/^https?:\/\//, async route => {
    report.httpRequests.push(route.request().url());
    await route.abort();
  });
  await context.addInitScript(() => {
    window.__learningCodeCopies = [];
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: async text => { window.__learningCodeCopies.push(text); } },
    });
  });
  const page = await context.newPage();
  page.setDefaultTimeout(15000);
  page.on('pageerror', error => report.errors.push(String(error)));
  await page.goto(pathToFileURL(options.html).href, { waitUntil: 'load' });
  const screenshot = async name => {
    const filename = path.join(options.out, name);
    await page.screenshot({ path: filename });
    report.screenshots.push(filename);
  };
  await screenshot('desktop-top.png');

  const cards = await page.locator('article.code-card').evaluateAll(nodes => nodes.map(node => ({
    id: node.id,
    path: node.dataset.path,
    start: Number(node.dataset.start),
    end: Number(node.dataset.end),
    lines: [...node.querySelectorAll('.line-src')].map(line => line.textContent),
    rows: [...node.querySelectorAll('.code-line')].map(line => ({ id: line.id, line: Number(line.dataset.line) })),
  })));
  assert.ok(cards.length > 0, 'No source code cards found');
  assert.equal(new Set(cards.map(card => card.id)).size, cards.length, 'Code card IDs must be unique');
  for (const card of cards) {
    assert.ok(card.id, 'Code card is missing an ID');
    assert.ok(Number.isInteger(card.start) && Number.isInteger(card.end)
      && card.start > 0 && card.end >= card.start, `${card.id}: invalid source range`);
    const filename = sourcePath(card.path);
    const lines = sourceLines(filename);
    sourceHashes.set(filename, sha(filename));
    assert.ok(card.end <= lines.length, `${card.id}: source range exceeds the file`);
    assert.deepEqual(card.lines, lines.slice(card.start - 1, card.end), `${card.id}: displayed source differs`);
    assert.deepEqual(card.rows, Array.from({ length: card.end - card.start + 1 }, (_, index) => {
      const line = card.start + index;
      return { id: `${card.id}-L${line}`, line };
    }), `${card.id}: source row IDs or line numbers differ`);
  }
  pass('Every displayed source line matches its file exactly', {
    cards: cards.length,
    displayedLines: cards.reduce((count, card) => count + card.lines.length, 0),
    sourceFiles: sourceHashes.size,
  });

  const declaredCount = await page.locator('body').getAttribute('data-question-count');
  assert.ok(/^(?:0|[1-9]\d*)$/.test(declaredCount || ''), 'body[data-question-count] must be a nonnegative integer');
  const questionCount = await page.locator('.question').count();
  assert.equal(questionCount, Number(declaredCount), 'Question count differs from lesson metadata');
  pass('Question count matches lesson metadata', { questions: questionCount });

  const mappings = await page.locator('.explanation-step').evaluateAll(nodes => nodes.map(button => {
    const card = button.closest('article.code-card');
    return {
      tag: button.tagName,
      cardId: card?.id,
      start: Number(card?.dataset.start),
      end: Number(card?.dataset.end),
      lines: button.dataset.lines,
      controls: button.getAttribute('aria-controls'),
      pressed: button.getAttribute('aria-pressed'),
    };
  }));
  for (const [index, mapping] of mappings.entries()) {
    assert.equal(mapping.tag, 'BUTTON', `Step ${index + 1} must be a native button`);
    assert.ok(mapping.cardId, `Step ${index + 1} is outside a source card`);
    assert.ok(/^[1-9]\d*(?:-[1-9]\d*)?(?:,[1-9]\d*(?:-[1-9]\d*)?)*$/.test(mapping.lines || ''),
      `Step ${index + 1} has an invalid data-lines range`);
    const expected = [];
    for (const range of mapping.lines.split(',')) {
      const [start, end = start] = range.split('-').map(Number);
      assert.ok(start <= end && start >= mapping.start && end <= mapping.end,
        `Step ${index + 1} is outside its own source card`);
      for (let line = start; line <= end; line++) expected.push(`${mapping.cardId}-L${line}`);
    }
    assert.equal(new Set(expected).size, expected.length, `Step ${index + 1} repeats a source line`);
    assert.deepEqual((mapping.controls || '').split(/\s+/), expected, `Step ${index + 1}: aria-controls differs`);
    assert.equal(mapping.pressed, 'false', `Step ${index + 1}: expected an initial unselected state`);
  }
  const missingTargets = await page.evaluate(() => {
    const issues = [];
    for (const button of document.querySelectorAll('.explanation-step')) {
      for (const id of button.getAttribute('aria-controls').split(/\s+/)) {
        const matches = [...document.querySelectorAll('[id]')].filter(node => node.id === id);
        if (matches.length !== 1 || matches[0].closest('article.code-card') !== button.closest('article.code-card')) {
          issues.push(id);
        }
      }
    }
    return issues;
  });
  assert.deepEqual(missingTargets, [], 'Targets must be unique and belong to the same source card');
  const unlinkedGroups = await page.locator('.explanation').evaluateAll(nodes => nodes.filter(node =>
    [...node.querySelectorAll('strong')].some(label => /^逐行(?:\/分组)?含义：$/.test(label.textContent.trim()))
      && !node.querySelector('.explanation-step')).length);
  assert.equal(unlinkedGroups, 0, 'Some line-explanation groups have no clickable steps');
  pass('All explanation ranges, row ownership and ARIA targets agree', { buttons: mappings.length });

  const detailsCount = await page.locator('details').count();
  const sourceDetailsCount = await page.locator('details.source-detail').count();
  const expand = page.locator('#expand');
  async function allDetailsOpen() {
    if (await page.locator('details:not([open])').count()) {
      assert.equal(await expand.count(), 1, 'Folded content requires an #expand control');
      await expand.click();
      assert.equal(await page.locator('details:not([open])').count(), 0, 'Expand did not reveal every optional section');
    }
  }
  if (sourceDetailsCount) {
    assert.equal(await page.locator('details.source-detail[open]').count(), 0, 'Optional source must initially be folded');
  }
  await allDetailsOpen();
  if (mappings.length) {
    const clicked = await page.evaluate(() => {
      let count = 0;
      for (const button of document.querySelectorAll('.explanation-step')) {
        button.click();
        const expected = button.getAttribute('aria-controls').split(/\s+/).sort();
        const actual = [...document.querySelectorAll('.code-line.is-highlighted')].map(line => line.id).sort();
        if (JSON.stringify(expected) !== JSON.stringify(actual)) throw new Error(`Wrong highlighted range in ${button.closest('article').id}`);
        if (document.querySelectorAll('.explanation-step[aria-pressed="true"]').length !== 1
            || button.getAttribute('aria-pressed') !== 'true') throw new Error('Selected step is not unique');
        count++;
      }
      return count;
    });
    pass('Every step highlights exactly its target set and clears previous selections', { buttons: clicked });
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('.code-line.is-highlighted').count(), 0);
    const first = page.locator('.explanation-step').first();
    await first.click();
    assert.equal(await first.getAttribute('aria-pressed'), 'true');
    await first.click();
    assert.equal(await page.locator('.code-line.is-highlighted').count(), 0);
    assert.equal(await first.getAttribute('aria-pressed'), 'false');
    for (const key of ['Enter', 'Space']) {
      await first.focus();
      await page.keyboard.press(key);
      assert.equal(await first.getAttribute('aria-pressed'), 'true', `${key} did not select a step`);
      await page.keyboard.press('Escape');
      assert.equal(await first.getAttribute('aria-pressed'), 'false', 'Escape did not deselect the step');
      assert.equal(await page.locator('.code-line.is-highlighted').count(), 0);
    }
    pass('Mouse toggle, Enter, Space and Escape work');
    const scrollStepIndex = mappings.reduce((best, mapping, index) =>
      mapping.end - mapping.start > mappings[best].end - mappings[best].start ? index : best, 0);
    await page.locator('.explanation-step').nth(scrollStepIndex).click();
    const position = await page.locator('.code-line.is-highlighted').first().evaluate(line => ({
      top: line.getBoundingClientRect().top,
      bottom: line.getBoundingClientRect().bottom,
      height: innerHeight,
      toolbar: document.querySelector('.toolbar')?.getBoundingClientRect().bottom || 0,
    }));
    assert.ok(position.top >= Math.max(0, position.toolbar) - 2 && position.bottom <= position.height + 2,
      `Selected code did not scroll into view: ${JSON.stringify(position)}`);
    await screenshot('desktop-code-highlight.png');
    await page.keyboard.press('Escape');
    pass('Selected code scrolls into the visible viewport', { position });
  } else {
    skip('Explanation interaction checks', 'No clickable explanation steps in this lesson');
  }

  // The Clipboard API mock returns immediately, so invoking copy buttons here
  // captures their intended payload without putting anything on the clipboard.
  const copied = await page.evaluate(async () => {
    const results = [];
    for (const card of document.querySelectorAll('article.code-card')) {
      const button = card.querySelector('.copy');
      if (!button) throw new Error(`Missing copy button in ${card.id}`);
      const before = window.__learningCodeCopies.length;
      button.click();
      await Promise.resolve();
      results.push({ id: card.id, copies: window.__learningCodeCopies.slice(before) });
    }
    return results;
  });
  assert.deepEqual(copied, cards.map(card => ({ id: card.id, copies: [card.lines.join('\n')] })),
    'Copy must preserve source indentation and blank lines, without line numbers');
  pass('All copy buttons preserve source exactly; clipboard remains untouched', { buttons: copied.length });

  if (detailsCount) {
    await expand.click();
    assert.equal(await page.locator('details[open]').count(), 0, 'Collapse did not close every optional section');
    const detail = page.locator('details').filter({ has: page.locator('.explanation-step') }).first();
    if (await detail.count()) {
      await detail.locator('summary').first().click();
      assert.equal(await detail.getAttribute('open'), '');
      const step = detail.locator('.explanation-step').first();
      await step.click();
      assert.equal(await step.getAttribute('aria-pressed'), 'true');
      await page.keyboard.press('Escape');
    }
    pass('Batch expand/collapse and individually opened source explanations work', { details: detailsCount });
  } else {
    skip('Folded source checks', 'No optional details elements in this lesson');
  }

  const savedFields = page.locator('textarea[data-save]');
  const savedCount = await savedFields.count();
  if (savedCount) {
    const keys = await savedFields.evaluateAll(nodes => nodes.map(node => node.dataset.save));
    assert.ok(keys.every(Boolean) && new Set(keys).size === keys.length, 'Saved field keys must be nonempty and unique');
    const expected = [];
    for (let index = 0; index < savedCount; index++) {
      const value = `Learning-code QA ${index + 1}: 保存与导出\n保留换行与缩进  ${index + 1}。`;
      await savedFields.nth(index).fill(value);
      expected.push(value);
    }
    await page.reload({ waitUntil: 'load' });
    assert.deepEqual(await savedFields.evaluateAll(nodes => nodes.map(node => node.value)), expected,
      'Notes or answers were not restored after reload');
    assert.equal(await page.locator('#export').count(), 1, 'Saved fields require an #export control');
    const pendingDownload = page.waitForEvent('download');
    await page.locator('#export').click();
    const download = await pendingDownload;
    const exportPath = path.join(options.out, `export-${path.basename(download.suggestedFilename())}`);
    await download.saveAs(exportPath);
    const exported = fs.readFileSync(exportPath, 'utf8');
    for (const value of expected) assert.ok(exported.includes(value), 'Export omits a saved field or changes its value');
    pass('Every note/answer survives reload and is included in export', { fields: savedCount, export: exportPath });
  } else {
    skip('Notes persistence and export checks', 'No textarea[data-save] elements in this lesson');
  }

  const overflow = async label => {
    const dimensions = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: innerWidth }));
    assert.ok(dimensions.scroll <= dimensions.width, `${label}: whole-page horizontal overflow ${JSON.stringify(dimensions)}`);
    return dimensions;
  };
  await allDetailsOpen();
  await overflow('Desktop, all optional sections open');
  for (const [id, className] of [['wrap', 'wrap-code'], ['wide', 'full-width']]) {
    const button = page.locator(`#${id}`);
    assert.equal(await button.count(), 1, `Missing #${id} control`);
    const before = await page.locator('body').evaluate((node, name) => node.classList.contains(name), className);
    await button.click();
    assert.equal(await page.locator('body').evaluate((node, name) => node.classList.contains(name), className), !before);
    await overflow(`Desktop ${id} enabled`);
    await button.click();
    assert.equal(await page.locator('body').evaluate((node, name) => node.classList.contains(name), className), before);
    await overflow(`Desktop ${id} restored`);
  }
  pass('1440 px desktop, all optional sections, wrap and wide modes have no page overflow');

  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => scrollTo(0, 0));
  await screenshot('mobile-top.png');
  await allDetailsOpen();
  const mobileDimensions = await overflow('390 px mobile with all optional sections open');
  if (mappings.length) {
    const step = page.locator('.explanation-step').first();
    await step.click();
    assert.equal(await step.getAttribute('aria-pressed'), 'true');
    const bounds = await page.locator('.code-line.is-highlighted').first().boundingBox();
    assert.ok(bounds && bounds.y >= -2 && bounds.y + bounds.height <= 846, 'Mobile highlighted line is outside the viewport');
    await screenshot('mobile-code-highlight.png');
    await page.keyboard.press('Escape');
  }
  if (questionCount) {
    await page.locator('.question').last().scrollIntoViewIfNeeded();
    await screenshot('mobile-last-question.png');
  }
  pass('390 px mobile has no page overflow with all optional sections open', { dimensions: mobileDimensions });

  assert.deepEqual(report.errors, [], 'JavaScript errors were reported');
  assert.deepEqual(report.httpRequests, [], 'The offline document attempted HTTP(S) requests');
  for (const [filename, hash] of sourceHashes) assert.equal(sha(filename), hash, `Source changed during QA: ${filename}`);
  pass('No JavaScript errors, no HTTP(S) requests, no source file changes');
  report.status = 'pass';
}

main().catch(error => {
  report.status = 'fail';
  report.failure = { message: String(error), stack: error.stack };
  process.exitCode = 1;
}).finally(async () => {
  if (browser) await browser.close().catch(error => {
    report.errors.push(`Browser close: ${error}`);
    report.status = 'fail';
    process.exitCode = 1;
  });
  fs.writeFileSync(path.join(options.out, 'report.json'), `${JSON.stringify(report, null, 2)}\n`);
  console.log(JSON.stringify(report, null, 2));
});
