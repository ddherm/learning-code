# learning-code

**把项目源码变成能点击、能追踪、能练习的中文课程。**

简体中文 · [English](README.en.md)

`learning-code` 是一个面向 Codex 的源码教学 skill。它让助手沿真实调用链阅读项目，再把一节课整理成可离线阅读的 HTML：左侧保留源码，右侧解释代码；点击任一解释，对应代码行会高亮并滚动到视野中。

适合接手陌生项目、按课学习框架，以及从实现细节准备技术面试。课程默认使用中文，英文介绍不代表课程界面已有完整英文版本。

![合成示例：点击右侧解释，高亮左侧对应源码](docs/preview.png)

上图来自仓库内的合成示例，展示逐条解释与源码高亮的对应关系。

## 学到什么，怎么学

- **沿调用链理解实现**：先给课程总览和贯穿问题，再讲前置概念、成功与失败路径、小实验及知识迁移。
- **源码与解释一一对应**：按“关键代码 → 逐行／分组含义 → 调用关系／作用”带读。每条解释独立换行、独立定位，关键设计使用红色粗体。
- **保留真实代码**：从本地文件摘取，保留缩进和行号；复制时只复制源码。Python 使用词法配色，JS／TS／JSON／Vue 使用轻量配色；不承诺完整 IDE 语义高亮。
- **按学习节奏组织**：默认 3–5 小时，包含 180 分钟核心内容和最多 120 分钟选读。长函数可拆卡，次要分支可折叠。
- **用题目检验理解**：默认 10 道不附答案的题目，优先使用指定面经，标明原题、改编或新增及来源。
- **边读边记录**：支持键盘定位、原文复制、个人笔记与回答导出。笔记使用浏览器存储，重要内容请导出备份。

生成脚本负责摘录、校验和排版。课程解释、题目选择和设计判断需要助手结合项目完成；单独运行脚本不会自动理解整个仓库。

## 安装到 Codex

将仓库克隆到尚不存在的技能目录：

```bash
mkdir -p ~/.codex/skills
git clone https://github.com/ddherm/learning-code.git ~/.codex/skills/learning-code
```

如果目标目录已经有 `learning-code`，先检查已有版本和本地修改，再决定如何合并更新，不要直接覆盖。使当前 Codex 会话重新加载技能后，即可调用。

生成 HTML 需要 **Python 3.9+**，只使用标准库。浏览器自动检查是可选步骤，另需 Node.js、Playwright 和可用的 Chromium／Edge 浏览器；仓库不自动安装这些依赖。

## 使用方式

在能读取项目文件的 Codex 会话里提供项目路径、课纲和课程编号。例如：

```text
使用 $learning-code，按照当前项目 tutorial.md 生成第 2 节课的中文教学 HTML。
课时控制在 3–5 小时，覆盖本节完整调用链和异常分支。
保留双栏源码解读，每条说明点击后高亮对应代码。
十道课后题优先从 interview.md 选择，标明来源，先不附答案。
最后补小实验、知识迁移和自测清单。
```

没有课纲时，也可以先限定一个具体入口或主题：

```text
使用 $learning-code，围绕当前项目的 HTTP 请求入口安排第一节课。
从参数校验追踪到服务调用与返回结果；说明前置知识和下一课边界。
```

默认交付包括 `lesson.html`、可编辑的 `lesson.json`、文本版、题目文件、源码索引和验证记录。渲染器本身固定生成下面四个文件，其余由课程作者维护。

| 文件 | 用途 |
| --- | --- |
| `lesson.html` | 自包含交互课程，可离线阅读 |
| `lesson.md` | 便于检索、比较和再编辑的文本版 |
| `questions.md` | 带来源说明的课后题 |
| `source-index.json` | 源码范围、摘要与题目来源索引 |

## 先运行合成示例

在仓库根目录运行，不需要模型、API 密钥或真实项目：

```bash
python3 scripts/render_lesson.py \
  --spec assets/example/lesson.json \
  --root assets/example \
  --out /tmp/learning-code-example
```

用浏览器打开 `/tmp/learning-code-example/lesson.html`。这个示例包含三张源码卡和三道题，用于体验格式与交互，不是一节完整的三小时课程。

制作正式课程时，先阅读 [教学规范](references/pedagogy.md) 和 [数据格式](references/lesson-format.md)，以示例 JSON 为结构参考，填入经过核对的教学内容和项目内相对路径。

```bash
python3 scripts/render_lesson.py \
  --spec /path/to/lesson.json \
  --root /path/to/project \
  --out /path/to/course
```

`--check` 只校验，不写文件。已有生成文件发生变化时，脚本会拒绝覆盖；先将需要保留的手改合并回 `lesson.json`，再用 `--replace` 重建，变化的旧成品会备份。

## 验证

运行脚本自检：

```bash
python3 scripts/self_test.py
```

自检使用合成材料，覆盖源码与缩进保真、行号映射、题数、来源、默认不附答案、完整符号覆盖，以及防止覆盖输入等约束。静态校验不能替代对教学内容的审阅。

若环境已有 Playwright 及其 Chromium，可继续检查生成示例的真实交互：

```bash
node scripts/check_browser.cjs \
  --html /tmp/learning-code-example/lesson.html \
  --root assets/example \
  --out /tmp/learning-code-browser-check
```

可选 `--browser /path/to/browser` 指定 Chromium／Edge；如 Node 无法解析已有的 Playwright，设置 `PLAYWRIGHT_MODULE=/path/to/playwright`。检查包含源码匹配、逐项高亮、键盘操作、复制、笔记导出、桌面与窄屏布局，并输出报告和截图。截图仍需要人工查看。[完整验证规范](references/verification.md)

## 仓库结构

```text
SKILL.md                 技能入口与工作流程
agents/openai.yaml       Codex 展示配置
references/              教学、选题、数据格式、验证和技能协作规范
scripts/render_lesson.py HTML 与文本生成器
scripts/self_test.py     生成器自检
scripts/check_browser.cjs 浏览器交互检查
assets/lesson.css        页面样式
assets/lesson.js         定位、笔记和导出交互
assets/example/         合成源码、面经和课程示例
evals/evals.json         技能行为评估场景
```

## 可选协作技能

`project-guide` 可帮助安排课程与确认调用链；`interview` 可在用户需要时接续模拟面试；浏览器、PDF、Word 和交互图解技能可处理对应交付需求。这些技能没有随本仓库打包，也不是渲染器运行依赖，按当前环境与任务需要选用。见 [协作入口](references/skill-routing.md)。

HTML 渲染器不调用模型、不启动服务，也不修改生产源码；生成课程的助手及其运行平台会按各自机制处理提供的材料。课程 HTML 包含摘录的源码和题目材料，公开分享前应检查内容与分享权限。生成课程默认不发布到外部网站。
