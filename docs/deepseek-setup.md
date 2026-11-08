# DeepSeek 本地配置

在仓库根目录将 `.env.example` 复制为 `.env`，在本地填写：

```dotenv
DEEPSEEK_API_KEY=你的真实密钥
DEEPSEEK_API_URL=https://api.deepseek.com
```

不要把密钥写入报告、日志、代码或聊天。`.env` 和 `.env.DeepSeek` 已被 Git 忽略。
加载顺序是 `.env`、`.env.DeepSeek`；后者如存在会覆盖前者。请从仓库根目录运行脚本。

2026-10-31 已通过官方 `/models` 接口验证 `deepseek-flash` 可用。模型用命令行指定，
仅在 `.env` 添加 `MODEL` 并不会更改本项目的模型选择。官方文档：
<https://api-docs.deepseek.com/api/list-models/>

本期来源富集、ROR 规范化及断点评估入口：

```bash
python -u -B scripts/process_bulletin_week.py \
  --start-date 2026-10-25 --date 2026-10-31 \
  --model deepseek-flash --workers 20
```

应先完成语料组装、日期核验、摘要补查和跨期去重，再执行评估。
本机可用解释器为 `/home/zhaoji/miniforge3/envs/crawler/bin/python`。
