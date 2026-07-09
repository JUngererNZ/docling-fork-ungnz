from pathlib import Path
from docling.document_converter import DocumentConverter
from datetime import datetime
import hashlib
import json
import traceback
import extract_msg
import random
import string
import re

# ==========================================================
# CONFIGURATION
# ==========================================================

SOURCE_FOLDER = Path(
    r"C:\Users\Jason\Projects\C:\Users\Jason\OneDrive - FML Freight Solutions\Microsoft Copilot Chat Files"
)

OUTPUT_ROOT = SOURCE_FOLDER / "_json_output"
DOCUMENTS_FOLDER = OUTPUT_ROOT / "documents"

DOCUMENTS_FOLDER.mkdir(parents=True, exist_ok=True)

HASH_FILE = OUTPUT_ROOT / "processed_files.json"
FAILED_LOG = OUTPUT_ROOT / "failed_files.log"
KNOWLEDGE_BASE = OUTPUT_ROOT / "knowledge_base.jsonl"

CHUNK_SIZE = 3000

SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".xlsx",
    ".msg",
    ".txt",
    ".md",
    ".json"
}

# ==========================================================
# HELPERS
# ==========================================================

def sha256_file(filepath):
    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            sha.update(block)
    return sha.hexdigest()


def generate_document_id():
    chars = string.ascii_uppercase + string.digits
    return "DOC-" + "".join(random.choice(chars) for _ in range(5))


def find_file_ref(text):
    patterns = [
        r"\b\d{4}DSI\d+\b",
        r"\b\d{4}DSI\d{4}\b"
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group()
    return None


def find_pin(text):
    patterns = [
        r"CAT[A-Z0-9]{10,}",
        r"PIN\s*NO[:\s]+([A-Z0-9]+)",
        r"PIN\s*NUMBER[:\s]+([A-Z0-9]+)"
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            if match.groups():
                return match.group(1)
            return match.group()
    return None


def get_document_category(relative_path):
    p = str(relative_path).lower()
    if "customs" in p:
        return "Customs"
    if "costing" in p:
        return "Costing"
    if "quote" in p:
        return "Quote"
    if "packing" in p:
        return "Packing List"
    if "claim" in p:
        return "Claim"
    if "email" in p or "msg" in p:
        return "Email"
    if "checklist" in p:
        return "Checklist"
    if "invoice" in p:
        return "Invoice"
    if "sop" in p:
        return "SOP"
    if "procedure" in p:
        return "Procedure"
    return "General"


def load_hashes():
    """Return dict: filepath -> {'hash': hash, 'doc_id': doc_id}"""
    if not HASH_FILE.exists():
        return {}
    with open(HASH_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Convert legacy format (just hash string) to new dict format
    for key, value in list(data.items()):
        if isinstance(value, str):
            data[key] = {"hash": value, "doc_id": generate_document_id()}
    return data


def save_hashes(data):
    with open(HASH_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def read_knowledge_base():
    """Read existing knowledge base lines, return list of (line, doc_id)."""
    entries = []
    if KNOWLEDGE_BASE.exists():
        with open(KNOWLEDGE_BASE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    doc_id = record.get("document_id")
                    if doc_id:
                        entries.append((line, doc_id))
                except json.JSONDecodeError:
                    # Keep the line as is to avoid data loss
                    entries.append((line, None))
    return entries


def write_knowledge_base(lines):
    with open(KNOWLEDGE_BASE, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")


# ==========================================================
# INITIALIZE
# ==========================================================

converter = DocumentConverter()
processed_hashes = load_hashes()

stats = {"processed": 0, "skipped": 0, "failed": 0}

# Clear failed log for this run
open(FAILED_LOG, "w", encoding="utf-8").close()

print("=" * 80)
print("DOCLING KNOWLEDGE BASE BUILDER (INCREMENTAL)")
print("=" * 80)

# ==========================================================
# PHASE 1: Determine which files need processing
# ==========================================================

to_process = []  # (file_path, doc_id, current_hash)

for file in SOURCE_FOLDER.rglob("*"):
    if not file.is_file():
        continue

    # **EXCLUDE OUTPUT FOLDER**
    if OUTPUT_ROOT in file.parents or str(file).startswith(str(OUTPUT_ROOT)):
        continue

    if file.suffix.lower() not in SUPPORTED_EXTENSIONS:
        continue

    current_hash = sha256_file(file)
    key = str(file)
    existing = processed_hashes.get(key)

    if existing and existing.get("hash") == current_hash:
        stats["skipped"] += 1
        print(f"SKIP    : {file.name}")
        continue

    doc_id = existing.get("doc_id") if existing else generate_document_id()
    to_process.append((file, doc_id, current_hash))
    print(f"TO PROCESS: {file.name} (doc: {doc_id})")

# ==========================================================
# PHASE 2: Filter knowledge base for files we'll update
# ==========================================================

update_doc_ids = {doc_id for _, doc_id, _ in to_process}
existing_entries = read_knowledge_base()
kept_entries = [
    line for line, doc_id in existing_entries
    if doc_id not in update_doc_ids
]
new_entries = []

# ==========================================================
# PHASE 3: Process each file and generate new chunks
# ==========================================================

for file, doc_id, current_hash in to_process:
    try:
        print(f"PROCESS : {file.name} (doc: {doc_id})")

        relative_path = file.relative_to(SOURCE_FOLDER)

        # ----- Convert -----
        if file.suffix.lower() == ".msg":
            msg = extract_msg.Message(str(file))
            attachments = []
            try:
                for att in msg.attachments:
                    filename = getattr(att, "longFilename", None) or getattr(att, "shortFilename", None)
                    if filename:
                        attachments.append(filename)
            except Exception:
                pass

            markdown_text = f"""
# Subject

{msg.subject}

# From

{msg.sender}

# To

{msg.to}

# Date

{msg.date}

# Attachments

{chr(10).join(attachments)}

# Body

{msg.body}
"""
            document_json = {
                "document_type": "email",
                "subject": msg.subject,
                "sender": msg.sender,
                "to": msg.to,
                "date": str(msg.date),
                "attachments": attachments,
                "body": msg.body
            }
        else:
            result = converter.convert(str(file))
            document_json = result.document.export_to_dict()
            markdown_text = result.document.export_to_markdown()

        # ----- Metadata -----
        file_ref = find_file_ref(markdown_text)
        pin = find_pin(markdown_text)
        category = get_document_category(relative_path)

        document_json["document_id"] = doc_id
        document_json["file_ref"] = file_ref
        document_json["pin"] = pin
        document_json["document_category"] = category

        # ----- Save document JSON -----
        output_json = DOCUMENTS_FOLDER / (relative_path.as_posix().replace("/", "__") + ".json")
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(document_json, f, indent=2, ensure_ascii=False)

        # ----- Chunking -----
        chunks = [markdown_text[i:i + CHUNK_SIZE] for i in range(0, len(markdown_text), CHUNK_SIZE)]
        modified_date = datetime.fromtimestamp(file.stat().st_mtime).isoformat()
        total_chunks = len(chunks)

        for idx, chunk in enumerate(chunks, start=1):
            record = {
                "document_id": doc_id,
                "file_ref": file_ref,
                "pin": pin,
                "chunk_id": f"{file.stem}_{idx}",
                "source_file": file.name,
                "source_path": str(file),
                "relative_path": str(relative_path),
                "folder": str(relative_path.parent),
                "document_category": category,
                "file_type": file.suffix.lower(),
                "last_modified": modified_date,
                "chunk_number": idx,
                "total_chunks": total_chunks,
                "document_json": str(output_json),
                "chunk_text": chunk
            }
            new_entries.append(json.dumps(record, ensure_ascii=False))

        # Update hash record
        processed_hashes[str(file)] = {"hash": current_hash, "doc_id": doc_id}
        stats["processed"] += 1

    except Exception as ex:
        stats["failed"] += 1
        with open(FAILED_LOG, "a", encoding="utf-8") as log:
            log.write(f"\nFILE: {file}\n")
            log.write(f"ERROR: {str(ex)}\n")
            log.write(traceback.format_exc())
            log.write("\n" + "=" * 80 + "\n")
        print(f"FAILED  : {file.name}")

# ==========================================================
# PHASE 4: Write the updated knowledge base
# ==========================================================

all_lines = kept_entries + new_entries
write_knowledge_base(all_lines)

# ==========================================================
# SAVE HASHES
# ==========================================================

save_hashes(processed_hashes)

# ==========================================================
# SUMMARY
# ==========================================================

print()
print("=" * 80)
print("BUILD COMPLETE")
print("=" * 80)
print(f"Processed : {stats['processed']}")
print(f"Skipped   : {stats['skipped']}")
print(f"Failed    : {stats['failed']}")
print()
print(f"Knowledge Base : {KNOWLEDGE_BASE}")
print(f"Documents      : {DOCUMENTS_FOLDER}")
print(f"Failed Log     : {FAILED_LOG}")
print(f"Hash File      : {HASH_FILE}")
print("=" * 80)