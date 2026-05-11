# HidenCloud_Re

HidenCloud 免费服务器自动续期工具，基于 SeleniumBase + GitHub Actions，每次运行约 1 分钟完成。

## 功能特性

- **自动续期** — 登录 → 提取服务器 → Renew → Pay，全自动流水线
- **Cloudflare Turnstile** — 自动绕过人机验证
- **浏览器缓存复用** — 跨运行保留登录态，避免重复登录
- **智能 Cron 调度** — 到期前 20 小时自动触发，无需手动维护
- **Telegram 通知** — 续期结果 + 截图 + 到期时间变更推送
- **多协议代理** — VLESS / VMess / Trojan / SS / SOCKS5 统一通过 Xray 转发
- **快速失败重试** — 域名检测 + 空白页检测，错误页面秒级判定并重启浏览器
- **运行记录自动清理** — 仅保留最近 2 次运行记录
- **零 Node.js 警告** — 全部使用最新版 GitHub Actions（checkout@v5, setup-python@v6, cache@v5, upload-artifact@v5）

## 快速开始

### 1. Fork 本仓库

### 2. 配置 Secrets

仓库 **Settings → Secrets and variables → Actions**：

| Secret | 必填 | 说明 |
|--------|:----:|------|
| `HIDENCLOUD` | ✅ | HidenCloud 账号，格式 `email-----password` |
| `PROXY_NODE` | ❌ | 代理节点链接（GitHub Runner 无法直连 HidenCloud，**强烈建议配置**） |
| `TG_BOT_TOKEN` | ❌ | Telegram Bot Token（从 [@BotFather](https://t.me/BotFather) 获取） |
| `TG_CHAT_ID` | ❌ | Telegram Chat ID |
| `REPO_TOKEN` | ❌ | GitHub PAT，需 `repo` 权限（用于自动更新 Cron 时间） |

### 3. 支持的代理协议

| 协议 | 链接格式 |
|------|----------|
| VLESS | `vless://uuid@host:port?security=reality&...` |
| VMess | `vmess://base64...` |
| Trojan | `trojan://password@host:port?sni=...` |
| Shadowsocks | `ss://base64@host:port` |
| SOCKS5 | `socks5://user:pass@host:port` |

所有协议统一由 Xray 转发至本地 `socks5://127.0.0.1:1080`，Chrome 始终连接本地端口。

### 4. 运行

**手动触发**：Actions → HidenCloud 续期 → Run workflow

**自动触发**：首次 Fork 后，Cron 默认 `13 3 4 5 *`（5 月 4 日），首次运行成功后会自动计算并更新为正确的下次运行时间。

## 工作流程

```
解析代理节点 → 启动 Xray 本地转发 → 测试连通性
        ↓
恢复浏览器缓存 → 清理残留锁文件 → 启动 Headless Chrome
        ↓
访问 Dashboard（最多重试 5 次，每次失败重启浏览器）
   ├─ 域名检测：URL 不含 hidencloud → 秒级失败，立即重试
   ├─ 空白页检测：页面内容 < 10 字符 → 秒级失败，立即重试
   └─ 连接错误检测：ERR_* 系列错误 → 记录并重试
        ↓成功
检测登录状态
   ├─ 未登录 → 填写表单 → Turnstile 验证 → 提交登录
   └─ 已登录（缓存命中）→ 跳过
        ↓
提取服务器 ID（4 种降级策略）
   ├─ 策略1: 表格行 id 属性 → table-column-body-{id}
   ├─ 策略2: span 文本 → Free Server #{id}
   ├─ 策略3: 链接 href → /service/{id}/manage
   └─ 策略4: 全页文本正则兜底
        ↓
访问管理页面 → 记录续期前到期时间
        ↓
点击 Renew
   ├─ 触发限制弹窗（Renewal Restricted）→ 记录剩余天数 → 关闭弹窗
   └─ 正常流程 → Create Invoice → Pay
        ↓
重新获取到期时间 → 对比前后变化 → 判断结果状态
        ↓
TG 通知（含截图 + 到期时间变更）→ 保存浏览器缓存 → 自动更新 Cron
```

## TG 通知示例

**续期成功：**
```
✅ 续订成功

账号: user@example.com
服务器: Free Server #123
到期: 28 Apr 2026 → 05 May 2026
时间: 2026-04-28 03:13:45

HidenCloud Auto Renew
```

**续期受限（未到续期窗口）：**
```
ℹ️ 暂无可续期

账号: user@example.com
服务器: Free Server #123
到期: 28 Apr 2026
剩余: 7 天 (需 ≤ 1 天可续)
时间: 2026-04-22 03:13:30

HidenCloud Auto Renew
```

## Cron 自动调度逻辑

```
到期时间 - 当前时间 = 剩余小时数

剩余 > 20 小时 → 下次运行 = 当前 + (剩余 - 20) 小时
剩余 ≤ 20 小时 → 4 小时后重试
```

每次运行成功后，脚本自动修改 YAML 中的 cron 表达式并提交到仓库，实现动态调度。

## 安全设计

| 措施 | 说明 |
|------|------|
| 日志脱敏 | 代理地址显示为 `*8***3*:****`，邮箱显示为 `use***@example.com` |
| 敏感文件清理 | Xray 配置文件运行结束后立即删除 |
| Artifact 过期 | 日志和截图仅保留 3 天自动过期 |
| 管道安全 | `set -o pipefail` 防止 Python 异常被 `tee` 吞掉导致假成功 |
| 浏览器缓存清理 | 每次运行前清理锁文件、崩溃标记、Session Storage、GPU 缓存等残留 |
| 旧缓存清理 | 每次运行后删除所有旧浏览器状态缓存，仅保留最新一次 |

## 调试

运行失败时，前往 **Actions → 对应的 Run → Artifacts** 下载：

| 文件 | 内容 |
|------|------|
| `renew.log` | 脚本完整运行日志 |
| `screenshots/` | 每个关键步骤的截图（含时间戳命名） |
| `xray.log` | Xray 代理日志（仅配置代理时生成） |

## 文件结构

```
.
├── .github/workflows/
│   └── HidenCloud_Renew.yml   # GitHub Actions 工作流
├── main.py                     # 主脚本
└── README.md
```

## 依赖

- Python 3.11
- [seleniumbase](https://github.com/sdnetsoft/SeleniumBase) — Headless Chrome + undetected mode
- [requests](https://github.com/psf/requests) — TG 通知发送
- Xray-core — 代理转发（运行时自动下载）
