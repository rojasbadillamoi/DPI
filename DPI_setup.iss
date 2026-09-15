; =============================================================================
; DPI_setup.iss — Script de Inno Setup para Dendro Pixel Interface (DPI)
; Suite MoiCedrus — Moisés E. Rojas Badilla
;
; USO:
;   1. Ejecuta primero build_DPI.bat para generar dist\DPI\
;   2. Abre este archivo con Inno Setup Compiler (v6.x recomendado)
;      Descarga gratis en: https://jrsoftware.org/isinfo.php
;   3. Presiona F9 (o Compile) para generar el instalador.
;   4. El instalador se guardará en: installer_output\DPI_Setup_vX.X.exe
;
; NOTA SOBRE EL ÍCONO:
;   Si tienes un archivo .ico, descomenta las líneas marcadas con
;   ; [ICONO] y ajusta la ruta.
; =============================================================================


; -----------------------------------------------------------------------------
; [Setup] — Metadatos del instalador
; -----------------------------------------------------------------------------
[Setup]
AppName=Dendro Pixel Interface
AppVersion=2.3.0
AppVerName=Dendro Pixel Interface 2.3.0
AppPublisher=Moisés E. Rojas Badilla
AppPublisherURL=https://github.com/MoiCedrus
AppSupportURL=https://github.com/MoiCedrus/DPI/issues
AppUpdatesURL=https://github.com/MoiCedrus/DPI/releases

; Identificador único del programa (generado automáticamente, no cambiar)
AppId={{A3F7B2C1-4E89-4D02-9F6A-1B3C8E5D7A20}

; Directorio de instalación por defecto
DefaultDirName={autopf}\MoiCedrus\DPI
DefaultGroupName=MoiCedrus\DPI

; El instalador NO requiere privilegios de administrador
; (instala en Archivos de programa pero puede cambiarse a la carpeta del usuario)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; Carpeta de salida del instalador .exe
OutputDir=installer_output
OutputBaseFilename=DPI_Setup_v2.3.0

; Compresión LZMA2 (mejor ratio, más lento)
Compression=lzma2
SolidCompression=yes
CompressionThreads=auto

; Idioma y configuración regional
; Inno Setup no incluye español nativo en el binario base.
; Si tienes el archivo Spanish.isl, descomenta la siguiente línea:
; ShowLanguageDialog=no

; Información de licencia (muestra el texto de GPL antes de instalar)
LicenseFile=LICENSE.txt

; Versión mínima de Windows: Windows 10 (10.0)
MinVersion=10.0

; Arquitectura: x64 solamente (PyInstaller genera binarios de 64 bits)
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

; Íconos del instalador
; [ICONO] Descomenta si tienes un .ico:
SetupIconFile=iconos\dpi.ico

; Imagen lateral del asistente (opcional, 164x314 px, BMP/PNG)
; WizardImageFile=iconos\wizard_side.bmp
; WizardSmallImageFile=iconos\wizard_top.bmp

; El desinstalador se guarda en la carpeta de instalación
UninstallDisplayName=Dendro Pixel Interface (DPI)
; [ICONO] Descomenta si tienes un .ico:
UninstallDisplayIcon={app}\iconos\dpi.ico

; Configuración visual del asistente
WizardStyle=modern


; -----------------------------------------------------------------------------
; [Languages] — Idiomas
; -----------------------------------------------------------------------------
[Languages]
; Idioma por defecto: inglés (siempre disponible en el binario base de Inno Setup)
Name: "english"; MessagesFile: "compiler:Default.isl"

; Para añadir español, descarga Spanish.isl de:
; https://jrsoftware.org/files/istrans/
; y descomenta:
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"


; -----------------------------------------------------------------------------
; [Messages] — Textos personalizados en español
; -----------------------------------------------------------------------------
[Messages]
; Estos mensajes sobrescriben los del idioma base
WelcomeLabel1=Bienvenido al instalador de Dendro Pixel Interface (DPI)
WelcomeLabel2=Este asistente instalará DPI en tu equipo.%n%nDPI es parte de la suite MoiCedrus, un conjunto de herramientas de código abierto para dendrocronología.%n%nSe recomienda cerrar todas las demás aplicaciones antes de continuar.
FinishedLabel=La instalación de Dendro Pixel Interface se completó correctamente.%n%nHaz doble clic en el ícono del escritorio para iniciar el programa.


; -----------------------------------------------------------------------------
; [Tasks] — Opciones que el usuario puede elegir durante la instalación
; -----------------------------------------------------------------------------
[Tasks]
Name: "desktopicon";     Description: "Crear icono en el Escritorio";               GroupDescription: "Iconos adicionales:"
Name: "quicklaunchicon"; Description: "Agregar al menu de Inicio";                  GroupDescription: "Iconos adicionales:"
Name: "associateRWL";    Description: "Asociar archivos .rwl con DPI";              GroupDescription: "Asociaciones de archivo:"; Flags: unchecked
Name: "associatePOS";    Description: "Asociar archivos .pos con DPI";              GroupDescription: "Asociaciones de archivo:"; Flags: unchecked

; -----------------------------------------------------------------------------
; [Files] — Archivos a instalar
; -----------------------------------------------------------------------------
[Files]
; === Ejecutable principal y todos los archivos de la carpeta dist\DPI\ ===
; IMPORTANTE: ejecuta build_DPI.bat antes de compilar este script.
Source: "dist\DPI\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; === Licencia (se copia al directorio de instalación como referencia) ===
Source: "LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion

; === README ===
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion

; === Perfiles de especie (por seguridad, forzar copia aunque PyInstaller lo incluyó) ===
Source: "species_profiles.json"; DestDir: "{app}"; Flags: ignoreversion

; === Carpeta de íconos (si existe) ===
Source: "iconos\*"; DestDir: "{app}\iconos"; Flags: ignoreversion recursesubdirs; Check: DirExists(ExpandConstant('{src}\iconos'))


; -----------------------------------------------------------------------------
; [Icons] — Accesos directos
; -----------------------------------------------------------------------------
[Icons]
; Menú Inicio
Name: "{group}\Dendro Pixel Interface"; Filename: "{app}\DPI.exe"; \
    IconFilename: "{app}\iconos\dpi.ico"; \
    Comment: "Medicion de anillos de arboles — Suite MoiCedrus"

Name: "{group}\Desinstalar DPI"; Filename: "{uninstallexe}"

; Escritorio
Name: "{autodesktop}\Dendro Pixel Interface"; Filename: "{app}\DPI.exe"; \
    IconFilename: "{app}\iconos\dpi.ico"; \
    Tasks: desktopicon; \
    Comment: "DPI — Suite MoiCedrus"

; -----------------------------------------------------------------------------
; [Registry] — Registro de Windows (asociaciones de archivo)
; -----------------------------------------------------------------------------
[Registry]
; Asociar .rwl con DPI (opcional, solo si el usuario lo marcó)
Root: HKCU; Subkey: "Software\Classes\.rwl"; ValueType: string; ValueName: ""; ValueData: "DPI.RWLFile"; \
    Flags: uninsdeletevalue; Tasks: associateRWL
Root: HKCU; Subkey: "Software\Classes\DPI.RWLFile"; ValueType: string; ValueName: ""; ValueData: "Archivo Tucson (.rwl)"; \
    Flags: uninsdeletekey; Tasks: associateRWL
Root: HKCU; Subkey: "Software\Classes\DPI.RWLFile\DefaultIcon"; ValueType: string; ValueName: ""; \
    ValueData: "{app}\DPI.exe,0"; Tasks: associateRWL
Root: HKCU; Subkey: "Software\Classes\DPI.RWLFile\shell\open\command"; ValueType: string; ValueName: ""; \
    ValueData: """{app}\DPI.exe"" ""%1"""; Tasks: associateRWL

; Asociar .pos con DPI (opcional)
Root: HKCU; Subkey: "Software\Classes\.pos"; ValueType: string; ValueName: ""; ValueData: "DPI.POSFile"; \
    Flags: uninsdeletevalue; Tasks: associatePOS
Root: HKCU; Subkey: "Software\Classes\DPI.POSFile"; ValueType: string; ValueName: ""; ValueData: "CooRecorder POS (.pos)"; \
    Flags: uninsdeletekey; Tasks: associatePOS
Root: HKCU; Subkey: "Software\Classes\DPI.POSFile\DefaultIcon"; ValueType: string; ValueName: ""; \
    ValueData: "{app}\DPI.exe,0"; Tasks: associatePOS
Root: HKCU; Subkey: "Software\Classes\DPI.POSFile\shell\open\command"; ValueType: string; ValueName: ""; \
    ValueData: """{app}\DPI.exe"" ""%1"""; Tasks: associatePOS

; Registrar la aplicación en "Agregar o quitar programas"
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\App Paths\DPI.exe"; \
    ValueType: string; ValueName: ""; ValueData: "{app}\DPI.exe"; Flags: uninsdeletekey


; -----------------------------------------------------------------------------
; [Run] — Acciones al finalizar la instalación
; -----------------------------------------------------------------------------
[Run]
; Ofrece lanzar DPI al terminar el instalador
Filename: "{app}\DPI.exe"; \
    Description: "Iniciar Dendro Pixel Interface ahora"; \
    Flags: nowait postinstall skipifsilent


; -----------------------------------------------------------------------------
; [UninstallDelete] — Archivos a limpiar al desinstalar
; -----------------------------------------------------------------------------
[UninstallDelete]
; Eliminar la carpeta completa de la aplicación al desinstalar
; (incluye archivos generados como species_profiles.json modificado)
Type: filesandordirs; Name: "{app}"


; -----------------------------------------------------------------------------
; [Code] — Pascal script para validaciones y lógica adicional
; -----------------------------------------------------------------------------
[Code]

// Verifica que el usuario ejecutó build_DPI.bat antes de compilar el .iss
function InitializeSetup(): Boolean;
begin
  Result := True;
end;

// Muestra un mensaje de bienvenida personalizado
procedure InitializeWizard();
begin
  WizardForm.WelcomeLabel2.Caption :=
    'DPI es una herramienta de medición dendrocronológica sobre imágenes de alta resolución.' + #13#10 +
    'Parte de la suite MoiCedrus (GPL v3).' + #13#10#13#10 +
    'Autor: Moisés E. Rojas Badilla';
end;

