# Embedded file name: mud\world\process.pyo


class Process:
    processCounter = 1L

    def __init__(self, src, dst):
        self.src = src
        self.dst = dst
        self.iter = None
        self.tickCounter = 0
        self.tickRate = 1
        self.canceled = False
        self.pid = Process.processCounter
        Process.processCounter += 1
        return

    def globalPush(self):
        self.src.processesOut.add(self)
        self.dst.processesIn.add(self)

    def clearSrc(self):
        self.src = None
        return

    def clearDst(self):
        self.dst = None
        return

    def begin(self):
        self.globalPush()
        self.iter = self.tick()
        return True

    def tick(self):
        return False

    def end(self):
        if self.canceled:
            return
        self.globalPop()

    def cancel(self):
        if self.canceled:
            return
        else:
            self.canceled = True
            self.iter = None
            self.globalPop()
            return

    def globalPop(self):
        self.src.processesOut.discard(self)
        self.dst.processesIn.discard(self)