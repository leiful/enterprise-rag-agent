# 备份与恢复手册

## 1. 使用范围

本手册适用于单台服务器部署场景，目标是先建立本机自动备份能力。

当前备份重点：

- PostgreSQL 数据库。
- 知识库原始文件。
- 备份清单 `manifest.json`。

当前不做：

- 不自动恢复生产数据库。
- 不自动备份或恢复 Milvus 向量索引；向量索引可通过重新索引知识库重建。
- 不复制 `.env.prod` 明文。
- 不替代异地备份、云盘快照或灾备方案。

## 2. 数据丢失场景

本机备份可以降低以下风险：

- 发版失败后需要回滚数据。
- 用户或管理员误删知识库文件。
- 数据库误操作。
- 应用 bug 写坏部分数据。

本机备份不能可靠防止：

- 服务器磁盘损坏。
- 云服务器被释放或重装。
- `/data/rag-agent` 整个目录被删除。
- 入侵者删除生产数据和本机备份。

只有一台服务器时，建议至少做到：

- 每天凌晨自动备份到 `/data/rag-agent/backups`。
- 每次重要更新前手动备份一次。
- 每周下载一份备份到服务器外。
- 每月做一次恢复演练。
- 本机默认只保留最近 14 份自动备份，避免磁盘无限增长。

## 3. 备份内容

默认生产目录：

```text
/data/rag-agent/postgres/   PostgreSQL 数据目录，不直接复制
/data/rag-agent/knowledge/  知识库原始文件
/data/rag-agent/milvus/     Milvus 向量索引数据，默认不进入脚本备份
/data/rag-agent/backups/    本机备份输出目录
```

备份脚本会生成：

```text
/data/rag-agent/backups/YYYYMMDD-HHMMSS/
  ai_agent.dump
  knowledge.tar.gz
  manifest.json
```

说明：

- `ai_agent.dump` 来自 `pg_dump -F c`，用于 `pg_restore`。
- `knowledge.tar.gz` 是知识库原始文件压缩包。
- `manifest.json` 记录备份时间、数据库名、知识库目录和文件名。
- Milvus 向量索引默认不备份；如果清空或丢失，恢复 PostgreSQL 和知识文件后重新同步或重建知识库索引。
- `.env.prod` 不会被复制，因为里面包含生产密钥、数据库密码和 Cookie secret。

## 4. 手动备份

在服务器 `/opt/rag-agent` 目录执行：

```bash
python scripts/backup_prod_data.py
```

默认参数：

```bash
python scripts/backup_prod_data.py \
  --backups-dir /data/rag-agent/backups \
  --knowledge-dir /data/rag-agent/knowledge \
  --retention-count 14
```

备份完成后检查：

```bash
ls -lh /data/rag-agent/backups
ls -lh /data/rag-agent/backups/YYYYMMDD-HHMMSS
cat /data/rag-agent/backups/YYYYMMDD-HHMMSS/manifest.json
```

如果备份失败，先查看输出错误，不要继续做发布或恢复操作。

## 5. 自动备份

服务器上使用 `cron` 做每天凌晨自动备份。

编辑 crontab：

```bash
crontab -e
```

加入：

```cron
0 2 * * * cd /opt/rag-agent && python scripts/backup_prod_data.py --retention-count 14 >> /data/rag-agent/backups/backup.log 2>&1
```

含义：

- 每天 02:00 执行一次。
- 在 `/opt/rag-agent` 目录运行脚本。
- 日志写入 `/data/rag-agent/backups/backup.log`。
- 备份成功后只保留最近 14 个形如 `YYYYMMDD-HHMMSS` 的备份目录。
- 不会删除 `backup.log`、手工命名目录或其他非脚本生成的文件。

配置后检查：

```bash
crontab -l
tail -n 100 /data/rag-agent/backups/backup.log
```

第一次配置后，建议手动执行一次脚本确认权限和路径正确。

## 6. 磁盘空间与保留策略

自动备份会持续占用磁盘空间。空间增长主要来自：

- `ai_agent.dump`：数据库、会话、审计、反馈、chunk 文本、元数据和 BM25 数据。
- `knowledge.tar.gz`：知识库原始文件。
- Milvus 向量索引不在当前脚本备份中；如需保留，可另行备份 `/data/rag-agent/milvus`，但通常可以通过重建索引恢复。

当前脚本默认：

```bash
python scripts/backup_prod_data.py --retention-count 14
```

含义：

- 每次备份成功后，扫描备份目录。
- 只识别形如 `YYYYMMDD-HHMMSS` 的目录。
- 超过保留数量时，删除最旧的脚本生成目录。
- 不删除日志文件、手工目录或其他文件。

建议定期检查磁盘：

```bash
df -h
du -sh /data/rag-agent/backups
du -sh /data/rag-agent/knowledge
du -sh /data/rag-agent/milvus
```

如果磁盘增长过快，可以临时降低保留数量，例如：

```bash
python scripts/backup_prod_data.py --retention-count 7
```

但保留数量越少，可回退的时间窗口越短。生产环境不要只依赖本机备份，仍应每周下载或同步一份到服务器外。

## 7. 恢复数据库

恢复生产数据库前必须确认：

- 当前目标环境就是要恢复的环境。
- 已经停止写入流量或安排停机窗口。
- 备份文件来自可信时间点。
- 知道恢复会覆盖或删除当前数据库中的部分数据。

停止后端和 nginx：

```bash
docker compose --env-file .env.prod -f compose.prod.yml stop backend nginx
```

复制 dump 到 PostgreSQL 容器：

```bash
docker cp /data/rag-agent/backups/YYYYMMDD-HHMMSS/ai_agent.dump ai-agent-postgres:/tmp/ai_agent.dump
```

恢复数据库：

```bash
docker exec ai-agent-postgres pg_restore \
  -U ai_agent_user \
  -d ai_agent \
  --clean \
  --if-exists \
  /tmp/ai_agent.dump
```

清理临时文件并重启：

```bash
docker exec ai-agent-postgres rm -f /tmp/ai_agent.dump
docker compose --env-file .env.prod -f compose.prod.yml up -d
python scripts/verify_prod_deploy.py
```

## 8. 恢复知识库文件

恢复知识库原始文件前，先停止后端：

```bash
docker compose --env-file .env.prod -f compose.prod.yml stop backend
```

恢复文件：

```bash
tar -xzf /data/rag-agent/backups/YYYYMMDD-HHMMSS/knowledge.tar.gz -C /data/rag-agent
sudo chown -R 1001:1001 /data/rag-agent/knowledge
```

重启服务：

```bash
docker compose --env-file .env.prod -f compose.prod.yml up -d
python scripts/verify_prod_deploy.py
```

如果知识库索引状态异常，进入系统检查知识库状态，必要时重新同步或重建索引。

## 9. 恢复后验证

恢复后至少检查：

```bash
python scripts/verify_prod_deploy.py --public-url https://your-domain.com
docker logs ai-agent-backend --tail 100
docker logs ai-agent-nginx --tail 100
```

浏览器 smoke test：

- 能登录。
- 聊天页正常。
- 历史会话还在。
- 知识库文件还在。
- 新问题能回答。
- 来源能正常展示。
- Console 没有红色运行时错误。

## 10. 后续演进

当本机备份稳定后，再考虑：

- 每周同步一份备份到本地电脑或对象存储。
- 云盘快照。
- 更细的备份保留策略，例如保留最近 7 天每日备份和最近 4 周周备份。
- 恢复演练脚本。
- 备份成功或失败通知。
