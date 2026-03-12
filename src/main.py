import logging
import signal
import sys

import uvicorn

from src.config import AppConfig
from src.db.connection import create_pool
from src.db.repository import TransactionRepo, FeedbackRepo, ExperimentRepo
from src.streaming.topics import ensure_topics, setup_ksqldb
from src.streaming.producer import SimulatedProducer
from src.streaming.consumer import FraudConsumer
from src.detection.ml_model import IsolationForestModel
from src.detection.pipeline import ScoringPipeline
from src.fraud_rings.graph_engine import FraudGraph
from src.llm.client import AzureOpenAIClient
from src.llm.analyzer import LLMAnalyzer
from src.feedback.review_queue import ReviewQueue
from src.feedback.feedback_store import FeedbackStore
from src.feedback.retrain_trigger import RetrainTrigger
from src.ab_testing.experiment import ExperimentManager
from src.ab_testing.router import ABRouter
from src.ab_testing.metrics import MetricsCollector
from src.api.app import create_app
from src.api import routes_transactions, routes_review, routes_ab, routes_metrics

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    config = AppConfig()

    # 1. MySQL pool
    pool = create_pool(
        config.MYSQL_HOST,
        config.MYSQL_PORT,
        config.MYSQL_USER,
        config.MYSQL_PASSWORD,
        config.MYSQL_DATABASE,
    )
    tx_repo = TransactionRepo()
    feedback_repo = FeedbackRepo()
    experiment_repo = ExperimentRepo()

    # 2. Kafka topics + ksqlDB streams
    ensure_topics(config.KAFKA_BOOTSTRAP_SERVERS)
    setup_ksqldb(config.KSQLDB_URL)

    # 3. Detection components
    ml_model = IsolationForestModel(
        contamination=config.ML_CONTAMINATION,
        min_training_samples=config.ML_MIN_TRAINING_SAMPLES,
        retrain_interval=config.ML_RETRAIN_INTERVAL,
    )
    graph = FraudGraph(min_users=config.FRAUD_RING_MIN_USERS)
    # 4. LLM (optional)
    llm_analyzer = None
    if config.LLM_ENABLED and config.AZURE_OPENAI_ENDPOINT:
        llm_client = AzureOpenAIClient(
            endpoint=config.AZURE_OPENAI_ENDPOINT,
            api_key=config.AZURE_OPENAI_API_KEY,
            deployment=config.AZURE_OPENAI_DEPLOYMENT,
            api_version=config.AZURE_OPENAI_API_VERSION,
        )
        llm_analyzer = LLMAnalyzer(client=llm_client, enabled=True)

    # 5. A/B testing
    experiment_manager = ExperimentManager(experiment_repo)
    models = {ml_model.version: ml_model}
    ab_router = ABRouter(experiment_manager, models)
    metrics_collector = MetricsCollector(experiment_repo)

    # 6. Scoring pipeline
    pipeline = ScoringPipeline(
        ml_model=ml_model,
        graph_engine=graph,
        fraud_threshold=config.SCORE_THRESHOLD_FRAUD,
        review_threshold=config.SCORE_THRESHOLD_REVIEW,
    )

    # 7. Feedback loop
    review_queue = ReviewQueue(config.KAFKA_BOOTSTRAP_SERVERS)
    feedback_store = FeedbackStore(feedback_repo, config.KAFKA_BOOTSTRAP_SERVERS)
    retrain_trigger = RetrainTrigger(
        feedback_store=feedback_store,
        ml_model=ml_model,
        bootstrap_servers=config.KAFKA_BOOTSTRAP_SERVERS,
        threshold=config.RETRAIN_FEEDBACK_THRESHOLD,
        check_interval_secs=config.RETRAIN_CHECK_INTERVAL_SECS,
    )

    # 8. Streaming
    consumer = FraudConsumer(
        bootstrap_servers=config.KAFKA_BOOTSTRAP_SERVERS,
        pipeline=pipeline,
        tx_repo=tx_repo,
    )
    producer = SimulatedProducer(
        bootstrap_servers=config.KAFKA_BOOTSTRAP_SERVERS,
        interval_min=config.PRODUCER_INTERVAL_MIN,
        interval_max=config.PRODUCER_INTERVAL_MAX,
    )

    # 9. Wire API dependencies
    routes_transactions._deps = {
        "pipeline": pipeline,
        "tx_repo": tx_repo,
    }
    routes_review._deps = {
        "review_queue": review_queue,
        "feedback_store": feedback_store,
        "tx_repo": tx_repo,
    }
    routes_ab._deps = {
        "exp_repo": experiment_repo,
        "experiment_manager": experiment_manager,
        "metrics_collector": metrics_collector,
    }
    routes_metrics._deps = {
        "tx_repo": tx_repo,
        "review_queue": review_queue,
        "exp_repo": experiment_repo,
        "feedback_store": feedback_store,
    }
    routes_transactions._deps["bootstrap_servers"] = config.KAFKA_BOOTSTRAP_SERVERS

    # 10. Create FastAPI app
    app = create_app()

    # 11. Start background threads
    components = [producer, consumer, review_queue, retrain_trigger]
    for c in components:
        c.start()
    logger.info("All background components started")

    # 12. Graceful shutdown
    def shutdown(signum, frame):
        logger.info("Shutdown signal received")
        for c in reversed(components):
            c.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # 13. Start FastAPI (blocking)
    logger.info("Starting FastAPI on %s:%d", config.API_HOST, config.API_PORT)
    uvicorn.run(app, host=config.API_HOST, port=config.API_PORT, log_level="info")


if __name__ == "__main__":
    main()
