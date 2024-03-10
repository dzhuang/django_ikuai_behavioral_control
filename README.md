[![codecov](https://codecov.io/gh/dzhuang/django_ikuai_behavioral_control/graph/badge.svg?token=SCIRK0ZKAO)](https://codecov.io/gh/dzhuang/django_ikuai_behavioral_control)
![isort](https://img.shields.io/badge/isort-passing-brightgreen)
![flake8](https://img.shields.io/badge/flake8-passing-brightgreen)

# Django iKuai 行为控制

## 概览

Django iKuai 行为控制是一个基于 Django 的网络行为管理和控制的 Web 应用程序。该项目专为 iKuai 爱快路由器设备设计，提供了一个用户友好的界面，用于处理复杂的路由管理任务。

## 特性

- **设备管理**：注册并管理网络中连接的设备。
- **协议控制**：为设备定义和执行网络协议。
- **域名黑名单**：管理并执行网络安全和控制的域名黑名单。
- **用户认证**：通过用户认证机制安全访问 Web 应用程序。

## 开始使用

### 先决条件

- Docker 和 Docker Compose

### 安装

1. **克隆仓库：**
   ```bash
   git clone https://github.com/dzhuang/django_ikuai_behavioral_control.git
   ```

2. **准备 Docker Compose 文件：**
   - 导航到克隆的仓库目录。
   - 复制 `docker-compose-example.yml` 文件并将副本重命名为 `docker-compose.yml`。
     ```bash
     cp docker-compose-example.yml docker-compose.yml
     ```
   - 根据您的环境和需求修改 `docker-compose.yml` 文件。这可能包括设置卷路径、环境变量和其他 Docker 配置。

3. **拉取 Docker 镜像：**
   ```bash
   docker pull dzhuang/ikuai_behavioral_control
   ```

4. **启动应用程序：**
   - 使用 Docker Compose 启动应用程序：
     ```bash
     docker-compose up
     ```
   - 该命令读取您刚刚准备的 `docker-compose.yml` 文件，并根据其配置启动应用程序。数据库迁移作为应用程序启动过程的一部分自动执行。

## 贡献

欢迎对 Django iKuai 行为控制项目做出贡献！请参阅 CONTRIBUTING.md 文件，了解如何为此项目贡献您的力量。

## 许可证

该项目根据 MIT 许可证授权 - 详情请见 [LICENSE.txt](https://github.com/dzhuang/django_ikuai_behavioral_control/blob/main/LICENSE.txt) 文件。
