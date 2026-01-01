# 项目 README 生成提示词

> 用途：生成/刷新 `README.md`。复制下方提示词，替换花括号中的占位内容后提交给 LLM 或写入 README。

---

# {PROJECT_NAME}

{ONE_LINE_DESCRIPTION}

> 项目类型：{Backend / Data Platform / AI / Library / Tool / Web App / CLI}  
> 主要语言：{LANGUAGES}  
> 技术栈：{TECH_STACK}  
> 目标用户：{Developers / Data Engineers / End Users / Internal Teams}

---

## 徽章（可选）
<!-- 可根据需要替换或移除 -->
![License](https://img.shields.io/badge/license-{LICENSE}-blue)
![Build](https://img.shields.io/badge/build-passing-brightgreen)
![Status](https://img.shields.io/badge/status-active-success)

---

## 目录
- [功能特性](#功能特性)
- [架构 / 设计概览](#架构--设计概览)
- [前置条件](#前置条件)
- [安装](#安装)
- [配置](#配置)
- [使用示例](#使用示例)
- [项目结构](#项目结构)
- [开发指南](#开发指南)
- [测试](#测试)
- [部署（如适用）](#部署如适用)
- [路线图（可选）](#路线图可选)
- [贡献指南](#贡献指南)
- [许可证](#许可证)
- [维护者 / 联系方式](#维护者--联系方式)

---

## 功能特性
> 以下为通用占位描述，请根据实际功能补充或替换。
- 清晰的模块化设计，便于扩展与维护
- 面向 {Target users} 的友好接口
- 与 {TECH_STACK} 集成
- 可配置、可测试、可部署

---

## 架构 / 设计概览
> 简要说明系统的整体架构或核心设计思想。

- 核心组件：`{Core Module / Service / Library}`
- 接口层：`{API / CLI / UI}`
- 数据或状态管理：`{Database / Storage / In-memory}`
- 扩展点：`{Plugins / Hooks / Pipelines}`

如有需要，可在此处添加架构图或链接到更详细的设计文档。

---

## 前置条件
在开始之前，请确保已安装以下依赖：
- {Language Runtime} >= {Version}
- {Package Manager / Build Tool}
- 其他依赖（如有）

---

## 安装
```bash
# 克隆仓库
git clone https://github.com/your-org/{PROJECT_NAME}.git
cd {PROJECT_NAME}

# 安装依赖（示例）
{INSTALL_COMMAND}
```

---

## 配置
- 复制并修改示例配置：`{CONFIG_SAMPLE_PATH} -> {CONFIG_PATH}`
- 设置必要的环境变量：`{ENV_VARS}`
- 如有密钥或凭证，请使用本地 `.env` 或密钥管理工具存储

---

## 使用示例
```bash
# 运行核心流程
{RUN_COMMAND}
```

输出示例：
- {OUTPUT_ITEM_1}
- {OUTPUT_ITEM_2}

---

## 项目结构
```bash
{PROJECT_TREE}
```

---

## 开发指南
- 代码风格：{LINT_RULES / FORMATTER}
- 提交规范：{COMMIT_RULES}
- 分支策略：{BRANCH_STRATEGY}

---

## 测试
```bash
{TEST_COMMAND}
```
> 可补充集成测试/端到端测试的运行方式与跳过条件。

---

## 部署（如适用）
- 部署目标：{Cloud / On-Prem / Container}
- 交付方式：{Docker / Helm / Serverless / Wheel}
- 关键参数：{ENV / Secrets / Scaling}

---

## 路线图（可选）
- [ ] 里程碑 1：{M1_DESC}
- [ ] 里程碑 2：{M2_DESC}
- [ ] 里程碑 3：{M3_DESC}

---

## 贡献指南
- 提交 PR 前请确认通过全部测试并更新相关文档
- 讨论/Issue 模板：{ISSUE_TEMPLATE}
- 代码评审：{REVIEW_POC}

---

## 许可证
本项目遵循 `{LICENSE}` 协议，详见 `LICENSE` 文件。

---

## 维护者 / 联系方式
- Owner：{OWNER_NAME} ({OWNER_CONTACT})
- 协作渠道：{Slack / WeCom / Email}
