import logging
import curses
import sys
import shutil
import time

if hasattr(shutil, "get_terminal_size"):
    get_terminal_size = shutil.get_terminal_size
else:
    def get_terminal_size():
        import struct
        import os
        def ioctl_GWINSZ(fd):
            try:
                import fcntl
                import termios
                cr = struct.unpack('hh',
                                fcntl.ioctl(fd, termios.TIOCGWINSZ, '1234'))
                return cr
            except:
                pass
        cr = ioctl_GWINSZ(0) or ioctl_GWINSZ(1) or ioctl_GWINSZ(2)
        if not cr:
            try:
                fd = os.open(os.ctermid(), os.O_RDONLY)
                cr = ioctl_GWINSZ(fd)
                os.close(fd)
            except:
                pass
        if not cr:
            try:
                cr = (os.environ['LINES'], os.environ['COLUMNS'])
            except:
                return None
        return int(cr[1]), int(cr[0])

class FancyTerminalHandler(logging.Handler):
    """
    A log handler that provides fancy output to a terminal.

    It handles colors, and it turns DEBUG entries into progressbars.

    This is a mix of StreamHandler and tornado's formatter.
    """
    FORMAT = '%(level_color)s%(asctime)-15s %(levelname)s%(end_color)s %(message)s'
    PROGRESS_FORMAT = ' (%(ticker)s) %(levelname)s %(message)s'
    DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

    def __init__(self, stream=None):
        """
        Initialize the handler.

        If stream is not specified, sys.stderr is used.
        """
        super().__init__()
        self.stream = stream if stream is not None else sys.stderr

        # Log level above which entries are not considered progress entries
        self.non_progress = logging.WARN

        # Build a mapping between level types and color escape sequences
        self._level_colors = {}
        fg_color = (curses.tigetstr("setaf") or
                    curses.tigetstr("setf") or "")
        for levelno, code in (
                (logging.DEBUG,      4),  # Blue
                (logging.INFO,       2),  # Green
                (logging.WARNING,    3),  # Yellow
                (logging.ERROR,      1)): # Red
            self._level_colors[levelno] = str(curses.tparm(fg_color, code), "ascii")
        self._normal = str(curses.tigetstr("sgr0"), "ascii")
        self._progress = str(curses.tparm(fg_color, 6), "ascii") # Cyan
        self._clreol = str(curses.tigetstr("el"), "ascii")
        self._ticker = "-\|/"
        self._ticker_index = 0

        cols, lines = get_terminal_size()
        self._output_width = cols

    def emit(self, record):
        """
        Format and print out a record.
        """
        try:
            record.message = record.getMessage()
            record.asctime = time.strftime(self.DATE_FORMAT, time.localtime(record.created))

            if record.levelno < self.non_progress:
                #record.progress_color = self._progress
                #record.end_color = self._normal
                record.ticker = self._ticker[self._ticker_index]
                self._ticker_index = (self._ticker_index + 1) % len(self._ticker)

                # Progress output
                formatted = (self.PROGRESS_FORMAT % record.__dict__).expandtabs()
                formatted = formatted[:self._output_width]
                stream = self.stream
                stream.write(self._progress)
                stream.write(formatted)
                stream.write(self._normal)
                stream.write(self._clreol)
                stream.write("\r")
            else:
                # Terminal log output
                level_color = self._level_colors.get(record.levelno, None)
                if level_color is not None:
                    record.level_color = level_color
                    record.end_color = self._normal
                else:
                    record.level_color = record.end_color = ''

                formatted = self.FORMAT % record.__dict__

                #if record.exc_info:
                #    if not record.exc_text:
                #        record.exc_text = self.formatException(record.exc_info)
                #if record.exc_text:
                #    lines = "\n".join((formatted.rstrip(), record.exc_text))
                msg = formatted.replace("\n", "\n    ")
                stream = self.stream
                stream.write(msg)
                stream.write(self._clreol)
                stream.write("\n")

            self.flush()
        except Exception:
            self.handleError(record)

    def finish_logging(self):
        """
        Notify that there will be no more logging, so that we can clean things
        up if needed.
        """
        # Send a clear to EOL command: this way, if the last thing that we
        # logged was a progress indicator, we do not have the shell prompt
        # appear in the middle of it
        self.stream.write(self._clreol)
        self.stream.flush()


