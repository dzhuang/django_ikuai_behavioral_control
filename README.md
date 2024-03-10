[![codecov](https://codecov.io/gh/dzhuang/django_ikuai_behavioral_control/graph/badge.svg?token=SCIRK0ZKAO)](https://codecov.io/gh/dzhuang/django_ikuai_behavioral_control)
![isort](https://img.shields.io/badge/isort-passing-brightgreen)
![flake8](https://img.shields.io/badge/flake8-passing-brightgreen)

# Django iKuai 行为控制

## 概览

Django iKuai Behavioral Control (Django iKuai行为控制)是一个基于 Django 的网络行为管理和控制的 Web 应用程序。该项目专为 iKuai 爱快路由器设备设计，提供了一个用户友好的界面，用于处理复杂的路由管理任务。目前支持的 [爱快固件](https://www.ikuai8.com/component/download) 版本为免费版iKuai8_3.7.11_Build202403051040.

## 开发的初衷

- 实现家庭中所有设备网络访问权限的基本控制
- 借助爱快内置的协议控制(acl_l7)，有效防止未成年人访问或沉迷各类游戏和短视频
- 提供快速设置的webui，弥补爱快Web界面上快速设置时间范围等功能缺失

## 特性

- **设备管理**：注册并管理网络中连接的设备。
- **协议控制**：为设备定义和执行网络协议，设置设备在不同时间不同优先级允许/不允许使用的网络协议。
- **域名黑名单**：管理并执行网络安全和控制的域名黑名单。

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
   - 根据您的环境和需求修改 `docker-compose.yml` 文件。这可能包括设置卷路径、环境变量和其他 Docker 配置，详见后面的`docker-compose.yml`文件中的配置说明。

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


## `docker-compose.yml`文件中的配置说明

### behavioral_control_service 服务

以下的项目必须修改，以保证安全。

| 设置项                                         | 描述                                                                                   |
|----------------------------------------------|--------------------------------------------------------------------------------------|
| `DJANGO_SUPERUSER_USERNAME`                  | Django 超级用户的用户名，用于创建初始管理员账户。                                                 |
| `DJANGO_SUPERUSER_PASSWORD`                  | Django 超级用户的密码。                                                                     |
| `DJANGO_SUPERUSER_EMAIL`                     | Django 超级用户的电子邮件地址。                                                               |
| `BEHAVIORAL_CONTROL_SERVER_SECRET_KEY`       | Django 应用的秘密密钥，用于安全性关键的操作，如会话、签名等。应保持秘密。                            |
| `BEHAVIORAL_CONTROL_SERVER_REDIS_LOCATION`   | Redis 服务的连接位置，格式为 `redis://redis_service:6379`。用于配置与 Redis 实例的连接，不要随意修改。           |
| `BEHAVIORAL_CONTROL_ALLOWED_HOST_`           | 重要：以此开头的键名表示允许访问应用的主机名或IP地址，对应于Django设置中的 [ALLOWED_HOSTS](https://docs.djangoproject.com/en/5.0/ref/settings/#allowed-hosts) 。键值不需要包含scheme，应包含该网站的主机域名和实例的本地ip。例如：`BEHAVIORAL_CONTROL_ALLOWED_HOST_router=foo.com` 和 `BEHAVIORAL_CONTROL_ALLOWED_HOST_local=192.168.1.1`。 |
| `BEHAVIORAL_CONTROL_CSRF_TRUSTED_ORIGINS_`   | 重要：以此开头的键名表示可信的来源域名或IP，用于 CSRF 验证，对应于Django设置中的 [CSRF_TRUSTED_ORIGINS](https://docs.djangoproject.com/en/5.0/ref/settings/#std-setting-CSRF_TRUSTED_ORIGINS)。键值中必须包含scheme（如 `http://` 或 `https://`）。应包含该网站的域名访问方式和实例的本地ip访问方式，例如示例中的：`BEHAVIORAL_CONTROL_CSRF_TRUSTED_ORIGINS_router=https://foo.com` 和 `BEHAVIORAL_CONTROL_CSRF_TRUSTED_ORIGINS_local=http://192.168.1.1`。 |

以下的项目必须修改，以保证安全。

| 设置项                                         | 描述                                                                                   |
|----------------------------------------------|--------------------------------------------------------------------------------------|
| `BEHAVIORAL_CONTROL_SERVER_LANGUAGE_CODE`    | 应用的默认语言代码，例如 `zh-hans` 表示简体中文。                                                  |
| `BEHAVIORAL_CONTROL_SERVER_TZ`               | 应用服务器的时区设置，例如 `Asia/Shanghai`。                                                      |
| `BEHAVIORAL_CONTROL_SERVER_DB_HOST`          | 数据库服务器的主机名，例如 `postgres_db_service` 表示 Docker Compose 中定义的 PostgreSQL 服务名称，不要随意修改。 |
| `BEHAVIORAL_CONTROL_SERVER_DB_PORT`          | 数据库服务器的端口，通常 PostgreSQL 默认为 `5432`。                                               |
| `BEHAVIORAL_CONTROL_SERVER_DB_USER`          | 用于数据库连接的用户名。                                                                     |
| `BEHAVIORAL_CONTROL_SERVER_DB_PASSWORD`      | 用于数据库连接的密码。                                                                     |
| `BEHAVIORAL_CONTROL_SERVER_DB`               | 数据库的名称，用于存储应用数据。                                                               |
| `RABBITMQ_HOST`                              | RabbitMQ 服务的主机名，用于消息队列服务。应与`rabbit 服务`中的`hostname`一致.|
| `RABBITMQ_USER`                              | 连接 RabbitMQ 服务的用户名。应与`rabbit 服务`中的`environment`对应项目一致.|
| `RABBITMQ_PASSWORD`                          | 连接 RabbitMQ 服务的密码。应与`rabbit 服务`中的`environment`对应项目一致.|
| `BEHAVIORAL_CONTROL_SERVER_DEBUG`            | 控制 Django 应用的调试模式是否启用，生产环境中应设置为 `off`。默认为 `off`.                                   |

### postgres_db_service 服务

| 设置项                                         | 描述                                                                                   |
|----------------------------------------------|--------------------------------------------------------------------------------------|
| `POSTGRES_USER`                              | PostgreSQL 数据库的用户名，必须与 `behavioral_control_service 服务` 中的`BEHAVIORAL_CONTROL_SERVER_DB_USER` 相同。                      |
| `POSTGRES_PASSWORD`                          | PostgreSQL 数据库的密码，必须与 `behavioral_control_service 服务` 中的`BEHAVIORAL_CONTROL_SERVER_DB_PASSWORD` 相同。                    |
| `POSTGRES_DB`                                | PostgreSQL 数据库的名称，必须与 `behavioral_control_service 服务` 中的`BEHAVIORAL_CONTROL_SERVER_DB` 相同。                             |


### rabbit 服务

| 设置项                                         | 描述                                                                                   |
|----------------------------------------------|--------------------------------------------------------------------------------------|
| `RABBITMQ_DEFAULT_USER`                      | RabbitMQ 服务的默认用户名，必须与 `behavioral_control_service 服务` 中的 `RABBITMQ_USER` 相同。         |
| `RABBITMQ_DEFAULT_PASS`                      | RabbitMQ 服务的默认密码，必须与 `behavioral_control_service 服务` 中的 `RABBITMQ_PASSWORD` 相同。       |

### celery 服务

该服务中列出的`environment`项目的设置，应与`behavioral_control_service 服务`中对应的项目一致.


## 贡献

欢迎对 Django iKuai 行为控制项目做出贡献！请参阅 CONTRIBUTING.md 文件，了解如何为此项目贡献您的力量。

## 许可证

该项目根据 MIT 许可证授权 - 详情请见 [LICENSE.txt](https://github.com/dzhuang/django_ikuai_behavioral_control/blob/main/LICENSE.txt) 文件。
