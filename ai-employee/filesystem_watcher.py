import time
import shutil
import logging
from pathlib import Path
from watchdog.observers.polling import PollingObserver as Observer
from watchdog.events import FileSystemEventHandler

from audit_logger import audit_success, audit_failure

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)
logger = logging.getLogger(__name__)

VAULT_PATH = Path("/mnt/c/AI_Employee_Vault")
WATCH_FOLDER = VAULT_PATH / "Drop_Here"
NEEDS_ACTION = VAULT_PATH / "Needs_Action"

ACTOR = "filesystem_watcher"

class DropFolderHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return

        source = Path(event.src_path)
        size = source.stat().st_size
        dest = NEEDS_ACTION / f"FILE_{source.name}"

        logger.info(f"New file detected: {source.name}")
        audit_success(
            "file_detected",
            actor=ACTOR,
            target=str(source.name),
            parameters={"source_path": str(source), "size_bytes": size},
        )

        try:
            # Copy file to Needs_Action
            shutil.copy2(source, dest)

            # Create metadata .md file
            meta_path = NEEDS_ACTION / f"FILE_{source.stem}.md"
            meta_path.write_text(f"""---
type: file_drop
original_name: {source.name}
size: {size} bytes
status: pending
---

## New File Detected
- **File:** {source.name}
- **Size:** {size} bytes

## Suggested Actions
- [ ] Review file contents
- [ ] Process and move to /Done
""")
            logger.info(f"Action file created: {meta_path.name}")
            audit_success(
                "file_moved",
                actor=ACTOR,
                target=str(dest.name),
                parameters={
                    "source": str(source.name),
                    "destination": str(dest),
                    "meta_file": str(meta_path.name),
                    "size_bytes": size,
                },
            )
        except Exception as exc:
            logger.error(f"Failed to process {source.name}: {exc}")
            audit_failure(
                "file_moved",
                actor=ACTOR,
                target=str(source.name),
                detail=str(exc),
                parameters={"source_path": str(source)},
            )

def main():
    # Create Drop_Here folder if not exists
    WATCH_FOLDER.mkdir(exist_ok=True)
    logger.info(f"Watching folder: {WATCH_FOLDER}")
    logger.info("Drop any file into Drop_Here folder to trigger the watcher...")

    event_handler = DropFolderHandler()
    observer = Observer()
    observer.schedule(event_handler, str(WATCH_FOLDER), recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        logger.info("Watcher stopped.")
    observer.join()

if __name__ == "__main__":
    main()
