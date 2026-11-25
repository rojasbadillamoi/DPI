# Pruebas de DPI

Desde la raíz del repositorio:

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Las pruebas usan datos sintéticos y archivos temporales, sin muestras privadas.
No requieren iniciar la interfaz gráfica. GitHub Actions ejecuta la misma suite
con Python 3.10 y 3.12 en Linux y Windows, en cada push y pull request.

Las pruebas de regresión no certifican equivalencia con COFECHA o ARSTAN ni
sustituyen las pruebas manuales de Qt. Al corregir un error, añadir un caso que
reproduzca el problema antes de modificar el algoritmo.
