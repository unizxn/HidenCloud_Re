# HidenCloud_Re

HidenCloud 自动续期脚本，基于 SeleniumBase + GitHub Actions 定时运行。

## 2026-05-08 更新（关键修复）

### 🎯 根因：SOCKS5 直连在 GitHub Actions 上不可用

对比同账号下可正常运行的 [JustRunMy_Renew_2](https://github.com/unizxn/JustRunMy_Renew_2) 和 [KataBump-Re](https://github.com/unizxn/KataBump-Re) 项目，发现它们都通过本地代理工具（sing-box / gost）转发所有协议，而不是让 Chrome 直连外部代理。

| 项目 | 代理处理方式 | 是否正常 |
|------|------------|---------|
| JustRunMy_Renew_2 | sing-box：外部代理 → 本地 `http://127.0.0.1:8080` | ✅ |
| KataBump-Re | gost：外部代理 → 本地 `http://127.0.0.1:8080` | ✅ |
| HidenCloud_Re（旧） | Chrome 直连外部 SOCKS5 | ❌ ERR_CONNECTION_RESET |
| HidenCloud_Re（新） | Xray：外部代理 → 本地 `socks5://127.0.0.1:1080` | ✅ |

**GitHub Actions runner（Azure 环境）的网络策略会阻止 Chrome/Selenium 直接连接外部 SOCKS5 服务器，但允许本地工具（Xray/sing-box/gost）建立出站连接后通过本地端口转发。**

### 修复内容

1. **SOCKS5 改为走 Xray 本地转发（核心修复）**
   - 原代码对 `socks5://` 协议直接 `sys.exit(0)` 退出，让 Chrome 直连外部 SOCKS5。
   - 现在所有协议（vless/vmess/trojan/ss/socks5）统一通过 Xray 生成配置，在本地 `127.0.0.1:1080` 建立 SOCKS5 代理。
   - Chrome 始终使用 `socks5://127.0.0.1:1080`（本地连接），Xray 负责转发到外部代理服务器。
   - 删除了 `use_external_socks.txt` 和外部 SOCKS5 直连测试逻辑。

2. **保留之前的所有修复**
   - 连接错误早期检测（`detect_connection_error`）
   - "已登录"误判修复
   - 服务器 ID 多策略提取（4 种降级策略）
   - `set -o pipefail` 修复 Actions 假成功
   - 日志和截图 Artifact 上传

### 之前的修复（2026-05-06 / 2026-05-07）

3. **修复服务器 ID 提取失败**
   - HidenCloud Dashboard 页面改版后，`<span>` 内嵌套了 `<small>` 子元素。
   - 改用多策略容错提取（行 ID → `contains(.,)` → 链接 href → body 文本正则）。

4. **修复 Due Date 提取容错**（多选择器降级）

5. **修复 GitHub Actions 假成功**（`set -o pipefail`）

## 环境变量

| 变量 | 必填 | 说明 |
|------|------|------|
| `HIDENCLOUD` | ✅ | `email-----password` 格式 |
| `TG_BOT_TOKEN` | ❌ | Telegram Bot Token（可选） |
| `TG_CHAT_ID` | ❌ | Telegram Chat ID（可选） |
| `PROXY_NODE` | ❌ | 代理节点，支持 `vless://` / `vmess://` / `trojan://` / `ss://` / `socks5://` |
| `REPO_TOKEN` | ❌ | 用于自动更新 Cron 的 GitHub PAT |

## 工作流程

```
1. 安装依赖 + 配置 Xray 代理（所有协议统一本地转发）
   ├─ 解析 PROXY_NODE → 生成 xray_config.json
   ├─ 启动 Xray（本地 127.0.0.1:1080）
   └─ 验证连通性（curl 通过本地代理访问 api.ipify.org）
2. 恢复浏览器缓存 → 清理锁文件
3. 启动 Headless Chrome（proxy = socks5://127.0.0.1:1080）
   ├─ 连接错误检测 → 快速报错
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

- 浏览器状态通过 Actions Cache 跨运行保留。
- 每次运行前自动清理 Chrome 锁文件。
- 运行日志和截图可在 Actions → Artifacts 下载。
