# Ubuntu服务器部署快速指南

## 🚨 遇到 "externally-managed-environment" 错误？

这是Ubuntu 23.04+的新安全机制，**必须使用虚拟环境**。

---

## ✅ 快速部署（3步）

### 1️⃣ 上传文件到服务器

```bash
# 在本地执行
scp -r backend/scripts ubuntu@your_server:/path/to/alpha_strategy_v2/backend/
scp requirements.txt ubuntu@your_server:/path/to/alpha_strategy_v2/
```

### 2️⃣ 创建虚拟环境

```bash
# SSH登录服务器
ssh ubuntu@your_server

# 进入项目目录
cd /path/to/alpha_strategy_v2/backend/scripts

# 赋予执行权限
chmod +x *.sh

# 🔧 创建虚拟环境并安装依赖（一键完成）
bash setup_venv.sh
```

**期望输出：**
```
==========================================
创建Python虚拟环境
==========================================
项目目录: /path/to/alpha_strategy_v2

🔧 创建虚拟环境: /path/to/alpha_strategy_v2/venv
✅ 虚拟环境创建成功

🔧 激活虚拟环境...
🔧 升级pip...
🔧 安装项目依赖...
✅ 所有依赖安装成功

==========================================
🎉 虚拟环境设置完成
==========================================
```

### 3️⃣ 测试并启动

```bash
# 测试运行一次
bash test_sync_once.sh

# 如果测试成功，启动定时服务
bash start_daily_chance_scheduler.sh
```

---

## 📋 常见错误及解决

### ❌ 错误1：pip install 报错
```
error: externally-managed-environment
```

**解决：**
```bash
# ✅ 不要直接用pip，使用虚拟环境
bash setup_venv.sh
```

### ❌ 错误2：启动时报"虚拟环境不存在"
```
❌ 错误: 虚拟环境不存在
请先运行: bash /path/to/setup_venv.sh
```

**解决：**
```bash
bash setup_venv.sh
```

### ❌ 错误3：python3-venv 未安装
```
The virtual environment was not created successfully
```

**解决：**
```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
bash setup_venv.sh
```

---

## 🔍 验证安装

```bash
# 1. 检查虚拟环境是否存在
ls -la /path/to/alpha_strategy_v2/venv

# 2. 激活虚拟环境
source /path/to/alpha_strategy_v2/venv/bin/activate

# 3. 检查依赖
pip list | grep -i apscheduler
# 应该显示：APScheduler  3.10.4

# 4. 退出虚拟环境
deactivate
```

---

## 🚀 完整部署流程

```bash
# SSH登录
ssh ubuntu@your_server

# 进入项目目录
cd /path/to/alpha_strategy_v2/backend/scripts

# 1. 赋予执行权限
chmod +x *.sh

# 2. 创建虚拟环境
bash setup_venv.sh

# 3. 测试运行
bash test_sync_once.sh

# 4. 启动定时服务
bash start_daily_chance_scheduler.sh

# 5. 检查状态
bash check_scheduler_status.sh

# 6. 查看日志
tail -f logs/daily_chance_scheduler.log
```

---

## 📌 重要提示

1. **必须使用虚拟环境** - Ubuntu 23.04+不允许直接pip安装到系统
2. **虚拟环境位置** - `/path/to/alpha_strategy_v2/venv`
3. **启动脚本会自动激活虚拟环境** - 不需要手动激活
4. **每次修改代码后** - 重启服务：`bash stop_daily_chance_scheduler.sh && bash start_daily_chance_scheduler.sh`

---

## 🔧 手动操作（高级）

如果需要手动激活虚拟环境：

```bash
# 激活
source /path/to/alpha_strategy_v2/venv/bin/activate

# 运行Python脚本
python backend/scripts/daily_chance_scheduler.py

# 退出
deactivate
```

---

## 💡 systemd服务配置（开机自启动）

如果希望服务开机自启动：

```bash
# 创建服务文件
sudo nano /etc/systemd/system/daily-chance-sync.service
```

内容：
```ini
[Unit]
Description=Daily Chance Data Sync Service
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/path/to/alpha_strategy_v2
ExecStart=/path/to/alpha_strategy_v2/venv/bin/python /path/to/alpha_strategy_v2/backend/scripts/daily_chance_scheduler.py
Restart=on-failure
RestartSec=10
StandardOutput=append:/path/to/alpha_strategy_v2/backend/scripts/logs/scheduler_output.log
StandardError=append:/path/to/alpha_strategy_v2/backend/scripts/logs/scheduler_output.log

[Install]
WantedBy=multi-user.target
```

启用服务：
```bash
sudo systemctl daemon-reload
sudo systemctl enable daily-chance-sync
sudo systemctl start daily-chance-sync
sudo systemctl status daily-chance-sync
```

---

## 📞 需要帮助？

如遇到问题，提供以下信息：

```bash
# 系统信息
cat /etc/os-release

# Python版本
python3 --version

# 虚拟环境是否存在
ls -la /path/to/alpha_strategy_v2/venv

# 错误日志
cat /path/to/alpha_strategy_v2/backend/scripts/logs/scheduler_output.log
```

