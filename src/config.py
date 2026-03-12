from pydantic_settings import BaseSettings


class AppConfig(BaseSettings):
    # -- Kafka --
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:29092"

    # -- ksqlDB --
    KSQLDB_URL: str = "http://ksqldb-server:8088"

    # -- MySQL --
    MYSQL_HOST: str = "mysql"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "fraud_user"
    MYSQL_PASSWORD: str = "change_me"
    MYSQL_DATABASE: str = "fraud_db"

    # -- Azure OpenAI --
    AZURE_OPENAI_ENDPOINT: str = ""
    AZURE_OPENAI_API_KEY: str = ""
    AZURE_OPENAI_DEPLOYMENT: str = "gpt-4o"
    AZURE_OPENAI_API_VERSION: str = "2024-10-21"
    LLM_ENABLED: bool = True

    # -- Fraud Detection --
    HIGH_AMOUNT_THRESHOLD_FULL: float = 10000.0
    HIGH_AMOUNT_THRESHOLD_PARTIAL: float = 5000.0
    FRAUD_RING_MIN_USERS: int = 3
    ML_CONTAMINATION: float = 0.1
    ML_MIN_TRAINING_SAMPLES: int = 50
    ML_RETRAIN_INTERVAL: int = 100

    # -- Routing thresholds --
    SCORE_THRESHOLD_FRAUD: int = 80
    SCORE_THRESHOLD_REVIEW: int = 30

    # -- Retraining --
    RETRAIN_FEEDBACK_THRESHOLD: int = 100
    RETRAIN_CHECK_INTERVAL_SECS: int = 300

    # -- A/B Testing --
    AB_MAX_TRAFFIC_SPLIT: float = 0.5
    AB_MIN_SAMPLE_SIZE: int = 500

    # -- API --
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # -- Producer --
    PRODUCER_INTERVAL_MIN: float = 0.1
    PRODUCER_INTERVAL_MAX: float = 1.0

    model_config = {"env_file": ".env", "case_sensitive": True}
