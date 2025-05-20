## 📍 Дата-центр: MSK
### Микросервисы
```md
| Сервис | Пиковый RPS | Характер нагрузки | **CPU**<br/>= RPS / RPS_на_1_ядро | **RAM**<br/>= CPU × MB_на_ядро | Выходной трафик |
|--------|---------------|--------------------|----------------------------------|------------------------|------------------|
| **AuthorizationService** | 156 | лёгкая (Go Gin) | **156 / 5000 ≈ 0.0 CPU** | **0 × 50 ≈ 1.6 MB** | ≈ 50 Mbit/s |
| **UserService** | 66 | средняя (Go CRUD) | **66 / 1000 ≈ 0.1 CPU** | **0 × 100 ≈ 6.6 MB** | 20 Mbit/s |
| **CalendarService** | 868 | лёгкая | **868 / 5000 ≈ 0.2 CPU** | **0 × 50 ≈ 8.7 MB** | 300 Mbit/s |
| **EventService** | 1,215 | тяжёлая (Go-stream) | **1215 / 300 ≈ 4.1 CPU** | **4 × 200 ≈ 810.3 MB** | 500 Mbit/s |
| **InvitationService** | 694 | средняя | **694 / 1000 ≈ 0.7 CPU** | **0 × 100 ≈ 69.5 MB** | 200 Mbit/s |
| **ReminderService** | 347 | средняя | **347 / 1000 ≈ 0.3 CPU** | **0 × 100 ≈ 34.7 MB** | 100 Mbit/s |
| **SyncService** | 120 | средняя | **120 / 1000 ≈ 0.1 CPU** | **0 × 100 ≈ 12.0 MB** | 50 Mbit/s |
| **EmailService** | 120 | лёгкая | **120 / 5000 ≈ 0.0 CPU** | **0 × 50 ≈ 1.2 MB** | 50 Mbit/s |
| **API Gateway** | 3,125 | маршрутизация | **3125 / 5000 ≈ 0.6 CPU** | **0 × 50 ≈ 31.3 MB** | 1 Gbit/s |
| **Nginx** | 3,125 | reverse-proxy | **3125 / 5000 ≈ 0.6 CPU** | **0 × 10 ≈ 6.3 MB** | 1 Gbit/s |
```
### Контейнеры (поды)
```md
| Сервис | Контейнеров |
|--------|--------------|
| AuthorizationService | 0 |
| UserService | 0 |
| CalendarService | 1 |
| EventService | 12 |
| InvitationService | 2 |
| ReminderService | 1 |
| SyncService | 0 |
| EmailService | 0 |
| API Gateway | 5 |
| Nginx | 1 |
```
### Базы данных
```md
| База данных | Целевая нагрузка | CPU | RAM | Диск |
|-------------|------------------|-----|-----|------|
| Cassandra (Events, Calendars, Reminders, Sessions) | 3120 RPS | 62 | 360 GB | ~10.56 PB |
| ElasticSearch (User Search) | 66 RPS | 1 | 6 GB | 0.3 TB |
| Kafka Cluster (Event Bus) | 600 сообщений/сек | 12 | 4 GB | 0.3 TB |
```
