class Fail(BaseException):
    """
    Exception thrown when some check decided that the CDD building process
    cannot proceed.
    """
    def __str__(self):
        return self.args[0] % self.args[1:]
