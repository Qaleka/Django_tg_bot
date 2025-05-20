## 📍 Дата-центр: NY
### Микросервисы
```md
| Сервис | RPS | CPU | RAM |
|--------|-----|-----|-----|
| AuthorizationService | 520.00 | 0.10 | 5.20 MB |
| UserService | 220.00 | 0.22 | 22.00 MB |
| CalendarService | 2893.60 | 0.58 | 28.94 MB |
| EventService | 4051.60 | 13.51 | 2701.07 MB |
| InvitationService | 2315.20 | 2.32 | 231.52 MB |
| ReminderService | 1157.60 | 1.16 | 115.76 MB |
| SyncService | 400.00 | 0.40 | 40.00 MB |
| EmailService | 400.00 | 0.08 | 4.00 MB |
| API Gateway | 10418.00 | 2.08 | 104.18 MB |
| Nginx | 10418.00 | 2.08 | 20.84 MB |
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
| База данных | CPU | RAM | Диск |
|-------------|-----|-----|------|
| Cassandra   | 208.00 | 1200.00 GB | ≈ 35.2 PB |
| Elastic     | 2.20 | 19.20 GB | 1.0 TB |
| Kafka       | 40.00 | 12.80 GB | 1.0 TB |
```
