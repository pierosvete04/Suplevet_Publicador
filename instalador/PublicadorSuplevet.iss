; Instalador del Publicador (Inno Setup). Lo compila GitHub Actions en cada versión:
;   iscc /DVersion=1.0.0 /DOrigen=..\dist\PublicadorSuplevet instalador\PublicadorSuplevet.iss
; Se instala en la carpeta del usuario (sin permisos de administrador), así puede actualizarse solo.
; Los datos (datos\: credenciales, cola, tokens, métricas) nunca se borran: ni al actualizar ni al desinstalar.

#ifndef Version
  #define Version "0.0.0"
#endif
#ifndef Origen
  #define Origen "..\dist\PublicadorSuplevet"
#endif

[Setup]
AppId={{9B2E7C41-3D6A-4F8E-B1C5-50554C495354}
AppName=Publicador
AppVersion={#Version}
AppPublisher=Piero Svete
DefaultDirName={localappdata}\PublicadorSuplevet
DisableDirPage=no
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..
OutputBaseFilename=PublicadorSuplevet-Instalador-v{#Version}
SetupIconFile=icono.ico
UninstallDisplayIcon={app}\PublicadorSuplevet.exe
UninstallDisplayName=Publicador
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "escritorio"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"
Name: "inicio"; Description: "Abrir el publicador al prender la PC (para que salgan las piezas programadas)"; GroupDescription: "Arranque:"; Flags: unchecked

[Files]
Source: "{#Origen}\*"; DestDir: "{app}"; Excludes: "datos\*"; Flags: recursesubdirs ignoreversion createallsubdirs
Source: "icono.ico"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
Name: "{app}\datos"; Flags: uninsneveruninstall

[InstallDelete]
; accesos directos con el nombre anterior
Type: files; Name: "{userprograms}\Publicador Suplevet.lnk"
Type: files; Name: "{userdesktop}\Publicador Suplevet.lnk"
Type: files; Name: "{userstartup}\Publicador Suplevet.lnk"

[Icons]
Name: "{userprograms}\Publicador"; Filename: "{app}\PublicadorSuplevet.exe"; WorkingDir: "{app}"; IconFilename: "{app}\icono.ico"
Name: "{userdesktop}\Publicador"; Filename: "{app}\PublicadorSuplevet.exe"; WorkingDir: "{app}"; IconFilename: "{app}\icono.ico"; Tasks: escritorio
Name: "{userstartup}\Publicador"; Filename: "{app}\PublicadorSuplevet.exe"; WorkingDir: "{app}"; IconFilename: "{app}\icono.ico"; Tasks: inicio

[Run]
Filename: "{app}\PublicadorSuplevet.exe"; Description: "Abrir el publicador ahora"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent
