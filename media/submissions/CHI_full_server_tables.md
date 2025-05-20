## 📍 Дата-центр: CHI
### Микросервисы
```md
| Сервис | Пиковый RPS | Характер нагрузки | **CPU**<br/>= RPS / RPS_на_1_ядро | **RAM**<br/>= CPU × MB_на_ядро | Выходной трафик |
|--------|---------------|--------------------|----------------------------------|------------------------|------------------|
| **AuthorizationService** | 520 | лёгкая (Go Gin) | **520 / 5000 ≈ 0.1 CPU** | **0 × 50 ≈ 5.2 MB** | ≈ 50 Mbit/s |
| **UserService** | 220 | средняя (Go CRUD) | **220 / 1000 ≈ 0.2 CPU** | **0 × 100 ≈ 22.0 MB** | 20 Mbit/s |
| **CalendarService** | 2,893 | лёгкая | **2893 / 5000 ≈ 0.6 CPU** | **0 × 50 ≈ 28.9 MB** | 300 Mbit/s |
| **EventService** | 4,051 | тяжёлая (Go-stream) | **4051 / 300 ≈ 13.5 CPU** | **13 × 200 ≈ 2701.1 MB** | 500 Mbit/s |
| **InvitationService** | 2,315 | средняя | **2315 / 1000 ≈ 2.3 CPU** | **2 × 100 ≈ 231.5 MB** | 200 Mbit/s |
| **ReminderService** | 1,157 | средняя | **1157 / 1000 ≈ 1.2 CPU** | **1 × 100 ≈ 115.8 MB** | 100 Mbit/s |
| **SyncService** | 400 | средняя | **400 / 1000 ≈ 0.4 CPU** | **0 × 100 ≈ 40.0 MB** | 50 Mbit/s |
| **EmailService** | 400 | лёгкая | **400 / 5000 ≈ 0.1 CPU** | **0 × 50 ≈ 4.0 MB** | 50 Mbit/s |
| **API Gateway** | 10,418 | маршрутизация | **10418 / 5000 ≈ 2.1 CPU** | **2 × 50 ≈ 104.2 MB** | 1 Gbit/s |
| **Nginx** | 10,418 | reverse-proxy | **10418 / 5000 ≈ 2.1 CPU** | **2 × 10 ≈ 20.8 MB** | 1 Gbit/s |
```
### Контейнеры (поды)
```md
| Сервис | Контейнеров |
|--------|--------------|
| AuthorizationService | 1 |
| UserService | 1 |
| CalendarService | 5 |
| EventService | 41 |
| InvitationService | 8 |
| ReminderService | 4 |
| SyncService | 1 |
| EmailService | 1 |
| API Gateway | 17 |
| Nginx | 2 |
```
### Базы данных
```md
| База данных | Целевая нагрузка | CPU | RAM | Диск |
|-------------|------------------|-----|-----|------|
| Cassandra (Events, Calendars, Reminders, Sessions) | 10400 RPS | 208 | 1200 GB | ~35.2 PB |
| ElasticSearch (User Search) | 220 RPS | 2 | 19 GB | 1.0 TB |
| Kafka Cluster (Event Bus) | 2000 сообщений/сек | 40 | 13 GB | 1.0 TB |
```
