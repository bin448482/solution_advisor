# PPT解析与项目画像流水线（MVP）

将项目介绍类 PPT 转换为结构化画像：渲染 → 提取文本 → 单页总结 → 项目画像 → manifest。

## 准备
- Python 3.9+
- 安装依赖：`pip install -r requirements.txt`
- 安装 LibreOffice（可执行 `soffice`）与 Poppler（提供 `pdftoppm`）；确保二者在 PATH，或在 `.env` 中指定路径。
- 配置 `.env`（可复制 `.env.example`），填入 LLM 参数。无外网/无 Key 时可设置 `LLM_PROVIDER=mock` 跳过真实调用。

## 运行
```bash
python -m src --input ppts/ChatBI产品介绍_2025.pptx --output ppt_outputs/ChatBI产品介绍_2025 --force
```

输出目录包含：
- `slides/001.png`...：渲染图片
- `page_summaries/001.json`...：单页总结
- `doc_summary/project_profile.json`：聚合画像
- `manifest.json`：元数据与错误

## 测试
```bash
pytest
```
若缺少 LibreOffice/Poppler 或未配置 LLM，相关测试会自动跳过。
