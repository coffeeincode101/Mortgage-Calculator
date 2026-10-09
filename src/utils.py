import os
import logging
from pathlib import Path
import functools
import time


logger = logging.getLogger(__name__)
def time_it(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        end = time.perf_counter()
        logger.info(f'Function {func.__name__} took {end - start:.4f}s')
        return result
    return wrapper
    
def get_output_path() -> Path:
    """
    Finds the best folder to save results. 
    Priority: 1. .env variable, 2. OneDrive, 3. Local Documents, 4. Project Root.
    """
    # 1. Check for manual override in .env first
    env_path = os.getenv('MORTGAGE_OUTPUT')
    if env_path:
        return Path(env_path)

    home = Path.home()
    
    # 2. Try the standard OneDrive redirection path
    onedrive_docs = home / "OneDrive" / "Documents"
    if onedrive_docs.exists():
        return onedrive_docs / "Mortgage_Schedules"
        
    # 3. Fallback to the classic local path
    local_docs = home / "Documents"
    if local_docs.exists():
        return local_docs / "Mortgage_Schedules"
        
    # 4. Ultimate fallback: Create a 'Results' folder in the project itself
    # .parent.parent moves up from src/ to the project root
    return Path(__file__).resolve().parent.parent / "Results"

