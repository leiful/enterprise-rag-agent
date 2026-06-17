# 资源规范

本目录用于存放 README、架构文档和部署文档中直接引用的图片资源。

## 目标

- 让 GitHub 首页展示稳定、统一、易维护
- 让占位图后续可平滑替换为真实截图
- 避免把原稿、临时导出文件和超大素材提交进仓库

## 建议保留的正式资源

- `console-overview-placeholder.svg`
- `knowledge-management-placeholder.svg`
- `architecture-placeholder.svg`
- 后续替换后的正式截图或架构图导出文件

建议正式展示文件使用以下命名：

```text
console-overview.png
knowledge-management.png
architecture-diagram.png
```

## 尺寸建议

- 控制台截图：建议宽度 `1200px`
- 架构图：建议宽度 `1200px`
- 长图尽量控制在 GitHub 首页首屏能完整感知的高度范围内
- 多张截图尽量统一宽高比，建议使用浅色背景

## 导出建议

- 优先使用 `PNG` 或 `SVG`
- 截图内尽量避免暴露真实密钥、用户隐私、企业名称和生产地址
- 架构图优先导出为 `SVG`，保证 GitHub 缩放后仍清晰
- 如果使用深色主题，建议额外确认 GitHub 浅色背景下的对比度

## 目录约定

- 本目录只放会被文档直接引用的正式资源
- 原始截图、设计稿和临时导出文件放到 `docs/assets/raw/`
- `docs/assets/raw/` 默认不进入 Git

## 替换占位图时的建议步骤

1. 准备正式截图或架构图
2. 按推荐命名导出到 `docs/assets/`
3. 更新 `README.md` 中的图片引用
4. 确认 GitHub 预览效果、清晰度和首屏长度
5. 删除不再使用的占位图引用
