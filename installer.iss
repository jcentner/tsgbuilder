; installer.iss — Inno Setup script for TSG Builder (Windows)
;
; Builds a per-user installer that:
;   - Installs to {localappdata}\TSGBuilder (no admin rights required)
;   - Replaces app files on upgrade, preserves .env and .agent_ids.json
;   - Creates Start Menu and Desktop shortcuts
;   - Registers in Add/Remove Programs
;
; CI passes the version via: ISCC installer.iss /DAppVersion=1.0.7
; For local testing:         ISCC installer.iss /DAppVersion=dev

#ifndef AppVersion
  #define AppVersion "dev"
#endif

[Setup]
AppName=TSG Builder
AppVersion={#AppVersion}
AppPublisher=Jacob Centner
AppPublisherURL=https://github.com/jcentner/tsgbuilder
AppSupportURL=https://github.com/jcentner/tsgbuilder/issues
DefaultDirName={localappdata}\TSGBuilder
PrivilegesRequired=lowest
OutputBaseFilename=tsg-builder-windows-setup
UninstallDisplayName=TSG Builder
; No installer icon bundled yet — uses default
Compression=lzma2
SolidCompression=yes
; Allow user to pick a different directory if desired
DisableDirPage=no
DisableProgramGroupPage=yes
; Force-close running TSG Builder via Restart Manager before replacing files
CloseApplications=force
RestartApplications=no

[Files]
; Main executable
Source: "dist\tsg-builder-windows\tsg-builder-windows.exe"; DestDir: "{app}"; Flags: ignoreversion
; Bundled Python runtime + dependencies
Source: "dist\tsg-builder-windows\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
; Documentation
Source: "dist\tsg-builder-windows\GETTING_STARTED.md"; DestDir: "{app}"; Flags: ignoreversion
; Explicitly NOT including .env or .agent_ids.json — user config preserved by omission

[Icons]
Name: "{userprograms}\TSG Builder"; Filename: "{app}\tsg-builder-windows.exe"
Name: "{userdesktop}\TSG Builder"; Filename: "{app}\tsg-builder-windows.exe"

[UninstallDelete]
; Clean up _internal directory on uninstall (Inno Setup normally handles this,
; but explicit entry ensures leftover .pyc / __pycache__ files are removed)
Type: filesandordirs; Name: "{app}\_internal"

[Code]
// Close any running TSG Builder instance before installing (upgrade scenario).
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
  Retries: Integer;
begin
  // Kill any running instance
  Exec('taskkill', '/F /IM tsg-builder-windows.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  // Wait up to 5 seconds for the process to fully terminate and release file handles.
  // taskkill signals termination but the OS may hold the exe lock briefly.
  Retries := 0;
  while Retries < 10 do
  begin
    // tasklist exits 0 if process found, non-zero if not found
    Exec('tasklist', '/FI "IMAGENAME eq tsg-builder-windows.exe" /NH', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    if ResultCode <> 0 then
      Break;
    Sleep(500);
    Retries := Retries + 1;
  end;
  Result := True;
end;
