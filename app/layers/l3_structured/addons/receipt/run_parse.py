import argparse
import asyncio
import json
from app.infrastructure.db.session import AsyncSessionLocal
from .service import parse_receipt_file, DEFAULT_TOOL_NAME

async def run(args):
    async with AsyncSessionLocal() as session:
        result = await parse_receipt_file(session, args.file_hash, args.artifact_id, args.tool_name)
    print(json.dumps(result, ensure_ascii=False, indent=2))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file-hash", required=True)
    parser.add_argument("--artifact-id", required=True)
    parser.add_argument("--tool-name", default=DEFAULT_TOOL_NAME)
    asyncio.run(run(parser.parse_args()))

if __name__ == "__main__":
    main()
