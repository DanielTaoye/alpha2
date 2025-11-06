# 快速开始指南

## 📋 前置条件

- Python 3.7+
- MySQL 5.7+
- 浏览器（Chrome/Edge推荐）

## 🚀 三步启动

### 第一步：安装依赖

**Windows用户：**
```bash
install.bat
```

**Linux/Mac用户：**
```bash
pip install -r requirements.txt
```

### 第二步：配置数据库

编辑 `backend/app.py`，找到第10行左右：

```python
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'your_password',  # ⚠️ 改成你的密码
    'database': 'your_database',  # ⚠️ 改成你的数据库名
    'charset': 'utf8mb4'
}
```

### 第三步：启动服务

**Windows用户：**
```bash
start.bat
```

**Linux/Mac用户：**
```bash
cd backend
python app.py
```

## 🌐 访问系统

打开浏览器访问：http://localhost:5000

## 📊 系统界面说明

系统将显示15支股票，分为三组：

### 波段策略（5支）
- 国投智能 (SZ300188)
- 海兴电力 (SH603556)
- 沃尔核材 (SZ002130)
- 歌华有线 (SH600037)
- 中集车辆 (SZ301039)

### 短线策略（5支）
- 白云机场 (SH600004)
- 金雷股份 (SZ300443)
- 南京化纤 (SH600889)
- 慧智微-U (SH688512)
- 锴威特 (SH688693)

### 中长线策略（5支）
- 立讯精密 (SZ002475)
- 宁德时代 (SZ300750)
- 农业银行 (SH601288)
- 中国石油 (SH601857)
- 紫金矿业 (SH601899)

## 🔧 数据库检查（可选）

如果遇到问题，可以先检查数据库：

```bash
python database_check.py
```

这个工具会检查：
- ✅ 数据库连接
- ✅ 数据表是否存在
- ✅ 表结构是否完整
- ✅ 数据是否充足

## ❓ 常见问题

### 1. 数据库连接失败？

**检查项：**
- MySQL服务是否启动
- 用户名密码是否正确
- 数据库名是否存在

### 2. 页面显示"数据加载失败"？

**可能原因：**
- 数据表不存在（表名格式：`basic_data_股票代码小写`）
- 数据为空
- 网络问题

**解决方法：**
```bash
# 运行数据库检查工具
python database_check.py
```

### 3. 支撑线/压力线不显示？

这是正常的，这些数据来自外部API，可能：
- API调用失败
- Token过期
- 网络问题

K线图本身不受影响。

## 📁 项目结构

```
alpha_strategy_v2/
├── backend/
│   └── app.py              # Flask后端服务
├── frontend/
│   └── index.html          # 前端页面
├── config.py               # 配置文件
├── requirements.txt        # Python依赖
├── database_check.py       # 数据库检查工具
├── install.bat            # 安装脚本（Windows）
├── start.bat              # 启动脚本（Windows）
├── start.sh               # 启动脚本（Linux/Mac）
├── README.md              # 项目说明
├── QUICKSTART.md          # 本文件
└── USAGE.md               # 详细使用指南
```

## 🎯 功能特性

- **多周期K线**：30分钟、日、周、月四种周期
- **技术分析**：益损比、支撑线、压力线
- **实时指标**：量比、委比
- **交互操作**：缩放、拖动、详情查看
- **美观界面**：深色主题，现代化设计

## 📖 更多文档

- **详细使用指南**：查看 `USAGE.md`
- **项目说明**：查看 `README.md`

## 💡 小技巧

1. **切换周期**：点击右上角按钮
2. **缩放图表**：鼠标滚轮
3. **查看详情**：鼠标悬停在K线上
4. **调整范围**：拖动底部滑块

## 🎉 开始使用

现在你可以开始使用阿尔法策略2.0系统了！

如有问题，请查看 `USAGE.md` 获取更详细的帮助。

