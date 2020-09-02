### Что делает
- Скрипт находит последний nginx лог в заданной директории
- Парсит из него урл, время ответа от сервера
- Агрерирует данные по урлу и высчитывает:
    - count - кол-во реквестов
    - count_perc - кол-во реквестов в процентах
    - time_sum - суммарное время
    - time_perc - суммарное время в процентах
    - time_avg - среднее время
    - time_max - максимальное время
    - time_med - медиана времени
- Генерит html репорт в заданную директорию

### Формат логов
log_format ui_short '$remote_addr $remote_user $http_x_real_ip [$time_local] "$request" ' '$status $body_bytes_sent "$http_referer" '
'"$http_user_agent" "$http_x_forwarded_for" "$http_X_REQUEST_ID" "$http_X_RB_USER" ' '$request_time';

### Как запускать
```sh
python log_analyzer.py
```

### Опции
  - -- config - путь до конфиг в ini формате. Дефолтный конфиг лежит в configs/

### Тесты
```sh
python -m unittest -v test_log_analyzer
```