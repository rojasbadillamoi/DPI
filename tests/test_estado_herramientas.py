import unittest
from dpi.ui.medicion.herramientas.estado import EstadoCalibracion, EstadoSeleccion, EstadoEspacio, EstadoAutodeteccion
from dpi.medicion.edicion_ewlw import planificar_ewlw
from dpi.medicion.marcas import ModoMedicion
from dpi.ui.medicion.herramientas.despacho import acciones_click

class EstadoHerramientas(unittest.TestCase):
    def test_estado_independiente(self):
        for clase in (EstadoCalibracion, EstadoSeleccion, EstadoEspacio, EstadoAutodeteccion):
            a, b = clase(), clase()
            a.items.append(object())
            self.assertEqual(b.items, [])

    def test_plan_ewlw(self):
        self.assertEqual(planificar_ewlw([(0, 0), (4, 0)], [False, False], 0, .5), (1, (2., 0.), None))
        self.assertIsNotNone(planificar_ewlw([(0, 0), (4, 0)], [False, True], 0, .5)[2])

    def test_despacho(self):
        import inspect
        callbacks = {n: (lambda *args, n=n: n) for n in inspect.signature(acciones_click).parameters}
        acciones = acciones_click(**callbacks)
        self.assertIs(acciones[ModoMedicion.MEDIR], acciones[ModoMedicion.SALTO])
        self.assertEqual(acciones[ModoMedicion.EWLW](1, 2), "paso_ewlw")
        self.assertNotIn(ModoMedicion.MOVER, acciones)
