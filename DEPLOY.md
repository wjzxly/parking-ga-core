# 发布到 GitHub

## 零、网络前提（中国大陆环境必看）

本机实测结论：

| 目标 | 结果 |
| --- | --- |
| `github.com:443` 直连 | ❌ 超时 |
| `github.com:22`（SSH） | ✅ 通 |
| `github.com:443` 经 Clash 7897 | ✅ 通 |

因此 HTTPS 推送必须先让 git 走代理（**已配置好，无需重复操作**）：

```bash
git config --global http.proxy http://127.0.0.1:7897
git config --global https.proxy http://127.0.0.1:7897
```

验证：

```bash
git ls-remote https://github.com/git/git.git HEAD
```

能打印出一串 commit SHA 就说明通了。

> **端口不是固定的。** 梯子换节点或换客户端后端口可能变（Clash 默认 7897，v2rayN 常见 10809）。
> 断网时先查 `Get-NetTCPConnection -State Listen | Where LocalPort -lt 65535` 找到实际监听端口，
> 再同步改 git 配置。

## 一、首次配置（只需做一次）

```bash
git config --global user.name "wjzxly"
git config --global user.email "161605703+wjzxly@users.noreply.github.com"
```

已使用 GitHub 提供的匿名邮箱，真实邮箱不会出现在公开提交记录里。

## 二、创建远程仓库

在 GitHub 上新建一个仓库（https://github.com/new），**不要**勾选 "Add a README" / ".gitignore" / "license"（本地已有，勾了会冲突）。

- Repository name：`parking-ga-core`
- 可见性：Public（作品集必须公开，私有仓库招聘方看不到）

## 三、推送本仓库

本地仓库已初始化、已按开发过程完成 7 次提交，只差最后一步：

```bash
cd parking-ga-core
git remote add origin https://github.com/wjzxly/parking-ga-core.git
git push -u origin main
```

首次推送会要求输入凭据：

- 用户名：`wjzxly`
- 密码：**粘贴 PAT**（不是你的 GitHub 登录密码，GitHub 早就不支持密码推送了）

Windows 上 git 会把凭据存进「凭据管理器」，之后同一账号免密。

## 四、提交历史说明

本项目**未**使用一次性 `initial commit`，而是按开发顺序拆成了 7 次提交：

```
chore: 忽略本地推送脚本
docs: 补充算法推导、基准数据、部署说明与 CI 配置
feat: 模拟车库生成器与命令行入口
feat: PMX 排列编码与模拟退火遗传算法，补充 12 个单元测试
feat: 三维评分机制与适应度缓存
feat: 车位与许可领域模型
chore: 初始化项目脚手架与打包配置
```

招聘方看仓库时第一眼会扫提交历史。按功能拆分的历史能说明「这是逐步做出来的」，而不是「临时从别处拷来的」。

后续开发继续沿用 `feat:` / `fix:` / `docs:` / `chore:` 前缀，这是 Conventional Commits 规范，也是团队协作的通行做法。

## 五、仓库设置清单

推上去之后，在仓库页面右侧点齿轮：

- **Description**：`停车场车位分配的遗传算法求解器：三维评分 · PMX 排列编码 · 模拟退火扰动 · 零依赖`
- **Website**：如果有部署地址就填
- **Topics**：`genetic-algorithm` `optimization` `parking` `python` `qap` `simulated-annealing`

## 六、加 CI 徽章（强烈建议）

在仓库根目录新建 `.github/workflows/ci.yml`：

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12"]

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - name: Run tests
        run: python -m unittest discover -s tests -v
```

提交后，在 Actions 页面拿到徽章地址，加到 README 顶部。**绿徽章是「这个项目真的能跑」最有力的证据**，比任何文字描述都可信。

## 七、常见问题

**推送被拒（`rejected - non-fast-forward`）**
远程仓库建的时候勾选了 README，导致远程已有提交。解决：

```bash
git pull --rebase origin main
git push -u origin main
```

或者干脆删掉远程仓库重建，不勾任何初始化选项。

**提交记录里显示 `unknown`**
忘了设 `user.name` / `user.email`。改完之后用 `git commit --amend --reset-author` 修正最近一次。

**中文文件名在 Windows 下显示成转义码**
```bash
git config --global core.quotepath false
```
