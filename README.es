Traducci�n realizada por Alejandro S�nchez Mar�n (asmarin@us.es)

SchoolBell
==========


SchoolBell es una aplicaci�n de fuente abierta y libre para permitir a 
organizaciones y grupos coordinar la administraci�n de horarios y agendas.
Los usuarios puede gestionar sus calendarios personales, de grupo y de
recursos, por ejemplo, clases, proyectores, etc, via interface web, o usando 
el cliente de iCalendar para Mozilla o iCal.

SchoolBell est� escrito en Python, y es un componente Zope 3 que funciona 
tambi�n como servidor de calendarios. Es una parte del proyecto SchoolTool,
creado por la Fundaci�n Shuttleworth.

Sitio Web: http://www.schooltool.org/schoolbell

Lista de correo: http://lists.schooltool.org/mailman/listinfo/schooltool

Reporte de errores: http://issues.schooltool.org/


Requerimientos de sistema
-------------------------

- Python 2.3 (http://www.python.org/)
  (Usuarios Debian puede necesitar ambos paquetes python2.3 y python2.3-xml)

- Zope X3 (http://www.zope.org/)
  (Los usuarios necesitan la version ZopeX3 revisi�n subversion 29357, las 
  librerias de zope est�n incluidas en esta versi�n)

- Python Imaging library (http://www.pythonware.com/products/pil/index.htm)

- Entorno de desarrollo y compilador de C (para desarrolladores)
  (Existen paquetes binarios precompilados para usuarios Windows)


Construyendo SchoolBell
-----------------------

Ejecutar 'make' para construir todos los m�dulos de extensi�n necesarios.

Es una buena idea ejecutar 'make test' y 'make ftest' para chequear que todas
las unidades esenciales son funcionales.


Instalando y Configurando con Distutils
---------------------------------------

Es posible instalar SchoolBell usando distutils de python. Para hacer esto, 
necesita usar uno de los archivos comprimidos tar/zip, los cuales debe 
descomprimir usando las herramientas apropiadas a su SO. 

Para instalar el software hay dos maneras:

Primera, desde el directorio raiz de la distribuci�n SchoolBell descomprimida puede usarse
lo siguiente:

python setup.py install

Segunda, desde el directory Zope3/ incluido con la distribuci�n SchoolBell.

python setup.py schoolbell install


Finalmente, para configurar una instancia de SchoolBell, copia el script de instancia
en un directorio separado y crea un archivo de configuraci�n con el nombre del script 
y la extensi�n .conf. Una buena plantilla puede encontrarse en el directorio ra�z
de la distribuci�n SchoolBell (.conf.in). Ejecutando este script lanzaremos la instancia
en ese directorio.

Todos los interesados en instalar en una localizaci�n no est�ndar deber�n investigar
las opciones --paths y --default-config para los comandos de instalaci�n de distutils.

Nota: Si esta usando una distribuci�n linux estos paquetes existen, debera considera 
usar esos paquetes via apt-get en vez de este procedimiento.


Ejecuntando SchoolBell
----------------------

El directorio ra�z contiene el siguiente script ejecutable en Python:

  schoolbell-server.py      ejecuta el server SchoolBell


El server SchoolBell automaticamente crea una base de datos vac�a en caso de no 
encontrar ninguna previamente. Puede personalizar la localizaci�n de la base de datos
y otros pocos parametros en el fichero de configuraci�n schoolbell.conf. Hay un ejemplo
en el archivo schoolbell.conf.in, que puede renombrando y modificarlo a sus necesidades.

Por defecto el usuario con privilegios de administrador es creado con la nueva base de 
datos. El nombre de usuario es 'manager' y la contrase�a es 'schoolbell'.

El puerto por defecto de la aplicaci�n web es 7080. Una vez que el servidor est�
ejecutandose, puede conectarse a �l con un navegador web.

EL Makefile contiene diversos atajos, que son mantenidos para compatibilidad hacia atr�s.

  make run                  ejecuta el servidor SchoolBell
  make build                construye SchoolBell y las librerias incluidas en Zope 3
  make test                 ejecuta el test de integridad de postinstalaci�n en SchoolBell
  make ftest                ejecuta el test de funcionalidad de postinstalaci�n en Schoolbell

Estos comandos deben ejecutarse en el directorio ra�z.


Estructura del proyecto
-----------------------

  GPL                   GNU General Public License, version 2
  README                este archivo
  RELEASE               notas de novedades de la �ltima versi�n

  Makefile              makefile para construir los m�dulos de extensi�n
  setup.py              distutils script de configuraci�n para construir modulos de extensi�n
  test.py               test script
  remove-stale-bytecode.py
                        script que borra ficheros stale *.pyc

  schoolbell-server.py  script para ejecutar el servidor SchoolBell
  schoolbell.conf.in    ejemplo de archivo de configuraci�n de SchoolBell

  build/                archivos temporales durante el proceso de instalaci�n
  debian/               Soporte de paquetes Debian
  doc/                  documentaci�n
  src/                  c�digo fuente
    schoolbell/         Paquete Python 'schoolbell'
      app/              La aplicaci�n SchoolBell
      calendar/         Librer�a de calendario SchoolBell para Zope 3
      relationship/     La libreria interelacional de SchoolBell


Testing
-------

There are two sets of automated tests: unit tests and functional tests.
Unit tests (sometimes also called programmer tests) test individual components
of the system.  Functional tests (also called customer or acceptance tests)
test only externally visible behaviour of the whole system.

Tests themselves are scattered through the whole source tree.  Subdirectories
named 'tests' contain unit tests, while subdirectories named 'ftests' contain
functional tests.

To run all unit tests, do

  python2.3 test.py -pv

To run all functional tests, do

  python2.3 test.py -fpv

The test runner has more options and features.  To find out about them, do

  python2.3 test.py -h

Functional tests are are not completely isolated.  Some functional tests
create named database state snapshots, while other tests reuse those snapshots
of known database state.  The test runner does not know which tests create
which snapshots, so if you want to run just one (or a couple) of functional
tests in isolation, it is likely that you will have first run the full suite
to create the necessary snapshots.  Do not restart the test server, or all
saved snapshots will be gone.


Hosting Virtual
---------------

SchoolBell proporciona soporte para hosting virtual con la librer�a mod_rewrite de
Apache y libproxy. Por ejemplo, vamos a definir dos instancias de SchoolBell 
corriendo en los puertos 7001 y 7002, y los vamos ha hacer disponibles como
school1.example.org y school2.example.org, ambos en el puerto 80. Para hacerlo, 
a�adiremos las siguiente l�neas a los archivos de configuraci�n de Apache:

  NameVirtualHost *:80

  <VirtualHost *:80>
    ServerName school1.example.org
    RewriteEngine On
    RewriteRule ^/(.*) http://localhost:7001/++vh++http:school1.example.org:80/++/$1 [P]
  </VirtualHost>

  <VirtualHost *:80>
    ServerName school2.example.org
    RewriteEngine On
    RewriteRule ^/(.*) http://localhost:7002/++vh++http:school2.example.org:80/++/$1 [P]
  </VirtualHost>

Falta decir que mod_proxy y mod_rewrite deben de estar activados en Apache tambi�n.


Puede tener soporte para SSL en el mismo sentido, es una alternativa al construido con
soporte SSL:

  NameVirtualHost *:443

  <VirtualHost *:443>
    ServerName school1.example.org
    SSLEnable          # Apache 1.3
    # SSLEngine On     # Apache 2.0
    RewriteEngine On
    RewriteRule ^/(.*) http://localhost:7001/++vh++https:school1.example.org:443/++/$1 [P]
  </VirtualHost>

El interface de la aplicaci�n web tambi�n soporta hosting virtual de este modo, solo cambia 
el n�mero de puerto local.

