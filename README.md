# HidenCloud_Re

HidenCloud 自动续期脚本，基于 SeleniumBase + GitHub Actions 定时运行。

## 2026-05-06 更新

### 修复内容

1. **修复服务器 ID 提取失败**
   - HidenCloud Dashboard 页面改版后，`<span>` 内嵌套了 `<small>` 子元素，导致原 XPath `//span[contains(text(),'Free Server #')]` 失效。
   - 改用多策略容错提取：
     - **策略1**：从表格行 `id` 属性提取（如 `table-column-body-207579`）——最稳定
     - **策略2**：XPath 改用 `contains(.,'...')` 代替 `contains(text(),'...')`，可匹配嵌套文本
     - **策略3**：从页面链接 `href="/service/{id}/manage"` 提取
     - **策略4**：从整个页面 body 文本正则兜底
   - 同时增加了调试输出，失败时会打印页面内所有 `/service/` 链接，方便排查。

2. **修复 Due Date 提取容错**
   - 原代码只匹配 `//h6[contains(text(),'Due date')]/following-sibling::div`，现增加多策略降级。

3. **修复 GitHub Actions 假成功**
   - 原命令 `python3 main.py 2>&1 | tee renew.log` 配合 `bash -e` 会导致管道错误码被 `tee` 覆盖，即使脚本崩溃 Actions 也显示绿勾。
   - **修复**：在 Workflow 的 run 步骤前加 `set -o pipefail`。
     ```yaml
     - run: |
         set -o pipefail
         python3 main.py 2>&1 | tee renew.log
       shell: /usr/bin/bash -e {0}
     ```

## 环境变量

| 变量 | 说明 |
|------|------|
| `HIDENCLOUD` | `email-----password` 格式 |
| `TG_BOT_TOKEN` | Telegram Bot Token（可选） |
| `TG_CHAT_ID` | Telegram Chat ID（可选） |
| `PROXY_NODE` / `PROXY_SERVER` | 代理配置（可选） |

## 注意

- 脚本使用 `browser_state/selenium_profile` 保存登录态，通过 Actions Cache 跨运行保留。
- 每次运行前会自动清理 Chrome 的 SingletonLock 等锁文件，防止启动失败。
