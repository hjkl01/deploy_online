import asyncio
from collections import defaultdict

# API 进程内只保存连接状态；SQLite 是部署状态和日志的最终事实来源。
queues = defaultdict(set)
login_attempts = defaultdict(list)
