# lesson.json 与通用生成脚本

## 最短运行路径

生成器仅需要 Python 3.9+ 标准库，不依赖 Markdown 库、CDN 或在线字体。将 `<skill>` 替换为当前 skill 的目录：

```bash
python3 <skill>/scripts/render_lesson.py --spec <skill>/assets/example/lesson.json --root <skill>/assets/example --out /tmp/learning-code-example
```

实际课程用项目根目录替换 `--root`；例子只是检查结构与交互，不是完整课程的教学内容标准。

固定生成四个文件：`lesson.html`、`lesson.md`、`questions.md`、`source-index.json`。源 lesson.json 由作者保存；文本版允许内嵌 HTML，代码保留 fenced blocks。`--check` 只核验不写入；`--replace` 在备份变化的成品后重建，只有读过并合并用户修改后才使用。

## 顶层字段

| 字段 | 含义 |
|---|---|
| project_id | 稳定 ASCII 标识，用于笔记隔离，不使用机器路径 |
| project_name | 展示名称，可中文 |
| lesson_id | 如 C03；与 project_id 组成持久化键 |
| title / subtitle | 课程主题与目标 |
| notes_version | 默认 1；普通文字修正不改，避免笔记看似丢失 |
| time_budget | core_minutes 与 optional_minutes，默认 180、120 |
| question_count | 默认 10；例子可显式改为 2 或 3，实际按用户要求 |
| sections | 有序章节列表，每项含 id、title、subtitle（可省）、blocks |
| required_symbols | 需要证明完整摘录的 Python 符号列表：path＋symbol |
| questions | 主问题数组，与 question_count 一致 |
| include_answers | 默认 false；仅用户明确要答案时设 true |

所有 ID 仅用 ASCII 字母、数字、短横线、下划线。源码路径相对 `--root`；拒绝绝对路径、越根路径和指向根外的符号链接。若多个项目需要比较，可设置合理的共同父目录，仍只引用核查过的文件。

## 正文 prose block

```json
{"kind":"prose","html":"<h3>本课要思考什么</h3><p>从调用入口追到结果，标出每次等待。</p>"}
```

HTML 只用于作者审核后的讲义，不直接灌入源文件或外部网页。支持段落、h3/h4、列表、表格、代码、链接、引用、div/span。禁止脚本、iframe、事件属性和远端图片。正文不需要再经过 Markdown 转换。

表格尽量不超过 4 列；长标识可以用 code。关键设计使用 `<strong class="critical">面试关键设计｜……</strong>`。普通强调不用全部标红。

## 代码 code block

```json
{
  "kind":"code", "title":"输入为什么变成这个请求",
  "path":"service.py", "start":12, "end":30,
  "key":["指出这段关键动作。"],
  "steps":[
    {"ranges":[[12,15]],"paragraphs":["第一句解释这组代码。","第二句说明条件或数据变化。"]},
    {"ranges":[[17,20],[24,26]],"paragraphs":["两个不相邻的范围共同解释这一件事。"]}
  ],
  "call":["由谁调用，进入什么函数，返回到哪里。"],
  "critical":"这里的成功状态不等于业务任务已经完成。",
  "optional":false
}
```

- 每个 paragraph 是一个分句／短句，界面单独换行。不要将一整段说明用分号塞进单一字符串。
- 每项 steps 是一个可点击按钮，可对应单行、多行或不连续范围；范围要排序、互不重叠且在本卡内。
- 不从中文“Lxx”文字猜测映射。JSON ranges 是唯一定位数据，按钮标签自动生成。
- 不手抄 source 字段，渲染器从文件提取。行号与缩进不会混进复制的源码。
- Python 可将 start/end 换成 `"symbol":"ClassName.method"`；二者不可同时使用。
- required_symbols 检查所有非空源码行是否被本课全部卡片覆盖；空白分隔行可省，但要准确描述覆盖范围。
- Python 使用 tokenize；JS/TS/JSON/Vue 使用轻量词法配色，其余语言原样转义显示。后者不声称达到完整 VS Code 语义高亮；需要更丰富配色时可接环境已有高亮器，但继续核对原文。

## 题目 questions

```json
{
  "title":"你怎么证明输入正确？",
  "question":"不连接真实服务时如何观察传入客户端的参数？请指出替身能证明和不能证明的边界。",
  "origin":"改编",
  "original":"你怎么测试模型调用？",
  "source_note":"指定面经 · 第 4 题",
  "evidence":{"path":"面经.md","start":28,"end":31}
}
```

原题／改编必须有 original、evidence。original 要保留原文，脚本要求它确实出现在引用范围内；标点与空格的规范化只在 question 中进行。新增题用 `origin: 新增`，source_note 写“本课补充”，不假造外部来源。

脚本只能验证来源存在，不能判断题目是否跑题、原题是否被不当改写或追问是否超范围；这些仍由作者和独立审阅判断。脚本默认拒绝 answer 字段的非空值。用户提供的个人回答不放入 answer 当作标准答案，应保留在个人笔记中。

## 保持成品可重建

保留 JSON、源文件版本／摘要与生成脚本入口。只改 HTML 后再重建会失去手改，所以先同步回 JSON。脚本记录源码与面经摘要；HTML 自包含，复制单个 HTML 即可离线阅读，相关文本版与索引链接需要一并带上。

重建不会主动删除浏览器笔记；更换浏览器、文件 URL 或浏览器存储策略仍可能影响持久化，重要回答用导出备份。打印能力为浏览器打印布局；未检查分页时不要声称已交付排版验证过的 PDF。
