import uuid
import os


class LocalDir:
    def __init__(self, data_dir: str):
        cache_id = str(uuid.uuid4())
        self._data_dir = os.path.join(data_dir, cache_id)
        os.makedirs(self._data_dir)

    def get_local_root(self):
        return self._data_dir

    def get_target_path(self, path):
        target_relative_path = path.lstrip('/')
        return os.path.join(self._data_dir, target_relative_path)