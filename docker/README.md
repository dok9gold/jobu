# Docker 개발 환경

jobu 개발/테스트용 PostgreSQL, MySQL, Kafka 환경을 제공합니다.

## 실행

```bash
cd docker

# 전체 실행
docker-compose up -d

# PostgreSQL만 실행
docker-compose up -d postgres

# MySQL만 실행
docker-compose up -d mysql

# Kafka만 실행 (Zookeeper 포함)
docker-compose up -d kafka

# 로그 확인
docker-compose logs -f

# 종료
docker-compose down

# 볼륨 포함 완전 삭제
docker-compose down -v
```

## 접속 정보

### PostgreSQL
| 항목 | 값 |
|------|-----|
| Host | localhost |
| Port | 5432 |
| Database | jobu |
| User | jobu |
| Password | jobu_dev |

```bash
# CLI 접속
psql -h localhost -U jobu -d jobu
# 비밀번호: jobu_dev

# Docker 컨테이너 내부 접속
docker exec -it jobu-postgres psql -U jobu -d jobu
```

### MySQL
| 항목 | 값 |
|------|-----|
| Host | localhost |
| Port | 3306 |
| Database | jobu |
| User | jobu |
| Password | jobu_dev |
| Root Password | root_dev |

```bash
# CLI 접속
mysql -h localhost -u jobu -pjobu_dev jobu

# Docker 컨테이너 내부 접속
docker exec -it jobu-mysql mysql -u jobu -pjobu_dev jobu
```

### Kafka
| 항목 | 값 |
|------|-----|
| Host | localhost |
| Port | 9092 |
| Internal Port | 29092 (컨테이너 간 통신) |

```bash
# 토픽 목록 조회
docker exec -it jobu-kafka kafka-topics --bootstrap-server localhost:9092 --list

# 토픽 생성
docker exec -it jobu-kafka kafka-topics --bootstrap-server localhost:9092 \
  --create --topic job-events --partitions 1 --replication-factor 1

# 메시지 전송 테스트
docker exec -it jobu-kafka kafka-console-producer --bootstrap-server localhost:9092 --topic job-events

# 메시지 수신 테스트
docker exec -it jobu-kafka kafka-console-consumer --bootstrap-server localhost:9092 --topic job-events --from-beginning
```

### Zookeeper
| 항목 | 값 |
|------|-----|
| Host | localhost |
| Port | 2181 |

Kafka 의존성으로 자동 실행됩니다.

## 리소스 제한

| 서비스 | 최소 메모리 | 최대 메모리 |
|--------|-------------|-------------|
| PostgreSQL | 128MB | 256MB |
| MySQL | 256MB | 512MB |
| Kafka | 256MB | 512MB |
| Zookeeper | 128MB | 256MB |

## 초기화 SQL

컨테이너 최초 실행 시 아래 스크립트가 자동 실행됩니다:
- `init/postgres/init.sql` - PostgreSQL 테이블 생성
- `init/mysql/init.sql` - MySQL 테이블 생성

초기화 SQL을 다시 실행하려면 볼륨을 삭제 후 재시작:
```bash
docker-compose down -v
docker-compose up -d
```

## 상태 확인

```bash
# 컨테이너 상태
docker-compose ps

# 헬스체크 상태
docker inspect jobu-postgres --format='{{.State.Health.Status}}'
docker inspect jobu-mysql --format='{{.State.Health.Status}}'
docker inspect jobu-kafka --format='{{.State.Health.Status}}'
```
