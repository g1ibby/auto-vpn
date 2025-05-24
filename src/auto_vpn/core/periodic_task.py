import time
from collections.abc import Callable
from datetime import datetime
from threading import Thread

from .utils import setup_logger

logger = setup_logger(name="core.periodic_task")


class PeriodicTask:
    def __init__(self, interval_seconds: int, task_function: Callable):
        """
        Initialize a periodic task.

        Args:
            interval_seconds (int): Interval between task executions in seconds
            task_function (Callable): The function to be executed periodically
            on_update_callback (Callable, optional): Callback function to be called after each task execution
        """
        self.interval_seconds = interval_seconds
        self.task_function = task_function
        self.running = False
        self.thread = None
        self.last_check_time = None

    def start(self):
        """Start the periodic task"""
        if not self.running:
            self.running = True
            self.thread = Thread(target=self._run, daemon=True)
            self.thread.start()

    def stop(self):
        """Stop the periodic task"""
        self.running = False
        if self.thread:
            self.thread.join()

    def get_last_check_time(self) -> datetime | None:
        """Get the timestamp of the last check"""
        return self.last_check_time

    def _run(self):
        """Main loop for the periodic task"""
        while self.running:
            try:
                # Execute the task
                self.task_function()

                # Update last check time
                self.last_check_time = datetime.now()

                # Sleep until next interval
                time.sleep(self.interval_seconds)
            except Exception as e:
                logger.error(f"Error in periodic task: {e}")
                time.sleep(self.interval_seconds)  # Sleep even if there's an error
