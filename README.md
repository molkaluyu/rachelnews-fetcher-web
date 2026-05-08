# Rachelnews Fetcher Web

这是一个给非技术用户使用的物流新闻网页获取器。

## 本地运行

1. 进入仓库文件夹：

```bash
cd rachelnews-fetcher-web
```

2. 创建本地密钥文件：

```bash
mkdir -p .streamlit
cp .streamlit/secrets.example.toml .streamlit/secrets.toml
```

3. 把 `.streamlit/secrets.toml` 里的 `ak_your_key_here` 改成真实的 `AIGORISM_API_KEY`。

4. 安装依赖：

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

5. 启动网页：

```bash
.venv/bin/streamlit run streamlit_app.py
```

## 免费部署到 Streamlit Community Cloud

1. 打开 Streamlit Community Cloud。
2. 选择这个 GitHub 仓库。
3. App file 选择 `streamlit_app.py`。
4. 在 Advanced settings 的 Secrets 里填：

```toml
AIGORISM_API_KEY = "你的真实 API Key"
```

5. 点击 Deploy。

部署完成后，把网页链接发给朋友即可。
