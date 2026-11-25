import unittest
from dpi.medicion.modelo import ModeloSesionMedicion, RadioMedicion, PuntoMedicion
class Sesion(unittest.TestCase):
    def test_propietario(self):
        m = ModeloSesionMedicion()
        r = RadioMedicion('R', (PuntoMedicion((0,0)), PuntoMedicion((1,0))), 2000, 2000, 0)
        m.guardar_radio('R', r)
        with self.assertRaises(TypeError):
            m.radios['R'] = r
        with self.assertRaises(ValueError):
            m.guardar_radio('R', r)
        m.activo.agregar((3,4))
        self.assertEqual(len(m.radios['R'].puntos), 2)
        self.assertIs(m.eliminar_radio('R'), r)
        m.cargar_radios({'R': r})
        self.assertIs(m.radios['R'], r)

    def test_edicion_multiple(self):
        from dpi.medicion.modelo import TipoMarca
        m = ModeloSesionMedicion().activo
        m.cargar([(i,0) for i in range(5)], [False]*5)
        m.editar_puntos([1,3], TipoMarca.SALTO)
        self.assertEqual(list(m.marcas), [False, True, False, True, False])
        m.editar_puntos([1,3])
        self.assertEqual(list(m.coordenadas), [(0,0),(2,0),(4,0)])
