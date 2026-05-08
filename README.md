# HidenCloud_Re

HidenCloud 自动续期脚本，基于 SeleniumBase + GitHub Actions 定时运行。

## 2026-05-07 更新

### 修复内容

1. **修复代理连接失败时脚本无法快速报错**
   - 新增 `detect_connection_error()` 函数，可识别 `ERR_CONNECTION_RESET`、`ERR_TIMED_OUT`、`ERR_PROXY_CONNECTION_FAILED`、`ERR_SOCKS_CONNECTION_FAILED` 等所有 Chrome 网络错误。
   - 新增 `navigate_and_wait()` 函数，访问页面后立即检测是否为错误页，若连续 3 次检测到错误则快速失败并给出明确提示，不再白等 20 秒。
   - 在登录判断前、Dashboard 等待期间、管理页面访问后均加入连接错误检测，防止在错误页上误操作。

2. **修复"已登录"误判**
   - 原逻辑仅通过"URL 不含 `/auth/login` 且无 `input#username`"判断已登录，但 Chrome 错误页也满足此条件。
   - 现在在判断"已登录"之前先通过 `navigate_and_wait()` 确认页面真正加载了有效内容，连接错误会直接抛异常退出。

3. **修复 GitHub Actions 外部 SOCKS5 代理跳过连接测试**
   - 原代码对外部 SOCKS5 代理（`socks5://` 协议）直接保存 URL 后 `exit 0`，**不经过任何连通性测试**。
   - 现在增加两阶段测试：
     - **测试 1**：通过代理访问 `api.ipify.org`（最多 5 次），确认代理本身能通。
     - **测试 2**：通过代理访问 `dash.hidencloud.com`（最多 3 次），确认代理能访问目标站。
   - 任一阶段失败都会 `exit 1`，后续步骤不会执行。

4. **启用日志和截图 Artifact 上传**
   - 取消注释 `actions/upload-artifact@v4` 步骤，每次运行（无论成功失败）都会上传截图和日志。
   - 路径加 `$GITHUB_ENV` 前缀确保文件能正确打包。
   - `retention-days: 3` 自动清理，`if-no-files-found: warn` 避免无文件时报错。

5. **减少冗余调试日志**
   - 等待服务列表渲染时，改为每 3 次打印一次状态（原来每次都打印 body 前 200 字），减少日志量。

### 之前的修复（2026-05-06）

6. **修复服务器 ID 提取失败**
   - HidenCloud Dashboard 页面改版后，`<span>` 内嵌套了 `<small>` 子元素，导致原 XPath `//span[contains(text(),'Free Server #')]` 失效。
   - 改用多策略容错提取：
     - **策略1**：从表格行 `id` 属性提取（如 `table-column-body-207579`）
     - **策略2**：XPath 改用 `contains(.,'...')` 代替 `contains(text(),'...')`
     - **策略3**：从页面链接 `href="/service/{id}/manage"` 提取
     - **策略4**：从整个页面 body 文本正则兜底

7. **修复 Due Date 提取容错**
   - 增加多策略降级选择器。

8. **修复 GitHub Actions 假成功**
   - 加 `set -o pipefail`，防止 `tee` 掩盖 Python 异常退出码。

## 环境变量

| 变量 | 必填 | 说明 |
|------|------|------|
| `HIDENCLOUD` | ✅ | `email-----password` 格式 |
| `TG_BOT_TOKEN` | ❌ | Telegram Bot Token（可选） |
| `TG_CHAT_ID` | ❌ | Telegram Chat ID（可选） |
| `PROXY_NODE` | ❌ | 代理配置，支持 `vless://` / `vmess://` / `trojan://` / `ss://` / `socks5://`（可选） |
| `REPO_TOKEN` | ❌ | 用于自动更新 Cron 的 GitHub PAT（自动更新 Cron 时需要） |

## 工作流程

```
1. 安装依赖 + 配置代理（含连接测试）
2. 恢复浏览器缓存 → 清理锁文件
3. 启动 Headless Chrome → 访问 Dashboard
   ├─ 页面连接失败 → 快速报错退出
   ├─ 未登录 → 自动登录（含 Turnstile 处理）
   └─ 已登录 → 直接进入下一步
4. 提取服务器 ID（4 种策略降级）
5. 访问管理页面 → 获取到期时间
6. 点击 Renew → Create Invoice → Pay
7. 获取续期后到期时间 → 判断结果
8. 发送 TG 通知 → 保存浏览器缓存
9. 自动计算下次运行时间并更新 Cron
10. 上传日志和截图 Artifact
```

## 注意

- 脚本使用 `browser_state/selenium_profile` 保存登录态，通过 Actions Cache 跨运行保留。
- 每次运行前会自动清理 Chrome 的 SingletonLock 等锁文件，防止启动失败。
- 如果使用 SOCKS5 代理，建议在本地先用 `curl -x socks5://your-proxy https://dash.hidencloud.com` 验证代理是否能访问目标站。GitHub Actions runner 位于 Azure 北美区域，部分地区代理可能无法使用。
- 运行日志和截图可在 Actions 页面的 Artifacts 区域下载。
