import json
import random
import unittest
from dpi.medicion.modelo import ModeloMedicion, TipoMarca


class TestModeloMedicion(unittest.TestCase):
    def test_operaciones_comparadas(self):
        rng = random.Random(531)
        m = ModeloMedicion()
        c, s = [], []
        vistas = m.coordenadas, m.marcas
        tipos = [t.value for t in TipoMarca]
        for _ in range(2000):
            op = rng.randrange(6) if c else 0
            i = rng.randrange(len(c)) if c else 0
            p = (rng.random(), rng.random())
            marca = rng.choice(tipos)
            if op == 0:
                m.agregar(p, marca); c.append(p); s.append(marca)
            elif op == 1:
                m.insertar(i, p, marca); c.insert(i, p); s.insert(i, marca)
            elif op == 2:
                m.borrar(i); c.pop(i); s.pop(i)
            elif op == 3:
                m.mover(i, p); c[i] = p
            elif op == 4:
                m.marcar(i, marca); s[i] = marca
            else:
                m.borrar(slice(i, i+2)); del c[i:i+2]; del s[i:i+2]
            self.assertEqual(list(vistas[0]), c)
            self.assertEqual(list(vistas[1]), s)
            self.assertTrue(all(a is b or a == b for a,b in zip(vistas[1],s)))

    def test_historial_y_json(self):
        m = ModeloMedicion()
        coords = [(i,i+1) for i in range(5)]
        marcas = [t.value for t in TipoMarca]
        m.cargar(coords, marcas)
        antes = m.captura()
        m.marcar(0, True); m.mover(1, (100,200)); m.borrar(2)
        despues = m.captura()
        m.restaurar(antes)
        self.assertEqual(list(m.coordenadas), coords)
        self.assertEqual(list(m.marcas), marcas)
        self.assertIs(m.marcas[0], False)
        self.assertIs(m.marcas[1], True)
        datos = json.loads(json.dumps([list(m.coordenadas), list(m.marcas)]))
        m.limpiar(); m.cargar(*datos)
        self.assertEqual(m.captura(), antes)
        m.restaurar(despues)
        self.assertEqual(m.captura(), despues)

    def test_historial_incluye_anomalias(self):
        from dpi.medicion.modelo import HistorialMedicion
        m = ModeloMedicion()
        h = HistorialMedicion(m, 3)
        m.agregar((0, 0))
        m.anomalias[2000] = 'a'
        h.guardar()
        m.agregar((1, 0))
        m.anomalias[2000] = 'b'
        m.pixeles_por_mm = 2
        self.assertTrue(h.deshacer())
        self.assertEqual(len(m.captura()), 1)
        self.assertEqual(m.anomalias, {2000: 'a'})
        self.assertEqual(m.pixeles_por_mm, 2.)
        self.assertTrue(h.rehacer())
        self.assertEqual(len(m.captura()), 2)
        self.assertEqual(m.anomalias, {2000: 'b'})

    def test_escala_del_modelo(self):
        m = ModeloMedicion()
        m.pixeles_por_mm = 2
        for valor in (0, -1, float('inf'), True, None):
            with self.assertRaises(ValueError):
                m.pixeles_por_mm = valor
            self.assertEqual(m.pixeles_por_mm, 2.)

    def test_carga_invalida_no_modifica(self):
        m = ModeloMedicion(); m.agregar((1,2))
        estado = m.captura()
        for coords, marcas in [([(1,2)], []), ([], [False]), ([(1,2)], ['desconocida'])]:
            with self.assertRaises(ValueError):
                m.cargar(coords, marcas)
            self.assertEqual(m.captura(), estado)


if __name__ == '__main__':
    unittest.main()
