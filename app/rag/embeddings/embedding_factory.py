# app/rag/embeddings/embedding_factory.py
import logging
from langchain_core.embeddings import Embeddings
from app.config import RAGConfig

logger = logging.getLogger(__name__)

def get_embedding_model(config: RAGConfig) -> Embeddings:
    """
    Factory function to create and return an embedding model based on the config.
    Args:
        config: The RAG configuration object.
    Returns:
        An instance of an embedding model.
    """
    embedding_config = config.embedding

    if embedding_config.type == "huggingface":
        from langchain_huggingface import HuggingFaceEmbeddings

        logger.info(
            "Initializing HuggingFace embedding model: %s",
            embedding_config.model_name,
        )
        return HuggingFaceEmbeddings(
            model_name=embedding_config.model_name,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )

    if embedding_config.type == "siliconflow":
        from langchain_openai import OpenAIEmbeddings

        if not embedding_config.api_key:
            raise ValueError(
                "SiliconFlow embedding requires an API key. "
                "Set embedding.api_key in config.yml or EMBEDDING_API_KEY in .env."
            )

        base_url = (embedding_config.base_url or "https://api.siliconflow.cn/v1").rstrip("/")
        logger.info(
            "Initializing SiliconFlow embedding model: %s via %s",
            embedding_config.model_name,
            base_url,
        )
        return OpenAIEmbeddings(
            model=embedding_config.model_name,
            api_key=embedding_config.api_key,
            base_url=base_url,
            chunk_size=embedding_config.batch_size,
        )

    raise ValueError(f"Unsupported embedding type: {embedding_config.type}")
