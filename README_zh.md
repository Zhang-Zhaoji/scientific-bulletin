# 神经科学通报

**注意：部分代码由 Kimi K2.5 模型和其他大语言模型生成，可能包含幻觉内容，请谨慎使用。**

本项目致力于打造一个神经科学领域的微信公众号内容平台，自动追踪最新的神经科学研究论文并分享给读者。我们提供完整的端到端处理流水线：
- 🕷️ 从15+顶级神经科学相关期刊和预印本服务器爬取论文标题、摘要和元数据
- 🔍 使用欧洲PMC和ROR（研究机构注册表）对论文进行摘要和机构信息富集
- 💾 将所有处理后的数据存储在SQLite数据库中，方便查询和分析
- 🤖 使用多个大语言模型（通义千问3.5-plus、豆包-Seed-1.8_TPM、DeepSeek-V3.2）对论文进行总结并生成每周研究报告
- 📊 生成全球科研产出、国家分布和论文统计的数据可视化图表

目前已发布6期内容，所有内容汇总在知乎专栏【神经科学快讯】：https://www.zhihu.com/column/c_2016331747525157941
最新一期（第六期）：https://zhuanlan.zhihu.com/p/2028897146196206750

本仓库包含神经科学通报项目的所有代码和数据，我们希望将项目开源并惠及更多研究者。如果您有任何问题或建议，欢迎联系我们。

---

## 🚀 快速开始

### 环境依赖

```bash
# 核心爬虫依赖
pip install requests beautifulsoup4 jsonlines python-dateutil tqdm selenium

# 数据富集和数据库依赖
pip install pandas numpy sqlite3

# LLM处理依赖
pip install openai tiktoken

# 可视化依赖
pip install plotly matplotlib seaborn
```

### 使用方法

```bash
# 从所有来源抓取论文（默认最近7天）
python src/main.py

# 仅从arXiv和bioRxiv抓取预印本
python src/main.py --arxiv-only --biorxiv-only

# 抓取最近14天的论文（适用于所有来源）
python src/main.py --days 14

# 使用ROR对论文进行机构信息富集
python src/batch_enrich_authors.py

# 从处理后的论文构建SQLite数据库
python sql_scripts/build_sqlite.py

# 生成LLM总结和报告
python LLM_eval/main.py

# 生成数据可视化图表
python visualize/main.py
```

更多爬虫选项请查看 `python src/main.py --help`。

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
| Nature Reviews Neuroscience | ✅ |
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
| **Scientific Reports** | ✅ 已支持 | PubMed API |

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

---

## 💾 SQLite数据库

所有处理后的论文都存储在SQLite数据库中，用于高效查询和分析：
- 数据库Schema支持所有论文元数据、富集信息和机构数据
- 支持按日期、来源、期刊、国家、关键词快速查询
- 与可视化和LLM处理模块深度集成
- 自动对多来源重复论文进行去重

---

## 🤖 LLM分析与报告生成

我们使用多个大语言模型处理收集到的论文：
- **支持的模型**：通义千问3.5-plus、豆包-Seed-1.8_TPM、DeepSeek-V3.2
- **核心功能**：
  - 将论文摘要总结为简洁易懂的亮点
  - 按研究主题对论文分类（认知神经科学、分子神经科学、临床神经科学等）
  - 生成适合微信公众号和知乎的每周研究报告
  - 支持自定义Prompt模板以适应不同场景
- **输出格式**：结构化JSON分析结果、格式化Markdown报告

---

## 📊 数据可视化

内置可视化模块用于分析研究趋势：
- **全球热力图**：可视化不同国家/地区的科研产出分布
- **国家分布饼图**：展示不同国家论文数量占比
- **论文评分直方图**：论文影响力指标的统计分布
- **输出格式**：静态PNG图片、交互式HTML图表
- 所有可视化内容会作为每周流水线的一部分自动生成

---

## 📁 项目结构

```
.
├── src/                          # 核心爬虫和数据富集代码
│   ├── main.py                  # 爬虫主入口
│   ├── main_beta.py             # 测试版爬虫
│   ├── crawler_*.py             # 15+期刊/预印本服务器的独立爬虫
│   ├── enrich_papers.py         # 一级论文富集（从欧洲PMC获取摘要、PMID/PMCID）
│   ├── enrich_authors.py        # 使用ROR数据对作者机构信息富集
│   ├── batch_enrich_authors.py  # ROR富集批量处理
│   ├── ror_refine_batch.py      # ROR数据优化
│   ├── supp_func.py             # 支持函数
│   └── utils.py                 # 工具函数
├── LLM_eval/                     # LLM分析和报告生成模块
│   ├── main.py                  # LLM处理主入口
│   ├── call_API.py              # 通义千问、豆包、DeepSeek的LLM API客户端
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
- 论文主题分类模型
- 数据库高级搜索功能
- 改进的LLM总结提示词
- 更多可视化选项（研究趋势折线图、机构排名）
- 微信公众号自动发布

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
