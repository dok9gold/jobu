"""Kafka 테스트 프로듀서"""
import asyncio
import json
from aiokafka import AIOKafkaProducer


async def send_test_message():
    producer = AIOKafkaProducer(
        bootstrap_servers='localhost:9092',
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )

    await producer.start()
    try:
        # 테스트 메시지 전송
        message = {
            "handler_name": "db_loader",
            "params": {
                "input_path": "/tmp/test.parquet",
                "target_table": "sample_data"
            }
        }

        await producer.send_and_wait("jobu-events", message)
        print(f"Sent: {message}")

    finally:
        await producer.stop()


if __name__ == "__main__":
    asyncio.run(send_test_message())
