# app/rag/data_sources/howtocook_loader.py
"""
HowToCook data ingestion command.

This module parses local HowToCook Markdown recipes/tips, stores the parent
documents in PostgreSQL, and indexes chunks into the Milvus recipes collection.
It is intended to run during setup or whenever the public recipe corpus changes:

    python -m scripts.howtocook_loader
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter

from app.config import DefaultRAGConfig, settings
from app.database.document_repository import DocumentRepository
from app.database.session import close_db, init_db
from app.rag.embeddings.embedding_factory import get_embedding_model
from app.rag.vector_stores.vector_store_factory import get_vector_store

logger = logging.getLogger(__name__)

DOC_NAMESPACE = uuid.UUID("7a7de5f8-7435-4354-9b1b-d50a09848520")


@dataclass
class ParsedDocument:
    """A parent document ready for PostgreSQL insertion and chunking."""

    doc_id: str
    dish_name: str
    category: str
    difficulty: str
    data_source: str
    source_type: str
    source: str
    is_dish_index: bool
    content: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "dish_name": self.dish_name,
            "category": self.category,
            "difficulty": self.difficulty,
            "data_source": self.data_source,
            "source_type": self.source_type,
            "source": self.source,
            "is_dish_index": self.is_dish_index,
            "content": self.content,
            "user_id": None,
        }

    def to_metadata(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "parent_id": self.doc_id,
            "dish_name": self.dish_name,
            "category": self.category,
            "difficulty": self.difficulty,
            "is_dish_index": self.is_dish_index,
            "data_source": self.data_source,
            "user_id": "GLOBAL",
            "source_type": self.source_type,
        }


class HowToCookLoader:
    """Parse HowToCook Markdown files into parent documents and chunks."""

    CATEGORY_MAPPING = {
        "meat_dish": "荤菜",
        "vegetable_dish": "素菜",
        "soup": "汤品",
        "dessert": "甜品",
        "breakfast": "早餐",
        "staple": "主食",
        "aquatic": "水产",
        "condiment": "调料",
        "drink": "饮品",
        "semi-finished": "半成品",
    }

    def __init__(
        self,
        data_path: str | Path,
        tips_path: str | Path | None = None,
        headers_to_split_on: list[tuple[str, str]] | None = None,
        source_root: str | Path | None = None,
    ) -> None:
        self.data_path = Path(data_path)
        self.tips_path = Path(tips_path) if tips_path else None
        self.source_root = Path(source_root) if source_root else self.data_path.parent
        self.headers_to_split_on = headers_to_split_on or [
            ("#", "header_1"),
            ("##", "header_2"),
        ]
        self._splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=self.headers_to_split_on,
            strip_headers=False,
        )

    def load_documents(self) -> list[ParsedDocument]:
        """Load recipes, tips, and generated index documents."""
        documents: list[ParsedDocument] = []
        dishes_by_category: dict[str, list[str]] = {}
        dishes_by_difficulty: dict[str, list[str]] = {}

        if not self.data_path.exists():
            raise FileNotFoundError(f"HowToCook dishes path not found: {self.data_path}")

        logger.info("Loading recipes from %s", self.data_path)
        for md_file in sorted(self.data_path.rglob("*.md")):
            doc = self._parse_recipe_file(md_file)
            if not doc:
                continue
            documents.append(doc)
            dishes_by_category.setdefault(doc.category, []).append(doc.dish_name)
            dishes_by_difficulty.setdefault(doc.difficulty, []).append(doc.dish_name)

        if self.tips_path and self.tips_path.exists():
            logger.info("Loading tips from %s", self.tips_path)
            for md_file in sorted(self.tips_path.rglob("*.md")):
                doc = self._parse_tip_file(md_file)
                if not doc:
                    continue
                documents.append(doc)
                dishes_by_category.setdefault(doc.category, []).append(doc.dish_name)
                dishes_by_difficulty.setdefault(doc.difficulty, []).append(doc.dish_name)
        elif self.tips_path:
            logger.warning("Tips path not found, skipping: %s", self.tips_path)

        index_docs = self._create_index_documents(
            dishes_by_category=dishes_by_category,
            dishes_by_difficulty=dishes_by_difficulty,
        )
        documents.extend(index_docs)

        logger.info(
            "Loaded %d documents (%d source docs, %d index docs)",
            len(documents),
            len(documents) - len(index_docs),
            len(index_docs),
        )
        return documents

    def create_chunks(self, documents: list[ParsedDocument]) -> list[Document]:
        """Create LangChain chunks for Milvus indexing."""
        chunks: list[Document] = []

        for doc in documents:
            metadata = doc.to_metadata()
            if doc.is_dish_index:
                chunks.append(
                    Document(
                        id=str(uuid.uuid5(DOC_NAMESPACE, f"chunk::{doc.doc_id}")),
                        page_content=self._create_index_chunk_content(doc),
                        metadata=metadata,
                    )
                )
                continue

            split_docs = self._splitter.split_text(doc.content)
            if not split_docs:
                split_docs = [Document(page_content=doc.content)]

            for index, chunk_doc in enumerate(split_docs):
                chunk_metadata = metadata.copy()
                chunk_metadata.update(chunk_doc.metadata or {})
                chunks.append(
                    Document(
                        id=str(uuid.uuid5(DOC_NAMESPACE, f"chunk::{doc.doc_id}::{index}")),
                        page_content=chunk_doc.page_content,
                        metadata=chunk_metadata,
                    )
                )

        logger.info("Created %d chunks from %d documents", len(chunks), len(documents))
        return chunks

    def _parse_recipe_file(self, file_path: Path) -> ParsedDocument | None:
        content = self._read_text(file_path)
        if not content.strip():
            return None

        source = self._source_for(file_path)
        return ParsedDocument(
            doc_id=str(uuid.uuid5(DOC_NAMESPACE, source)),
            dish_name=file_path.stem,
            category=self._extract_category(file_path),
            difficulty=self._extract_difficulty(content),
            data_source="recipes",
            source_type="recipes",
            source=source,
            is_dish_index=False,
            content=content,
        )

    def _parse_tip_file(self, file_path: Path) -> ParsedDocument | None:
        content = self._read_text(file_path)
        if not content.strip():
            return None

        source = self._source_for(file_path)
        return ParsedDocument(
            doc_id=str(uuid.uuid5(DOC_NAMESPACE, source)),
            dish_name=file_path.stem,
            category="技巧",
            difficulty="简单",
            data_source="recipes",
            source_type="tips",
            source=source,
            is_dish_index=False,
            content=content,
        )

    def _read_text(self, file_path: Path) -> str:
        try:
            return file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            logger.warning("UTF-8 decode failed, retrying with utf-8-sig: %s", file_path)
            return file_path.read_text(encoding="utf-8-sig")

    def _source_for(self, file_path: Path) -> str:
        try:
            return file_path.relative_to(self.source_root).as_posix()
        except ValueError:
            return file_path.as_posix()

    def _extract_category(self, file_path: Path) -> str:
        for part in file_path.parts:
            if part in self.CATEGORY_MAPPING:
                return self.CATEGORY_MAPPING[part]
        return "其他"

    def _extract_difficulty(self, content: str) -> str:
        star_count = max(
            content.count("⭐"),
            content.count("★"),
            content.count("鈽"),
        )
        if star_count >= 5:
            return "非常困难"
        if star_count == 4:
            return "困难"
        if star_count == 3:
            return "中等"
        if star_count == 2:
            return "简单"
        if star_count == 1:
            return "非常简单"
        return "未知"

    def _create_index_documents(
        self,
        *,
        dishes_by_category: dict[str, list[str]],
        dishes_by_difficulty: dict[str, list[str]],
    ) -> list[ParsedDocument]:
        index_docs: list[ParsedDocument] = []

        overall = self._create_overall_index(dishes_by_category, dishes_by_difficulty)
        if overall:
            index_docs.append(overall)

        for category, names in sorted(dishes_by_category.items()):
            index_docs.append(
                self._create_index_document(
                    key=f"dish_index::category::{category}",
                    dish_name="菜谱索引",
                    category=category,
                    difficulty="未知",
                    title=f"菜谱索引 - {category}",
                    names=names,
                )
            )

        for difficulty, names in sorted(dishes_by_difficulty.items()):
            index_docs.append(
                self._create_index_document(
                    key=f"dish_index::difficulty::{difficulty}",
                    dish_name="菜谱索引",
                    category="索引",
                    difficulty=difficulty,
                    title=f"菜谱索引 - {difficulty}",
                    names=names,
                )
            )

        return index_docs

    def _create_overall_index(
        self,
        dishes_by_category: dict[str, list[str]],
        dishes_by_difficulty: dict[str, list[str]],
    ) -> ParsedDocument | None:
        all_names = sorted(
            {
                name
                for names in dishes_by_category.values()
                for name in names
            }
        )
        if not all_names:
            return None

        content_parts = ["# 菜谱索引\n\n"]
        content_parts.append("本索引包含所有可用菜谱，按类别和难度组织。\n\n")
        content_parts.append("## 按类别\n\n")
        for category, names in sorted(dishes_by_category.items()):
            content_parts.append(f"### {category}\n\n")
            content_parts.append("、".join(sorted(set(names))))
            content_parts.append("\n\n")

        content_parts.append("## 按难度\n\n")
        for difficulty, names in sorted(dishes_by_difficulty.items()):
            content_parts.append(f"### {difficulty}\n\n")
            content_parts.append("、".join(sorted(set(names))))
            content_parts.append("\n\n")

        content_parts.append("## 所有菜谱\n\n")
        content_parts.append("、".join(all_names))
        content_parts.append("\n")

        return ParsedDocument(
            doc_id=str(uuid.uuid5(DOC_NAMESPACE, "dish_index::all")),
            dish_name="菜谱索引",
            category="索引",
            difficulty="未知",
            data_source="recipes",
            source_type="recipes",
            source="dish_index::all",
            is_dish_index=True,
            content="".join(content_parts),
        )

    def _create_index_document(
        self,
        *,
        key: str,
        dish_name: str,
        category: str,
        difficulty: str,
        title: str,
        names: list[str],
    ) -> ParsedDocument:
        unique_names = sorted(set(names))
        content = f"# {title}\n\n" + "、".join(unique_names)
        return ParsedDocument(
            doc_id=str(uuid.uuid5(DOC_NAMESPACE, key)),
            dish_name=dish_name,
            category=category,
            difficulty=difficulty,
            data_source="recipes",
            source_type="recipes",
            source=key,
            is_dish_index=True,
            content=content,
        )

    def _create_index_chunk_content(self, doc: ParsedDocument) -> str:
        return (
            f"{doc.content}\n\n"
            "推荐菜、菜谱列表、菜品、食谱、有哪些菜、按类别推荐、按难度推荐。"
        )


def _build_parser() -> argparse.ArgumentParser:
    default_base = Path(DefaultRAGConfig.paths.base_data_path)
    default_dishes = default_base / DefaultRAGConfig.data_source.howtocook.path_suffix
    default_tips = default_base / DefaultRAGConfig.data_source.howtocook.tips_path_suffix
    default_collection = DefaultRAGConfig.vector_store.collection_names.get(
        "recipes",
        "cook_hero_recipes",
    )

    parser = argparse.ArgumentParser(
        description="Ingest HowToCook Markdown recipes into PostgreSQL and Milvus."
    )
    parser.add_argument("--base-path", default=str(default_base))
    parser.add_argument("--dishes-path", default=str(default_dishes))
    parser.add_argument("--tips-path", default=str(default_tips))
    parser.add_argument("--collection", default=default_collection)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append to existing data instead of rebuilding the recipes corpus.",
    )
    parser.add_argument(
        "--db-only",
        action="store_true",
        help="Only write parent documents to PostgreSQL; skip Milvus indexing.",
    )
    return parser


async def ingest_howtocook(args: argparse.Namespace) -> None:
    """Run the end-to-end ingestion workflow."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    base_path = Path(args.base_path)
    headers = [
        tuple(item)
        for item in DefaultRAGConfig.data_source.howtocook.headers_to_split_on
    ]
    loader = HowToCookLoader(
        data_path=Path(args.dishes_path),
        tips_path=Path(args.tips_path) if args.tips_path else None,
        headers_to_split_on=headers,
        source_root=base_path,
    )

    logger.info("Initializing database schema")
    await init_db()

    if not args.append:
        deleted = await DocumentRepository.delete_by_data_source("recipes")
        logger.info("Deleted %d existing PostgreSQL recipe documents", deleted)

    documents = loader.load_documents()
    if not documents:
        logger.warning("No documents found; nothing to ingest")
        return

    logger.info("Writing %d parent documents to PostgreSQL", len(documents))
    for start in range(0, len(documents), args.batch_size):
        batch = documents[start : start + args.batch_size]
        await DocumentRepository.create_batch([doc.to_dict() for doc in batch])
        logger.info("Wrote PostgreSQL batch %d-%d", start + 1, start + len(batch))

    await DocumentRepository.init_all_metadata_cache()

    if args.db_only:
        logger.info("DB-only mode enabled; skipping Milvus indexing")
        return

    chunks = loader.create_chunks(documents)
    if not chunks:
        logger.warning("No chunks created; skipping Milvus indexing")
        return

    logger.info("Initializing embedding model and Milvus collection")
    embeddings = get_embedding_model(DefaultRAGConfig)
    vector_store = get_vector_store(
        milvus_config=settings.database.milvus,
        collection_name=args.collection,
        embeddings=embeddings,
        chunks=[],
        force_rebuild=not args.append,
    )

    logger.info("Indexing %d chunks into Milvus collection %s", len(chunks), args.collection)
    for start in range(0, len(chunks), args.batch_size):
        batch = chunks[start : start + args.batch_size]
        await asyncio.to_thread(vector_store.add_documents, batch)
        logger.info("Indexed Milvus batch %d-%d", start + 1, start + len(batch))

    logger.info(
        "HowToCook ingestion complete: %d parent documents, %d chunks",
        len(documents),
        len(chunks),
    )


async def run_with_cleanup(args: argparse.Namespace) -> None:
    """Run ingestion and close async database resources in the same event loop."""
    try:
        await ingest_howtocook(args)
    finally:
        await close_db()


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        asyncio.run(run_with_cleanup(args))
    except KeyboardInterrupt:
        logger.warning("Ingestion interrupted")
        return 130
    except Exception:
        logger.exception("HowToCook ingestion failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
