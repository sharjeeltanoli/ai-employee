import time
import shutil
import logging
from pathlib import Path
from watchdog.observers.polling import PollingObserver as Observer
from watchdog.events import FileSystemEventHandler

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)
logger = logging.getLogger(__name__)

VAULT_PATH = Path("/mnt/c/AI_Employee_Vault")
WATCH_FOLDER = VAULT_PATH / "Drop_Here"
NEEDS_ACTION = VAULT_PATH / "Needs_Action"

class DropFolderHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        
        source = Path(event.src_path)
        dest = NEEDS_ACTION / f"FILE_{source.name}"
        
        logger.info(f"New file detected: {source.name}")
        
        # Copy file to Needs_Action
        shutil.copy2(source, dest)
        
        # Create metadata .md file
        meta_path = NEEDS_ACTION / f"FILE_{source.stem}.md"
        meta_path.write_text(f"""---
type: file_drop
original_name: {source.name}
size: {source.stat().st_size} bytes
status: pending
---

## New File Detected
- **File:** {source.name}
- **Size:** {source.stat().st_size} bytes

## Suggested Actions
- [ ] Review file contents
- [ ] Process and move to /Done
""")
        logger.info(f"Action file created: {meta_path.name}")

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
