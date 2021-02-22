from ._handle_object import HandleObject
from ._local_driver import LocalDriver


class FileObject(HandleObject):
    def __init__(self, handle: int, path: str, flags: int, driver: LocalDriver):
        super().__init__(path, handle)
        self.flags = flags
        self._driver = driver
        self.is_dirty = False

    def read(self, size, offset, buffer):
        return self._driver.read(self.path, size, offset, self.handle, buffer)

    def write(self, size, offset, buffer):
        # TODO check the flags if it's writable
        result = self._driver.write(self.path, size, offset, self.handle, buffer)
        if result > 0:
            self.is_dirty = True
        return result

    def release(self):
        pass
