from .commands import *
from .modules import *
from .power import *

import inspect

# register commands
classes = [(n, c) for (n, c) in globals().items() if inspect.isclass(c) and issubclass(c, ATCommand) and not c is ATCommand]
for class_info in classes:
    SIM800.register(*class_info)
