from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from proofline.llm import OpenAIExtractor
from proofline.pipeline import KnowledgeLayer
from proofline.store import Store


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Ingest PDFs into the Proofline knowledge layer")
    parser.add_argument("pdfs", nargs="+", type=Path)
    parser.add_argument(
        "--db",
        type=Path,
        default=Path(os.getenv("PROOFLINE_DB_PATH", "data/proofline.db")),
    )
    parser.add_argument("--skip-relations", action="store_true")
    args = parser.parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        parser.error("OPENAI_API_KEY is required to process new PDFs")

    layer = KnowledgeLayer(
        Store(args.db),
        OpenAIExtractor(model=os.getenv("OPENAI_MODEL", "gpt-5.4-mini")),
    )
    for path in args.pdfs:
        result = layer.ingest_pdf(
            path,
            progress=lambda name, current, total: print(
                f"{name}: extracting chunk {current}/{total}", flush=True
            ),
        )
        state = "already present" if result.skipped else f"{result.facts_added} facts"
        print(f"{result.name}: {state}; {result.facts_rejected} rejected")
    if not args.skip_relations:
        print(f"Added {layer.discover_relations()} cross-document relations")


if __name__ == "__main__":
    main()
