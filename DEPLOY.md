# 发布到 GitHub

## 零、网络前提（中国大陆环境必看）

本机实测：`github.com:443` **直连不通**（超时），但通过梯子（Clash 默认端口 7897）完全正常。因此推送前必须先让 git 走代理：

```bash
git config --global http.proxy http://127.0.0.1:7897
git config --global https.proxy http://127.0.0.1:7897
```

验证：

```bash
git ls-remote https://github.com/git/git.git HEAD
```

能打印出一串 commit SHA 就说明通了。如果只用 SSH（`git@github.com`），22 端口本身是通的，不依赖代理，但需要先配 SSH key。

> 梯子端口不一定是 7897。在 Clash / v2rayN 的设置里看「混合端口 / HTTP 端口」，换成对应的数字即可。

## 一、首次配置（只需做一次）

```bash
git config --global user.name "你的 GitHub 用户名"
git config --global user.email "你的 GitHub 邮箱"
```

邮箱建议用 GitHub 提供的匿名邮箱（在 GitHub → Settings → Emails 里可以查到），避免真实邮箱出现在公开提交记录里。

## 二、创建远程仓库

在 GitHub 上新建一个仓库，**不要**勾选 "Add a README" / ".gitignore" / "license"（本地已有，勾了会冲突）。

仓库名就用目录名：`parking-ga-core`。

## 三、推送本仓库

```bash
cd parking-ga-core
git init -b main
git add .
git commit -m "feat: 停车场车位分配遗传算法求解器"
git remote add origin https://github.com/<用户名>/parking-ga-core.git
git push -u origin main
```

## 四、建议分步提交，而不是一次性 init

招聘方会看提交历史。一次性 `initial commit` 塞进所有文件，会显得项目是「临时糊出来的」。更真实的做法是按开发过程拆分：

```bash
git add parking_ga/models.py
git commit -m "feat: 车位与许可领域模型"

git add parking_ga/fitness.py
git commit -m "feat: 三维评分机制与适应度缓存"

git add parking_ga/ga.py tests/
git commit -m "feat: PMX 编码与模拟退火遗传算法，补充单元测试"

git add parking_ga/datasets.py parking_ga/cli.py
git commit -m "feat: 模拟车库生成器与命令行入口"

git add README.md docs/ examples/
git commit -m "docs: 补充算法推导、基准数据与使用说明"
```

commit message 用 `feat:` / `fix:` / `docs:` 前缀，是业界通行规范，一眼就知道你懂协作。

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
