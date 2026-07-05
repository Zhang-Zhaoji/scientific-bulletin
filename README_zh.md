# 神经科学通报

[English](https://github.com/Zhang-Zhaoji/scientific-bulletin) [中文](https://github.com/Zhang-Zhaoji/scientific-bulletin/blob/main/README_zh.md)

**注意：本项目使用AI辅助开发工具（包括 Kimi K2.5、GPT-5.3 Codex、GPT-5.5 等领先大语言模型）进行代码生成。虽然我们已对代码进行审查和测试，但部分组件可能存在意外行为，请谨慎使用并欢迎反馈问题。**

神经科学通报是一个自动化文献策展平台，致力于追踪近期神经科学研究论文并通过微信公众号分享给读者。仓库提供完整的端到端流水线：
- 🕷️ 从18+顶级神经科学相关期刊和预印本服务器爬取论文标题、摘要和元数据（含PLoS Biology、PLoS Computational Biology、PLoS One）
- 🔍 使用欧洲PMC和ROR（研究机构注册表）对论文进行摘要、作者机构和标准机构名称富集
- 💾 将所有处理后的数据存储在SQLite数据库中，方便查询和分析
- 🤖 使用大语言模型对论文进行领域分类、评分、分级推荐和总结，并生成每周Markdown报告与微信公众号格式报告
- 📊 生成全球科研产出、国家分布、机构排名和论文评分统计的数据可视化图表

仓库目前包含2026年3月至7月的每周抓取数据、富集后的JSONL文件、LLM分析结果、报告和配图。本地最新报告产物生成于 **2026-07-05**。公开发布内容汇总在知乎专栏【神经科学快讯】：https://www.zhihu.com/column/c_2016331747525157941

我们已发布 **17期常规周报** 和 **2期特别专题**，涵盖神经科学前沿研究。

本仓库包含神经科学通报项目的所有代码和数据，我们希望将项目开源并惠及更多研究者。如果您有任何问题或建议，欢迎联系我们。

---

## 🚀 快速开始

### 环境依赖

```bash
# 推荐方式
pip install -r requirements.txt

# 核心爬虫依赖
pip install requests beautifulsoup4 jsonlines python-dateutil tqdm selenium

# 数据富集依赖；数据库使用Python内置sqlite3模块
pip install pandas numpy

# LLM处理依赖
pip install openai tiktoken

# 可视化依赖
pip install matplotlib pyecharts snapshot_selenium
```

### 使用方法

```bash
# 从所有来源抓取论文（默认最近8天）
python src/main.py

# 抓取论文，但跳过自动作者/ROR机构富集
python src/main.py --no-auto-enrich

# 增加富集并发数，并检查更多历史期次用于跨期去重
python src/main.py --workers 4 --history-weeks 3

# 仅从arXiv和bioRxiv抓取预印本
python src/main.py --arxiv-only --biorxiv-only

# 仅从PLOS系列期刊抓取（PLoS Biology, PLoS Computational Biology, PLoS One）
python src/main.py --plos-only

# 抓取最近14天的论文（适用于所有来源）
python src/main.py --days 14

# 使用ROR对论文进行机构信息富集
python src/batch_enrich_authors.py

# 从处理后的论文构建SQLite数据库
python sql_scripts/build_sqlite.py

# 从所有每周 JSONL/LLM 输出重建完整 SQLite 数据库
bashScripts/build_sq.bat

# 生成LLM总结和报告
python LLM_eval/main.py

# 使用配置好的平台/模型处理指定的富集JSONL文件
python LLM_eval/main.py -i getfiles/all_papers_2026-05-23_enriched_ror_refined.jsonl

# 临时覆盖配置中的平台/模型
python LLM_eval/main.py --platform Aliyuncs --model qwen3.7-plus

# 生成数据可视化图表
python visualize/main.py

# 从每周 JSONL 生成国家热力图和国家分布饼图
python visualize/global_heatmap.py --jsonl getfiles/all_papers_2026-05-23_enriched_ror_refined.jsonl --date 2026-05-23

# 将生成的Markdown报告构建为静态网页
python scripts/build_pages.py --input-dir LLM_Results --output-dir docs
```

更多爬虫和LLM处理选项请查看 `python src/main.py --help` 与 `python LLM_eval/main.py --help`。LLM平台和默认模型在 `LLM_eval/config.py` 中配置；API key 可以放在 `.env`、`.env.DeepSeek` 或 `.env.Aliyuncs` 中。

---

## 📚 支持的数据源

### 预印本服务器 ✅

| 来源 | 状态 | 说明 |
|--------|--------|-------------|
| **arXiv** | ✅ 已支持 | q-bio.NC、q-bio.TO、q-bio.MN分类 |
| **bioRxiv** | ✅ 已支持 | 所有神经科学相关预印本 |

**arXiv说明**：从三个核心神经科学分类抓取论文：
- **q-bio.NC** - 神经元与认知（主要神经科学方向）
- **q-bio.TO** - 组织与器官（神经组织、类脑器官）
- **q-bio.MN** - 分子网络（分子神经科学）

### Springer Nature 期刊 ✅

| 期刊 | 状态 |
|---------|--------|
| Nature | ✅ |
| Nature Biomedical Engineering | ✅ |
| Nature Methods | ✅ |
| Nature Neuroscience | ✅ |
| Nature Human Behaviour | ✅ |

### 其他期刊 ✅

| 期刊 | 状态 | 实现方法 |
|---------|--------|--------|
| **Science** | ✅ 已支持 | 列表页 + 欧洲PMC数据富集 |
| **Science Advances** | ✅ 已支持 | TOC页面 + Selenium（日期过滤） |
| **PNAS** | ✅ 已支持 | PubMed API |
| **Cell Press** | ✅ 已支持 | Selenium + 欧洲PMC数据富集 |
| **Nature Communications** | ✅ 已支持 | 主题页（生物/健康科学） |
| **Brain** | ✅ 已支持 | PubMed API |
| **eLife** | ✅ 已支持 | PubMed API |
| **Journal of Neurophysiology** | ✅ 已支持 | PubMed（主要） + 欧洲PMC（补充） |
| **Journal of Neuroscience** | ✅ 已支持 | PubMed API（默认过滤Journal Club文章） |
| **Journal of Cognitive Neuroscience** | ✅ 已支持 | PubMed API |
| **Journal of Vision** | ✅ 已支持 | PubMed API |
| **PLoS Biology** | ✅ 已支持 | PubMed API |
| **PLoS Computational Biology** | ✅ 已支持 | PubMed API |
| **PLoS One** | ✅ 已支持 | PubMed API（限制结果数量） |

### Cell Press 期刊 ✅

| 期刊 | 状态 | 实现方法 |
|---------|--------|--------|
| **Cell** | ✅ 已支持 | 当前期目录页 + 欧洲PMC数据富集 |
| **Neuron** | ✅ 已支持 | 当前期目录页 + 欧洲PMC数据富集 |
| **Current Biology** | ✅ 已支持 | 当前期目录页 + 欧洲PMC数据富集 |
| **Trends in Neurosciences** | ✅ 已支持 | 当前期目录页 + 欧洲PMC数据富集 |

**Science说明**：采用智能富集策略：
1. 从Science列表页获取基本信息（无需验证码）
2. 通过DOI从欧洲PMC富集摘要、PMID等信息
3. 如果欧洲PMC未收录，回退到预印本服务器（bioRxiv/arXiv）搜索
4. 如果均未找到，保留原始数据

---

## 🔬 数据富集

### 元数据富集

| 服务 | 用途 |
|---------|---------|
| **欧洲PMC** | 主要富集来源（PubMed摘要、PMC全文、PMID/PMCID） |
| **预印本回退** | 在bioRxiv/arXiv搜索已发表论文的预印本版本 |

### ROR机构信息富集 ✅

我们使用研究机构注册表（ROR）对作者单位信息进行标准化：
- 将机构名称标准化为标准ROR标识符
- 提取所有作者的国家/地区信息
- 生成全球科研产出分布统计
- 支持大规模论文数据集的批处理
- 支持在主爬虫流程中自动完成作者/ROR富集，并可配置并发数和ROR匹配阈值

### 去重与重查

主爬虫可以合并多来源论文，并基于DOI、PMID和标准化标题去重。它还会检查最近若干历史期次，避免重复收录已覆盖论文；对于历史期次中缺少摘要的论文，则会保留重查机会，以便后续补全。

---

## 💾 SQLite数据库

所有处理后的论文都存储在SQLite数据库中，用于高效查询和分析：
- 数据库Schema支持所有论文元数据、富集信息和机构数据
- 支持按日期、来源、期刊、国家、关键词快速查询
- 与可视化和LLM处理模块深度集成
- 自动对多来源重复论文进行去重

---

## 🤖 LLM分析与报告生成

我们使用兼容OpenAI接口的大语言模型处理收集到的论文：
- **默认处理模型**：`deepseek-v4-flash` (DeepSeek) 或 `qwen3.7-plus` (Aliyuncs)，可在 `LLM_eval/config.py` 中配置
- **报告润色脚本模型**：报告脚本中使用 `qwen3.6-flash-2026-04-16`
- **核心功能**：
  - 判断论文属于核心神经科学、高影响跨界、有限跨界或域外内容
  - 对符合条件的论文进行结构化评分并分配推荐等级
  - 将论文摘要总结为简洁易懂的亮点
  - 按研究主题和跨界标签对论文分类
  - 生成适合微信公众号和知乎的每周研究报告
  - 支持自定义Prompt模板以适应不同场景
- **输出格式**：结构化JSON分析结果、格式化Markdown报告、微信公众号格式Markdown报告

---

## 📊 数据可视化

内置可视化模块用于分析研究趋势：
- **全球热力图**：可视化不同国家/地区的科研产出分布
- **国家分布饼图**：展示不同国家论文数量占比
- **论文评分直方图**：论文影响力指标的统计分布
- **机构排名**：生成报告周期内的研究机构TOP表格
- **报告统计文字**：将国家、机构和评分分布统计写入生成的Markdown报告
- **输出格式**：静态PNG图片、交互式HTML图表
- 所有可视化内容会作为每周流水线的一部分自动生成

---

## 🌐 静态网页 / GitHub Pages

报告发布为完整的静态网站，避免受知乎和微信公众号排版规则限制。网站通过 `.github/workflows/pages.yml` 在每次推送到 `main` 时自动构建并部署到 GitHub Pages。

**核心功能：**
- `scripts/build_pages.py` 将 `LLM_Results/report_*.md` 转换成 `docs/` 下的静态站点
- 报告页面嵌入匹配的封面图、国家热力图、国家分布饼图和评分直方图
- 首页为每期报告显示带封面缩略图的列表
- **全文搜索**：独立的搜索页面（`docs/search.html`）基于 MiniSearch 实现客户端模糊搜索，覆盖全部 7000+ 篇论文（标题、摘要、期刊、分类）。搜索结果支持收藏和锚点跳转，点击直接定位到报告中的对应文章
- **浮动目录（TOC）**：每个报告页面自动生成页内目录，便于快速导航
- **收藏夹系统**：读者可以跨报告和搜索结果收藏感兴趣的论文，收藏内容存储在 `localStorage` 中，支持导出为 Markdown 或 `.md` 文件
- **带锚点的论文卡片**：每篇论文渲染为带有元数据（推荐等级、评分、期刊、日期、领域）的卡片，具有 `id` 锚点用于深度链接，并提供原文链接
- 构建脚本使用 Python `markdown` 包及表格/列表扩展，因此 `**加粗**`、Markdown表格等语法会转换为真正的HTML
- 支持特别专题报告（如 `report_*_specialissue.md`），具有自定义布局和嵌入图片
- 如果本地构建提示缺少依赖，请先运行 `python -m pip install markdown` 或 `pip install -r requirements.txt`

**交互式数据看板：**
- 独立的统计看板页面（`docs/dashboard.html`），基于 sql.js + ECharts 实现交互式数据可视化
- 精简版 SQLite 数据库（`literature_slim.db`，约7MB）在浏览器端加载，支持 IndexedDB 缓存，二次访问秒级加载
- **9个可视化模块**：国家发文量热力图、国家平均评分热力图、国家×领域归一化热力图（支持绝对数量/贡献度/专注度三种模式）、评分分布直方图、研究领域雷达图、时间趋势线图、期刊发文量TOP20、机构排名散点图、交叉标签词云
- **交互控件**：日期范围选择器、领域多选筛选、归一化模式切换——所有图表实时联动更新
- 运行 `python sql_scripts/build_slim_db.py` 从 `data/literature.db` 重建精简数据库

---

## 📁 项目结构

```
.
├── .github/workflows/            # GitHub Pages部署工作流
├── src/                          # 核心爬虫和数据富集代码
│   ├── main.py                  # 爬虫主入口
│   ├── crawler_*.py             # 15+期刊/预印本服务器的独立爬虫
│   ├── enrich_papers.py         # 一级论文富集（从欧洲PMC获取摘要、PMID/PMCID）
│   ├── enrich_authors.py        # 使用ROR数据对作者机构信息富集
│   ├── batch_enrich_authors.py  # ROR富集批量处理
│   ├── ror_refine_batch.py      # ROR数据优化
│   ├── supp_func.py             # 支持函数
│   └── utils.py                 # 工具函数
├── LLM_eval/                     # LLM分析和报告生成模块
│   ├── main.py                  # LLM处理主入口
│   ├── call_API.py              # 兼容OpenAI接口的LLM API客户端
│   ├── Summary.py               # 论文总结逻辑
│   ├── Summary_wechat.py        # 微信公众号报告生成
│   ├── StructuredPrompt.py      # LLM提示词模板
│   ├── util.py                  # LLM工具函数
│   └── util_enriched.py         # 富集数据处理工具
├── visualize/                    # 数据可视化模块
│   ├── main.py                  # 可视化主入口
│   ├── dbapi.py                 # 可视化用数据库API
│   ├── global_heatmap.py        # 全球科研产出热力图生成
│   └── vis_stat.py              # 统计图表（直方图、饼图）
├── sql_scripts/                  # SQLite数据库脚本
│   ├── build_sqlite.py          # 数据库构建脚本
│   ├── schema.sql               # 数据库Schema
│   └── sqlfuncs.py              # 数据库工具函数
├── data/                         # 静态数据文件
│   ├── ROR*.json                # 用于机构标准化的研究机构注册表数据
│   ├── *country*.json           # 国家/地区标准化映射
│   ├── literature.db            # 存储所有处理后论文的SQLite数据库
│   └── normalize_country.py     # 国家标准化脚本
├── getfiles/                     # 抓取和处理后的论文数据
│   ├── all_papers_YYYY-MM-DD.jsonl              # 原始抓取的论文
│   ├── all_papers_YYYY-MM-DD_enriched.jsonl     # 经过摘要/元数据富集的论文
│   └── all_papers_YYYY-MM-DD_enriched_ror_refined.jsonl  # 完成全量ROR机构信息富集的论文
├── LLM_Results/                  # LLM输出和生成的报告
│   ├── LLM_results_*.json       # 原始LLM分析结果
│   ├── report_*.md              # 生成的每周研究报告
│   └── report_*_wechat.md       # 微信公众号格式报告
├── Imgs/                         # 可视化输出
│   ├── visulize_img/            # 生成的图表（PNG/HTML格式的热力图、饼图、直方图）
│   └── *.png                    # 每周报告封面图片
├── bashScripts/                  # 构建和流水线脚本
│   ├── build_ror.*              # ROR数据构建脚本
│   ├── build_sql.*              # 数据库构建脚本
│   └── sql_pipeline.bat         # 完整数据流水线脚本
├── logs/                         # 日志文件
├── scripts/                      # 工具脚本
│   ├── build_pages.py           # 静态站点生成器
│   ├── generate_score_histograms.py  # 评分分布可视化
│   └── page_builder/            # 静态站点构建模块
│       ├── core.py              # 核心工具（slugify、日期解析、锚点生成）
│       ├── page.py              # 页面生成（含TOC和收藏夹）
│       ├── articles.py          # 论文卡片渲染（含锚点）
│       ├── favorites.py         # 收藏夹系统（localStorage）
│       ├── search_index.py      # 全文搜索索引 + 搜索页面生成
│       ├── reports.py           # 报告页面生成
│       ├── sources.py           # 来源URL标准化
│       ├── markdown_render.py   # Markdown转HTML
│       ├── styles.py            # CSS样式
│       └── cli.py               # 命令行接口
├── docs/                         # 生成的静态网站（GitHub Pages）
│   ├── index.html               # 报告索引（含缩略图）
│   ├── search.html              # 全文搜索页面（MiniSearch）
│   ├── search-index.js          # 搜索索引数据（JSONP格式）
│   ├── report_*.html            # 各期报告页面
│   └── assets/                  # 静态资源（封面、图表、样式）
├── .gitignore
├── LICENSE
├── README.md                    # 英文说明文档
├── README_zh.md                 # 中文说明文档（本文件）
└── ScriptOnColabNoScience.ipynb  # 用于运行流水线的Colab笔记本
```

---

## 🔧 开发指南

### 测试单个爬虫

```bash
# 测试arXiv爬虫
python src/crawler_arxiv.py

# 测试bioRxiv爬虫
python src/crawler_biorxiv.py
```

### 添加新期刊支持

1. 检查期刊是否提供API或RSS源
2. 在`src/crawler_<journal>.py`创建新的爬虫文件
3. 实现以下接口：
   - `fetch_papers()`：返回论文字典列表，包含键：`title`、`authors`、`date`、`url`、`abstract`
   - `save_papers()`：保存到JSONL文件
4. 在`src/main.py`中添加新爬虫

---

## 📖 数据格式

论文以JSONL格式保存，包含以下字段（富集版本包含额外字段）：

```json
{
  "type": "Article",
  "title": "论文标题",
  "authors": ["作者1", "作者2", "..."],
  "affiliations": ["机构1, 国家1", "..."],
  "ror_ids": ["https://ror.org/xxxxxx", "..."],
  "countries": ["国家1", "..."],
  "date": "DD MMM YYYY",
  "url": "https://...",
  "abstract": "论文摘要...",
  "source": "arXiv|bioRxiv|Nature|...",
  "pdf_url": "https://... (可选)",
  "doi": "10.xxxx/... (可选)",
  "pmid": "xxxxxx (可选)",
  "pmcid": "PMCxxxxxx (可选)"
}
```

---

## ⚠️ 注意事项

### 速率限制

- **arXiv**：没有严格的速率限制，但请合理使用（请求间隔1秒）
- **bioRxiv**：没有公开的速率限制文档
- **Nature/Science**：可能需要请求延迟和User-Agent轮换
- **LLM API**：请遵守各模型提供商的速率限制

### 反爬虫保护

部分出版商（Science、Cell/Elsevier）使用Cloudflare或类似保护机制，我们的应对策略：

1. **优先方案**：尽可能使用官方API（arXiv、bioRxiv、PubMed）
2. **替代方案**：使用PubMed/欧洲PMC获取期刊论文
3. **最后方案**：使用Selenium，必要时手动解决验证码

---

## 🚀 计划功能

我们正在开发更多功能：

**新数据源：**
- PLoS Biology
- PLoS One
- Frontiers in Neuroscience
- Progress in Neurobiology
- Cerebral Cortex
- Annual Review of Neuroscience
- Science Translational Medicine
- Journal of Neural Engineering
- Trends in Cognitive Sciences
- Current Opinion in Neurobiology
- NeuroImage
- Behavioral and Brain Sciences

**增强功能：**
- 引用数和替代计量学指标富集
- 网站跨期过滤和按领域/期刊/评分浏览
- 改进的LLM总结提示词
- 更多可视化选项（研究趋势折线图、作者合作网络）
- 预印本全文PDF提取与OCR深度分析

---

## 🤝 贡献指南

我们欢迎各种形式的贡献！优先方向：

1. 通过PubMed API添加更多期刊支持
2. 提高去重准确率
3. 添加更多元数据富集（引用数、替代计量学指标）
4. 提升LLM总结质量
5. 添加新的可视化类型

---

## 📧 联系方式

如有问题或建议，欢迎提交Issue或联系维护者。

---

## 许可证

本项目开源，详情请查看LICENSE文件。
