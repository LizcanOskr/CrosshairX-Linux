# CrosshairX para Linux

Una mira configurable para KDE Plasma en Wayland. La configuración y la
bandeja están hechas con Python y PyQt6; la mira se dibuja con una superficie
LayerShellQt del compositor.

## Ejecutar

```bash
python3 ./crosshair.py
```

Requiere Python 3, PyQt6, Qt 6, CMake y LayerShellQt. Compila el renderizador
una vez con:

```bash
./build.sh
```

Después ejecuta la aplicación. La configuración se guarda en
`~/.config/crosshairx-linux/settings.json`.

También se puede abrir desde el menú de aplicaciones como **CrosshairX para
Linux**.

## Instalación

Para instalarla para tu usuario, ejecuta:

```bash
chmod +x install.sh
./install.sh
```

Consulta [INSTRUCCIONES.txt](INSTRUCCIONES.txt) para los requisitos por
distribución, la instalación de sistema y la desinstalación.

## Uso

La ventana permite elegir forma, color, tamaño total desde 1 px, separación,
grosor en pasos de 0,25 px, borde, pantalla, posición X/Y y visibilidad. El
botón «Centrar en la pantalla» vuelve a poner ambos desplazamientos a cero. Los
cambios se guardan automáticamente.

Con la mira visible, las flechas desplazan la posición un píxel cada vez.
En teclados Apple, `Fn` + ←/→/↑/↓ se traduce respectivamente a `Home`, `End`,
`Page Up` y `Page Down`; esas teclas también mueven la mira si se pulsan sin Fn.
Los desplazamientos se reflejan en los controles X/Y y se guardan en la
configuración.

`Ctrl` + `Alt` + `º` alterna la visibilidad de la mira desde cualquier
aplicación. `Fn` no se transmite como modificador separado para esa tecla en
este teclado, así que no se puede distinguir globalmente `Fn` + `º` de `º`.

El icono blanco y transparente de la bandeja alterna la mira con un clic
izquierdo. El menú contextual permite abrir la configuración, activar o
desactivar la mira y cerrar la aplicación. Cerrar la ventana de configuración
la oculta en la bandeja sin detener la mira.

## KDE Plasma y Wayland

La mira se crea como superficie de capa `Overlay`, anclada al área completa de
la pantalla elegida. No es una ventana normal: no recibe entrada del ratón ni
teclado y reserva cero espacio exclusivo, por lo que el dock y la barra superior
conservan su área y reciben los clics. Su posición central se calcula desde el
centro físico de la salida, sin restar el espacio de los paneles. Las superficies
de capa pertenecen a la salida del compositor, no a un escritorio virtual.

La prioridad visual depende de las reglas del compositor y de otras superficies
de sistema; no puede forzarse por encima de pantallas de bloqueo o avisos seguros.
La aplicación requiere una sesión KDE Plasma Wayland y LayerShellQt instalado.

Este proyecto no inyecta código en juegos ni modifica sus archivos.
