"""Descubre y ejecuta tests/ registrando el estado de cada prueba (PASS/FAIL/ERROR/SKIP) en JSON."""
import json
import sys
import unittest

destino = sys.argv[1]


class Resultado(unittest.TextTestResult):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.filas = []

    def _f(self, test, estado, motivo=""):
        self.filas.append({"test": test.id(), "estado": estado, "motivo_skip_o_fallo": motivo})

    def addSuccess(self, test):
        super().addSuccess(test); self._f(test, "PASS")

    def addFailure(self, test, err):
        super().addFailure(test, err); self._f(test, "FAIL", self._exc_info_to_string(err, test)[-600:])

    def addError(self, test, err):
        super().addError(test, err); self._f(test, "ERROR", self._exc_info_to_string(err, test)[-600:])

    def addSkip(self, test, reason):
        super().addSkip(test, reason); self._f(test, "SKIP", reason)


suite = unittest.defaultTestLoader.discover("tests")
res = unittest.TextTestRunner(verbosity=1, resultclass=Resultado).run(suite)
with open(destino, "w", encoding="utf-8") as fh:
    json.dump({"testsRun": res.testsRun, "filas": res.filas}, fh, ensure_ascii=False, indent=2)
sys.exit(0 if res.wasSuccessful() else 1)
