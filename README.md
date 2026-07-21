# 表情包生成器

基于 [meme-generator](https://github.com/MemeCrafters/meme-generator-rs) 的 Web 应用，支持 300+ 表情包模板。

## 功能

- 300+ 模板，支持关键词搜索
- 图片输入：本地上传 / QQ头像 / 网络图片
- 生成后可下载或复制到剪贴板

## 部署

```bash
pip install -r requirements.txt
python app.py
# 访问 http://localhost:7861
```

## 文件结构

```
├── app.py           # Flask 后端
├── index.html       # 前端页面
├── requirements.txt # Python 依赖
└── .gitignore
```
