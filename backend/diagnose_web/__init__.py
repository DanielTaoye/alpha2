"""R点诊断 Web（挂载到主服务的 Blueprint）。

说明：
- 该目录原先只是一个独立 Flask 小应用（默认 8000）。
- 现在通过 Blueprint 方式可挂载到主服务 5000 端口下（例如 /r_diagnose/）。
"""


