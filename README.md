# 录音转文字工具

一个基于 Flask + Whisper 的网页转写工具，既能本地运行，也适合部署成公网 AI 网站。

## 功能

- 上传 `.mp3`、`.m4a`、`.wav` 录音
- 使用 Whisper 转写
- 支持阿拉伯语、西班牙语、英语、韩语、日语、德语、泰语、法语转写为中文
- 默认使用免费 LibreTranslate / Argos Translate 兼容接口完成外语转中文
- 页面直接展示结果
- 一键下载 `.txt`
- 提供 `/health` 健康检查
- 支持 Docker 和 Gunicorn 部署

## 启动

1. 安装依赖：

```bash
python3 -m pip install -r requirements.txt
```

2. 启动服务：

```bash
.venv/bin/python app.py
```

3. 打开浏览器访问：

```text
http://127.0.0.1:5000
```

## 生产启动

```bash
.venv/bin/gunicorn --bind 0.0.0.0:5000 --timeout 600 app:app
```

## Docker 部署

```bash
docker build -t whisper-transcriber .
docker run -p 5000:5000 whisper-transcriber
```

说明：
- Docker 构建里会先安装兼容版 `setuptools==80.9.0` 和 `wheel`
- `openai-whisper` 会用非隔离构建方式安装，避免部分云平台上出现 `pkg_resources` 缺失导致的构建失败

## 公网部署建议

### Render

1. 把当前项目推到 GitHub
2. 在 Render 新建 Web Service
3. 连接 GitHub 仓库
4. 选择 Docker 部署
5. 部署后获得 `onrender.com` 公网地址

参考官方文档：
- [Deploy a Flask App on Render](https://render.com/docs/deploy-flask)
- [Docker on Render](https://render.com/docs/docker)

### Railway

1. 把当前项目推到 GitHub，或使用 Railway CLI 直接上传
2. 在 Railway 新建项目
3. 选择 GitHub Repo 或本地上传
4. Railway 会读取 `Dockerfile` 或 `railway.toml`
5. 在 Networking 里生成公网域名

注意：
- 如果使用 Docker 部署，优先让容器自己的 `CMD` 启动应用
- 不要在 Railway 后台额外填写一个会覆盖 Docker `CMD` 的旧 `Start Command`

参考官方文档：
- [Deploy a Flask App | Railway](https://docs.railway.com/guides/flask)
- [Deploying with the CLI | Railway](https://docs.railway.com/cli/deploying)

## 可选配置

- `WHISPER_MODEL`
  - 默认值：`base`
  - 可选示例：`tiny`、`base`、`small`、`medium`、`large`
- `TRANSLATION_PROVIDER`
  - 默认值：`libretranslate`
- `LIBRETRANSLATE_URL`
  - 默认值：`https://translate.argosopentech.com/translate`
- `LIBRETRANSLATE_API_KEY`
  - 默认留空
  - 只有当你使用带鉴权的 LibreTranslate 实例时才需要填写
- `MAX_UPLOAD_MB`
  - 默认值：`100`
  - 控制单个上传文件的大小上限
- `PORT`
  - 默认值：`5000`
- `HOST`
  - 默认值：`0.0.0.0`

示例：

```bash
WHISPER_MODEL=small MAX_UPLOAD_MB=200 .venv/bin/python app.py
```

## 注意

- `openai-whisper` 依赖本机可用的 `ffmpeg`
- 首次运行 Whisper 时会下载模型文件
- 当前版本支持 `.mp3`、`.m4a`、`.wav`
- 默认外语转中文走免费 LibreTranslate / Argos Translate 兼容接口；公开免费实例可能会限流或临时不可用
- 如果要真正开放给公网，建议放在云服务器、Render、Railway、Fly.io 或自建 Docker 环境，并配反向代理与 HTTPS
- 当前版本把转写结果写到本机/容器文件系统，适合单机部署；如果你要长期公网运营，建议后续接对象存储和数据库
