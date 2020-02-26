from termcolor import colored

LOGLEVELS = ["INFO", "WARNING", "ERROR", "ALL"]
SUPPRESSBELOW = "ERROR"


def log(ltype, message, outdesc=None):
    """Prints log messages.

    Parameters
    ----------
    ltype: str
        Log type, can be INFO, WARNING, ERROR
    message: str
        Log message
    """
    if ltype not in LOGLEVELS[:-1]:
        return
    dat = {"INFO": (0, "green"),
           "WARNING": (1, "yellow"),
           "ERROR": (2, "red"),
           "ALL": (3, "black")}
    if dat[ltype][0] >= dat[SUPPRESSBELOW][0]:
        print(colored("{}: {}".format(ltype, message), dat[ltype][1]))
        if outdesc:
            print(
                    colored("{}: {}".format(ltype, message), dat[ltype][1]),
                    file=outdesc)
