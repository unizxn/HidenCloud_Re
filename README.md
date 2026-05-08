# HidenCloud_Re

HidenCloud 免费服务器自动续期脚本，基于 SeleniumBase + GitHub Actions 定时运行。

## 功能

- 自动登录 HidenCloud Dashboard（含 Cloudflare Turnstile 验证）
- 自动提取 Free Server ID 并执行续期操作
- 支持多协议代理（Xray 本地转发）
- 自动调整 Cron 定时（到期前 20 小时触发）
- Telegram 通知推送
- 浏览器状态缓存跨运行保留（减少重复登录）

## 使用方法

### 1. Fork 本仓库

### 2. 配置 Secrets

在仓库 **Settings → Secrets and variables → Actions** 中添加：

| Secret | 必填 | 说明 |
|--------|:----:|------|
| `HIDENCLOUD` | ✅ | HidenCloud 账号，格式为 `email-----password` |
| `PROXY_NODE` | ❌ | 代理节点链接（GitHub Actions runner 无法直连 HidenCloud，建议配置） |
| `TG_BOT_TOKEN` | ❌ | Telegram Bot Token |
| `TG_CHAT_ID` | ❌ | Telegram Chat ID |
| `REPO_TOKEN` | ❌ | GitHub PAT（用于自动更新 Cron，需 `repo` 权限） |

### 3. 支持的代理协议

| 协议 | 示例 |
|------|------|
| VLESS | `vless://uuid@host:port?security=reality&...` |
| VMess | `vmess://base64...` |
| Trojan | `trojan://password@host:port?...` |
| Shadowsocks | `ss://base64@host:port` |
| SOCKS5 | `socks5://user:pass@host:port` |

所有协议统一通过 Xray 转发至本地 `socks5://127.0.0.1:1080`，Chrome 始终连接本地端口。

### 4. 手动触发

**Actions → HidenCloud 续期 → Run workflow**，或等待自动 Cron 触发。

## 工作流程

```
解析代理节点 → 启动 Xray 本地转发 → 测试连通性
        ↓
恢复浏览器缓存 → 启动 Headless Chrome
        ↓
访问 Dashboard ──失败──→ 重启浏览器重试（最多 3 次）
        ↓成功
检测登录状态
   ├─ 未登录 → 填写表单 → Turnstile 验证 → 提交登录
   └─ 已登录 → 继续
        ↓
提取服务器 ID（4 种降级策略）
        ↓
访问管理页面 → 获取续期前到期时间
        ↓
点击 Renew → Create Invoice → Pay
        ↓
获取续期后到期时间 → 判断结果
        ↓
TG 通知 → 保存浏览器缓存 → 自动更新 Cron
```

## 安全说明

- 代理节点地址和端口在日志中自动脱敏显示（如 `*8***3*:****`）
- Xray 配置文件在运行结束后自动删除
- 日志和截图仅通过私有 Artifact 提供（3 天后自动过期）
- `set -o pipefail` 确保 Python 异常不会被管道吞掉导致假成功

## 调试

运行失败时，前往 **Actions → 对应的 Run → Artifacts** 下载：

| 文件 | 内容 |
|------|------|
| `renew.log` | 脚本完整运行日志 |
| `screenshots/` | 每个关键步骤的截图 |
| `xray.log` | Xray 代理日志（仅代理失败时有用） |
