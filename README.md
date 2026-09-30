# 摸鱼助手 FishMate

Windows 托盘应用：健康提醒、资讯摘要、工作痕迹与「摸大鱼」面板。数据保存在本机，单实例运行，支持浅色/深色主题。

仓库：<https://github.com/superlongking111/touchingfishv1.0>

## 特性

- **健康提醒**：喝水、走动、休息、厕所等可配置间隔；右下角 toast，支持稍后静默；同时仅显示一条提醒。
- **资讯**：RSS / JSON 门户热榜 + 基于「今日话题」的资讯搜索；本地去重入库；可选 LLM 生成搜索摘要并托盘推送。
- **摸大鱼**：计时面板、本地内容库浏览、工作痕迹摘要、日报草稿、ZIP 导出。
- **工作痕迹**：监听已配置工作目录的文件事件（元数据与路径，不读取文件正文）。
- **摸大鱼与小摸鱼**：摸大鱼窗口打开期间，小摸鱼提醒暂停计时且不弹窗；关闭后从剩余时间继续。

## 系统要求

- Windows 10 / 11（x64）
- 使用打包版无需安装 Python

## 使用

### 发行版（推荐）

1. 打开 [Releases 页面](https://github.com/superlongking111/touchingfishv1.0/releases)，在最新版本里下载 **`摸鱼助手.exe`**。  
   （若页面提示 “There aren’t any releases here”，说明维护者还未上传安装包，请改用下方「从源码打包」，或自行在本地 `dist\` 使用已构建的 exe。）
2. 运行后托盘驻留，右键打开 **设置** / **摸大鱼**。
3. 在 **设置 → 内容** 填写 **今日话题**，需要摘要推送时配置 **模型 API**；可点击 **立即抓取并筛选** 填充本地内容库。

### 从源码运行

```bash
git clone git@github.com:superlongking111/touchingfishv1.0.git
cd touchingfishv1.0
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
python run.py
```

## 配置说明

| 能力 | 说明 |
|------|------|
| 今日话题 | 驱动资讯搜索与搜索摘要推送；在 **设置** 中修改。 |
| 内容抓取 | 后台按随机间隔抓取（可在 **设置 → 内容** 调整分钟范围）。 |
| LLM | OpenAI 兼容接口；用于搜索一句话摘要、日报草稿等；**可选**。 |
| 邮件 | SMTP 发送导出包等；**可选**。 |

敏感凭据（API Key、SMTP 密码）保存在 **Windows 凭据管理器**，不写入仓库或明文配置文件。其余偏好保存在本机 `%LOCALAPPDATA%\FishMate\fishmate.db`。

## 从源码打包

```bash
.venv\Scripts\activate
pyinstaller --noconfirm fishmate.spec
```

产物：`dist\摸鱼助手.exe`。打包前请退出已运行的托盘实例。

## 开发

```bash
pytest -q
```

## 项目结构

```
run.py              # 入口
fishmate/
  app.py            # 应用与托盘
  domain/           # 领域逻辑
  repositories/     # SQLite
  services/         # 调度、抓取、LLM、导出、邮件
  ui/               # 界面
  migrations/       # 数据库迁移
  resources/        # 静态资源
tests/
fishmate.spec       # PyInstaller 配置
requirements.txt
```

## 技术栈

Python 3.12 · PySide6 · SQLite · APScheduler · httpx · feedparser · BeautifulSoup · keyring

## 免责声明

第三方来源内容仅供个人阅读；请遵守相应网站条款与当地法规。LLM 输出与日报草稿仅供参考，不构成正式工作记录。

## License

尚未指定开源许可证；使用前请与维护者确认。
