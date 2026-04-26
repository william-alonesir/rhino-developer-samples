# 自动下棋脚本（Lichess）

这个示例脚本会自动打开 [https://lichess.org](https://lichess.org) 并尝试在「人机对弈」模式自动走子。

> 仅用于学习自动化与测试。请勿在有禁止自动化规则的对局中使用。

## 环境准备

```bash
python -m venv .venv
source .venv/bin/activate
pip install playwright python-chess
python -m playwright install chromium
```

## 运行

```bash
python automation/auto_lichess_bot.py --level 1 --delay 1.2
```

如果你希望我“接管你自己的 Chrome”来自动执行，需要先启动带远程调试端口的 Chrome：

```bash
google-chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-bot
```

然后运行：

```bash
python automation/auto_lichess_bot.py --cdp-url http://127.0.0.1:9222 --level 1
```

常用参数：

- `--level`：电脑等级（1-8）
- `--delay`：每步基础延迟秒数
- `--headless`：无头模式（不显示浏览器窗口）
- `--cdp-url`：连接你已打开的 Chrome（CDP 地址）

## 说明

- 脚本会优先选择「吃子 / 将军」这类简单战术走法，否则随机合法走子。
- 页面结构变动可能导致脚本失效，可按 `open_vs_ai` 和 DOM 选择器进行调整。
